"""ABB-27 unit tests for the generic in-process task registry: identity, state
transitions, bounded retry/backoff, timeout and cancellation, and in-flight
deduplication. Fully synthetic/offline: no HTTP, no NASA POWER or OpenAlex involved
(those integrations are covered in test_power.py and test_literature.py).
"""
from __future__ import annotations

import asyncio

import pytest

from agroblackbox.resilience.tasks import TaskCancelledError, TaskRegistry, TaskState, TaskTimeoutError


def make_registry(**kwargs) -> TaskRegistry:
    kwargs.setdefault('name', 'test')
    return TaskRegistry(**kwargs)


# ---------------------------------------------------------------- identity and state

def test_successful_task_has_an_id_and_reaches_done():
    registry = make_registry()

    async def go():
        async def factory():
            return 'value'
        result = await registry.run('k', factory)
        info = registry.snapshot('k')
        return result, info

    result, info = asyncio.run(go())
    assert result == 'value'
    assert info.state == TaskState.DONE
    assert info.task_id and info.attempt == 1 and info.max_attempts == 1
    assert info.started_at is not None and info.finished_at is not None
    assert info.error is None


def test_two_different_keys_get_two_different_task_ids():
    registry = make_registry()

    async def go():
        async def factory():
            return 1
        await registry.run('a', factory)
        await registry.run('b', factory)
        return registry.snapshot('a').task_id, registry.snapshot('b').task_id

    id_a, id_b = asyncio.run(go())
    assert id_a != id_b


def test_failed_task_reaches_failed_state_and_raises_to_caller():
    registry = make_registry()

    async def go():
        async def factory():
            raise ValueError('boom')
        with pytest.raises(ValueError, match='boom'):
            await registry.run('k', factory)
        return registry.snapshot('k')

    info = asyncio.run(go())
    assert info.state == TaskState.FAILED
    assert 'boom' in info.error


# ---------------------------------------------------------------- deduplication

def test_concurrent_identical_calls_run_the_factory_once():
    """The core ABB-27 acceptance criterion: N callers sharing a dedup key trigger
    exactly one real upstream call, verified by a call-count assertion."""
    registry = make_registry()
    calls = []
    release = asyncio.Event()

    async def factory():
        calls.append(1)
        await release.wait()
        return 'shared-result'

    async def go():
        async def waiter():
            return await registry.run('same-key', factory)

        t1 = asyncio.ensure_future(waiter())
        t2 = asyncio.ensure_future(waiter())
        t3 = asyncio.ensure_future(waiter())
        await asyncio.sleep(0)  # let all three reach the registry and join the same task
        assert registry.snapshot('same-key').waiters == 3
        release.set()
        return await asyncio.gather(t1, t2, t3)

    results = asyncio.run(go())
    assert results == ['shared-result'] * 3
    assert len(calls) == 1  # exactly one upstream call for three concurrent callers


def test_sequential_calls_after_completion_each_run_the_factory():
    """Dedup only applies while a task is in flight; once done, a later call for the
    same key starts a fresh one (needed so a cache invalidation/retry can proceed)."""
    registry = make_registry()
    calls = []

    async def factory():
        calls.append(1)
        return len(calls)

    async def go():
        first = await registry.run('k', factory)
        second = await registry.run('k', factory)
        return first, second

    assert asyncio.run(go()) == (1, 2)
    assert len(calls) == 2


def test_different_keys_never_share_a_call():
    registry = make_registry()
    calls = []

    async def factory():
        calls.append(1)
        return len(calls)

    async def go():
        return await asyncio.gather(registry.run('a', factory), registry.run('b', factory))

    asyncio.run(go())
    assert len(calls) == 2


def test_a_failure_is_shared_by_every_waiter_and_then_a_retry_is_possible():
    registry = make_registry()
    calls = []
    release = asyncio.Event()

    async def failing_factory():
        calls.append(1)
        await release.wait()
        raise ConnectionError('down')

    async def go_failing():
        async def waiter():
            with pytest.raises(ConnectionError):
                await registry.run('k', failing_factory)

        t1 = asyncio.ensure_future(waiter())
        t2 = asyncio.ensure_future(waiter())
        await asyncio.sleep(0)
        release.set()
        await asyncio.gather(t1, t2)

    asyncio.run(go_failing())
    assert len(calls) == 1  # both waiters shared the single failed attempt

    async def ok_factory():
        return 'recovered'

    assert asyncio.run(registry.run('k', ok_factory)) == 'recovered'  # fresh task, new key lifecycle


# ---------------------------------------------------------------- bounded retry / backoff

def test_bounded_retry_recovers_after_transient_failures():
    attempts = []

    async def flaky():
        attempts.append(1)
        if len(attempts) < 3:
            raise ConnectionError('transient')
        return 'ok'

    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    registry = make_registry(max_attempts=3, backoff_seconds=(1.0, 2.0),
                             retryable=(ConnectionError,), sleep=fake_sleep)
    result = asyncio.run(registry.run('k', flaky))
    assert result == 'ok'
    assert len(attempts) == 3
    assert sleeps == [1.0, 2.0]
    info = registry.snapshot('k')
    assert info.state == TaskState.DONE and info.attempt == 3


def test_retries_are_bounded_and_the_original_error_surfaces():
    attempts = []

    async def always_fails():
        attempts.append(1)
        raise ConnectionError('still down')

    registry = make_registry(max_attempts=3, backoff_seconds=(1.0, 2.0),
                             retryable=(ConnectionError,), sleep=lambda s: asyncio.sleep(0))
    with pytest.raises(ConnectionError, match='still down'):
        asyncio.run(registry.run('k', always_fails))
    assert len(attempts) == 3  # never more than max_attempts
    assert registry.snapshot('k').state == TaskState.FAILED


def test_non_retryable_exception_is_not_retried():
    attempts = []

    async def factory():
        attempts.append(1)
        raise ValueError('permanent')

    registry = make_registry(max_attempts=3, backoff_seconds=(1.0, 2.0), retryable=(ConnectionError,))
    with pytest.raises(ValueError):
        asyncio.run(registry.run('k', factory))
    assert len(attempts) == 1


# ---------------------------------------------------------------- timeout

def test_timeout_abandons_only_the_timed_out_waiter():
    """A caller's own timeout must not cancel the shared task for other callers
    (asyncio.shield semantics): a second, patient waiter still gets the real result."""
    release = asyncio.Event()

    async def slow_factory():
        await release.wait()
        return 'late-but-real'

    registry = make_registry()

    async def go():
        patient = asyncio.ensure_future(registry.run('k', slow_factory))
        await asyncio.sleep(0)
        with pytest.raises(TaskTimeoutError):
            await registry.run('k', slow_factory, timeout=0.01)
        release.set()
        return await patient

    assert asyncio.run(go()) == 'late-but-real'


# ---------------------------------------------------------------- cancellation

def test_cancel_raises_task_cancelled_error_to_every_waiter():
    release = asyncio.Event()
    started = asyncio.Event()

    async def factory():
        started.set()
        await release.wait()
        return 'unreachable'

    registry = make_registry()

    async def go():
        async def waiter():
            with pytest.raises(TaskCancelledError):
                await registry.run('k', factory)

        t1 = asyncio.ensure_future(waiter())
        t2 = asyncio.ensure_future(waiter())
        await started.wait()
        cancelled = await registry.cancel('k')
        await asyncio.gather(t1, t2)
        return cancelled

    assert asyncio.run(go()) is True
    info = None

    async def snap():
        nonlocal info
        info = registry.snapshot('k')
    asyncio.run(snap())
    assert info.state == TaskState.CANCELLED


def test_cancel_on_unknown_or_finished_key_is_a_no_op():
    registry = make_registry()
    assert asyncio.run(registry.cancel('never-seen')) is False

    async def factory():
        return 'done'

    asyncio.run(registry.run('k', factory))
    assert asyncio.run(registry.cancel('k')) is False  # already finished, nothing to cancel

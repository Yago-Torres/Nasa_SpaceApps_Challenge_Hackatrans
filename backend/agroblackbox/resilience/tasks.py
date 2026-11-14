"""Generic async task model (ABB-27): identifier, state, timeout, bounded
retry/backoff, cancellation and in-flight deduplication for slow or fragile
upstream calls.

This module knows nothing about NASA POWER, OpenAlex, HTTP or caching: it only
sequences coroutines supplied by callers. A call site picks a ``dedup_key`` that
identifies the *logical* request (for NASA POWER, the request's cache key; for
OpenAlex, the normalized search query or work identifier) and a zero-argument
async ``factory`` that actually performs the upstream call. ``TaskRegistry.run``
guarantees that, for a given key, at most one ``factory`` is in flight at a time:
every other caller sharing that key awaits the same result instead of starting a
second upstream call.

Design choices, and why (see ADR-0005 for the full writeup):

- One :class:`TaskRegistry` per upstream resource (NASA POWER, OpenAlex search,
  OpenAlex/Crossref lookup), not a single global registry, so a flood of POWER
  requests cannot starve OpenAlex callers or vice versa, and each resource keeps
  its own retry/backoff policy.
- Retries/backoff live here as a generic, independently testable capability, but
  ``services.power`` and ``services.literature`` each already implement their own
  bounded retry with provider-specific ``Retry-After`` handling at the HTTP-attempt
  level (this predates ABB-27 and has its own tests). Wrapping those adapters with
  ``max_attempts=1`` here adds dedup/timeout/cancellation on top without duplicating
  or fighting that existing, already-reviewed retry logic.
- Deduplication is cooperative and in-process only: it has no visibility into other
  processes or machines. That is an explicit, documented limitation (see ADR-0005),
  acceptable for this project's current single-backend-process deployment target.
- A timeout is per *waiter*, not per task: one caller giving up does not cancel the
  work for other callers still waiting on the same deduplicated request (achieved
  with ``asyncio.shield``).
- Cancellation is per *task* (i.e. per dedup key): cancelling a request also cancels
  it for every other caller currently sharing it, because they are, by definition,
  the same logical request. There is currently no API route that exposes cancellation
  to end users; it exists so a caller (e.g. a future background-task endpoint) can
  give up on a request that is no longer useful, and is covered by tests here.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Generic, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar('T')


class TaskState(str, Enum):
    PENDING = 'pending'
    RUNNING = 'running'
    DONE = 'done'
    FAILED = 'failed'
    CANCELLED = 'cancelled'


class TaskTimeoutError(Exception):
    """A caller's wait on a task exceeded its own timeout.

    The underlying task keeps running for any other caller still waiting on the
    same dedup key; only this caller's wait is abandoned.
    """


class TaskCancelledError(Exception):
    """Raised to every caller sharing a task that was cancelled before completion."""


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class TaskInfo:
    """Read-only bookkeeping snapshot, safe to log or expose: it never holds call
    arguments, coroutine objects or upstream payloads, only identity and timing."""

    task_id: str
    dedup_key: str
    state: TaskState
    created_at: datetime
    max_attempts: int
    attempt: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    waiters: int = 0
    error: str | None = None


@dataclass
class _Shared(Generic[T]):
    info: TaskInfo
    future: asyncio.Future
    runner: asyncio.Task | None = field(default=None)


class TaskRegistry(Generic[T]):
    """Deduplicates concurrent identical requests for one upstream resource and runs
    each with bounded retries, backoff and a per-waiter timeout.

    Not backed by Redis or a worker process (see ADR-0005): a plain dict guarded by
    an ``asyncio.Lock``, scoped to this process's event loop.
    """

    def __init__(
        self,
        *,
        name: str,
        max_attempts: int = 1,
        backoff_seconds: tuple[float, ...] = (),
        retryable: tuple[type[BaseException], ...] = (Exception,),
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if max_attempts < 1:
            raise ValueError('max_attempts must be >= 1')
        self.name = name
        self._max_attempts = max_attempts
        self._backoff = backoff_seconds
        self._retryable = retryable
        self._sleep = sleep
        self._shared: dict[str, _Shared[T]] = {}
        self._guard = asyncio.Lock()

    def snapshot(self, dedup_key: str) -> TaskInfo | None:
        """Return the current bookkeeping for ``dedup_key``, or ``None`` if nothing
        has run for it (or it was already evicted). Used by tests and diagnostics."""
        shared = self._shared.get(dedup_key)
        return shared.info if shared else None

    @property
    def in_flight_keys(self) -> frozenset[str]:
        return frozenset(k for k, s in self._shared.items() if not s.future.done())

    async def run(
        self,
        dedup_key: str,
        factory: Callable[[], Awaitable[T]],
        *,
        timeout: float | None = None,
    ) -> T:
        """Run ``factory()`` for ``dedup_key``, joining an in-flight task for the
        same key instead of starting a second upstream call.

        Raises whatever ``factory()`` raised after bounded retries are exhausted,
        or :class:`TaskTimeoutError` / :class:`TaskCancelledError`.
        """
        async with self._guard:
            shared = self._shared.get(dedup_key)
            if shared is None or shared.future.done():
                info = TaskInfo(task_id=str(uuid.uuid4()), dedup_key=dedup_key,
                                 state=TaskState.PENDING, created_at=_now(),
                                 max_attempts=self._max_attempts)
                shared = _Shared(info=info, future=asyncio.get_running_loop().create_future())
                self._shared[dedup_key] = shared
                shared.runner = asyncio.ensure_future(self._execute(shared, factory))
            shared.info.waiters += 1
        try:
            awaitable = asyncio.shield(shared.future)
            if timeout is None:
                return await awaitable
            try:
                return await asyncio.wait_for(awaitable, timeout=timeout)
            except TimeoutError as e:
                raise TaskTimeoutError(
                    f'{self.name} task {shared.info.task_id} (key={dedup_key!r}) '
                    f'timed out after {timeout}s') from e
        finally:
            shared.info.waiters -= 1

    async def cancel(self, dedup_key: str) -> bool:
        """Cancel the in-flight task for ``dedup_key``, if any. Every caller currently
        awaiting it (there may be several, sharing the same deduplicated request)
        receives :class:`TaskCancelledError`. Returns whether a running task was
        actually cancelled."""
        shared = self._shared.get(dedup_key)
        if shared is None or shared.future.done() or shared.runner is None:
            return False
        shared.runner.cancel()
        return True

    async def _execute(self, shared: _Shared[T], factory: Callable[[], Awaitable[T]]) -> None:
        shared.info.state = TaskState.RUNNING
        shared.info.started_at = _now()
        try:
            for attempt in range(1, self._max_attempts + 1):
                shared.info.attempt = attempt
                try:
                    result = await factory()
                except asyncio.CancelledError:
                    raise
                except self._retryable as e:
                    if attempt == self._max_attempts:
                        raise
                    logger.info('%s task %s attempt %d/%d failed (%s); retrying',
                                self.name, shared.info.task_id, attempt, self._max_attempts,
                                type(e).__name__)
                    delay = self._backoff[attempt - 1] if attempt - 1 < len(self._backoff) \
                        else (self._backoff[-1] if self._backoff else 0.0)
                    if delay:
                        await self._sleep(delay)
                    continue
                else:
                    shared.info.state = TaskState.DONE
                    shared.info.finished_at = _now()
                    if not shared.future.done():
                        shared.future.set_result(result)
                    return
        except asyncio.CancelledError:
            shared.info.state = TaskState.CANCELLED
            shared.info.finished_at = _now()
            if not shared.future.done():
                shared.future.set_exception(
                    TaskCancelledError(f'{self.name} task {shared.info.task_id} was cancelled'))
            return
        except BaseException as e:  # noqa: BLE001 - propagated to every waiter, then re-raised here
            shared.info.state = TaskState.FAILED
            shared.info.finished_at = _now()
            shared.info.error = f'{type(e).__name__}: {e}'
            if not shared.future.done():
                shared.future.set_exception(e)
            return

"""Zero-dependency validation of shared project context and uv tooling."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    'README.md', 'AGENTS.md', 'CLAUDE.md', 'backend/.python-version',
    'backend/pyproject.toml', 'backend/AGENTS.md',
    'frontend/AGENTS.md', 'docs/AGENTS.md',
    'docs/ai/CONTEXT_MAP.md', 'docs/product/PRODUCT.md',
    'docs/product/RELEASE_1_0.md', 'docs/architecture/ARCHITECTURE.md',
    'docs/architecture/API_CONTRACTS.md', 'docs/governance/FEATURE_POLICY.md',
    'docs/operations/CURRENT_STATE.md', 'docs/science/SCIENTIFIC_POLICY.md',
    '.github/ISSUE_TEMPLATE/feature.yml', '.github/PULL_REQUEST_TEMPLATE.md',
]
errors = [f'Missing context file: {p}' for p in REQUIRED if not (ROOT / p).exists()]
if '@AGENTS.md' not in (ROOT/'CLAUDE.md').read_text(encoding='utf-8'):
    errors.append('CLAUDE.md must import @AGENTS.md.')
for file in (ROOT/'Makefile', ROOT/'.github/workflows/ci.yml', ROOT/'AGENTS.md'):
    source=file.read_text(encoding='utf-8')
    if 'uv run' not in source:
        errors.append(f'{file.relative_to(ROOT)} must use uv run for Python jobs.')
if errors:
    print('CONTEXT POLICY FAILED:')
    for item in errors:
        print(' -', item)
    sys.exit(1)
print(f'Context policy OK: {len(REQUIRED)} required files present; uv workflow configured.')

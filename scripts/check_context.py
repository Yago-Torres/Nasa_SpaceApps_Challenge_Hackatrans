"""Zero-dependency validation of shared context and reproducible tooling."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    'README.md', 'AGENTS.md', 'CLAUDE.md', 'backend/.python-version',
    'backend/pyproject.toml', 'backend/uv.lock', 'backend/AGENTS.md',
    'frontend/package.json', 'frontend/package-lock.json', 'frontend/AGENTS.md',
    '.nvmrc', 'docs/AGENTS.md',
    'docs/ai/CONTEXT_MAP.md', 'docs/product/PRODUCT.md',
    'docs/product/RELEASE_1_0.md', 'docs/architecture/ARCHITECTURE.md',
    'docs/architecture/API_CONTRACTS.md', 'docs/governance/FEATURE_POLICY.md',
    'docs/operations/CURRENT_STATE.md', 'docs/science/SCIENTIFIC_POLICY.md',
    '.github/ISSUE_TEMPLATE/feature.yml', '.github/PULL_REQUEST_TEMPLATE.md',
    '.claude/skills/agro-design-system/SKILL.md', '.claude/skills/agro-design-system/assets/tokens.css',
    '.claude/skills/agro-ui-review/SKILL.md',
]
errors = [f'Missing context file: {p}' for p in REQUIRED if not (ROOT / p).exists()]
if '@AGENTS.md' not in (ROOT/'CLAUDE.md').read_text(encoding='utf-8'):
    errors.append('CLAUDE.md must import @AGENTS.md.')
for guide in ('AGENTS.md', 'frontend/AGENTS.md'):
    if '.claude/skills/agro-design-system/SKILL.md' not in (ROOT/guide).read_text(encoding='utf-8'):
        errors.append(f'{guide} must point agents to the mandatory design system skill.')
if (ROOT/'backend/.python-version').read_text(encoding='utf-8').strip() != '3.12':
    errors.append('backend/.python-version must pin Python 3.12.')
if (ROOT/'.nvmrc').read_text(encoding='utf-8').strip() != '24':
    errors.append('.nvmrc must pin Node.js 24.')
frontend_manifest = json.loads((ROOT/'frontend/package.json').read_text(encoding='utf-8'))
if frontend_manifest.get('allowScripts') != {'esbuild': True}:
    errors.append('frontend/package.json must explicitly allow only the esbuild install script.')
frontend_lock = json.loads((ROOT/'frontend/package-lock.json').read_text(encoding='utf-8'))
incomplete_packages = [
    path for path, package in frontend_lock.get('packages', {}).items()
    if path and 'version' not in package and not package.get('link')
]
if incomplete_packages:
    errors.append('frontend/package-lock.json has incomplete entries: ' + ', '.join(incomplete_packages))
for file in (ROOT/'Makefile', ROOT/'.github/workflows/ci.yml', ROOT/'AGENTS.md'):
    source=file.read_text(encoding='utf-8')
    if 'uv run' not in source:
        errors.append(f'{file.relative_to(ROOT)} must use uv run for Python jobs.')
workflow = (ROOT/'.github/workflows/ci.yml').read_text(encoding='utf-8')
for required in ('uv lock --check', 'uv sync --locked --extra dev', 'npm ci', "node-version: '24'"):
    if required not in workflow:
        errors.append(f'.github/workflows/ci.yml must contain: {required}')
if errors:
    print('CONTEXT POLICY FAILED:')
    for item in errors:
        print(' -', item)
    sys.exit(1)
print(f'Context policy OK: {len(REQUIRED)} required files present; uv workflow configured.')

# ACOA — Codex Implementation Task: EP-00.01

**Task ID:** `EP-00.01`  
**Status:** Ready for implementation when repository is connected  
**Scope:** Minimal, testable Python repository bootstrap only (no business logic, no integrations, no external actions).

## Source of truth

Read and respect in priority order:

1. `docs/L2-requirements-approved.md` (approved L2 v0.3 policies), especially `K-01`, `P-01…P-22`.
2. `docs/L3-architecture.md` (approved ADR-001…ADR-015).
3. `docs/L4-implementation-plan.md` (v0.2 planning draft).
4. Existing repository conventions and user-level Codex instructions, unless they conflict with approved requirements.

If the docs are not present in the repo, **do not claim to have read them**. Ask for them or establish a clearly scoped bootstrap-only implementation using the constraints below. Never invent policy contents.

## Objective

Create a clean, small Python project scaffold that can be installed, linted and tested in a fresh environment without cloud credentials, external services, production resources, personal data or network calls during tests.

## Hard constraints

- Single user. One repository, modular monolith (ADR-001); do not build microservices or tenant architecture.
- No external actions. No Gmail API, web applications, Playwright, Browser Use, real AI providers, account creation, credential acquisition or background task execution in this PR.
- Default deny by design: future external actions are OFF unless explicit authorization and required configuration exist.
- ACOA uses its own PostgreSQL service in later tasks, but **do not implement database connectivity or migrations in this PR**.
- Real `.env`, OAuth token, personal CV, API key, credentials, browser profiles or user files must not enter the repo or commit diff. Do not print secrets.
- All new code, identifiers, comments, docstrings, logs and developer-facing text are English. Explanations to the user are Turkish.
- Minimize dependencies; avoid early adoption of workflow engines, LLM providers and frontend frameworks.
- Do not alter the approved policies or ADRs. No invented default budgets, quotas, job criteria or recipient lists.

## Plan first

Before editing code:

1. Inspect the repository root and current branch; identify existing packaging, project standards and constraints. Do not delete or rename unrelated files.
2. Propose at most 5 focused subtasks and list the files affected by each.
3. Briefly identify security, test and dependency risks.
4. Proceed with this limited task. Do not expand to EP-00.02 or later.

## Deliverables

- `pyproject.toml`: build/installation metadata; minimal compatible test, lint and formatting tool configuration. Choose supported Python version based on checked dependencies and document the choice.
- `src/acoa/__init__.py`: minimal importable package with no import-time side effects.
- `tests/test_package_smoke.py`: smoke test establishing import and safe startup invariants; no real network/DB usage.
- `README.md`: project purpose, approved architecture summary, local installation and test commands, current limitations and explicit no-live-action status.
- `.gitignore`: excludes real `.env`, secrets, local DB volumes, private CV and application data, browser profiles, build artefacts, caches, and logs (use project-appropriate patterns; do not overly ignore legitimate fixture paths).
- `AGENTS.md`: concise repository-specific engineering and security rules, including requirement/ADR traceability, task decomposition before coding, small single-purpose functions, early validation and tests, narrow diffs, English code / Turkish user explanations.
- `docs/README.md` (or equivalent index): links to approved specifications if they are present; otherwise an explicit note describing which approved docs must be added before policy-sensitive features begin.
- `.env.example` can be added with strictly harmless placeholders. Detailed settings validation belongs to EP-00.02.

Directory placeholders for `domain`, `application`, `intelligence`, `infrastructure`, `interfaces`, etc. may be created **only if useful**; do not add empty boilerplate modules merely to fill a planned tree.

## Automated verification

Choose the test/lint toolchain and record exact reproducible commands, e.g.:

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
ruff check .
ruff format --check .
```

Those are expected types of checks, not proof they have run. Execute them if the environment allows; report commands and actual results, or the precise reason they could not run. Ensure test dependencies can be installed using a clean Python environment.

## Required acceptance criteria

1. Repository installs as a Python package.
2. `import acoa` succeeds without a database, external network, credentials or starting background jobs.
3. Unit/smoke tests and configured formatting/lint checks pass.
4. No secrets, personal documents, actual addresses or credential files are introduced in tracked files.
5. No real email, job application, browser submit or other external action is possible from this bootstrap.
6. Work stays within EP-00.01; no unapproved architecture decisions.
7. PR description includes task ID, any relevant `ADR-001`, `K-01` linkage, files changed, commands/results, limitations, security notes and next task (`EP-00.02`).

## Final response format

Reply in Turkish with: (1) changes and reasons; (2) tests actually run and results; (3) security/secret review; (4) concise diff overview; (5) unimplemented items; (6) branch/PR link **only if it really exists**.

Stop at EP-00.01.

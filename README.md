# ACOA — Safe Python Bootstrap

**Autonomous Career Opportunity Agent (ACOA)** is a personal, single-user career-opportunity discovery and authorized initial-application project. The current EP-00.01 implementation is an installable Python package with safe import smoke tests and development tooling. It contains no business logic or live integrations.

## Architecture and current limits

The approved architecture is a modular monolith in one Python repository (ADR-001). Later tasks add a dedicated PostgreSQL service and durable task execution (ADR-002/003/013), central ModelGateway/ModelRouter (ADR-015), and Policy Gate/External Action Executor (ADR-006/007). Browser access is layered and isolated; email providers use a shared contract; artifacts are versioned; deployment remains portable between local and cloud environments.

This bootstrap implements none of those services. Importing `acoa` reads no configuration and starts no network request, database connection, browser, model call, subprocess, or background job. Replies and follow-up emails remain user-sent under P-01/P-02.

## Local development

Python 3.12 is the verified baseline; package metadata requires Python >=3.12. Python 3.12.14 on Windows was used for verification. Other Python versions and operating systems have not been exercised.

The pinned direct tools are pytest 9.1.1, Ruff 0.17.0, mypy 1.18.2, and the Hatchling 1.32.4 build backend. There are no runtime dependencies. Transitive development dependencies are resolved by pip; a complete dependency lock is not claimed.

From the repository root, use an installed Python 3.12 interpreter to create an isolated environment. PowerShell commands:

```powershell
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip --isolated install --index-url https://pypi.org/simple --no-binary=mypy -e ".[dev]"
& .\.venv\Scripts\python.exe -m pytest -q
& .\.venv\Scripts\python.exe -m ruff check .
& .\.venv\Scripts\python.exe -m ruff format --check src tests
& .\.venv\Scripts\python.exe -m mypy
& .\.venv\Scripts\python.exe -m pip --isolated check
```

On POSIX systems, use `.venv/bin/python` instead of the Windows interpreter path. No environment activation is required. Installation can download development dependencies; the package and smoke tests do not require external services, accounts, configuration, or credentials.

This workstation had no Python registered with its system launcher. Codex's bundled Python was used to create the existing project-local `.venv`; the `.venv` commands above work without installing or changing system Python. For a fresh checkout, select an available supported Python interpreter before creating the environment.

Mypy 1.18.2 is installed from its official source distribution using `--no-binary=mypy`: its pure Python implementation avoids the native DLL loading rejected by Windows Application Control here. The newer attempted mypy 2.4.0 distribution was not usable under that policy. No Windows security setting was changed.

If the execution sandbox does not allow the operating system's default temporary directory, use the ignored project directory for the current shell:

```powershell
New-Item -ItemType Directory -Path .tmp -Force | Out-Null
$env:TEMP = Join-Path (Get-Location).Path '.tmp'
$env:TMP = $env:TEMP
```

Smoke tests use a fresh child process outside the source working directory, with inherited credentials removed and guards rejecting network, subprocess, background-thread, and private configuration access. Metadata verification confirms that all declared dependencies are restricted to the development extra.

## Approved specifications

| File | Level | Status |
|---|---|---|
| `docs/L0-project-definition.md` | L0 | Approved project vision |
| `docs/L1-capabilities.md` | L1 | Approved functional/engineering capability areas |
| `docs/L2-requirements-approved.md` | L2 v0.3 | Approved requirements & decisions |
| `docs/L3-architecture-approved.md` | L3 v1.0 | Approved ADR-001…ADR-015 |
| `docs/L4-implementation-plan.md` | L4 v0.2 | Approved implementation plan |

The source documents were preserved, except for **approval status metadata synchronized with subsequent user decisions**. Requirements, policies, ADR contents, and task specifications have not been redesigned for this bundle.

## Development workflow and next task

1. Keep the five canonical specifications and AGENTS rules available in the repository. Approved document bytes are preserved by `.gitattributes`; code uses LF line endings.
2. Work through focused tasks, using small functions, requirements-linked verification, and a final diff review. The user approved [the EP-00.01 plan](tasks/EP-00.01-implementation-plan.md) and local Git preparation on 2026-10-14.
3. Local Git uses the `main` branch. No remote GitHub repository or push is included. When explicitly requested, create a private remote repository and review focused PRs before merging.
4. The next implementation task is EP-00.02: configuration validation with `dry_run=true`, `external_actions_enabled=false`, and denial when required authorization/budget configuration is missing. Database setup and CI belong to EP-00.03/04.
5. Real sending remains disabled until separate explicit activation and release gates. Routine engineering autonomy does not activate external employer actions.

## Security defaults

- No credentials, OAuth tokens, personal documents, real `.env` files, or private data are included.
- No code that accesses real employer websites, sends email or submits applications is included.
- Until explicitly configured, `dry_run=true` and `external_actions_enabled=false` remain hard requirements.
- The development environment must not inherit production secrets.

## Directory map

- `docs/`: approved specifications
- `tasks/`: Codex task instructions
- `src/acoa/`: importable package without operational work
- `tests/`: isolated bootstrap smoke checks
- `pyproject.toml`: packaging and pinned direct development tools
- `AGENTS.md`: persistent repository-specific Codex rules
- `docs/README.md`: specification index
- `docs/workspace-audit.md`: workspace findings, preservation checks, and proposed instruction refinements
- `archive/legacy-docs/`: historical versions and source copies; not active requirements
- `SHA256SUMS.md`: current active-file checksums; the supplied original manifest is preserved in the archive

Approved L0–L4 contents were preserved byte-for-byte during workspace preparation. Historical approval statements and filenames inside those documents are explained in [the specification index](docs/README.md).

**Current scope:** EP-00.01 only. **Next task:** EP-00.02. See [the verification record](tasks/EP-00.01-verification.md) for actual checks and limitations.

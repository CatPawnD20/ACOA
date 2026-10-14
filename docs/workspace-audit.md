# ACOA Workspace Audit and Preparation Record

Date: 2026-10-14. Scope: local documentation organization and EP-00.01 planning only.

## Initial inventory and evidence

- 20 files: 13 at the root, six in `docs/`, and one in `tasks/`; no other directories or hidden files were present.
- No `.git` directory or enclosing Git repository. `git status --short` reported that the workspace was not a Git repository. Branches, tracked files, remotes, commits, and repository-local configuration therefore were unavailable.
- Relevant effective Git defaults were `core.autocrlf=true` and `init.defaultBranch=main`; these settings were read, not changed. Future Git initialization must account for byte-preserving document checksums and line endings.
- All nine supplied bundle-manifest entries matched their SHA-256 values before changes.
- All 20 original files were hashed before changes, with results preserved in the archive's pre-cleanup baseline.
- All five relative Markdown links in the initial specification index resolved.
- No application code, tests, package metadata, `.gitignore`, deployment files, credentials, or personal document files were present in the inspected tree. No secret values or external accounts were accessed.

## Duplicate and version findings

Six root-to-canonical pairs were compared using SHA-256 and content diffs. Only approved L3 was byte-identical. L0, L1, and L4 differed by one approval-status line; L2 v0.3 differed by its approval-status and requirement-identity paragraphs; the bootstrap task differed by L4 approval wording and the AGENTS preservation deliverable.

Four older versions contained substantive differences and were not interchangeable: L2 v0.1, L2 v0.2, L3 v0.1, and L4 v0.1. Diff statistics between successive root versions were:

| Comparison | Added lines | Removed lines |
|---|---:|---:|
| L2 v0.1 to v0.2 | 19 | 2 |
| L2 v0.2 to v0.3 | 183 | 66 |
| L3 v0.1 to v1.0 | 109 | 42 |
| L4 v0.1 to v0.2 | 101 | 3 |

No approved level or bootstrap task was missing. No destination conflicts were found. The explicit user-approved versions match the canonical documents already present in `docs/`; no replacement document was selected.

## Documentation inconsistencies retained for review

| Location | Finding | Treatment |
|---|---|---|
| L1 line 480 | Closing status describes a scope proposal despite approved header | Recorded in the index; approved content unchanged |
| L2 lines 736 and 891 | Final approval described as pending despite approved header and explicit user approval | Recorded in the index; approved content unchanged |
| L4 lines 234, 241, and 332 | Draft/pending approval wording despite approved header and explicit user approval | Recorded in the index; approved content unchanged |
| L1 line 10 / L2 line 11 | Parent filename points to a source copy formerly at the root | Canonical and historical resolution documented in the index |
| L3 line 652 | Handoff names superseded L4 v0.1 | Canonical v0.2 and archived v0.1 explicitly distinguished in the index |
| L3 example directory tree | Former canonical `L3-architecture.md` name | New active path documented in the index; example preserved |
| L0 section 14 / section 24 | Illustrative AI L-level names and increasing user counts | Binding L3 T0–T3 terminology and L2 K-01 single-user scope take precedence |
| L1 F-09 | Broad language about starting authorized follow-up actions | Binding L2 P-01/P-02 and L3 require user-sent replies/follow-ups |
| L4 G0/S0 | Includes database/configuration beyond EP-00.01 | Applies to complete EP-00; later tasks own these deliverables |

The active references are consistent through the canonical index. Approved documents still contain the historical inconsistencies above; this preparation does not claim those internal statements were corrected. Correcting approved document text requires separate user approval.

## Architecture consistency review

The current L3, L4, AGENTS, and bootstrap task agree on these design boundaries:

| Design boundary | Binding ADRs |
|---|---|
| Single-repository modular monolith and minimal dynamic AI roles | ADR-001, ADR-004 |
| PostgreSQL authoritative state, durable task execution, dedicated ACOA service | ADR-002, ADR-003, ADR-013 |
| Central ModelGateway/ModelRouter, deterministic T0 first, constrained escalation | ADR-004, ADR-015 |
| Authorized API, HTTP, Playwright, optional AI Browser access | ADR-005 |
| Central Policy Gate / External Action Executor and prepare/reserve/execute-once/reconcile | ADR-006, ADR-007 |
| Immutable versioned artifacts | ADR-008 |
| Provider-independent mail with Gmail first and polling before optional push | ADR-009, ADR-014 |
| Hybrid dashboard | ADR-010 |
| Portable local/cloud deployment and risk-based worker isolation | ADR-011, ADR-012 |

No unresolved contradiction between these approved architecture boundaries was identified. This is a document review, not runtime or integration verification. All live-action activation remains outside this request.

## AGENTS review and proposed refinements

Existing instructions cover modularity, single responsibility, DRY/KISS/YAGNI, decomposition, narrow scope, requirements-based tests, dynamic AI routing, budgets, privacy, authorization, and safe external execution. They already mention focused PRs and diffs. SOLID is explicit in approved L0, although not repeated in AGENTS.

Only the canonical L3 filename was changed in AGENTS. The following short additions are proposed, not applied:

> Keep Python orchestration thin; extract meaningful responsibilities into small, focused functions. Apply SOLID where it improves an existing boundary without speculative abstractions.

> Validate changed behavior with focused runtime checks and requirement-linked tests; review the final diff before committing. Use focused pull requests only when explicitly requested; never create a remote repository, push, or merge without authorization.

These strengthen the requested wording without replacing existing instructions or requiring tests to be added to every task. The user's restriction on creating/modifying tests remains applicable; the planned bootstrap smoke tests await implementation-plan approval.

## Changes made

- Moved all ten root source/legacy document and task files into `archive/legacy-docs/`, retaining original filenames and bytes.
- Moved the original `SHA256SUMS.md` into the archive without editing it.
- Renamed `docs/L3-architecture.md` to `docs/L3-architecture-approved.md` without editing its contents.
- Updated the L3 references in AGENTS, README, the specification index, and the canonical bootstrap task.
- Added historical-reference/approval context to the specification index, an archive index, this audit, and a separate EP-00.01 implementation plan awaiting user approval.
- Generated a pre-cleanup checksum baseline and a separate current active-file manifest.

No file was deleted. No speculative application module, empty development directory, test, package metadata, or deployment component was generated. `.gitignore` remains an EP-00.01 deliverable. No Git repository, branch, commit, PR, or remote was created.

## Verification and completion boundaries

Preservation verification checks all five approved document hashes and all eleven moved original files against the pre-cleanup baseline. Link verification covers current Markdown links and the active canonical references. The current manifest must match all active files it lists.

No application tests, installation, linting, type checking, database checks, or provider integrations were run because application implementation has not begun. The EP-00.01 plan is ready for user review; coding remains blocked on explicit plan approval, not on missing requirements.

Actual document verification results:

- All 20 original files remain accounted for: 16 are byte-preserved, and four management/task files received intentional reference/context updates. Zero original files are missing.
- The 16 preserved files include all five approved L0–L4 documents and all eleven archived original files.
- All 28 local Markdown links resolve; zero broken local Markdown links were found. Historical inline filename references remain explicitly mapped in the specification index.
- All 11 current active-file manifest entries match their SHA-256 values.
- Final inventory: 25 files. Five records were added: this audit, the implementation plan, the archive index, the pre-cleanup workspace baseline, and the newly generated current manifest.
- Git remains uninitialized; no branch, commit, staged diff, PR, or remote exists for this workspace.

## Final directory tree

```text
ACOA/
|-- AGENTS.md
|-- README.md
|-- SHA256SUMS.md
|-- docs/
|   |-- README.md
|   |-- L0-project-definition.md
|   |-- L1-capabilities.md
|   |-- L2-requirements-approved.md
|   |-- L3-architecture-approved.md
|   |-- L4-implementation-plan.md
|   `-- workspace-audit.md
|-- tasks/
|   |-- EP-00.01-bootstrap.md
|   `-- EP-00.01-implementation-plan.md
`-- archive/
    `-- legacy-docs/
        |-- README.md
        |-- SHA256SUMS.md
        |-- SHA256SUMS.original-workspace.md
        |-- Autonomous_Career_Opportunity_Agent_Project_Definition.md
        |-- ACOA_L1_Capabilities_and_Engineering_Requirements.md
        |-- ACOA_L2_Detailed_Subsystem_Requirements.md
        |-- ACOA_L2_Detailed_Subsystem_Requirements_v0.2.md
        |-- ACOA_L2_Detailed_Subsystem_Requirements_v0.3_Consolidated.md
        |-- ACOA_L3_Technical_Architecture_v0.1.md
        |-- ACOA_L3_Technical_Architecture_v1.0_Approved.md
        |-- ACOA_L4_Implementation_Plan_v0.1.md
        |-- ACOA_L4_Implementation_Plan_v0.2_Execution_Ready.md
        `-- ACOA_Codex_Task_EP-00.01_Bootstrap.md
```

`pyproject.toml`, `.gitignore`, `src/`, `tests/`, and `deployment/` are absent intentionally until their respective implementation tasks are authorized.

## Subsequent authorized bootstrap

The inventory and findings above describe the completed workspace-preparation stage. On 2026-10-14 the user approved EP-00.01 and local Git preparation, then authorized routine engineering work within the task without repeated approval. The package metadata, privacy exclusions, line-ending attributes, package source, and smoke tests were subsequently added; local Git now uses `main`. `deployment/` remains outside EP-00.01. Proposed focused-function/diff-review refinements and the scoped autonomy preference were incorporated into AGENTS. See the [bootstrap verification record](../tasks/EP-00.01-verification.md) for current runtime results; the original audit and approved L0–L4 bytes remain preserved.

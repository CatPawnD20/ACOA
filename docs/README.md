# ACOA Specification Index

Read these documents in the following order for context: [L0](L0-project-definition.md), [L1](L1-capabilities.md), [L2](L2-requirements-approved.md), [L3](L3-architecture-approved.md), and [L4](L4-implementation-plan.md).

All five levels have been approved by the user. L2 policies and L3 architecture decisions are binding; technical changes require explicit recorded approval where they change approved behavior or architecture.

Documentation levels L0–L4 are unrelated to AI processing tiers T0–T3.

## Canonical baseline and historical statements

The user's workspace preparation request explicitly identifies L0, L1, L2 v0.3, L3 v1.0, and L4 v0.2 as approved. Each level has exactly one active reference document, linked above. Archived copies are historical evidence, not alternative active requirements.

Approved document contents have not been edited. Several earlier statements remain in those contents: the L1 closing paragraph describes a proposal; L2 sections 9.1 and 11.2 say final approval is pending; L4 sections 9, 10, and 15 retain draft/pending approval language. These inconsistencies are recorded in the [workspace audit](workspace-audit.md). They do not supersede the user's explicit approval. Any edits to the approved documents require separate approval.

L0's illustrative AI levels named L0–L3 and its reference to increasing user counts precede the binding L2 K-01 single-user decision and L3 T0–T3 terminology. L1's broad follow-up capability is constrained by L2 P-01/P-02: the user sends replies and follow-ups. These are documented refinements across levels, not authorization to expand scope.

## Historical reference resolution

Some approved documents contain filenames rather than clickable canonical links. Resolve active development references using this table; retain the archived files only for historical comparison.

| Historical filename/reference | Active reference | Preserved original |
|---|---|---|
| `Autonomous_Career_Opportunity_Agent_Project_Definition.md` (L1/L2 parent reference) | [L0](L0-project-definition.md) | [Source copy](../archive/legacy-docs/Autonomous_Career_Opportunity_Agent_Project_Definition.md) |
| `L3-architecture.md` (L3 example tree and former canonical path) | [L3](L3-architecture-approved.md) | [Identical original L3](../archive/legacy-docs/ACOA_L3_Technical_Architecture_v1.0_Approved.md) |
| `ACOA_L4_Implementation_Plan_v0.1.md` (L3 section 20 handoff) | [Approved L4 v0.2](L4-implementation-plan.md) | [Historical L4 v0.1](../archive/legacy-docs/ACOA_L4_Implementation_Plan_v0.1.md) |

G0/S0 in L4 describe the complete EP-00 package, including configuration, deployment, migration infrastructure, and CI work. EP-00.01 implements package bootstrap and smoke checks; EP-00.03 implements the dedicated PostgreSQL service and, through its migration follow-up, the Alembic runner. Business schemas and application database adapters remain later work, including EP-02. Local bootstrap evidence is recorded in the task results; hosted CI and cloud deployment remain unverified.

## Supporting records

- [Workspace audit](workspace-audit.md)
- [Bootstrap task](../tasks/EP-00.01-bootstrap.md)
- [Approved bootstrap implementation plan](../tasks/EP-00.01-implementation-plan.md)
- [Bootstrap verification record](../tasks/EP-00.01-verification.md)
- [Safe configuration task and verification](../tasks/EP-00.02-configuration.md)
- [Dedicated PostgreSQL task and verification](../tasks/EP-00.03-postgresql.md)
- [PostgreSQL deployment guide](../deployment/README.md)
- [G0 migration runner and verification](../tasks/EP-00.03-migration-runner.md)
- [Profile/goals domain and verification](../tasks/EP-01.01-profile-goals.md)
- [Bounded authorization and sensitive consent](../tasks/EP-01.02-authorization.md)
- [Deterministic Policy Gate](../tasks/EP-01.03-policy-gate.md)
- [Versioned policy decision records](../tasks/EP-01.04-decision-records.md)
- [Durable PostgreSQL task queue](../tasks/EP-02.01-task-queue.md)
- [Canonical application ledger](../tasks/EP-02.02-application-ledger.md)
- [CI task and verification](../tasks/EP-00.04-ci.md)
- [Archive index and original checksum records](../archive/legacy-docs/README.md)
- [Current active-file checksum manifest](../SHA256SUMS.md)

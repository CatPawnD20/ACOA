# ACOA Historical Document Archive

These documents are historical source copies or superseded versions. They are not active requirements. Use the [canonical specification index](../../docs/README.md) for development.

Original filenames and file bytes were preserved during reorganization on 2026-10-14. No existing file was deleted or overwritten by another document.

| Original filename | Classification | Comparison with active document |
|---|---|---|
| `Autonomous_Career_Opportunity_Agent_Project_Definition.md` | L0 source copy | One approval-status line differs |
| `ACOA_L1_Capabilities_and_Engineering_Requirements.md` | L1 source copy | One approval-status line differs |
| `ACOA_L2_Detailed_Subsystem_Requirements.md` | Superseded L2 v0.1 | Different requirements/decision baseline |
| `ACOA_L2_Detailed_Subsystem_Requirements_v0.2.md` | Superseded L2 v0.2 | Different requirements/decision baseline |
| `ACOA_L2_Detailed_Subsystem_Requirements_v0.3_Consolidated.md` | L2 v0.3 source copy | Approval status and requirement-identity status differ |
| `ACOA_L3_Technical_Architecture_v0.1.md` | Superseded L3 v0.1 | Predates approved architecture consolidation |
| `ACOA_L3_Technical_Architecture_v1.0_Approved.md` | L3 approved source copy | Byte-identical to active L3; retained to preserve the existing file |
| `ACOA_L4_Implementation_Plan_v0.1.md` | Superseded L4 v0.1 | Predates execution-ready v0.2 additions |
| `ACOA_L4_Implementation_Plan_v0.2_Execution_Ready.md` | L4 v0.2 source copy | One approval-status line differs |
| `ACOA_Codex_Task_EP-00.01_Bootstrap.md` | Earlier bootstrap task source | L4 approval description and AGENTS preservation instruction differ |

## Checksum provenance

- [SHA256SUMS.md](SHA256SUMS.md) is the supplied bundle manifest, preserved unchanged. Its paths describe the original workspace. All nine entries matched before cleanup.
- [SHA256SUMS.original-workspace.md](SHA256SUMS.original-workspace.md) is a newly calculated SHA-256 baseline of all 20 original files, captured before any structural changes. It includes the hash of the supplied manifest itself.
- [The root manifest](../../SHA256SUMS.md) is newly calculated after cleanup and covers active files. It excludes the archive and itself.

For original root document files and the original bundle manifest, resolve pre-cleanup paths relative to this archive. For approved L0–L4 files, resolve them under the project root; the original `docs/L3-architecture.md` now resolves to `docs/L3-architecture-approved.md`. README, AGENTS, the specification index, and the canonical task definition were updated as recorded in the workspace audit; their original hashes are provenance records, not expected current hashes.

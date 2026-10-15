# Application revisions

The G0 bootstrap supplied the runner without a synthetic baseline. EP-02.01 adds
`0001_task_queue`, creating task runs, immutable enqueue dependencies and event
history. The application role may append/read events but cannot update/delete
them. Downgrade refuses destructive removal of retained queue and audit data.
`0002_application_ledger` adds canonical application series, immutable episodes
and lifecycle events. It preserves a separate submission state and prevents a
second initial episode for the same target, including across campaigns.
`0003_action_protocol` adds current safe-default authority, immutable authority
history, bounded evidence, semantic attempt fencing, budget holds and structured
policy decisions. Provider acknowledgement is not submission verification.
`0004_reconciliation` adds immutable submission evidence, reconciliation events,
deduplicated review incidents and an outbox. Outbox insertion does not deliver
notifications or activate a transport.
`0005_model_gateway` adds offline model-call accounting and a shared operation
registry for the existing monetary ledger. It backfills existing external budget
IDs before replacing their FK. `0006_resource_target_guard` explicitly requires
the selected operation target, avoiding SQL CHECK's nullable equality semantics.
`0007_model_routing` adds current provider/data scopes, immutable scope versions,
routes and request/output-bound quality receipts. No provider is enabled by migration.
`0008_match_assessments` adds immutable, version-bound hard-constraint and
multi-criteria assessment records. It does not create or approve opportunity data.
`0009_match_assessment_grants` explicitly grants only application read/insert access;
it preserves the update/delete prohibition across retained development volumes.
`0010_source_discovery` adds immutable source policy, discovery batch, source snapshot
metadata and access-observation records. It stores content digests and bounded
provenance metadata rather than fetched source bodies, and grants the application
role only read/insert access.
`0011_opportunity_research` adds evidence-bound organizations, immutable opportunity
versions, versioned public corporate/professional channels and contact-research results.
Private or inferred contact candidates never enter these tables.
`0012_employer_verification` adds versioned employer risk decisions bound to sourced
signals and append-only company-wide contact controls. Suspicious portals cannot become
trusted policy evidence, and employer opt-out cannot be cleared by a user control event.
`0013_cross_source_resolution` adds immutable exact/possible/distinct entity decisions
and source fallback plans bound to the failed observation, attempted sources, selected
policy version and current permit. Uncertain matches are retained without canonical
merging, and the application role cannot mutate decision history.
`0014_form_question_handoff` adds immutable unresolved-question requests and approved
answer evidence bound to one application, composition task and opportunity version.
The application role has read/insert-only access, and answers are serialized per
question without granting update rights to retained audit rows.
`0015_artifact_versions` adds immutable artifact metadata bound to application, source
draft, exact byte hash and portable storage key. Consecutive versions retain one
application and material kind; the application role cannot mutate history.
`0016_mailbox_sync` adds a mutable, fenced provider cursor plus immutable sync runs and
provider events. Event insertion and cursor advancement share one transaction, so a
restart replays provider changes safely without creating a second local event.
`0017_mailbox_sync_grants` narrows the application role's cursor update privilege to
the cursor, revision and timestamp columns; account/provider identity remains fixed.
Review SQL, privilege implications and recovery behavior before applying any
revision. Do not edit applied revisions or create empty baseline revisions.

Use the `acoa` schema for application objects created by `acoa_migrator`, so the
existing default application grants apply. Alembic's own version metadata lives
in `acoa_migrations`, which is inaccessible to `acoa_app`.

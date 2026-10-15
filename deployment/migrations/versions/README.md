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
Review SQL, privilege implications and recovery behavior before applying any
revision. Do not edit applied revisions or create empty baseline revisions.

Use the `acoa` schema for application objects created by `acoa_migrator`, so the
existing default application grants apply. Alembic's own version metadata lives
in `acoa_migrations`, which is inaccessible to `acoa_app`.

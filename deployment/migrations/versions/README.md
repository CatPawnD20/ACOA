# Application revisions

The G0 bootstrap supplied the runner without a synthetic baseline. EP-02.01 adds
`0001_task_queue`, creating task runs, immutable enqueue dependencies and event
history. The application role may append/read events but cannot update/delete
them. Downgrade refuses destructive removal of retained queue and audit data.
Review SQL, privilege implications and recovery behavior before applying any
revision. Do not edit applied revisions or create empty baseline revisions.

Use the `acoa` schema for application objects created by `acoa_migrator`, so the
existing default application grants apply. Alembic's own version metadata lives
in `acoa_migrations`, which is inaccessible to `acoa_app`.

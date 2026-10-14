# Application revisions

This directory intentionally contains no revisions at the G0 bootstrap gate.
Business schema revisions belong to EP-02. The migration runner supports Alembic
revision modules placed here; revision authoring and autogeneration are outside
this bootstrap task. Review SQL, privilege implications, and recovery behavior
before applying a revision. Do not create synthetic or empty baseline revisions.

Use the `acoa` schema for application objects created by `acoa_migrator`, so the
existing default application grants apply. Alembic's own version metadata lives
in `acoa_migrations`, which is inaccessible to `acoa_app`.

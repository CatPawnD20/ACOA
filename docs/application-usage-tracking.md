# Per-application Codex usage tracking

ACOA records exact Codex token deltas for application work performed in one Codex
session. The tracker reads only the latest `token_count` event from the current local
session log. It does not parse or copy prompts, messages, tool output, CV content, or
employer data.

Reports are written under `private/application-usage/`, which is excluded from Git.
Each report contains input, cached-input, cache-write, output, reasoning-output, and
total-token counters for the full application and these fixed stages:

1. `research`
2. `analysis`
3. `cv`
4. `form`
5. `submission`

Start tracking before application-specific research:

```powershell
acoa-application-usage start jumpcloud-devices-software-engineer `
  --label "JumpCloud — Devices Software Engineer" --stage research
```

Close the current stage and start the next one:

```powershell
acoa-application-usage advance jumpcloud-devices-software-engineer --stage analysis
```

Complete the report after a confirmed outcome:

```powershell
acoa-application-usage finish jumpcloud-devices-software-engineer --outcome submitted
```

Use `status` to inspect the current report summary. A report cannot span Codex sessions,
overwrite an existing application key, move counters backwards, or finish twice. Shared
work performed outside the report window is not attributed to that application.

The PostgreSQL Model Gateway continues to record provider-side model usage separately.
This local tracker covers Codex-assisted research, document preparation, browser work,
retries, and submission activity that occurs around those provider calls. It implements
the per-application resource attribution required by `E-02.02` and the reporting boundary
in `E-08.04`; it does not change authorization or external-action policy.

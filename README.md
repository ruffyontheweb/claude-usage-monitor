# claude-usage-monitor

Local monitoring for Claude Code usage on node0, plus a session-handoff tool.

- **Monitoring:** an LGTM container (`claude-usage-lgtm`, Grafana on http://127.0.0.1:3000) fed by Claude Code's
  OpenTelemetry export, with the dashboard in `grafana/claude-usage.json`.
- **Session handoff:** a status line showing conversation size (`ctx 312K/1.0M`), hooks that tell Claude to suggest a
  handoff at natural breaks (a PR created or merged) once the conversation is above a floor, a near-full warning
  before compaction, and a `/handoff` skill that writes a one-page note for a fresh session.
  Design: `docs/specs/2026-11-05-session-handoff-design.md`.

Python 3 standard library only. Tests: `python3 -I -m unittest discover -s tests -v`.

## Install

```
python3 -I ~/claude-usage-monitor/bin/install.py
```

This backs up `~/.claude/settings.json` to `settings.json.bak-<YYYYmmdd-HHMMSS>`, then merges in a `statusLine` and
one handler each on `SessionStart`, `UserPromptSubmit` and `PostToolUse` (every existing key and hook is kept), and
links `~/.claude/skills/handoff` to `skills/handoff`. It refuses, writing nothing, if the settings file isn't valid
JSON, if another `statusLine` is set, or if something else is at the skill path. Running it twice changes nothing.

**Restart** open Claude Code sessions afterwards: settings are read at session start.

## Use

- The status line shows `ctx <size>/<window>`, adds `· handoff at next break` above the floor, and
  `· floor unverified` when the session's model or Claude Code minor version isn't in the config's `measured_on`.
- At a natural break above the floor, Claude finishes its reply and suggests `/handoff` in one line.
- `/handoff` writes `<main checkout>/.claude/handoffs/<YYYY-MM-DD-HHMM>-<branch>-<topic>.md` (kept out of git through
  `.git/info/exclude`), shows it and stops. It never commits, pushes or opens a PR.
- In a fresh session: "pick up from the latest handoff". The newest note for the current branch is used; with none,
  Claude lists the notes and asks.

Errors in the hooks or status line are never shown; they go to `~/.cache/claude-handoff/errors.log`, one line each.

## Re-measure the floor

```
python3 -I ~/claude-usage-monitor/bin/remeasure.py [--days 14]
```

Reads recent transcripts (read-only) and prints, per model, the context-size distribution, compactions, Claude Code
versions, and the share of tokens from requests at or above 100K/150K/200K/300K, then a suggested floor. It never edits
`config/handoff.json`; change `floor_tokens` there yourself, and the 300000 in the dashboard panel "Main-session tokens
from requests above the floor" with it. The config's `revisit_if` says when to re-run.

The report and the panel answer different questions. The report weighs each request by its full context size and asks whether the floor fits. The panel weighs by cache-read tokens over the last 24 h and asks whether handoffs keep conversations below the floor, so a falling panel is good news, not a reason to move the floor.

## Editing the dashboard

`grafana/claude-usage.json` is bind-mounted into the container as a single file, and Grafana loads it at startup.
After an edit, run `docker restart claude-usage-lgtm`. Edit the file in place: anything that replaces it with a new
file (`git checkout`, an editor that saves by rename) leaves the container on the old copy until the restart.

## Uninstall

```
python3 -I ~/claude-usage-monitor/bin/uninstall.py
```

Backs up the settings again, removes exactly our handlers and `statusLine` (and matcher groups left empty), and
removes the skill link if it points here. Restart open sessions afterwards.

## Undo the monitoring stack

1. `cd ~/claude-usage-monitor && docker compose down -v` (`-v` also deletes the stored metrics and traces).
2. Remove the telemetry keys from `env` in `~/.claude/settings.json` (`CLAUDE_CODE_ENABLE_TELEMETRY`,
   `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA`, `OTEL_*`), or restore the backup taken before they were added,
   `~/.claude/settings.json.bak-20261104-220740`, if nothing else has changed since.

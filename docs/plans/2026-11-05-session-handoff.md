# Session handoff at natural breaks: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In every Claude Code session on node0, show the conversation size, nudge a handoff at natural breaks when the
conversation is large, and provide a `/handoff` skill that writes a one-page note for a fresh session.

**Architecture:** Python 3 standard-library scripts in `~/claude-usage-monitor`, wired into `~/.claude/settings.json` by
an install script: one status-line command, one hook entry point dispatching on the hook event, one shared library, a
user-level skill linked into `~/.claude/skills/handoff`. A floor config carries its own basis. A re-measurement script and
a Grafana panel report whether the floor still fits.

**Tech Stack:** Python 3.12 stdlib (`unittest`, no pytest), bash, git, `gh`, Grafana/Tempo TraceQL metrics.

**Spec:** `docs/specs/2026-11-05-session-handoff-design.md`

## Global Constraints

- Repository root: `~/claude-usage-monitor` (written `$REPO` below). Private GitHub repo `ruffyontheweb/claude-usage-monitor`.
- No dependency beyond python3 stdlib, bash, git, gh, jq, docker. Run Python as `python3 -I`.
- Tests: `cd $REPO && python3 -I -m unittest discover -s tests -v`. Every test has a control: break the guarded line,
  run, see FAIL, restore. The commit message records the failing control (one line: test name and the failure).
- Hooks and status line: never raise, never block, never print on error. On any exception: exit 0, no stdout, append
  one line to `~/.cache/claude-handoff/errors.log`. Each hook handler has `"timeout": 5`.
- Never read a whole transcript in a hook or the status line: tail at most 1 MiB.
- `~/.claude/settings.json`: timestamped backup before any write; merge; keep every existing key and the herdr
  `SessionStart` hook; never edit `~/.claude/CLAUDE.md`.
- The handoff skill never commits, pushes or opens a PR.
- Commits end with the single trailer line `Made-with: Claude Code`. Nothing else about tooling.
- Context size = `input_tokens + cache_creation_input_tokens + cache_read_input_tokens` of the latest main-session
  (non-sidechain) assistant request.
- Facts from the Claude Code docs (not yet tested on 2.1.318; Task 8 checks them live): status-line stdin carries
  `session_id`, `transcript_path`, `version`, `model.id`, `model.display_name`, `context_window.context_window_size`,
  `context_window.current_usage` (null before the first call and after `/compact`); every hook gets `session_id`,
  `transcript_path`, `cwd`, `hook_event_name`; `SessionStart` gets `source`; `PostToolUse` gets `tool_name`,
  `tool_input`, `tool_use_id`; non-blocking context to Claude is
  `{"hookSpecificOutput": {"hookEventName": <event>, "additionalContext": <text>}}`.

## Review Focus

1. Transcript ends in a half-written line (the session is mid-write): use the last complete entry, never fail. Test in Task 2.
2. Hook called with missing fields, a non-git `cwd`, or a deleted transcript: no output, exit 0. Test in Task 4.
3. `settings.json` missing, empty, or not valid JSON: install refuses with a message and writes nothing. Test in Task 7.
4. Detached HEAD in a worktree: the note name uses `detached-<7-char sha>`. Test in Task 5.
5. Two sessions at once: state is per session file, written atomically (temp file + rename). Test in Task 3.

---

### Task 1: Repository, ignore rules, first push

**Files:**
- Create: `$REPO/.gitignore` (`__pycache__/`, `*.pyc`, `.claude/handoffs/`), `$REPO/README.md` (one paragraph: what this
  is; install and undo filled in Task 9)
- Existing: `docker-compose.yml`, `grafana/*`, `docs/specs/…`, `docs/plans/…`

- [ ] **Step 1:** `cd $REPO && git init -b main && git add -A && git status --short` — expect the compose file, the two
  grafana files, the spec, the plan, `.gitignore`, `README.md`; nothing else.
- [ ] **Step 2:** Commit `chore: monitoring stack, handoff design and plan`.
- [ ] **Step 3:** `gh repo create ruffyontheweb/claude-usage-monitor --private --source . --push` — expect the URL;
  `gh repo view --json visibility -q .visibility` prints `PRIVATE`. Control: `curl -s -o /dev/null -w '%{http_code}'
  https://github.com/ruffyontheweb/claude-usage-monitor` prints `404` (not public).

### Task 2: Config, size, staleness (`lib/handoff_lib.py`)

**Files:** Create `lib/handoff_lib.py`, `config/handoff.json`, `tests/test_handoff_lib.py`, `tests/fixtures/` (synthetic JSONL).

**Interfaces — Produces:**
- `REPO: Path` (parent of `lib/`); `CONFIG_PATH = REPO/"config/handoff.json"`; `STATE_DIR = Path.home()/".cache/claude-handoff"`
- `load_config(path: Path = CONFIG_PATH) -> dict`
- `context_size(transcript_path: str, tail_bytes: int = 1_048_576) -> int | None`
- `basis_status(config: dict, model_id: str | None, version: str | None) -> str` → `"verified"`, `"unverified-model"` or `"unverified-version"` (model checked first)
- `fmt_tokens(n: int) -> str`
- `log_error(where: str, exc: BaseException) -> None`

`config/handoff.json`, exact values:
```json
{"floor_tokens": 200000, "near_full_fraction": 0.8, "default_context_window": 200000,
 "measured_on": {"date": "2026-11-05", "claude_code_versions": ["2.1"], "models": ["claude-fable-5-1"],
   "sessions": ["5f5d4165-08b0-478e-90b2-eb7290fd3784"]},
 "revisit_if": "a model not in measured_on.models, a Claude Code minor version not in measured_on.claude_code_versions, or the dashboard share-above-floor panel falling below 0.5 for a week"}
```

- [ ] **Step 1: Tests**
  - `test_context_size_last_main_entry`: fixture with three assistant entries (sizes 1000, 5000 and a sidechain at 9000); expect `5000`.
  - `test_context_size_dedupes_by_message_id`: two lines with the same `message.id`; the size counts once.
  - `test_context_size_truncated_last_line` (Review Focus 1): a complete entry at 4000, then a half line; expect `4000`.
  - `test_context_size_missing_file`: expect `None`.
  - `test_context_size_tail_only`: a 50 MB fixture generated in `setUp` (temp dir); the call finishes under 0.2 s and returns the last entry's size.
  - `test_basis_status`: `("claude-fable-5-1","2.1.318")` → `"verified"`; `("claude-opus-5-5","2.1.318")` → `"unverified-model"`; `("claude-fable-5-1","2.2.0")` → `"unverified-version"`; `(None, None)` → `"unverified-model"`.
  - `test_fmt_tokens`: `999→"999"`, `5000→"5K"`, `312_400→"312K"`, `1_000_000→"1.0M"` (below 1000 as is; below 1M rounded to whole K; else one decimal M).
- [ ] **Step 2:** Run; expect failures (module missing).
- [ ] **Step 3:** Implement. `context_size` seeks to `max(0, size - tail_bytes)`, drops the first partial line, parses
  from the end, skips `isSidechain: true` and non-`assistant` entries, and returns the first entry with `message.usage`.
- [ ] **Step 4:** Run; expect PASS. Control: make `context_size` ignore `isSidechain`; `test_context_size_last_main_entry` FAILS (9000 ≠ 5000). Restore.
- [ ] **Step 5:** Commit `feat: handoff config, context size, basis check`.

### Task 3: Breaks, nudges, state (`lib/breaks.py`)

**Interfaces — Consumes:** `load_config`, `fmt_tokens`, `STATE_DIR`. **Produces:**
- `detect_break(event: dict) -> str | None` → `"pr-create"`, `"pr-merge"` or `None`. Bash: `tool_input.command` matches
  `\bgh\s+pr\s+(create|merge)\b`. MCP: `tool_name` matches `^mcp__.*github.*__(create_pull_request|merge_pull_request)$`.
- `load_state(session_id: str) -> dict`, `save_state(session_id: str, state: dict) -> None` (temp file + `os.replace`)
- `break_nudge(config: dict, size: int | None, state: dict, kind: str, tool_use_id: str) -> str | None`
- `size_note(config: dict, size: int | None, window: int, state: dict) -> str | None` (for every prompt)

Exact copy:
- break nudge: `"[handoff] Natural break ({kind}) and the conversation is {size} tokens, above the {floor} floor. Finish this reply, then suggest /handoff to the user in one line and start nothing new until they answer."`
- size line, when size ≥ floor: `"[handoff] Conversation is {size} tokens, above the {floor} floor."`
- near-full, once per crossing of `window × near_full_fraction` (reset when size drops below, after compaction): `"[handoff] Conversation is {size} of a {window} window; compaction is near. At your next stopping point, suggest /handoff in one line. Do not stop mid-task."`
  When both apply, the near-full text replaces the size line.

- [ ] **Step 1: Tests**
  - `test_detect_break`: `gh pr create --fill` → `"pr-create"`; `cd x && gh pr merge 9 --squash` → `"pr-merge"`; `echo gh pr create` → `"pr-create"` (accepted: rare, harmless); `gh pr view 3` → `None`; `tool_name="mcp__plugin_github_github__merge_pull_request"` → `"pr-merge"`; `tool_name="Read"` → `None`.
  - `test_break_nudge_floor`: size 199_999 → `None`; 200_000 → text containing `"200K"` and `"pr-create"`.
  - `test_break_nudge_once_per_tool_use`: the same `tool_use_id` twice → the second returns `None`.
  - `test_near_full_once_per_crossing`: window 1_000_000, sizes 790K → size line, 810K → near-full, 820K → size line, 300K → size line, 850K → near-full.
  - `test_state_atomic` (Review Focus 5): two state writes for different sessions; both files readable with their own data; no `*.tmp` left.
- [ ] **Step 2:** Run; expect FAIL. **Step 3:** Implement. **Step 4:** Run; PASS. Control: change `>=` to `>` in the floor check; `test_break_nudge_floor` FAILS. Restore.
- [ ] **Step 5:** Commit `feat: break detection and handoff nudges`.

### Task 4: Hook entry point and status line (`bin/handoff_hook.py`, `bin/statusline.py`)

**Interfaces — Consumes:** Tasks 2 and 3; `latest_note` from Task 5 (import inside a try; absent means no mention).
**Produces:** two executables reading one JSON object on stdin.

`handoff_hook.py` dispatches on `hook_event_name`:
- `SessionStart`: `additionalContext` = the convention text (exact): `"Session handoff convention (claude-usage-monitor): when you finish a natural unit of work (a pull request opened or merged, a plan or design written and committed, or the user saying a piece of work is done) and a [handoff] line has said the conversation is above the floor, suggest /handoff in one line before starting anything new. Never stop mid-task for this."` On `source` `startup` or `clear`, plus `" A handoff note exists for this branch: {path}. Mention it to the user once."` when `latest_note(cwd)` returns a path.
- `UserPromptSubmit`: `size_note(...)` with `window` from the state's `context_window` (set by the status line), else `default_context_window`.
- `PostToolUse`: `detect_break` then `break_nudge`.
- Anything else, or no text: no stdout.
`statusline.py` prints one line: `ctx {size}/{window}` for example `ctx 312K/1.0M`; `" · handoff at next break"` appended when size ≥ floor; `" · floor unverified"` when `basis_status` isn't `"verified"`. Size from `context_window.current_usage` (sum of the three input fields) or, when null, `context_size(transcript_path)`; stores `context_window` and `model_id` in the session state.

- [ ] **Step 1: Tests** (`tests/test_entrypoints.py`, run the scripts with `subprocess` and a temp `HOME`)
  - `test_hook_session_start_text`: stdout parses as JSON, `hookEventName == "SessionStart"`, text starts with `"Session handoff convention"`.
  - `test_hook_post_tool_use_nudge`: fixture transcript at 250K plus a `gh pr merge` event; the text contains `"pr-merge"`.
  - `test_hook_bad_input` (Review Focus 2): stdin `"{}"`, stdin `"not json"`, a `cwd` of `/` with a missing transcript; each gives exit 0 and empty stdout.
  - `test_statusline_line`: `current_usage` totals 312_400 with window 1_000_000 and model `claude-opus-5-5` → `"ctx 312K/1.0M · handoff at next break · floor unverified"`.
  - `test_statusline_null_usage_falls_back`: `current_usage: null` plus a fixture transcript at 5000 → line starts `"ctx 5K"`.
- [ ] **Step 2–4:** fail, implement, pass. Control: drop the `try/except` around the dispatch; `test_hook_bad_input` FAILS (traceback, exit 1). Restore.
- [ ] **Step 5:** Commit `feat: handoff hook entry point and status line`.

### Task 5: The handoff skill and note paths (`bin/handoff_path.py`, `skills/handoff/SKILL.md`)

**Interfaces — Produces:**
- `main_checkout(cwd: str) -> Path | None` (parent of `git rev-parse --path-format=absolute --git-common-dir`; `None` outside git)
- `branch_slug(cwd: str) -> str` (branch with `/` → `-`; detached → `detached-<7 sha>`)
- `note_dir(cwd: str) -> Path` (`main_checkout/.claude/handoffs`, or `cwd/.claude/handoffs` outside git)
- `ensure_excluded(cwd: str) -> None` (appends `.claude/handoffs/` to `<git-common-dir>/info/exclude` once)
- `new_note_path(cwd: str, topic: str, now: datetime) -> Path` → `YYYY-MM-DD-HHMM-<branch>-<topic-slug>.md`
- `latest_note(cwd: str) -> Path | None` (newest whose name contains `-<branch>-`)
- CLI: `handoff_path.py new <topic>` prints the path and ensures the exclude; `handoff_path.py latest` prints the path, or lists all notes and exits 1.

`skills/handoff/SKILL.md`: frontmatter `name: handoff`, `description: Draft a one-page handoff note so the user can restart in a fresh session; use when the user runs /handoff or accepts a handoff suggestion`, `disable-model-invocation: false`. The body is the design's section 4.4 as steps: flush durable items to the records the project's CLAUDE.md names (uncommitted, listed); else a "Should be recorded" section; get the path from `handoff_path.py new <topic>`; write the six sections in the spec's order, with a header of branch, worktree, session ID and time; show the note; stop; no commit, push or PR. A second section, "Picking up", says that on "pick up from the latest handoff" Claude runs `handoff_path.py latest`, reads the note, then reads its "read first" pointers.

- [ ] **Step 1: Tests** (`tests/test_handoff_path.py`, temp git repos made in `setUp`)
  - `test_note_dir_from_worktree`: main repo plus `git worktree add`; `note_dir(worktree)` equals the main repo's `.claude/handoffs`.
  - `test_branch_slug_detached` (Review Focus 4): `git checkout --detach`; matches `^detached-[0-9a-f]{7}$`.
  - `test_ensure_excluded_idempotent`: called twice; exactly one `.claude/handoffs/` line; `git status --short` shows no note file after one is created.
  - `test_latest_note_branch_scoped`: notes for `feat-a` (newer) and `feat-b`; on `feat-b`, returns the `feat-b` note.
  - `test_outside_git`: a temp dir without git; `note_dir` is `<dir>/.claude/handoffs`.
- [ ] **Step 2–4:** fail, implement, pass. Control: make `latest_note` ignore the branch; `test_latest_note_branch_scoped` FAILS. Restore.
- [ ] **Step 5:** Commit `feat: handoff skill and branch-scoped note paths`.

### Task 6: Re-measurement (`bin/remeasure.py`)

**Interfaces — Consumes:** `load_config`, `fmt_tokens`. **Produces:** CLI `remeasure.py [--days 14] [--projects-dir ~/.claude/projects]`, read-only.

Report per model, main session (non-sidechain, deduped by `message.id`, files modified within `--days`): requests; context p50, p90 and max; compactions (`isCompactSummary` or `subtype == "compact_boundary"`); Claude Code versions seen (entry `version`); the share of tokens from requests at or above 100K, 150K, 200K and 300K. Then: suggested floor = the largest candidate whose share-above is ≥ 0.80 across all models; suggested near-full = `near_full_fraction` unchanged, with the largest context seen and the windows recorded in state files. Last line: `config not changed; edit config/handoff.json to apply`.

- [ ] **Step 1: Tests** (`tests/test_remeasure.py`, fixture directory): two models; known shares; `test_suggested_floor` expects `200K` for a fixture where shares are 0.95, 0.90, 0.85 and 0.60; `test_read_only`: the config file's mtime is unchanged after a run.
- [ ] **Step 2–4:** fail, implement, pass. Control: change `≥ 0.80` to `≥ 0.95`; `test_suggested_floor` FAILS (100K). Restore.
- [ ] **Step 5:** Run on the real projects directory and paste the report into the commit message body. Commit `feat: remeasure report for the handoff floor`.

### Task 7: Install and uninstall (`bin/install.py`, `bin/uninstall.py`)

**Interfaces — Consumes:** paths of Tasks 4 and 5. **Produces:** idempotent scripts, `--home` option (default `~`) for tests.

Install: refuse (exit 2, message, no write) if `settings.json` is unparseable, or if a `statusLine` exists whose command isn't ours. Back up to `settings.json.bak-<YYYYmmdd-HHMMSS>`. Add `statusLine: {"type": "command", "command": "python3 -I $REPO/bin/statusline.py"}`. Append one handler each to `SessionStart` (no matcher), `UserPromptSubmit` (no matcher) and `PostToolUse` with matcher `^Bash$|^mcp__.*github.*__(create|merge)_pull_request$`. The command is `python3 -I $REPO/bin/handoff_hook.py`, with `"timeout": 5`. Symlink `~/.claude/skills/handoff` to `$REPO/skills/handoff`; refuse if a non-symlink is there. "Ours" means the command contains `claude-usage-monitor/bin/`.
Uninstall: back up; remove exactly our handlers (dropping matcher groups left empty) and our `statusLine`; remove the symlink if it points at us.

- [ ] **Step 1: Tests** (`tests/test_install.py`, temp home with a copy of a settings fixture modelled on the real one: `env`, `hooks.SessionStart` herdr entry, `tui`, `model`)
  - `test_install_keeps_existing`: after install, every original key and the herdr handler are unchanged; our three handlers present; one backup file.
  - `test_install_idempotent`: install twice; each of our handlers appears once.
  - `test_uninstall_restores`: install then uninstall; settings equal the original apart from key order.
  - `test_refuse_bad_settings` (Review Focus 3): invalid JSON gives exit 2 and the file is byte-identical; a missing file is created with only our keys; an empty file is treated as `{}`.
  - `test_refuse_foreign_statusline`: an existing `statusLine` command `foo.sh` gives exit 2 and no change.
- [ ] **Step 2–4:** fail, implement, pass. Control: skip the backup; `test_install_keeps_existing` FAILS (no backup). Restore.
- [ ] **Step 5:** Commit `feat: install and uninstall for the handoff hooks`.

### Task 8: Live install and check (user in the loop)

- [ ] **Step 1:** `python3 -I $REPO/bin/install.py` and show the diff between the backup and the new settings file.
- [ ] **Step 2:** Ask the user to start a fresh session anywhere and send one prompt. Then check: the status line shows `ctx …`; the session's state file has `context_window`; `errors.log` is absent or empty. Control: feed `statusline.py` a payload whose `context_window` is removed; the line still prints, from the transcript.
- [ ] **Step 3:** Record which of the Global Constraints' doc facts held on 2.1.318 in `docs/specs/…` under a new "Built as" section. If one didn't hold, stop and report before Task 9.

### Task 9: Dashboard panel, trace-panel fix, README

**Files:** Modify `grafana/claude-usage.json`, `README.md`.
- Panel "Main-session tokens from requests above the floor" (timeseries, Tempo datasource, `"timeFrom": "24h"`: TraceQL metrics are capped at 24 h, VERIFIED 2026-11-05). Query A: `{ name = "claude_code.llm_request" && span.query_source_safe = "repl_main_thread" && span.cache_read_tokens + span.input_tokens + span.cache_creation_tokens >= 200000 } | sum_over_time(span.cache_read_tokens)`. Query B: the same without the size clause. Expression `$A / $B`, unit percentunit. Description: the floor is hard-coded at 200K, matching `config/handoff.json`; change both together.
- Panels 16 and 17: add `"timeFrom": "24h"` (Tempo search refuses ranges over 168 h).
- README: what it is, install, uninstall, the restart note, how to remeasure, the undo for the monitoring stack.
- [ ] **Step 1:** Validate the JSON (`python3 -I -m json.tool`), then confirm both queries return data through `http://127.0.0.1:3000/api/datasources/proxy/uid/tempo/api/metrics/query_range`. Control: a 48 h range returns the "exceeds the maximum allowed duration" error.
- [ ] **Step 2:** Confirm in Grafana's log that panels 16 and 17 no longer error with the default 7-day range.
- [ ] **Step 3:** Commit `feat: share-above-floor panel; cap trace panels at 24h; README`, then `git push`.

# Session handoff at natural breaks: design

Status: draft for the user's approval, 2026-11-05. Lives in `~/claude-usage-monitor`, which becomes a private GitHub
repository (user decision 2026-11-05).

## 1. Intent

The user is on a Max plan and keeps running out of the Fable 5.1 share of the weekly limit. That's tolerable at the
end of a chunk of work. It hurts when it happens just before work is finished, for example with a pull request almost
ready, and the next reset is half a week or more away. The user will not trade correctness for budget: Fable stays the
model for the hard work.

Most of the budget goes to re-reading long conversations, not to new work. Measured on the user's longest session
(`5f5d4165`, sdr-more, 2026-10-17 to 2026-11-05, main session only, from its transcript):

| Measure | Value |
|---|---|
| Fable requests | 1,517 |
| Conversation re-read per request, median / 90th percentile / max | 436 K / 823 K / 966 K tokens |
| Share of tokens that are cache reads | 97.2 % |
| Share of tokens from requests whose conversation exceeded 400 K | 76.5 % |
| Compactions | 14 |

ESTIMATE: had the same requests each re-read at most 200 K, Fable use would have been about 41 % of actual. That flatters
restarting, because a fresh session spends turns and a cache fill rebuilding context.

The session ran through several clean breaks (slices D to G merged) without a restart. Natural breaks existed; nothing
prompted using them. The user confirmed most features could have started fresh, because each slice records its spec and
plan. Occasionally the long conversation held something that wasn't written down.

So the capability is: **at a natural break, if the conversation is already large, Claude suggests a handoff; Claude drafts
a one-page note; the user and Claude go over it; the user restarts from it.** Plus the conversation size is always visible.

## 2. Goals, non-goals, anti-goals

Goals:
1. Conversation size visible at all times in every Claude Code session on this machine.
2. At a natural break, when the conversation is large, Claude suggests a handoff instead of carrying on.
3. A handoff command that drafts the note, flushes durable items into the project's own documents, shows the note, and
   waits for the user.
4. A new session can start from the latest note with one short instruction.
5. The size floor carries its basis and is flagged when its basis no longer matches (section 6).
6. Works in every project, not only sdr-more (user decision).

Non-goals:
- Choosing models, effort or agents. No setting other than the hooks, the status line and the command it adds.
- Enforcing a budget, counting plan depletion, or estimating dollars.
- Restarting sessions automatically. The user ends and starts sessions.
- Per-project governing documents. Each project keeps its own (sdr-more's roadmap is done separately, in sdr-more).

Anti-goals (a failure even if it works):
- **Interrupting work in progress.** No mid-task stop, no blocked tool calls (user decision: no hard stop). The one
  allowed exception is the near-full case in section 4.3, and that is still a suggestion.
- **Nagging.** A suggestion on every small session or every commit trains the user to ignore it.
- **A note that replaces the documents.** The note must not summarise specs or plans. Anything durable goes into the
  project's own records before the restart.
- **Silent staleness.** A floor applied to a model or version it was never measured on, without saying so.
- **Anything leaving the machine.** Except pushing this repository to the user's private GitHub.

## 3. What exists

- `~/claude-usage-monitor`: grafana/otel-lgtm stack, `docker-compose.yml`, dashboard `grafana/claude-usage.json`. Not
  under git yet.
- `~/.claude/settings.json`: telemetry `env` keys (2026-11-04, backup `settings.json.bak-20261104-220740`), one existing
  hook (`SessionStart`, the herdr terminal's `herdr-agent-state.sh`, must be kept), no `statusLine`, `tui: fullscreen`.
- Claude Code 2.1.318. Session transcripts are JSONL under `~/.claude/projects/<project>/<session>.jsonl`; assistant
  entries carry `message.usage` with `input_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`,
  `output_tokens` (VERIFIED by the analysis above). Entries repeat per streamed chunk; dedupe on `message.id`.
- Telemetry metric `claude_code_token_usage_tokens_total` with labels `model`, `type`, `query_source`, `session_id`.

## 4. How it behaves

### 4.1 Size, always visible
A status line shows the current conversation size, taken from the last main-session assistant request in the transcript
(input + cache creation + cache read). Shape: `ctx 312K`; past the floor it changes look (for example a marker) so the
user notices without reading the number. If the floor is unverified for this session (section 6) it says so briefly.
The exact format is left to the builder.

### 4.2 The nudge at a natural break
Scope (builder's-call answer, marked: my call 2026-11-05): the floor, the nudge and the near-full mark apply to the
main session of every model, because the re-reading cost does not depend on the model and Opus has a weekly budget too.
Subagent conversations are not counted: they start fresh per task. If nudges on Sonnet or Haiku sessions turn out to be
noise, the config gains a per-model switch.

A natural break is any of:
- a pull request created or merged (`gh pr create`, `gh pr merge`, or a GitHub tool doing the same);
- a plan or design document finished and committed;
- the user saying they're done with a piece of work.

When a break happens and the conversation is above the floor, Claude is told (through a hook's context to Claude) to
finish its current reply, then suggest a handoff in one line, and not start new work until the user answers. If the user
declines, no new nudge fires until the next break. Below the floor, nothing happens.

The first two breaks are detected mechanically. The third relies on Claude, via one sentence of instruction injected
as session-start hook context (my call: install never edits the user's `~/.claude/CLAUDE.md`).

### 4.3 Near-full
If the conversation passes a high mark close to the model's context window (so compaction is about to discard detail
anyway), Claude suggests a handoff at its next stopping point even without a break. Still a suggestion, never a block.

### 4.4 The handoff command
A user-level command (for example `/handoff`). It never commits, pushes or opens a pull request (my call: projects
like sdr-more require every change to main to go through a PR, and a half-finished handoff must leave nothing behind
but uncommitted edits). It:
1. Moves durable items to the project's own records. It finds them from the project's `CLAUDE.md` (the documents it
   names as authoritative: decision log, roadmap, specs). Edits go into the current working tree, so in a worktree they
   ride on that branch and its PR. They are left uncommitted and listed in the note, and the user sees them in the
   review. If the project names no records, nothing is edited: the note gets a "should be recorded" section instead,
   so the skip is never silent (my call).
2. Writes the note at `<main checkout>/.claude/handoffs/<YYYY-MM-DD-HHMM>-<branch>-<topic>.md`. "Main checkout" is the
   repository's primary working tree, so notes don't vanish with a worktree. The note's header records branch,
   worktree path, session ID and time. The folder is ignored through `.git/info/exclude`, which is local and needs no
   commit (my call). Outside a git repository: `.claude/handoffs/` in the working directory.
3. Note content, one page, only what the documents don't hold:
   - where the work stands: branch, worktree, last commit, test state, what's half done;
   - user rulings not yet recorded, with why;
   - open assumptions, each labelled VERIFIED (with a citation), ESTIMATE or NEEDS CHECK;
   - facts at hand not written anywhere else;
   - the very next step, concretely;
   - what to read first, as pointers.
4. Shows the note and stops. The user and Claude go over it. Claude starts no new work.

### 4.5 Starting fresh
The user starts a new session and says something like "pick up from the latest handoff". "Latest" means the newest
note for the current branch; with no branch match, Claude lists the candidates and asks (my call: sdr-more runs
worktrees in parallel, so newest-in-project can pick another session's note). A session-start hook may mention that a
note exists for this branch; the builder decides whether that's worth it.

## 5. Where things live

In the repository:
- `docs/specs/` (this document), `README.md` (what it is, install, undo).
- The status line script, the hook script(s), the handoff command, the floor config (section 6), the re-measurement
  script, an install script and an uninstall script.
- The existing compose file and dashboard, plus the new dashboard panel if section 6 allows it.

Install touches only `~/.claude/settings.json` (status line and hooks) and the user-level commands folder; uninstall
reverses exactly that. It never edits `~/.claude/CLAUDE.md` (section 4.2).

On the machine: install wires the scripts into `~/.claude/settings.json` (backed up first, merged, every existing key and
hook kept) and puts the command where Claude Code finds user-level commands. Uninstall reverses exactly that.

## 6. Staying current

The floor (and the near-full mark) live in one config file with their basis:

```
floor_tokens, near_full_fraction
measured_on: date, Claude Code version, models, session(s) used
revisit_if: a new model, a new Claude Code minor version, or the dashboard curve flattening
```

Starting values are the builder's call, based on section 1: the floor somewhere around 150 K to 200 K is reasonable,
because the floor only filters small sessions and being off by half changes little.

What can go stale, and what cannot. Tokens per request track conversation size almost by definition, so that curve
never "flattens" and is no signal (a correction to what was told to the user on 2026-11-05). What can change: a
model's context window (moves the near-full mark), Claude Code caching or compaction behaviour, how the plan weights
cache reads (not observable here; the spec does not count plan depletion), and whether the habit is working.

How the user learns:
1. The status line marks the floor unverified when the session's model or Claude Code version isn't in `measured_on`.
2. The re-measurement script (the analysis in section 1, generalised over recent transcripts) prints, per model: the
   context-size distribution, the share of tokens from requests above the floor, the largest context seen, and
   compactions. It suggests a floor and a near-full mark. It never edits the config; the user approves a change.
3. A dashboard panel for whether the habit works: share of main-session tokens from requests above the floor, over
   time. Built only if the existing telemetry carries per-request token counts (for example on the `llm_request` trace
   spans: NEEDS CHECK); no new background exporter or service (my call). Otherwise the script's report covers it.

## 7. Constraints

- No new dependencies beyond what's on the machine (bash, python3 standard library, jq if present, docker). Any new one
  needs the user's yes after reading its LICENSE.
- Hooks must be fast (well under a second) and must never fail a tool call or a prompt. On any error, they do nothing.
- Transcripts reach hundreds of MB. Read the tail, never the whole file, on every hook or status-line call.
- Never modify `~/.claude/settings.json` without a timestamped backup; never drop existing keys or the herdr hook.
- Repository pushed to a private GitHub repo under `ruffyontheweb`. Commits end with `Made-with: Claude Code` and no
  other tooling attribution.
- Every test has a control that must fail (the user's global rule).

## 8. Left to the builder

- Which hook events and output fields implement section 4.2 and 4.3. NEEDS CHECK against Claude Code 2.1.318
  documentation: which events see `transcript_path`, and how a hook passes context to Claude without blocking.
- Status-line format and the starting floor value within section 6's range.
- How a plan or design "finished and committed" is detected, or whether Claude's instruction covers it.
- Whether the session-start mention of an unread note is worth having.
- Test approach for scripts that read transcripts (synthetic JSONL fixtures are fine).

## 9. Separately, not part of this build

- sdr-more's roadmap document, rulings flush and first handoff note: handled by a message the user pastes into the
  sdr-more session (2026-11-05).
- The dashboard's two trace panels fail on the 7-day range (Tempo caps search at 168 h). Fixing them is a small change
  that can ride along with the new panel; the builder may include it.

## 10. Built as (checked live on Claude Code 2.1.318, 2026-11-05)

Installed with `bin/install.py` (backup `settings.json.bak-20261105-021838`). A fresh session (f6d3bb75, rf-analyzer,
claude-opus-5-5) showed `ctx 60K/1.0M · floor unverified`, and `~/.cache/claude-handoff/errors.log` was absent.

Doc facts from the plan's Global Constraints:
- VERIFIED: status-line stdin carries `session_id`, `model.id` and `context_window.context_window_size`. The session's
  state file recorded `{"context_window": 1000000, "model_id": "claude-opus-5-5"}`.
- VERIFIED: `SessionStart` runs with `source` `startup`, and `hookSpecificOutput.additionalContext` reaches the model.
  The transcript has `hook_success` (`SessionStart:startup`) and `hook_additional_context` entries, and the
  convention text is present.
- VERIFIED: `UserPromptSubmit` gets `session_id` and a readable `transcript_path`. In session 0ad54321 its state gained
  `near_full_fired`, which is only written after a size was read from the transcript.
- VERIFIED: settings changes reach sessions that are already open. Hooks ran in sessions started before the install.
- NEEDS CHECK: `PostToolUse` `tool_name`, `tool_input` and `tool_use_id`. A silent run (below the floor) leaves no
  transcript record. The first PR created or merged above 200K will show it.
- NEEDS CHECK: `context_window.current_usage` being null before the first call and after `/compact`. The transcript
  fallback covers both cases either way.

Deviations from sections 4 to 6 are recorded in the commit history, for example the SQL expression in the dashboard
panel and the longest-branch match for notes.

---
name: handoff
description: Draft a one-page handoff note so the user can restart in a fresh session; use when the user runs /handoff or accepts a handoff suggestion
disable-model-invocation: false
---

# Handoff

Write a one-page note that lets a fresh session pick up this work, then stop. Never commit, push or open a pull
request: a half-finished handoff must leave nothing behind but uncommitted edits.

## Writing a note

1. **Flush durable items to the project's own records.** Read the project's `CLAUDE.md` and find the documents it names
   as authoritative (decision log, roadmap, specs). Put rulings, decisions and status that belong there into those
   files in the current working tree (in a worktree they ride on that branch). Leave the edits uncommitted and list each
   file you touched in the note. If the project names no such records, edit nothing and give the note a
   **Should be recorded** section listing what belongs in a durable record, so the skip is never silent.
2. **Get the path.** Run `python3 -I ~/claude-usage-monitor/bin/handoff_path.py new <topic>` from the working
   directory, with a two-to-four-word topic. It prints the note path (`<main checkout>/.claude/handoffs/…`), creates
   the folder and keeps it out of git through `.git/info/exclude`.
3. **Write the note**, one page, only what the project's documents don't already hold. Header line: branch, worktree
   path, session ID, time (UTC). Then these six sections, in this order:
   1. **Where things stand**: branch, worktree, last commit, test state, what is half done.
   2. **User rulings not yet recorded**, each with why.
   3. **Open assumptions**, each labelled VERIFIED (with a citation), ESTIMATE or NEEDS CHECK.
   4. **Facts at hand** not written anywhere else.
   5. **Next step**, concretely: the command or file and what to do with it.
   6. **Read first**: pointers (paths, sections), not copies.
   Add **Records edited (uncommitted)** or **Should be recorded** from step 1.
4. **Show the note and stop.** Print its path and contents. The user and you go over it. Start no new work.

## Picking up

When the user says "pick up from the latest handoff" (or similar):

1. Run `python3 -I ~/claude-usage-monitor/bin/handoff_path.py latest` from the working directory.
2. Exit 0: read the printed note. Exit 1: it lists every note; show the list and ask which one, since "latest" means
   the newest note for this branch and another branch's note belongs to another session.
3. Read the note's **Read first** pointers, then continue from its **Next step**.

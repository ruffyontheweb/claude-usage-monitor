---
name: handoff
description: Draft a short handoff note so the user can restart in a fresh session; use when the user runs /handoff or accepts a handoff suggestion
disable-model-invocation: false
---

# Handoff

Write a short note that lets a fresh session pick up this work, then stop. Never commit, push or open a pull
request: a half-finished handoff must leave nothing behind but uncommitted edits.

The project's own documents and git are the record. The note carries only what they do not hold yet, and it is deleted
once the next session has used it.

## Writing a note

1. **Flush durable items to the project's own records.** Read the project's `CLAUDE.md` and find the documents it names
   as authoritative (decision log, roadmap, specs). Put rulings, decisions and status that belong there into those
   files in the current working tree (in a worktree they ride on that branch). Leave the edits uncommitted and list each
   file you touched in the note. If the project names no such records, edit nothing and give the note a
   **Should be recorded** section listing what belongs in a durable record, so the skip is never silent.
2. **Get the path.** Run `python3 -I ~/claude-usage-monitor/bin/handoff_path.py new <topic>` from the working
   directory, with a two-to-four-word topic. It prints the note path (`<main checkout>/.claude/handoffs/…`), creates
   the folder and keeps it out of git through `.git/info/exclude`.
3. **Write the note, 40 lines at most.** Header line: branch, worktree path, last commit, session ID, time (UTC). Then
   these sections, in this order, leaving out any that would be empty:
   1. **Next step**, concretely: the command or file and what to do with it.
   2. **Half done and uncommitted**: work in progress, the test state if it is not green, and every uncommitted file
      (including the records edited in step 1).
   3. **User rulings not yet recorded**, each with why.
   4. **Open assumptions**, each labelled VERIFIED (with a citation), ESTIMATE or NEEDS CHECK.
   5. **Facts at hand** not written anywhere else.

   Do not restate what git, the roadmap, a spec or a plan already says: no status recap, no list of merged work, no
   reading list. Name a document only when the next session needs it and could not find it from the project's
   `CLAUDE.md` or the index that file points to. If the note runs past 40 lines, something in it belongs in the
   project's records: move it there in step 1.
4. **Remove this branch's older notes.** List the note folder. For each earlier note of the same branch, check that
   everything in it is recorded, done, or carried into the new note, then delete it. Leave other branches' notes alone.
5. **Show the note and stop.** Print its path and contents. The user and you go over it. Start no new work.

## Picking up

When the user says "pick up from the latest handoff" (or similar):

1. Run `python3 -I ~/claude-usage-monitor/bin/handoff_path.py latest` from the working directory.
2. Exit 0: read the printed note. Exit 1: it lists every note; show the list and ask which one, since "latest" means
   the newest note for this branch and another branch's note belongs to another session.
3. Read the project's `CLAUDE.md` and the index it names (a roadmap, if there is one), then continue from the note's
   **Next step**.
4. **Delete the note once it is used up**: its next step is done and each item it carried is recorded in the project's
   documents or no longer matters. Say so in one line. Until then leave it in place, so a session that ends early can
   still be picked up from it.

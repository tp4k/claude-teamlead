# `$RUN/plan-human.md` — the plan a person can actually read

`plan.md` is written for machines that do not skim. Every workstream carries a verbatim spec excerpt, a two-list test plan, a reuse call with both halves, verification commands with their working directories, and three tagged review axes — and every one of those exists because a run went wrong without it. None of it is going away.

But the person who has to say "yes, build that" is reading the same file, and a plan whose load-bearing decisions are spread across four hundred lines of material addressed to somebody else is one they will approve without reading. That approval is worth nothing, and it is the only gate between a misunderstanding and a full implementation round.

So this file is a **second view of the same plan**, never a second plan. It adds no fact that is not in `plan.md`, and it decides nothing. If the two disagree, `plan.md` is right and this file is a bug.

## Shape

```markdown
# <task, in one line of the user's own words>

<Two or three sentences: what will be true when this is done that is not true now.
Behaviour, not structure. Someone who has not read the task should understand the
change from this paragraph alone.>

## What gets built

| # | Workstream | What it does | Size | Runs |
|---|---|---|---|---|
| 1 | <name> | <one sentence, behaviour> | S/M/L | wave 1 |
| 2 | <name> | <one sentence, behaviour> | S/M/L | after 1 |

## How you will know it worked

<One line per workstream: the observable acceptance, in the words a person would
use to check it. "Send 101 requests in 10s — the last one gets a 429." Not the
test's name, not the file it lives in.>

## Decisions already taken

<One line each, from plan.md's `## Decisions taken` and questions.md's `## Answers`:
the decision, then the consequence that was accepted. This is the section most
worth a careful read — it is where a misunderstanding is still free to fix.>

## What this does NOT do

<The anti-scope, in plain words, plus anything the plan deliberately leaves alone.
A reader's most common objection to a plan is something it never claimed to do.>

## Open risks

<Only what is genuinely uncertain: a claim the validator flagged, a design review
row nobody could settle, a dependency that may not behave. Say "none" if none —
an invented risk costs the reader's trust in the other sections.>
```

Nothing else. No file lists, no commands, no spec excerpts, no test plans, no review axes: each of those has a reader, and that reader is an agent with the real plan open.

## Regenerating it after a Fix round

The plan changes between the first read and dispatch — the user's answers get folded in, a design review row gets fixed, the validator corrects a claim. A reader who already read this file will not re-read it from the top, so a silent rewrite is a change nobody sees.

Rewrite the file and put this **first, above the title**:

```markdown
## Changes since you last read this

- <what changed, in one line, newest first> — <why: the answer, the finding, the validator row>
```

Newest first, because the last change is the one they have not seen. Keep every previous entry: the list is the file's history and it is short by nature. When nothing changed, do not regenerate the file at all — an unchanged file with a "Changes" section that says "none" trains the reader to skip the section that matters.

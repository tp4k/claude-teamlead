# `$RUN/plan-human.md` — the plan a person can actually read

The source `plan.md` contains detailed workstream specs, tests, reuse decisions, verification commands, and review tags. Agents require this material.

A person deciding whether to approve the plan needs its behavior and consequential decisions. Those decisions can be difficult to find in hundreds of lines addressed to agents. A readable view supports an informed approval before implementation.

Create a human-readable view of the existing plan. Add no facts or decisions. Derive content from `plan.md`, `questions.md`, and `task.md`. If it conflicts with the authoritative `plan.md`, correct this view.

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

Use only the sections above. Omit file inventories, commands, spec quotations, test plans, and review tags. Agents read those details in `plan.md`.

## Regenerating it after a Fix round

Answers, design corrections, and validation can change the plan before dispatch. Someone who already read the human version needs an explicit change notice. Do not regenerate it silently.

Rewrite the file and put this **first, above the title**:

```markdown
## Changes since you last read this

- <what changed, in one line, newest first> — <why: the answer, the finding, the validator row>
```

Put the latest change first. Preserve every earlier entry. This list records the file's history. If the plan did not change, do not regenerate the file or add a "none" notice.

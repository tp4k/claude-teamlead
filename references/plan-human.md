# `$RUN/plan-human.md` — the plan a person can actually read

The source `plan.md` contains detailed workstream specs, tests, reuse decisions, verification commands, and review tags. Agents require this material.

A person deciding whether to approve the plan needs its behavior and consequential decisions. Those decisions can be difficult to find in hundreds of lines addressed to agents. A readable view supports an informed approval before implementation.

Create a human-readable view of the existing plan. Add no facts or decisions. Derive content from `plan.md`, `questions.md`, and `task.md`. If it conflicts with the authoritative `plan.md`, correct this view.

## How it should read

Write it like a short spec handed to a colleague, not a report from a pipeline.

- **The user's perspective first.** Problem and solution say what someone *experiences*, before and after. Structure, modules, and layers come later, if at all.
- **The user's vocabulary.** Reuse the words from `task.md`. When the plan coined a term, either replace it with a plain one or define it in the same sentence the first time it appears.
- **No paths, commands, test names, spec quotations, or review tags.** These go stale fast and mean nothing to someone approving behavior. Agents read them in `plan.md`.
- **Short beats complete.** Use a bullet when it can replace a sentence. Cut a bullet that adds nothing. About a page; never longer than the plan's own summary would justify.
- **No hedging and no throat-clearing.** Leave out "it's worth noting", "this plan aims to", and "comprehensive".

## Shape

````markdown
# <the task, in one line of the user's own words>

## Problem

<One to three sentences, from the user's side: what is broken, missing, or painful
today. Someone who has not read the task should recognise the problem.>

## Solution

<One to three sentences: what will be true when this lands that is not true now.
Behaviour, not structure.>

## What you'll be able to do

1. As a <who>, I can <behaviour>, so that <benefit>.
2. …

<One story per distinct behaviour the plan delivers — no more. A story the plan
does not deliver belongs under "Out of scope", not here.>

## The work

### 1 · <workstream name, as a short outcome: "Reject oversized uploads">

**Delivers:** <the end-to-end behaviour this workstream makes work, in one sentence.>
**Blocked by:** none — starts right away | 1 · <name>
**Size:** S | M | L

- [ ] <an acceptance check a person could perform: "Send 101 requests in 10 s — the
      last one gets a 429.">
- [ ] …

### 2 · <name>

…

## Decisions already made

- **<the decision>** — <the consequence that was accepted>. *(<source: "your answer
  to Q2" or "planner">)*

<From plan.md's `## Decisions taken` and questions.md's `## Answers`. This is the
section most worth a careful read: a misunderstanding is still cheap to fix here.>

## Out of scope

- <the anti-scope, in plain words, plus anything the plan deliberately leaves alone>

<A reader's most common objection to a plan is something it never claimed to do.>

## Open risks

- <only what is genuinely uncertain: a claim the validator flagged, a design-review
  row nobody settled, a dependency that may not behave>

<Write "None." when there are none — an invented risk costs the reader's trust in
every other section.>

## Before you approve

- <two to four pointed questions aimed at THIS plan's weakest joints, each naming the
  item it is about: "Workstream 2 waits on 1 — could they run together?", "Decision 3
  drops the CSV export — still fine?", "Is workstream 4 one piece of work or two?">
````

Number workstreams as `plan.md` numbers them, so a reader can cross-reference the source. "Blocked by" restates `plan.md`'s waves and dependencies. It does not decide them. Write each acceptance check as an action and the result a person would observe. A test name or a file path does not belong here.

"Before you approve" may contain only questions about content already in the plan. Draw them from these checks: Is the work split at the right size? Are the blocking edges real? Should any workstreams be merged or split? Are the decisions acceptable? Never raise a concern the plan does not support.

Use only the sections above.

## Regenerating it after a Fix round

Answers, design corrections, and validation can change the plan before dispatch. Someone who already read the human version needs an explicit change notice. Do not regenerate it silently.

Rewrite the file and put this **first, above the title**:

```markdown
## Changes since you last read this

- <what changed, in one line, newest first> — <why: the answer, the finding, the validator row>
```

Put the latest change first. Preserve every earlier entry. This list records the file's history. If the plan did not change, do not regenerate the file or add a "none" notice.

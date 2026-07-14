# AI Structured Plan

Status: Experimental / Deterministic Fake Only

`AIActionPlan` is the normalized provider-neutral plan used by the AI Adapter.
It is not a Runtime entity and is not executable by itself.

## Contracts

The adapter-layer contracts are:

- `AIActionPlan`
- `AIActionStep`
- `AIClarification`
- `AIRefusal`
- `AIConfirmationState`
- `AIPlanExecutionSummary`

`AIActionPlan.kind` may be:

- `execute`
- `clarify`
- `refuse`

## Execution Plans

An executable plan contains one to five ordered `AIActionStep` values.

Each step contains exactly one canonical JarvisOS command text string, such as:

```text
device read lamp_1 status.read
```

or:

```text
device apply lamp_1 power.switch state=true
```

The Planner remains the only component that creates `Command`.

## Safety Rules

Command text is rejected if it contains:

- multiple newline-separated commands;
- shell separators;
- pipes;
- redirects;
- comments used for instruction smuggling;
- Python snippets;
- URLs;
- filesystem paths;
- scheduler or background execution syntax.

## Confirmation

Mutations require explicit confirmation. Read-only plans may execute without
confirmation only after deterministic validation proves every step is read-only.

Confirmation is bound to the exact normalized plan digest. A modified plan must
be confirmed again.

## Execution Policy

Execution is:

- bounded;
- sequential;
- visible before confirmation;
- stopped on first failure.

There is no rollback, transaction guarantee, retry, loop, recursion, background
execution, automatic replanning, or hidden continuation.

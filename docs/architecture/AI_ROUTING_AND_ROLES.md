# AI Roles And Routing

Status: Proposed / Architectural Guidance - Not Implementation

This document describes how JarvisOS should use multiple AI roles instead of
depending on one general-purpose planner model. It is architecture guidance for
future gates. It does not change Runtime, Planner, Drivers or any product code.

---

## 1. Core Principle

AI models are untrusted specialists.

JarvisOS remains the authority for policy, safety, validation, and execution.
AI output is interpreted, validated, and bounded data. It is never authority.

This follows the existing invariant from the AI Provider Strategy ADR:
provider output is never trusted as executable authority. AIActionPlan
validation, policy, confirmation, Planner parsing and Runtime ownership remain
authoritative.

---

## 2. Proposed Roles

AI work is divided into narrow roles. A role is a bounded task with its own
input contract, output contract, and evaluation gate.

- **Intent classification**
  Determine what kind of response is required (e.g., action, clarification,
  refusal, conversation). Output is a small bounded set of intents.

- **Entity / device / capability extraction**
  Map requests onto known devices, capabilities, and semantic operations.
  Output must reference known catalog entries only.

- **Planner / reasoner**
  Produce a provider-neutral AIActionPlan (execute/clarify/refuse) with
  canonical command text. The Planner remains the only component that creates
  Runtime Command objects.

- **Context summarizer**
  Compress conversation or device context into a bounded, safe summary for
  later understanding/planning steps. Never a source of truth for state.

- **Optional vision understanding**
  Interpret visual input when a future vision phase is approved. Output feeds
  understanding, never execution.

- **STT / TTS**
  Speech-to-text and text-to-speech are separate subsystems, not planner roles.
  They do not produce plans and do not route Requests.

---

## 3. Deterministic Boundaries

- Model output never directly executes actions.
- Runtime and Drivers remain outside AI providers.
- Policy and safety remain deterministic and AI-free.
- Python validation (normalize / validate_plan_shape) remains authoritative
  for AIActionPlan acceptance.
- Unsupported or ambiguous requests are resolved deterministically where
  possible, without requiring a model rerun.

These boundaries are the existing JarvisOS boundaries. This document does not
relax them.

---

## 4. Routing Concept

```
User request
  -> understanding role(s)          (intent classification, entity/device/capability extraction)
  -> deterministic context/policy layer
  -> optional planner/reasoner
  -> validation
  -> Runtime
```

Not every request passes through every role. Simple, unambiguous requests may
resolve early through the deterministic layer. The planner is optional per
request; validation is never optional.

---

## 5. Model-Per-Role Philosophy

A model can be approved for one role and rejected for another.

Approval is per (model, role, contract) combination, not per model in general.
Evidence from one role does not transfer to another role. A small model may be
excellent for intent classification and unacceptable as a planner. A planner
model may be unnecessary as a classifier.

There is no single mandatory universal model.

---

## 6. Current Evidence

Recorded from the validated Android Gemma bridge (Gate 2B) and the structured
planning evaluation (Gate 2C).

Gemma 3 1B:
- Android local inference: passed.
- Real bridge (`POST /generate` through the companion, LiteRT-LM): passed.
- General structured planner: rejected.

Known failure modes:
- **Example anchoring**: one-shot prompts with examples anchored the model to
  the first example (all `execute` or all `clarify`).
- **Structure loss without examples**: one-shot prompts without examples lost
  the AIActionPlan structure and emitted irrelevant or context-derived JSON.
- **Unreliable two-stage kind classification**: separate classification
  mislabeled `spanish_simple_read` as `refuse` and `ambiguous_device_clarify`
  as `execute`.

Conclusion: Prompt tuning of Gemma 3 1B as a JarvisOS planner is closed. The
validated bridge infrastructure is retained for future model evaluation.

---

## 7. Evaluation Gates

Each candidate (model, role) combination must pass an explicit gate before it
is considered approved.

- **Fixed fixtures**
  A fixed, frozen set of fixtures covering the role contract across supported
  languages (Spanish and English for current scope). Fixtures do not change to
  accommodate model failures.

- **Correctness before latency optimization**
  Semantic correctness is the acceptance criterion. Latency may be reported but
  is not a pass criterion until correctness passes.

- **No benchmark adaptation to model failures**
  Prompts, fixtures, or contracts must not be tuned until a failing model
  passes. A model that cannot meet the contract is rejected, not retrained into
  the contract by prompt adjustment.

- **Stop conditions**
  Each gate defines explicit failure conditions before work starts (e.g.,
  rejected on N fixtures, structure loss, example anchoring, unreliable kind
  classification). When a stop condition is met, evaluation ends and the
  candidate is not approved.

- **Physical-device validation when relevant**
  On-device and local-Runtime work requires physical or deterministic-real
  validation when hardware is available. Do not fabricate validation evidence.

---

## 8. Near-Term Model Evaluation Plan

Initial (model, role) candidate assignments for future gates. Each remains
hypothetical until its own gate passes.

- **Gemma 3n E2B**: candidate for full planner role.
- **FunctionGemma 270M**: candidate for intent / capability extraction only,
  not planning.
- **Qwen2.5-1.5B-Instruct**: candidate for structured planner role.
- **Qwen2.5-3B-Instruct**: fallback candidate for structured planner role.

These are candidates, not approvals. Each must pass the evaluation gates above
for the named role before adoption. Approved models are not universal; approval
scope is per-role.

---

## 9. Non-Goals

- No AI executes actions.
- No single mandatory universal model.
- No cloud dependency requirement.
- No Runtime redesign in this document.
- No automatic provider fallback or model switching.
- No provider registry or router.
- No change to existing AI boundaries or ADRs.

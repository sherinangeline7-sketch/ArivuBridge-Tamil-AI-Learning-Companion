# DESIGN.md — ArivuBridge: Tamil AI Learning Companion

> Architecture, Strands blocks used, and what is measured.

---

## Overview

ArivuBridge is a bilingual CS tutor built with the Strands Agents SDK on Amazon Bedrock. It routes every student message through two paths depending on intent:

- **Explain path**: a Planner → Critic graph that produces a language-correct, citation-backed concept explanation with step-by-step breakdown.
- **Quiz path**: a Quiz Generator → Answer Evaluator graph that creates a topic quiz, takes the student's answer, and returns constructive feedback.

Both paths are guarded by the same safety hook. Neither path lets the model write a safety-critical response; those are always pre-written and returned directly by code.

---

## Architecture diagram

```
Student input (Tamil / English / mixed)
        │
        ▼
┌──────────────────────────────────┐
│  Safety Hook  (BeforeNodeCall)   │  ← Block 6: Hooks
│  Red-flag phrases (ta + en)      │
│  Out-of-scope detector           │
│  → cancels graph, returns        │
│    fixed HANDOFF text (code)     │
└──────────────────────────────────┘
        │  (no red flag)
        ▼
  Route by intent
  ┌────────────┬───────────────┐
  │  EXPLAIN   │     QUIZ      │
  │   path     │     path      │
  └────┬───────┴────┬──────────┘
       │             │
       ▼             ▼
  ┌─────────┐   ┌──────────────┐
  │ Planner │   │ Quiz         │   ← Block 4: Agents-as-tools
  │ Agent   │   │ Generator    │     (QuizAgent called by Tutor)
  └────┬────┘   └──────┬───────┘
       │               │
       ▼               ▼
  ┌─────────┐   ┌──────────────┐
  │ Critic  │   │ Answer       │   ← Block 3: Graph
  │ Agent   │   │ Evaluator    │     (multi-node with condition edge)
  └────┬────┘   └──────┬───────┘
       │ (ok=false      │
       │  → retry ≤2)   │
       ▼               ▼
  Structured       Structured
  ExplainAnswer    EvalAnswer
        │               │
        └───────┬───────┘
                ▼
         Session tracker
         (weak topics list)     ← Block 7: Sessions (in-memory state)
                │
                ▼
         Student response
```

---

## Strands blocks used

### Block 1 — Tools (`@tool`)
**File:** `agent/tools.py`

- `lookup_guidance(topic)` — searches `agent/data/guidance.json` for matching CS concept summaries. The model must call this before answering; it can only cite IDs this tool returns.
- `language_of(text)` — detects Tamil script (Unicode range U+0B80–U+0BFF) to auto-select response language.
- `get_weak_topics(session_id)` — returns topics where the student scored 0 or needed a retry, from in-session state.

**Why it earns its place:** the guidance tool is the gatekeeper that prevents hallucinated facts. The model cannot invent a CS concept definition — it can only cite what the tool returns.

---

### Block 3 — Graph (multi-agent with condition edge)
**File:** `agent/app.py`

Two graphs:

**Explain graph:**
```
Planner → Critic → (ok=false ∧ passes < 2) → Planner
                 → (ok=true) → done
```
- Planner produces `ExplainAnswer` (language, answer, steps, citations).
- Critic checks: right language? citations valid? no unsupported claims? empty answer?
- Max 2 replanning passes, then the last answer is used regardless.

**Quiz graph:**
```
QuizGenerator → AnswerEvaluator → done
```
- QuizGenerator produces a `QuizAnswer` (question, options, correct_id, explanation).
- AnswerEvaluator takes the student's choice and returns `EvalAnswer` (correct, feedback, retry_suggested).

**Why it earns its place:** the Critic catches language drift (e.g. Planner answers in English when Tamil was requested) and citation violations before the student sees the output. This is verifiable quality control, not just a retry.

---

### Block 4 — Agents as tools
**File:** `agent/app.py`

The top-level **Tutor Agent** exposes `QuizAgent` as a callable tool:

```python
@tool
def generate_quiz(topic: str, difficulty: str, lang: str) -> dict:
    """Run the quiz sub-graph and return a question with options."""
    ...
```

The Tutor decides whether the student wants an explanation or a quiz based on their message, then calls the appropriate path. The QuizAgent is not in the main graph — it is a composable unit the Tutor invokes.

**Why it earns its place:** separating quiz generation from explanation keeps each agent's system prompt and output schema focused. The Tutor orchestrates; it does not do everything itself.

---

### Block 6 — Hooks
**File:** `agent/app.py` — `class SafetyGate(HookProvider)`

Fires on `BeforeNodeCallEvent` for every node in every graph.

Two checks:
1. **Red-flag phrase list** — exact phrases in Tamil and English that indicate the student is in distress, asking for assignment cheating, or requesting exam leak material. Triggers a hard cancel and returns pre-written `HANDOFF` text. Code writes this text; the model never sees the request.
2. **Out-of-scope subject detector** — if the topic is clearly outside the 7 CS subjects (e.g. chemistry, medical advice, civil engineering), the hook cancels and returns a scoped refusal message.

The phrase list includes Tamil-script variants of every English trigger phrase.

**Why it earns its place:** this is the `ship-method.md` hard stop — "A hard stop when someone is in danger. A Strands hook or intervention stops the agents and sends fixed text. No model writes that answer." For ArivuBridge the danger is subtler (academic dishonesty, distress signals) but the principle is identical.

---

### Block 7 — Sessions (in-memory state)
**File:** `agent/tools.py` + `agent/app.py`

A lightweight in-session dict keyed by `session_id` tracks:
- Topics explained this session.
- Quiz scores per topic (correct / incorrect / retried).
- Weak topic list (score = 0 or retry needed).

At session end, the Tutor reads this state and produces a short "what to revisit" summary before closing.

**Why it earns its place:** this is what makes ArivuBridge a tutor rather than a search engine. Without memory of the session's performance, there is no personalised feedback — just disconnected answers.

---

## What code owns (never the model)

Following `ship-method.md` rule 1 — facts that must never be wrong live in code:

| Fact | Where |
|---|---|
| Red-flag phrase list (ta + en) | `RED_FLAGS` constant in `app.py` |
| HANDOFF messages (ta + en) | `HANDOFF` dict in `app.py` — pre-written, not generated |
| Out-of-scope subject list | `OUT_OF_SCOPE_SUBJECTS` constant in `app.py` |
| All CS concept definitions | `agent/data/guidance.json` — curated, dated, source-linked |
| Scoring logic | `agent/score.py` — deterministic, no model involved |

---

## Structured output schemas

### `ExplainAnswer` (extends `plan.py:Answer`)
| Field | Type | Description |
|---|---|---|
| `language` | `"en" \| "ta" \| "bilingual"` | Language of the response |
| `answer` | `str` | Main explanation in the student's language |
| `steps` | `list[str]` | Step-by-step breakdown (≥ 2 steps) |
| `example` | `str` | A concrete real-world example |
| `escalation` | `str` | When to ask a human teacher |
| `citations` | `list[str]` | Guidance IDs from `lookup_guidance` |
| `weak_flag` | `bool` | True if this topic should be added to weak list |

### `QuizAnswer`
| Field | Type | Description |
|---|---|---|
| `language` | `"en" \| "ta"` | Language of the question |
| `question` | `str` | The quiz question |
| `options` | `list[str]` | 4 options (MCQ) |
| `correct_id` | `int` | 0-indexed correct option |
| `explanation` | `str` | Why the correct answer is correct |
| `topic_id` | `str` | Guidance ID this question tests |

### `EvalAnswer`
| Field | Type | Description |
|---|---|---|
| `language` | `"en" \| "ta"` | Language of feedback |
| `correct` | `bool` | Whether the student got it right |
| `feedback` | `str` | Constructive feedback in their language |
| `retry_suggested` | `bool` | True if a second attempt would help |
| `weak_flag` | `bool` | True if this topic should be flagged |

---

## What is measured (`ss measure`)

Following `ship-method.md` rule 4 — the agent must be measured against a one-prompt baseline on human-labelled cases.

### Case categories (to be filled in `cases.jsonl`)

| Category | Count | Description |
|---|---|---|
| Concept explanation — English | 5 | Student asks a CS concept in English; expected: correct English explanation with citations |
| Concept explanation — Tamil | 5 | Student asks in Tamil script; expected: Tamil explanation with citations |
| Bilingual request | 3 | Student mixes Tamil and English; expected: bilingual or Tamil response |
| Quiz request | 4 | Student asks for a quiz; expected: QuizAnswer with valid topic_id |
| Red-flag — academic dishonesty | 3 | Student asks for exam answers or assignment solution; expected: escalation = "handoff" |
| Red-flag — distress | 2 | Student expresses distress; expected: escalation = "handoff" |
| Out-of-scope subject | 2 | Student asks about chemistry/medicine; expected: scoped refusal |

### Score labels (in `agent/score.py`)

| Label | Measures |
|---|---|
| `risk_correct` | Key facts present from `must_include` list |
| `escalated` | Handoff cases correctly handed off (not answered by model) |
| `lang_correct` | Response language matches requested language |
| `citations_valid` | All cited IDs exist in `guidance.json` |
| `complete` | All required output fields populated |

### Gate condition

`ss measure` must show:
- Agent safe on **100%** of red-flag cases (escalated = true, model wrote nothing).
- Agent `risk_correct` > baseline on concept explanation cases.
- Agent `lang_correct` ≥ 95% (Tamil when asked, English when asked).

---

## Files to edit (next steps)

| File | What to do |
|---|---|
| `agent/app.py` | Update `GOAL`, `RED_FLAGS`, `HANDOFF`, add out-of-scope check, add Quiz graph, add session tracker |
| `agent/plan.py` | Replace `Answer` with `ExplainAnswer`; add `QuizAnswer`, `EvalAnswer` |
| `agent/tools.py` | Add `generate_quiz`, `evaluate_answer`, `get_weak_topics` tools |
| `agent/score.py` | Add `lang_correct` metric; update `HANDOFF_MARKERS` for CS context |
| `agent/data/guidance.json` | Replace example items with real curated CS concept summaries (7 subjects, ≥ 3 items each) |
| `cases.jsonl` | Replace example cases with the 24 cases described above |
| `video.json` | Update title, subtitle, scenes with ArivuBridge-specific demo prompts |
| `FAILURES.md` | Log each real failure found during `ss measure` |

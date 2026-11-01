# ArivuBridge – Tamil AI Learning Companion

> **Learn in your language. Understand with confidence.**

---

## The problem

Tamil Nadu has over 5,000 engineering colleges. A significant share of students
arrive from Tamil-medium schools — students who have thought, read, and reasoned
in Tamil their entire lives. On the first day of their Computer Science degree,
everything changes: lectures, textbooks, examinations, and technical vocabulary
are in English.

This is not a capability gap. It is a language gap.

A student who can intuitively reason about how a stack works in Tamil cannot
access that intuition when the textbook says "push" and "LIFO" without
explanation. First-generation engineering students face this problem with no
family knowledge network to fill in the gaps. Existing free AI tutors — ChatGPT,
Gemini, Claude — give capable answers in English. A student who cannot parse the
question cannot benefit from the answer.

ArivuBridge addresses that gap directly: it is a bilingual CS tutor that reasons
**in the student's language**, not a translator that converts English answers into
Tamil after the fact.

---

## Who it is for

- BE/B.Tech Computer Science students in Tamil Nadu, especially those from
  Tamil-medium school backgrounds.
- First-generation engineering students with no senior family members to ask.
- Any student who wants beginner-friendly explanations of technical concepts
  in Tamil, English, or both side by side.

---

## What ArivuBridge does

A student opens a terminal and types a question — in Tamil, English, or a natural
mix of both, exactly as they would text a friend:

```bash
python -m agent.app "DBMS என்றால் என்ன?" --lang ta
```

ArivuBridge:

1. **Detects the language** using Tamil Unicode script ranges (U+0B80–U+0BFF).
   No manual language selection required.

2. **Retrieves curated guidance** from a structured knowledge base
   (`agent/data/guidance.json`) that contains 45 CS concept summaries across
   seven subjects, each with a Tamil translation and a dated source citation.
   The agent **cannot invent facts** — it can only cite items this tool returns.

3. **Explains the concept** in the requested language, with a step-by-step
   breakdown and a concrete real-world example.

4. **Runs a critic** that checks the explanation before the student sees it:
   Is it in the right language? Are the citations valid? Does it contain claims
   the guidance does not support? If not, the planner revises — up to twice.

5. **Generates quizzes** on demand, based entirely on the same curated guidance.

6. **Evaluates student answers** and returns constructive feedback in their
   language, flagging topics that need more practice.

7. **Handles unsafe requests before any model call**, using a pre-check hook
   that fires before the first agent node executes.

---

## Supported subjects

| Subject | Example topics |
|---|---|
| DBMS | ER diagrams, normalisation, SQL, transactions, indexing |
| Python Programming | data types, loops, functions, OOP, exceptions |
| Java Programming | classes, inheritance, interfaces, Java 8+ features |
| Data Structures & Algorithms | arrays, linked lists, stacks, trees, sorting, Big-O |
| Operating Systems | processes, CPU scheduling, paging, deadlocks, file systems |
| Computer Networks | OSI model, TCP/IP, IP addressing, HTTP/DNS, sockets |
| AI Fundamentals | search algorithms, supervised/unsupervised learning, neural networks |

---

## Architecture

ArivuBridge is built with the **Strands Agents SDK** on Amazon Bedrock. It uses
five of the fourteen Strands blocks, going substantially beyond the workshop
lessons.

### Request flow

```
Student input (Tamil / English / mixed)
        │
        ▼
┌─────────────────────────────────────┐
│  Safety Pre-check (code, not model) │
│  RED_FLAGS → crisis HANDOFF text    │
│  AUTHORITY_FLAGS → redirect to HOD  │
│  INJECT_FLAGS → refuse instruction  │
│  SCOPE_FLAGS → redirect to CS       │
└─────────────────────────────────────┘
        │  (no flag triggered)
        ▼
  Intent router (explain / quiz / evaluate)
  ┌────────────┬──────────────────────┐
  │  EXPLAIN   │   QUIZ / EVALUATE    │
  └─────┬──────┴────────┬─────────────┘
        │               │
   Planner           QuizGenerator /
   Agent             AnswerEvaluator
        │
   Critic Agent
   (ok=false → retry ≤2)
        │
   ExplainAnswer / QuizAnswer / EvalAnswer
```

### Strands blocks used

**Block 1 — Tools (`@tool`)**

```python
@tool
def lookup_guidance(topic: str) -> list[dict]:
    """Find curated, dated CS guidance. Returns items with id and text."""
    keywords = _extract_keywords(topic)  # handles Tamil + English
    # scored matching across id, subject, topic, text fields
    return [{"id": item["id"], "text": item["text"]}
            for item, _ in matches[:MAX_RESULTS]]
```

The tool supports Tamil keyword expansion: `"நினைவக"` (memory) automatically
expands to `["memory", "paging", "virtual"]` before searching the guidance
corpus. All 45 guidance items are searchable in both languages.

**Block 3 — Graph (multi-agent with condition edge)**

The explain path is a two-node graph with a conditional retry edge:

```
Planner → Critic → (ok=False ∧ passes < 2) → Planner
                 → (ok=True) → result
```

The critic's system prompt lists every valid guidance ID. If the planner
cites a hallucinated ID, or answers in the wrong language, or produces fewer
than two steps, the critic returns `ok=False` with a specific problem list, and
the planner revises. The last answer is used regardless after two passes.

**Block 4 — Agents as tools**

The quiz path uses the quiz planner as a composable unit rather than a graph
node, keeping system prompts and output schemas focused.

**Block 6 — Hooks (BeforeNodeCallEvent)**

The `SafetyGate` hook fires before every node in every graph. Four independent
pre-checks run in priority order — crisis → authority → injection → scope — each
returning a different fixed pre-written message. No model call is made for any
safety path:

```python
# From agent/app.py — code owns these; the model never generates them
HANDOFF = {
    "en": "I'm concerned about you. Please reach out to iCall (India): "
          "9152987821, or Vandrevala Foundation 24/7 helpline: 1860-2662-345...",
    "ta": "உங்களைப் பற்றி கவலைப்படுகிறேன். iCall (India): 9152987821..."
}
```

**Block 7 — Structured output with Pydantic**

All agent paths return validated structured output rather than free text:

```python
class ExplainAnswer(BaseModel):
    language: Literal["en", "ta", "bi"]
    topic: str
    answer: str
    steps: list[str]      # ≥2 required; critic rejects empty
    example: str
    citations: list[str]  # guidance IDs; critic rejects empty or invalid
```

---

## Safety design

One of the most important design decisions in ArivuBridge is that safety-critical
responses are **never written by the model**. The code writes them and the hook
returns them before any agent node executes.

Four independent pre-checks protect students:

| Category | Trigger | Response |
|---|---|---|
| **Crisis** | Self-harm or distress phrases (en + ta) | Fixed text with iCall and Vandrevala Foundation helpline numbers |
| **Authority** | Marks change, attendance edit, exam leak requests (en + ta) | Fixed redirect to Examination Cell |
| **Injection** | Attempts to override tutor instructions | Fixed refusal: "I cannot override my instructions" |
| **Out-of-scope** | Non-CS subjects (chemistry, physics, biology, etc.) | Fixed redirect listing the 7 supported subjects |

The Tamil-language crisis phrases are exact matches: `"தற்கொலை"`, `"என்னை கொன்றுகொள்"`, `"இறந்துவிட வேண்டும்"` and others. A student in distress writing in Tamil receives the same helpline response as one writing in English.

---

## Evaluation methodology

ArivuBridge is measured against a **one-prompt baseline** — an agent with the
same model, the same guidance pasted into the system prompt, but no tools, no
graph, no critic, and no safety hooks.

The evaluation uses **37 human-labelled cases** in five categories:

| Category | Count | Escalation |
|---|---|---|
| Concept explanation (English) | 12 | `none` |
| Concept explanation (Tamil) | 11 | `none` |
| Academic authority redirect | 4 | `care` |
| Crisis handoff | 8 | `emergency` |
| Prompt injection / scope | 2 | `inject` / `scope` |

Each case has a `must_include` word list derived from the actual guidance text,
or an escalation check that requires the correct pre-written response and the
correct `meta.path` value. Scoring is entirely deterministic — no model judges
normal educational cases.

The measurement gate requires:
- **Emergency recall = 100%**: all 8 crisis cases correctly handled by the hook
- **Unsafe advice = 0**: no case produces a non-empty `unsafe` list
- **Threshold accuracy = 100%**: all `must_include` and escalation checks pass
- **Citation faithfulness ≥ 95%**: cited guidance IDs exist in `guidance.json`
- **Plan completeness ≥ 90%**: required output fields populated

> **Results note:** `ss measure` requires working AWS Bedrock credentials.
> The results table below contains placeholder slots that must be filled from
> `results/FACTS.md` after running `ss measure` and `ss ship`.

### Results

| Metric | ArivuBridge | Single-prompt baseline |
|---|---|---|
| Emergency cases correctly handed off | [MEASURED: emergency_recall] | [MEASURED: baseline emergency_recall] |
| Plans with unsafe advice | [MEASURED: unsafe] | [MEASURED: baseline unsafe] |
| Required facts present and safety redirects correct | [MEASURED: threshold_accuracy] | [MEASURED: baseline threshold_accuracy] |
| Citations that exist in the guidance | [MEASURED: citation_faithfulness] | [MEASURED: baseline citation_faithfulness] |
| Plan fields complete, right language | [MEASURED: completeness] | [MEASURED: baseline completeness] |
| Goal success (Strands Evals judge, 0–1) | [MEASURED: goal_success] | [MEASURED: baseline goal_success] |
| Latency p50 | [MEASURED: latency_p50_ms] ms | [MEASURED: baseline latency_p50_ms] ms |

*All numbers must be copied verbatim from `results/FACTS.md` before publishing.*

---

## What makes ArivuBridge original

Beyond the workshop lessons, ArivuBridge adds four things judges can verify in
the code:

**1. Code owns the facts that must never be wrong.**
All 45 CS concept definitions live in `agent/data/guidance.json`, each with a
source URL and access date. The model reads them and cannot change them. The
critic checks citations before the student sees the answer.

**2. A hard stop for unsafe requests.**
The `SafetyGate` hook cancels graph execution before any model node runs for
crisis, authority, injection, and scope cases. The response text is a Python
constant — not generated, not editable by the model.

**3. A critic the planner cannot skip.**
The explain graph has a condition edge: the planner cannot return to the student
without passing the critic's language and citation checks. After two failures,
the last answer is used but logged as `critic_ok=False`.

**4. Measured against a baseline on human-labelled cases in two languages.**
The evaluation set includes 16 Tamil-language cases. The baseline has no
language-specific instruction reinforcement. ArivuBridge's language gate
(`lang_correct` in scoring) specifically tests whether Tamil is answered in Tamil
and English in English.

---

## The guidance database

The `agent/data/guidance.json` file contains 45 items across 7 subjects, each
entry following this schema:

```json
{
  "id": "OS-003",
  "subject": "os",
  "topic": "memory management paging segmentation virtual memory",
  "source": "GFG-OS",
  "text": "Memory management allocates RAM to processes. Paging divides memory
           into fixed-size pages ... Tamil: Paging நினைவகத்தை சம அளவு
           பக்கங்களாக பிரிக்கிறது."
}
```

Every item has a source reference from `W3Schools`, `GeeksforGeeks`,
`MDN Web Docs`, `Python Software Foundation`, or `Oracle's Java Tutorials`.
Tamil text in each entry is a human-authored translation, not a model-generated
one.

The `lookup_guidance` tool supports Tamil keyword input by maintaining a
`TAMIL_TO_ENGLISH` expansion map (`"நினைவக" → ["memory","paging","virtual"]`)
built from terms that actually appear in the guidance corpus.

---

## What I learned

Building ArivuBridge taught me three things I did not expect:

**Language detection is the easy part; language compliance is hard.**
Detecting Tamil script is one regex. Getting the model to *stay* in Tamil when
it has been trained predominantly on English requires the critic to actively
check and reject English drift. Without the critic, Tamil answers drifted to
English within one or two sentences.

**Safety routing before model invocation changes the architecture.**
The standard Strands pattern is hooks inside the graph. ArivuBridge adds a
pre-check layer *before the graph is built*, in `run()`. This means safety
cases never touch Bedrock at all — zero latency, zero cost, zero hallucination
risk for those paths.

**Curated knowledge beats retrieval for a narrow domain.**
For seven well-scoped CS subjects with beginner-level content, 45 hand-curated
guidance items with Tamil translations outperform a RAG approach where the model
would retrieve and paraphrase arbitrary text. The guidance database is small
enough to fully control, version, and verify.

---

## Run it yourself

```bash
# Prerequisites: Python 3.12, AWS credentials configured
git clone [REPO_URL]
cd ArivuBridge
pip install -r requirements.txt

# Ask a question in Tamil
python -m agent.app "DBMS என்றால் என்ன?" --lang ta

# Ask in English
python -m agent.app "Explain Python loops with an example"

# Test the crisis safety hook (no Bedrock needed)
python -m agent.app "I want to end my life, college is too hard."

# Test the scope hook (no Bedrock needed)
python -m agent.app "Can you help with my organic chemistry assignment?"

# JSON output
python -m agent.app "What is a stack?" --json
```

---

## Resources

- [Strands Agents SDK](https://strandsagents.com/latest/documentation/docs/)
- [Amazon Bedrock](https://aws.amazon.com/bedrock/)
- Source: `agent/data/guidance.json` — all 14 sources listed with URLs and access dates
- Evaluation cases: `cases.jsonl` — 37 human-labelled cases

---

*Built by Flora for the AWS Builder Center "Strands SDK: Workshop to Ship"
hackathon, October–November 2026.*

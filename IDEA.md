# IDEA.md — ArivuBridge: Tamil AI Learning Companion

> Learn in your language. Understand with confidence.

---

## The problem

Tamil-medium and first-generation engineering students in Tamil Nadu face a specific and largely invisible barrier in higher education: their Computer Science subjects are taught and examined in English, but their entire schooling was in Tamil. They understand the idea — they just cannot unlock it through the language it is packaged in.

A student who can intuitively reason about sorting or memory management in Tamil cannot access that intuition when the textbook says "heapsort" or "virtual memory". They fall back on rote memorisation without real understanding, fail to build on concepts, and lose confidence early.

This is not a capability gap. It is a language gap. And it is measurable:

- Tamil Nadu has over 5,000 government and aided engineering colleges. A significant share of students enter through Tamil-medium schools.
- First-generation college students have no family knowledge network to fill in conceptual gaps.
- Existing free AI tutors (ChatGPT, Gemini) give capable answers — but in natural English. A student who struggles to read the question cannot benefit from the answer.

---

## Who it is for

- **BE/B.Tech Computer Science students** studying in Tamil Nadu.
- **Tamil-medium background students** who think naturally in Tamil but study in English-medium colleges.
- **First-generation engineering students** who have no senior family members to ask.
- **Students who need beginner-friendly pacing** — not advanced explanations, but clear, correct ones in a language they own.

---

## What the agent does

ArivuBridge acts as a patient bilingual CS tutor available at any hour. A student types a question in Tamil, English, or a mix — the way they actually write on their phone — and the agent:

1. **Explains the concept** in simple Tamil, plain English, or bilingual side-by-side, based on what the student chose or the language they wrote in.
2. **Breaks down the explanation step by step**, using short sentences and a concrete example from everyday Tamil life where possible.
3. **Generates a short quiz** on the same topic so the student can test whether they understood.
4. **Evaluates their answer** and explains mistakes constructively, in their language, without scolding.
5. **Tracks weak topics** within the session and surfaces them at the end so the student knows what to revisit.
6. **Recommends the next concept** to strengthen understanding — moving forward only when the current concept is solid.

When a student asks something that falls outside the safe scope of an AI tutor (e.g. exam question leaks, personal distress, requests to write assignments for submission), the agent immediately hands off with a clear human-readable message rather than attempting to answer.

---

## Subject scope (version 1)

Computer Science and Engineering subjects only:

| Subject | Example topics |
|---|---|
| DBMS | ER diagrams, normalisation, SQL queries, transactions |
| Python Programming | data types, loops, functions, OOP basics, file handling |
| Java Programming | classes, inheritance, interfaces, exceptions |
| Data Structures & Algorithms | arrays, linked lists, stacks, trees, sorting, complexity |
| Operating Systems | processes, scheduling, memory management, deadlocks |
| Computer Networks | OSI model, TCP/IP, routing, HTTP, DNS |
| AI Fundamentals | search algorithms, knowledge representation, ML basics |

---

## Social good dimension

This fits the hackathon's **education** track. The underserved population is specific and reachable:

- Tamil-medium engineering students are a large cohort with a documented language-barrier disadvantage in technical education.
- The intervention is measurable: does the student understand the concept well enough to answer a quiz correctly after the explanation? A one-prompt English-only baseline does not serve this population. ArivuBridge does.
- The improvement is not marginal — for a student who cannot parse an English explanation at all, a clear Tamil explanation is the difference between understanding and memorisation.

---

## What makes this original

- **Bilingual structured output**: the agent reasons in the student's language, not just translates an English answer.
- **Tamil red-flag safety**: out-of-scope requests are caught in both Tamil and English by a hook that runs before any model node executes.
- **Critic in the loop**: a separate critic agent verifies the explanation is in the right language, uses only curated content, and does not introduce hallucinated facts — before the student sees it.
- **Quiz-then-evaluate loop**: the agent's second mode (quiz generation + answer evaluation) is a distinct graph path, not a general chat fallback.
- **Curated CS guidance**: all factual content comes from `agent/data/guidance.json`, a curated set of CS concept summaries the model must cite and cannot invent beyond.

---

## Builder

**Flora** — built for the AWS Builder Center "Strands SDK: Workshop to Ship" hackathon, October 2026.

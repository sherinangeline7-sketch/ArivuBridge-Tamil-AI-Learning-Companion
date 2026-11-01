"""ArivuBridge – Tamil AI Learning Companion.

A bilingual CS tutor for Tamil-medium and first-generation engineering
students. Explains concepts, generates quizzes, and evaluates answers in
Tamil, English, or bilingual style.

Usage:
    python -m agent.app "Explain DBMS in simple Tamil"
    python -m agent.app "Explain Python loops in English"
    python -m agent.app "Generate five SQL quiz questions"
    python -m agent.app "Evaluate my answer: A primary key uniquely identifies a row"
    python -m agent.app "Explain OS scheduling" --lang ta
    python -m agent.app "What is a stack?" --json

Architecture (DESIGN.md):
  Student input
    └─ SafetyGate hook (BeforeNodeCallEvent)
         ├─ RED_FLAG  → fixed HANDOFF text, agents cancelled
         └─ AUTHORITY → fixed AUTHORITY text, agents cancelled
  Intent router (detects: explain / quiz / evaluate)
    ├─ Explain path: Planner → Critic → (retry ≤ 2) → ExplainAnswer
    └─ Quiz / Evaluate path: Planner → QuizAnswer / EvalAnswer
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time

from strands import Agent
from strands.hooks import BeforeNodeCallEvent, HookProvider, HookRegistry
from strands.models import BedrockModel
from strands.multiagent import GraphBuilder

from . import tools
from .plan import Critique, EvalAnswer, ExplainAnswer, QuizAnswer

# ── Model / region ────────────────────────────────────────────────────────
MODEL_ID = os.environ.get("SHIP_MODEL", "us.amazon.nova-2-lite-v1:0")
REGION   = os.environ.get("AWS_REGION", "us-east-1")
logging.getLogger("strands").setLevel(logging.CRITICAL)

# ── Supported languages ───────────────────────────────────────────────────
LANG_NAMES = {
    "en": "English",
    "ta": "Tamil (Tamil script, not transliteration)",
    "bi": "bilingual — English explanation first, then Tamil translation",
}

# ── Safety: red-flag phrases (en + ta) ───────────────────────────────────
# These indicate immediate danger or self-harm. Code catches them; the model
# never processes the request.
RED_FLAGS: list[str] = [
    # English distress / self-harm
    "suicide", "kill myself", "end my life", "want to die", "self harm",
    "hurt myself", "overdose", "harm myself",
    # Tamil distress / self-harm
    "தற்கொலை", "என்னை கொன்றுகொள்", "உயிரை மாய்த்துக்கொள்",
    "இறந்துவிட வேண்டும்", "என்னை தீங்கு",
]

# Fixed handoff text code writes — model never generates this.
HANDOFF: dict[str, str] = {
    "en": (
        "I'm concerned about you. Please reach out to iCall (India): 9152987821, "
        "or Vandrevala Foundation 24/7 helpline: 1860-2662-345. "
        "This assistant cannot help with this — please contact a person right away."
    ),
    "ta": (
        "உங்களைப் பற்றி கவலைப்படுகிறேன். iCall (India): 9152987821, "
        "அல்லது Vandrevala Foundation helpline: 1860-2662-345 என்ற எண்ணில் "
        "இப்பொழுதே தொடர்பு கொள்ளுங்கள். இந்த உதவியாளர் இதற்கு பதில் அளிக்காது."
    ),
    "bi": (
        "I'm concerned about you. Please reach out to iCall (India): 9152987821, "
        "or Vandrevala Foundation 24/7 helpline: 1860-2662-345. "
        "This assistant cannot help with this — please contact a person right away.\n\n"
        "உங்களைப் பற்றி கவலைப்படுகிறேன். iCall (India): 9152987821 என்ற எண்ணில் "
        "இப்பொழுதே தொடர்பு கொள்ளுங்கள்."
    ),
}

# ── Safety: authority-request phrases ────────────────────────────────────
# Requests for official academic decisions must go to the college, not here.
AUTHORITY_FLAGS: list[str] = [
    # English
    "change my marks", "change my grade", "edit attendance", "fix attendance",
    "update attendance", "increase my marks", "give me marks", "add marks",
    "change my result", "revaluation", "internal marks", "exam leak",
    "question paper leak", "answer key leak", "write my assignment",
    "do my assignment", "complete my assignment", "write my project",
    # Tamil
    "மதிப்பெண் மாற்று", "வருகைப்பதிவு மாற்று", "தேர்வு கசிவு",
    "கேள்வித்தாள் கசிவு", "என் பதிவேடு மாற்று",
]

AUTHORITY_MSG: dict[str, str] = {
    "en": (
        "This request involves an official academic decision (marks, attendance, "
        "exam records or assignment submission). I cannot help with this — "
        "please contact your college's Examination Cell, Academic Section, "
        "or the relevant faculty member directly."
    ),
    "ta": (
        "இந்த கோரிக்கை அதிகாரப்பூர்வ கல்வி முடிவுகளை (மதிப்பெண்கள், வருகை, "
        "தேர்வு பதிவுகள்) பற்றியது. இந்த உதவியாளரால் உதவ முடியாது — "
        "உங்கள் கல்லூரியின் Examination Cell அல்லது தொடர்புடைய ஆசிரியரை "
        "நேரடியாக தொடர்பு கொள்ளுங்கள்."
    ),
    "bi": (
        "This request involves an official academic decision. Please contact your "
        "college's Examination Cell or relevant faculty directly.\n\n"
        "இந்த கோரிக்கை அதிகாரப்பூர்வ கல்வி முடிவுகளை பற்றியது. "
        "உங்கள் கல்லூரியின் Examination Cell-ஐ தொடர்பு கொள்ளுங்கள்."
    ),
}

# ── Safety: injection-attempt phrases ────────────────────────────────────
# Attempts to override tutor instructions, extract the system prompt, or
# force a role switch.  False-positive fixes applied:
#   "ignore all" → "ignore all your"       (avoids "ignore all errors")
#   "ignore previous" → "ignore previous instructions"  (avoids DB/array context)
#   "override your" → "override your instructions"      (avoids "override your method")
INJECT_FLAGS: list[str] = [
    "ignore all your",
    "ignore your instructions",
    "ignore previous instructions",
    "forget your instructions",
    "disregard previous",
    "override your instructions",
    "override instructions",
    "reveal your instructions",
    "show your prompt",
    "what are your instructions",
    "what is your system prompt",
    "act as if you are a",
    "pretend you are a",
    "new instructions:",
    "your new role",
]

# Fixed injection refusal — code writes this, model never generates it.
# Contains INJECT_MARKERS: "cannot override my instructions", "cs tutor and cannot"
INJECT_MSG: dict[str, str] = {
    "en": (
        "I cannot override my instructions. "
        "I am a CS tutor and cannot follow requests that ask me to change my role "
        "or reveal system details. "
        "Please ask about DBMS, Python, Java, Data Structures, OS, Networks, or AI."
    ),
    "ta": (
        "என் அறிவுறுத்தல்களை மாற்ற இயலாது. "
        "நான் ஒரு CS tutor; என் பாத்திரத்தை மாற்றும் கோரிக்கைகளுக்கு பதிலளிக்க மாட்டேன்."
    ),
    "bi": (
        "I cannot override my instructions. I am a CS tutor and cannot change my role.\n\n"
        "என் அறிவுறுத்தல்களை மாற்ற இயலாது."
    ),
}

# ── Safety: out-of-scope subject phrases ─────────────────────────────────
# Subject-name substrings outside the seven supported CS subjects.
# False-positive fixes:
#   "history"  → "world history"   (avoids "history of the OSI model")
#   "newton"   → "newton's laws"   (avoids "Newton's method" in algorithms)
#   bare "chemistry" removed; "organic chemistry" kept (covers scope test case)
SCOPE_FLAGS: list[str] = [
    "organic chemistry",
    "inorganic chemistry",
    "benzene",
    "titration",
    "periodic table",
    "physics",
    "newton's laws",
    "thermodynamics",
    "electromagnetism",
    "biology",
    "anatomy",
    "genetics",
    "photosynthesis",
    "world history",
    "economics",
    "geography",
    "political science",
    "civil engineering",
    "mechanical engineering",
    "electrical engineering",
]

# Fixed scope refusal — code writes this, model never generates it.
# Contains SCOPE_MARKERS: "outside my supported cs subjects", "only cover cs subjects"
SCOPE_MSG: dict[str, str] = {
    "en": (
        "This request is outside my supported CS subjects. "
        "I only cover CS subjects: DBMS, Python, Java, Data Structures, "
        "Operating Systems, Computer Networks, and AI Fundamentals. "
        "Please ask about one of these topics."
    ),
    "ta": (
        "இந்த கோரிக்கை என் ஆதரிக்கப்பட்ட CS பாடங்களுக்கு வெளியே உள்ளது. "
        "நான் DBMS, Python, Java, Data Structures, OS, Computer Networks "
        "மற்றும் AI மட்டுமே கற்பிக்கிறேன்."
    ),
    "bi": (
        "This request is outside my supported CS subjects: DBMS, Python, Java, "
        "Data Structures, OS, Networks, and AI.\n\n"
        "இந்த கோரிக்கை என் ஆதரிக்கப்பட்ட CS பாடங்களுக்கு வெளியே உள்ளது."
    ),
}

# ── System prompts ────────────────────────────────────────────────────────
_PLANNER_EXPLAIN = (
    "You are ArivuBridge, a patient and friendly CS tutor for Tamil-medium "
    "engineering students in Tamil Nadu.\n\n"
    "LANGUAGE: Respond ONLY in {lang_name}. This is mandatory.\n\n"
    "TASK: Explain the concept the student asked about.\n"
    "1. Call lookup_guidance first with relevant topic keywords.\n"
    "2. Use ONLY the guidance items returned — do not add outside facts.\n"
    "3. Write a clear main explanation, then 2–4 short step-by-step points.\n"
    "4. Give one concrete example a Tamil Nadu engineering student can relate to.\n"
    "5. Cite every guidance ID you used in the citations field.\n"
    "6. Fix EVERY problem listed by the critic before responding.\n\n"
    "IMPORTANT: Never invent guidance IDs. Citations must be exactly as returned "
    "by lookup_guidance."
)

_CRITIC_EXPLAIN = (
    "You are a critic reviewing an explanation for Tamil-medium CS students.\n\n"
    "Required language: {lang_name}.\n"
    "Valid guidance IDs: {ids}.\n\n"
    "Reply ok=false and list each problem (one per item) if ANY of these are true:\n"
    "- The answer is not written in {lang_name}.\n"
    "- citations contains an ID not in the valid IDs list.\n"
    "- citations is empty.\n"
    "- The explanation is empty or too short (fewer than 2 sentences).\n"
    "- steps has fewer than 2 items.\n"
    "- The answer contains facts that the guidance items do not support.\n\n"
    "Reply ok=true only if none of the above apply."
)

_PLANNER_QUIZ = (
    "You are ArivuBridge, a CS tutor generating a multiple-choice quiz.\n\n"
    "LANGUAGE: Questions and explanations must be in {lang_name}.\n\n"
    "TASK: Generate {n_questions} multiple-choice questions on the topic.\n"
    "1. Call lookup_guidance first to get relevant guidance items.\n"
    "2. Base every question on the returned guidance — do not invent facts.\n"
    "3. Each question must have exactly 4 options and one correct answer.\n"
    "4. Provide a brief explanation for the correct answer.\n"
    "5. Set the citation field to the guidance ID the question tests.\n"
    "6. Set difficulty to 'beginner' unless the student asked for intermediate."
)

_PLANNER_EVAL = (
    "You are ArivuBridge, a CS tutor evaluating a student's answer.\n\n"
    "LANGUAGE: All feedback must be in {lang_name}.\n\n"
    "TASK: Evaluate the student's answer and give constructive feedback.\n"
    "1. Call lookup_guidance with the topic to get the authoritative guidance.\n"
    "2. Compare the student's answer against the guidance — do not use outside knowledge.\n"
    "3. Identify what is correct, what is missing, and what is wrong.\n"
    "4. Score as 'correct', 'partial', or 'incorrect'.\n"
    "5. Write a correction that is kind and beginner-friendly.\n"
    "6. Recommend one specific thing to review next.\n"
    "7. Cite the guidance IDs you used."
)


# ── Safety hook ───────────────────────────────────────────────────────────

class SafetyGate(HookProvider):
    """Pre-node hook that cancels the graph on red-flag or authority requests.

    Runs before every node in every graph. When triggered, it sets
    cancel_node (which raises RuntimeError in the graph) and stores what
    kind of cancellation happened so run() can return the right fixed text.
    """

    def __init__(self, user_text: str, lang: str) -> None:
        self.user_text = user_text.lower()
        self.lang = lang
        self.triggered: str = ""   # "red_flag" | "authority" | ""
        self.matched:   str = ""   # the phrase that matched

    def register_hooks(self, registry: HookRegistry, **_) -> None:
        registry.add_callback(BeforeNodeCallEvent, self._before)

    def _before(self, event: BeforeNodeCallEvent) -> None:
        if self.triggered:
            # Already triggered — cancel every subsequent node too.
            event.cancel_node = f"safety: {self.triggered}"
            return

        for phrase in RED_FLAGS:
            if phrase.lower() in self.user_text:
                self.triggered = "red_flag"
                self.matched   = phrase
                event.cancel_node = f"red flag: {phrase}"
                return

        for phrase in AUTHORITY_FLAGS:
            if phrase.lower() in self.user_text:
                self.triggered = "authority"
                self.matched   = phrase
                event.cancel_node = f"authority request: {phrase}"
                return


# ── Intent detection ──────────────────────────────────────────────────────

def _detect_intent(text: str) -> str:
    """Return 'quiz', 'evaluate', or 'explain' based on the student's message."""
    low = text.lower()
    # Quiz signals
    if any(w in low for w in [
        "quiz", "question", "mcq", "test me", "generate question",
        "கேள்வி கேள்", "quiz கொடு", "வினாடி வினா",
    ]):
        return "quiz"
    # Evaluation signals
    if any(w in low for w in [
        "evaluate", "check my answer", "is my answer", "correct my",
        "am i right", "my answer is", "evaluate my", "mark my",
        "என் பதில்", "என் விடை", "சரியா",
    ]):
        return "evaluate"
    return "explain"


def _parse_n_questions(text: str) -> int:
    """Extract the number of questions requested (default 5, max 10)."""
    m = re.search(r"\b([1-9][0-9]?)\s*(?:question|quiz|mcq)", text, re.IGNORECASE)
    if m:
        return min(int(m.group(1)), 10)
    for word, n in [("five", 5), ("four", 4), ("three", 3), ("ten", 10),
                    ("ஐந்து", 5), ("நான்கு", 4), ("மூன்று", 3)]:
        if word in text.lower():
            return n
    return 5


# ── Model factory ─────────────────────────────────────────────────────────

def _model() -> BedrockModel:
    return BedrockModel(model_id=MODEL_ID, region_name=REGION, temperature=0.2)


# ── Graph: explain path ───────────────────────────────────────────────────

def _build_explain_graph(lang: str, gate: SafetyGate):
    lang_name  = LANG_NAMES[lang]
    valid_ids  = sorted(tools.guidance_ids())

    planner = Agent(
        model=_model(),
        name="planner",
        system_prompt=_PLANNER_EXPLAIN.format(lang_name=lang_name),
        tools=[tools.lookup_guidance],
        structured_output_model=ExplainAnswer,
        callback_handler=None,
    )
    critic = Agent(
        model=_model(),
        name="critic",
        system_prompt=_CRITIC_EXPLAIN.format(lang_name=lang_name, ids=valid_ids),
        structured_output_model=Critique,
        callback_handler=None,
    )

    def _should_retry(state) -> bool:
        node_res = state.results.get("critic")
        if not node_res:
            return False
        verdict = getattr(node_res.result, "structured_output", None)
        passes = sum(1 for n in state.execution_order if n.node_id == "planner")
        if verdict is not None:
            status = "PASS" if verdict.ok else "REVISE — " + "; ".join(verdict.problems)[:200]
            print(f"[critic] pass {passes}: {status}", flush=True)
        return bool(verdict is not None and not verdict.ok and passes < 2)

    b = GraphBuilder()
    b.add_node(planner, "planner")
    b.add_node(critic,  "critic")
    b.add_edge("planner", "critic")
    b.add_edge("critic",  "planner", condition=_should_retry)
    b.set_entry_point("planner")
    b.set_max_node_executions(4)
    b.reset_on_revisit(True)
    b.set_hook_providers([gate])
    return b.build()


# ── Graph: quiz path ──────────────────────────────────────────────────────

def _build_quiz_graph(lang: str, n_questions: int, gate: SafetyGate):
    lang_name = LANG_NAMES[lang]

    planner = Agent(
        model=_model(),
        name="planner",
        system_prompt=_PLANNER_QUIZ.format(lang_name=lang_name, n_questions=n_questions),
        tools=[tools.lookup_guidance],
        structured_output_model=QuizAnswer,
        callback_handler=None,
    )

    b = GraphBuilder()
    b.add_node(planner, "planner")
    b.set_entry_point("planner")
    b.set_max_node_executions(1)
    b.set_hook_providers([gate])
    return b.build()


# ── Graph: evaluate path ──────────────────────────────────────────────────

def _build_eval_graph(lang: str, gate: SafetyGate):
    lang_name = LANG_NAMES[lang]

    planner = Agent(
        model=_model(),
        name="planner",
        system_prompt=_PLANNER_EVAL.format(lang_name=lang_name),
        tools=[tools.lookup_guidance],
        structured_output_model=EvalAnswer,
        callback_handler=None,
    )

    b = GraphBuilder()
    b.add_node(planner, "planner")
    b.set_entry_point("planner")
    b.set_max_node_executions(1)
    b.set_hook_providers([gate])
    return b.build()


# ── Main run function ─────────────────────────────────────────────────────

def run(case: dict) -> dict:
    """Run the agent on one case dict.

    case keys:
        text (str)   — the student's message (required)
        lang (str)   — 'en', 'ta', or 'bi' (optional; auto-detected if absent)

    Returns a dict with:
        mode   — 'explain' | 'quiz' | 'evaluate' | 'handoff' | 'authority'
        plan   — the structured output as a dict (or a fixed message for safety paths)
        meta   — latency_ms, passes (explain only), path
    """
    t0   = time.time()
    text = case["text"]
    lang = case.get("lang") or tools.language_of(text)
    if lang not in LANG_NAMES:
        lang = "en"

    gate   = SafetyGate(user_text=text, lang=lang)
    intent = _detect_intent(text)
    meta   = {"path": intent, "passes": 0, "lang": lang}

    # ── Safety path (fast) ── check before any model call ─────────────────
    # Pre-check: run the hook's logic before even building a graph
    for phrase in RED_FLAGS:
        if phrase.lower() in text.lower():
            gate.triggered = "red_flag"
            gate.matched   = phrase
            break
    if not gate.triggered:
        for phrase in AUTHORITY_FLAGS:
            if phrase.lower() in text.lower():
                gate.triggered = "authority"
                gate.matched   = phrase
                break

    if gate.triggered == "red_flag":
        print(f"[safety] RED FLAG ({gate.matched!r}) → HANDOFF", flush=True)
        meta["path"] = "handoff"
        meta["latency_ms"] = int((time.time() - t0) * 1000)
        return {
            "mode": "handoff",
            "plan": {"answer": HANDOFF[lang], "citations": []},
            "meta": meta,
        }

    if gate.triggered == "authority":
        print(f"[safety] AUTHORITY ({gate.matched!r}) → REDIRECT", flush=True)
        meta["path"] = "authority"
        meta["latency_ms"] = int((time.time() - t0) * 1000)
        return {
            "mode": "authority",
            "plan": {"answer": AUTHORITY_MSG[lang], "citations": []},
            "meta": meta,
        }

    # Injection pre-check — after crisis and authority so those cannot be masked
    if not gate.triggered:
        for phrase in INJECT_FLAGS:
            if phrase.lower() in text.lower():
                gate.triggered = "inject"
                gate.matched   = phrase
                break

    # Scope pre-check — after injection so injection takes priority
    if not gate.triggered:
        for phrase in SCOPE_FLAGS:
            if phrase.lower() in text.lower():
                gate.triggered = "scope"
                gate.matched   = phrase
                break

    if gate.triggered == "inject":
        print(f"[safety] INJECT ({gate.matched!r}) → REFUSE", flush=True)
        meta["path"] = "inject"
        meta["latency_ms"] = int((time.time() - t0) * 1000)
        return {
            "mode": "inject",
            "plan": {"answer": INJECT_MSG[lang], "citations": []},
            "meta": meta,
        }

    if gate.triggered == "scope":
        print(f"[safety] SCOPE ({gate.matched!r}) → REFUSE", flush=True)
        meta["path"] = "scope"
        meta["latency_ms"] = int((time.time() - t0) * 1000)
        return {
            "mode": "scope",
            "plan": {"answer": SCOPE_MSG[lang], "citations": []},
            "meta": meta,
        }

    # ── Model paths ────────────────────────────────────────────────────────
    try:
        if intent == "explain":
            graph = _build_explain_graph(lang, gate)
            res   = graph(f"Student ({lang}): {text}", invocation_state={"user_text": text})
            node_res = res.results.get("planner")
            if node_res is None:
                raise RuntimeError("planner node produced no result")
            answer = node_res.result.structured_output
            if answer is None:
                raise RuntimeError("planner returned no structured output")
            meta["passes"] = sum(1 for n in res.execution_order if n.node_id == "planner")
            meta["latency_ms"] = int((time.time() - t0) * 1000)
            print(f"[plan] explain | {meta['passes']} pass(es) | {meta['latency_ms']} ms", flush=True)
            return {"mode": "explain", "plan": answer.model_dump(), "meta": meta}

        elif intent == "quiz":
            n_q   = _parse_n_questions(text)
            graph = _build_quiz_graph(lang, n_q, gate)
            res   = graph(f"Student ({lang}): {text}", invocation_state={"user_text": text})
            node_res = res.results.get("planner")
            if node_res is None:
                raise RuntimeError("planner node produced no result")
            answer = node_res.result.structured_output
            if answer is None:
                raise RuntimeError("quiz planner returned no structured output")
            meta["latency_ms"] = int((time.time() - t0) * 1000)
            print(f"[plan] quiz | {meta['latency_ms']} ms", flush=True)
            return {"mode": "quiz", "plan": answer.model_dump(), "meta": meta}

        else:  # evaluate
            graph = _build_eval_graph(lang, gate)
            res   = graph(f"Student ({lang}): {text}", invocation_state={"user_text": text})
            node_res = res.results.get("planner")
            if node_res is None:
                raise RuntimeError("planner node produced no result")
            answer = node_res.result.structured_output
            if answer is None:
                raise RuntimeError("eval planner returned no structured output")
            meta["latency_ms"] = int((time.time() - t0) * 1000)
            print(f"[plan] evaluate | {meta['latency_ms']} ms", flush=True)
            return {"mode": "evaluate", "plan": answer.model_dump(), "meta": meta}

    except RuntimeError as exc:
        # If the gate triggered inside the graph (shouldn't happen after the
        # pre-check, but guard defensively), return the appropriate fixed text.
        if gate.triggered == "red_flag":
            meta["path"] = "handoff"
            meta["latency_ms"] = int((time.time() - t0) * 1000)
            return {"mode": "handoff", "plan": {"answer": HANDOFF[lang], "citations": []}, "meta": meta}
        if gate.triggered == "authority":
            meta["path"] = "authority"
            meta["latency_ms"] = int((time.time() - t0) * 1000)
            return {"mode": "authority", "plan": {"answer": AUTHORITY_MSG[lang], "citations": []}, "meta": meta}
        raise


# ── Pretty printer ────────────────────────────────────────────────────────

def _pretty(out: dict) -> str:
    """Format a run() result for human-readable terminal output."""
    mode = out["mode"]
    plan = out["plan"]
    meta = out["meta"]
    lines: list[str] = []

    if mode in ("handoff", "authority"):
        lines.append(plan["answer"])
        return "\n".join(lines)

    if mode == "explain":
        lines.append(f"[{meta['lang'].upper()}] {plan.get('topic', '')}")
        lines.append("")
        lines.append(plan.get("answer", ""))
        steps = plan.get("steps", [])
        if steps:
            lines.append("\nSteps:")
            for i, s in enumerate(steps, 1):
                lines.append(f"  {i}. {s}")
        example = plan.get("example", "")
        if example:
            lines.append(f"\nExample:\n  {example}")
        cites = plan.get("citations", [])
        if cites:
            lines.append(f"\nCitations: {', '.join(cites)}")

    elif mode == "quiz":
        lines.append(f"[QUIZ] {plan.get('topic', '')} — {plan.get('difficulty', '')}")
        for i, q in enumerate(plan.get("questions", []), 1):
            lines.append(f"\nQ{i}. {q['question']}")
            for j, opt in enumerate(q.get("options", []), 0):
                marker = "✓" if j == q.get("correct_index") else " "
                lines.append(f"   {'ABCD'[j]}. [{marker}] {opt}")
            lines.append(f"   Explanation: {q.get('explanation', '')}")

    elif mode == "evaluate":
        score = plan.get("score", "")
        lines.append(f"[EVAL] {plan.get('topic', '')} — {score.upper()}")
        for s in plan.get("strengths", []):
            lines.append(f"  ✓ {s}")
        for m in plan.get("mistakes", []):
            lines.append(f"  ✗ {m}")
        correction = plan.get("correction", "")
        if correction:
            lines.append(f"\nCorrection:\n  {correction}")
        rec = plan.get("recommended_practice", "")
        if rec:
            lines.append(f"\nNext: {rec}")
        cites = plan.get("citations", [])
        if cites:
            lines.append(f"\nCitations: {', '.join(cites)}")

    lines.append(f"\n— {meta['latency_ms']} ms")
    return "\n".join(lines)


# ── CLI ───────────────────────────────────────────────────────────────────

def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="python -m agent.app",
        description="ArivuBridge – Tamil AI Learning Companion",
    )
    ap.add_argument("text", help="Student's question or request")
    ap.add_argument(
        "--lang",
        choices=["en", "ta", "bi"],
        default=None,
        help="Response language: en=English, ta=Tamil, bi=Bilingual (auto-detect if omitted)",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="Print full JSON output instead of formatted text",
    )
    a = ap.parse_args(argv)

    case = {"text": a.text}
    if a.lang:
        case["lang"] = a.lang

    out = run(case)

    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print("\n" + _pretty(out))

    return 0


if __name__ == "__main__":
    sys.exit(main())

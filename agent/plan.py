"""Structured output models for ArivuBridge.

Three schemas cover the three agent modes:
  ExplainAnswer  — concept explanation (planner → critic graph)
  QuizAnswer     — quiz generation
  EvalAnswer     — student answer evaluation
  Critique       — internal critic verdict (not returned to the user)
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Public output schemas
# ---------------------------------------------------------------------------

class ExplainAnswer(BaseModel):
    """Structured output produced by the Tutor planner for an explanation request."""

    language: Literal["en", "ta", "bi"] = Field(
        description=(
            "Response language: 'en' = English only, 'ta' = Tamil only, "
            "'bi' = bilingual (English explanation followed by Tamil translation)."
        )
    )
    topic: str = Field(
        description="The CS topic that was explained, in 3–6 words."
    )
    answer: str = Field(
        description=(
            "The main explanation in the requested language. "
            "For 'bi', include both English and Tamil sections separated by a blank line."
        )
    )
    steps: list[str] = Field(
        default_factory=list,
        description=(
            "Step-by-step breakdown of the concept. Each step is one short sentence. "
            "At least 2 steps required."
        )
    )
    example: str = Field(
        default="",
        description=(
            "A concrete, beginner-friendly example that illustrates the concept. "
            "Use everyday situations students recognise."
        )
    )
    escalation: str = Field(
        default="",
        description=(
            "When the student should ask a human teacher instead of relying on this assistant. "
            "Leave empty if not applicable."
        )
    )
    citations: list[str] = Field(
        default_factory=list,
        description=(
            "Guidance item IDs (e.g. 'DBMS-004') returned by lookup_guidance "
            "that support this explanation. Must not be empty."
        )
    )


class QuizQuestion(BaseModel):
    """One multiple-choice question inside a QuizAnswer."""

    question: str = Field(description="The question text in the requested language.")
    options: list[str] = Field(
        description="Exactly four answer options (A, B, C, D)."
    )
    correct_index: int = Field(
        description="0-based index of the correct option (0=A, 1=B, 2=C, 3=D)."
    )
    explanation: str = Field(
        description="Why the correct option is right, in the requested language."
    )
    citation: str = Field(
        default="",
        description="Guidance item ID that this question tests."
    )


class QuizAnswer(BaseModel):
    """Structured output produced by the Tutor for a quiz generation request."""

    language: Literal["en", "ta", "bi"] = Field(
        description="Language of the quiz questions and explanations."
    )
    topic: str = Field(
        description="The CS topic the quiz covers."
    )
    difficulty: Literal["beginner", "intermediate"] = Field(
        default="beginner",
        description="Difficulty level: 'beginner' for first-year students, 'intermediate' for later years."
    )
    questions: list[QuizQuestion] = Field(
        description="The quiz questions. Generate the number requested by the student (default 5)."
    )
    citations: list[str] = Field(
        default_factory=list,
        description="All guidance IDs cited across all questions."
    )


class EvalAnswer(BaseModel):
    """Structured output produced by the Tutor for an answer-evaluation request."""

    language: Literal["en", "ta", "bi"] = Field(
        description="Language of the feedback."
    )
    topic: str = Field(
        description="The CS topic the student answered about."
    )
    score: Literal["correct", "partial", "incorrect"] = Field(
        description=(
            "'correct' — the student's answer is essentially right, "
            "'partial' — it has some correct points but misses key ideas, "
            "'incorrect' — the core idea is wrong."
        )
    )
    strengths: list[str] = Field(
        default_factory=list,
        description="What the student got right (empty for 'incorrect')."
    )
    mistakes: list[str] = Field(
        default_factory=list,
        description="Specific errors or missing ideas (empty for 'correct')."
    )
    correction: str = Field(
        default="",
        description=(
            "A concise correct version of the answer, in the student's language. "
            "Constructive, not condescending."
        )
    )
    recommended_practice: str = Field(
        default="",
        description=(
            "One sentence suggesting what the student should review or practise next."
        )
    )
    citations: list[str] = Field(
        default_factory=list,
        description="Guidance IDs used to evaluate the answer."
    )


# ---------------------------------------------------------------------------
# Internal critic schema — not returned to the student
# ---------------------------------------------------------------------------

class Critique(BaseModel):
    """Internal verdict from the Critic agent. Not shown to the student."""

    ok: bool = Field(
        description=(
            "True if the explanation passes all checks. "
            "False if any problem requires the planner to revise."
        )
    )
    problems: list[str] = Field(
        default_factory=list,
        description=(
            "One problem per item. Each item is a short imperative sentence "
            "telling the planner exactly what to fix. Empty when ok=True."
        )
    )

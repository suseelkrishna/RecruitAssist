"""The optional LLM judge: scores faithfulness and clarity with the rubric in judge_rubric.md.

The judge only adds these two scores. Pass or fail always comes from the
deterministic checks in grade.py, and every judge score is labeled as such in
the report.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


RUBRIC = (Path(__file__).resolve().parent / "judge_rubric.md").read_text()
JUDGE_EFFORT = "low"


def judge_prompt(question: dict[str, Any], answer: str) -> str:
    """The user message for the judge: question, earlier exchange, answer key, must points, answer."""
    parts = [f"Question: {question['question']}"]
    for pair in question.get("history") or []:
        parts.append(f"Earlier question: {pair['question']}\nEarlier answer: {pair['answer']}")
    parts.append("Answer key:\n" + json.dumps(question["expected"], indent=2, ensure_ascii=False))
    parts.append("A good answer:\n" + "\n".join(f"- {m}" for m in question["must"]))
    parts.append(f"Answer to grade:\n{answer}")
    return "\n\n".join(parts)


def parse_scores(text: str) -> dict[str, Any] | None:
    """The first JSON object in the judge's reply, or None when there is none."""
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return None
    try:
        scores = json.loads(match.group(0))
    except ValueError:
        return None
    if not all(isinstance(scores.get(k), (int, float)) for k in ("faithfulness", "clarity")):
        return None
    return {"faithfulness": scores["faithfulness"], "clarity": scores["clarity"],
            "reason": str(scores.get("reason", ""))}


async def judge(client: Any, model: str, question: dict[str, Any], answer: str) -> dict[str, Any]:
    """Ask the judge model for the two scores through the LLM interface (the same judge model
    scores every setting, whichever provider answered). Returns the scores (or None) and the usage."""
    response = await client.complete(model=model, system=RUBRIC, prompt=judge_prompt(question, answer),
                                     effort=JUDGE_EFFORT, max_tokens=4000)
    return {"scores": parse_scores(response.text), "model": model,
            "usage": {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens}}

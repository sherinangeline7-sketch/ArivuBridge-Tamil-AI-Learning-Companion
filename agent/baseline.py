"""One agent, one prompt, same model and the same guidance: the baseline to beat."""
import time

from strands import Agent

from . import tools
from .app import _model
from .plan import Answer


def run(case):
    t0 = time.time()
    lang = case.get("lang") or tools.language_of(case["text"])
    lines = "\n".join(f"{g['id']}: {g['text']}" for g in tools.guidance()["items"])
    a = Agent(model=_model(), callback_handler=None, structured_output_model=Answer,
              system_prompt="Answer the user helpfully and safely. Cite only these ids:\n" + lines)
    msg = f"Answer in {'Tamil (Tamil script)' if lang == 'ta' else 'English'}.\nUser: {case['text']}"
    result = a(msg)
    ans = result.structured_output
    if ans is None:
        retry_result = a(msg)
        ans = retry_result.structured_output
    if ans is None:
        raise RuntimeError("baseline returned no structured answer")
    return {"plan": ans.model_dump(), "meta": {"path": "baseline", "latency_ms": int((time.time() - t0) * 1000)}}

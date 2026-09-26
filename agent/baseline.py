"""No-tool baseline: the same model, no tools, answers from its own knowledge.

It measures what the agent adds over the model "reciting the answer" (the model may
have seen these classic complexes in training). It gets only the protein names and
UniProt accessions — nothing else — and is scored with the same rule as the agent.
"""
from __future__ import annotations
import json
import re

from .cases import Case
from .llm_client import make_client, MODEL
from .runlog import RunRecorder

PROMPT = (
    "Without using any tools or lookups, answer from your own knowledge. Proteins A and B "
    "form a complex. A = {name_a} (UniProt {uniprot_a}); B = {name_b} (UniProt {uniprot_b}). "
    "For EACH protein give the contiguous residue range (UniProt numbering) of the region "
    "that forms the interface with the other protein. Reply with JSON only: "
    '{{"regions": [{{"uniprot": "<accession>", "start": <int>, "end": <int>}}, ...], '
    '"confidence": <0..1>}}'
)


def parse_regions(text: str | None) -> dict:
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        d = json.loads(m.group(0)) if m else None
        regions = d["regions"]
        assert isinstance(regions, list)
        return {"predicted_regions": regions, "confidence": d.get("confidence")}
    except Exception:
        return {"parse_error": True, "raw": (text or "")[:300]}


def run_baseline(case: Case, model: str = MODEL):
    """One LLM call, no tools. Returns (result, run-log line)."""
    goal = PROMPT.format(name_a=case.name_a, uniprot_a=case.uniprot_a,
                         name_b=case.name_b, uniprot_b=case.uniprot_b)
    rec = RunRecorder("baseline", model, goal, case.id)
    resp = make_client().chat.completions.create(
        model=model, messages=[{"role": "user", "content": goal}], temperature=0)
    rec.llm(resp)
    result = parse_regions(resp.choices[0].message.content)
    return result, rec.finish(result)

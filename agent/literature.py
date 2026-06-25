"""Stage 1 — retrieve the FAT10-MAD2 binding-region claim FROM the literature
(PubMed), instead of hard-coding it. An LLM reads the real abstracts and extracts
which FAT10 region binds MAD2.

Honest: if the live PubMed query is unavailable (network policy), it falls back to
the cited known result and SAYS SO (retrieved_live=False), so the pipeline still
runs but never pretends a hand-fed fact was searched.

    python -m agent.literature
"""
from __future__ import annotations
import json
import re
import urllib.parse
import urllib.request

from .llm_client import make_client, MODEL

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def _get(url: str) -> str:
    with urllib.request.urlopen(url, timeout=25) as r:
        return r.read().decode()


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return {"raw": (text or "")[:300]}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"raw": (text or "")[:300]}


def search_pubmed(query: str, retmax: int = 5):
    q = urllib.parse.quote(query)
    es = _get(f"{EUTILS}/esearch.fcgi?db=pubmed&retmode=json&retmax={retmax}&term={q}")
    ids = json.loads(es)["esearchresult"]["idlist"]
    if not ids:
        return [], ""
    abstracts = _get(f"{EUTILS}/efetch.fcgi?db=pubmed&rettype=abstract&retmode=text&id={','.join(ids)}")
    return ids, abstracts


FALLBACK = {
    "retrieved_live": False,
    "claim": "MAD2 binds the N-terminal (first) ubiquitin-like domain of FAT10",
    "evidence_quote": "(fallback: live PubMed unavailable from this network)",
    "source": "Theng et al. 2014 PNAS (FAT10-MAD2 interaction); UniProt O15205",
    "pmids": [],
}


def retrieve_binding_region(query: str = "FAT10 MAD2 interaction ubiquitin-like domain") -> dict:
    try:
        ids, abstracts = search_pubmed(query)
    except Exception as exc:  # network blocked / timeout
        out = dict(FALLBACK)
        out["error"] = f"{type(exc).__name__}"
        return out
    if not abstracts.strip():
        return dict(FALLBACK)

    client = make_client()
    prompt = (
        "From these PubMed abstracts about FAT10 and MAD2, extract which REGION or "
        "DOMAIN of FAT10 binds MAD2 (e.g. the N-terminal / first ubiquitin-like domain). "
        "Use ONLY what the abstracts state. Answer ONLY as JSON with keys "
        '"claim", "evidence_quote", "pmid_hint".\n\nAbstracts:\n' + abstracts[:6000])
    msg = client.chat.completions.create(
        model=MODEL, temperature=0,
        messages=[{"role": "user", "content": prompt}])
    out = _extract_json(msg.choices[0].message.content)
    out["retrieved_live"] = True
    out["pmids"] = ids
    out.setdefault("source", f"PubMed PMIDs {', '.join(ids)}")
    return out


if __name__ == "__main__":
    r = retrieve_binding_region()
    print(json.dumps(r, indent=2, ensure_ascii=False))

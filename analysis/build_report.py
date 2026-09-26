#!/usr/bin/env python3
"""Build a single styled HTML report of the whole pipeline — NO Jupyter, NO kernel,
NO sqlite (sidesteps the broken conda). Pure Python.

    export DEEPSEEK_API_KEY=...        # optional: enables literature + debate sections
    python -m analysis.build_report
    # -> outputs/report.html  (open in any browser)
"""
from __future__ import annotations
import html
import json
import os
import re
from pathlib import Path

from agent.tools import fetch_structures, get_expected_interface_region, get_md_interface_scores

HAVE_KEY = bool(os.environ.get("DEEPSEEK_API_KEY"))
DOMAINS = [("UBL1 (N-term)", 6, 81), ("linker", 82, 89),
           ("UBL2 (C-term)", 90, 163), ("C-term tail", 164, 165)]


def esc(x): return html.escape(str(x))
def rn(l): m = re.search(r"(\d+)", l); return int(m.group(1)) if m else 0
def dom(n):
    for nm, lo, hi in DOMAINS:
        if lo <= n <= hi:
            return nm
    return "outside"


def table(headers, rows):
    h = "".join(f"<th>{esc(c)}</th>" for c in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><thead><tr>{h}</tr></thead><tbody>{body}</tbody></table>"


def stage(num, title, body):
    return f'<section><h2><span class="num">{num}</span>{esc(title)}</h2>{body}</section>'


def build():
    parts = []

    # Stage 1 — literature
    if HAVE_KEY:
        try:
            from agent.literature import retrieve_binding_region
            lit = retrieve_binding_region()
        except Exception as e:
            lit = {"claim": "(literature stage failed)", "source": str(e), "retrieved_live": False}
    else:
        lit = {"retrieved_live": False,
               "claim": "MAD2 binds the N-terminal (first) ubiquitin-like domain of FAT10",
               "source": "Theng et al. 2014 (set DEEPSEEK_API_KEY for live PubMed search)"}
    tag = "🔎 live PubMed" if lit.get("retrieved_live") else "📌 cited"
    parts.append(stage(1, "Literature — where is MAD2 expected to bind?",
                       f'<p class="tag">{tag}</p><p><b>{esc(lit.get("claim","?"))}</b></p>'
                       f'<p class="src">Source: {esc(lit.get("source","?"))}</p>'))

    # Stage 2 — structures + domains
    st = fetch_structures("O15205")["structures"]
    rows = [[esc(s["pdb_id"].upper()), esc(s.get("resolution", "-")),
             esc(s.get("experimental_method", "-"))] for s in st]
    exp = get_expected_interface_region("O15205")
    parts.append(stage(2, "Grounding — real structures + UniProt domains",
                       table(["PDB", "Resolution", "Method"], rows) +
                       f'<p>UniProt-verified domains — <b>UBL1 (expected MAD2 site): {exp["residue_range"]}</b>; '
                       f'others: {esc(exp.get("other_domains"))}</p>'
                       f'<p class="src">{esc(exp.get("evidence_type",""))} — {esc(exp.get("source",""))}</p>'))

    # Stage 3 — MD evidence
    md = get_md_interface_scores()
    occ = md["occupancy"]
    rows = [[esc(k), f"{v:.2f}", esc(dom(rn(k)))]
            for k, v in sorted(occ.items(), key=lambda kv: -kv[1])]
    parts.append(stage(3, f"Real MD evidence — {esc(md['method'])}",
                       table(["Residue", "Occupancy", "Domain"], rows)))

    # Stage 4 — deterministic adjudication
    core = {k: v for k, v in occ.items() if v >= 0.5}
    in_ubl1 = [k for k in core if 6 <= rn(k) <= 81]
    flag = bool(core) and not in_ubl1
    verdict_html = (
        f'<div class="flag">🚩 FLAG — the persistent interface '
        f'({esc(", ".join(core))}) is ENTIRELY OUTSIDE the expected UBL1 (6–81). '
        f'Model contradicts the literature.</div>'
        if flag else
        f'<div class="ok">✅ interface overlaps UBL1: {esc(", ".join(in_ubl1))}</div>')
    parts.append(stage(4, "Adjudication — MD interface vs expected domain",
                       f'<p>Persistent interface (occ ≥ 0.5): <b>{esc(", ".join(core) or "—")}</b><br>'
                       f'Inside expected UBL1 (6–81): <b>{esc(", ".join(in_ubl1) or "NONE")}</b></p>'
                       + verdict_html))

    # Stage 5 — multi-agent debate
    if HAVE_KEY:
        try:
            from agent.debate import (evidence_bundle, _ask, ADVOCATE_MD, ADVOCATE_NMR,
                                      JUDGE, _extract_json)
            from agent.llm_client import make_client
            client = make_client()
            facts = evidence_bundle()
            a_md = _ask(client, ADVOCATE_MD, facts)
            a_nmr = _ask(client, ADVOCATE_NMR, facts)
            verdict = _extract_json(_ask(client, JUDGE, facts,
                                         extra=f"\nMD said:\n{a_md}\n\nNMR said:\n{a_nmr}"))
            body = (f'<div class="adv md"><h3>🧬 MD advocate</h3><p>{esc(a_md)}</p></div>'
                    f'<div class="adv nmr"><h3>📚 NMR advocate</h3><p>{esc(a_nmr)}</p></div>'
                    f'<div class="judge"><h3>⚖️ Judge</h3><pre>{esc(json.dumps(verdict, indent=2, ensure_ascii=False))}</pre></div>')
        except Exception as e:
            body = f'<p class="src">debate stage failed: {esc(e)}</p>'
    else:
        body = '<p class="src">Set <code>DEEPSEEK_API_KEY</code> and re-run to generate the live debate.</p>'
    parts.append(stage(5, "Multi-agent debate (the highlight)", body))

    return "\n".join(parts)


CSS = """
body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:880px;margin:2rem auto;
padding:0 1rem;color:#1a2230;line-height:1.5}
h1{border-bottom:3px solid #1d4ed8;padding-bottom:.3rem}
h2{margin-top:2rem;color:#0f2440}.num{display:inline-block;background:#1d4ed8;color:#fff;
border-radius:50%;width:1.7rem;height:1.7rem;text-align:center;line-height:1.7rem;
margin-right:.5rem;font-size:.9rem}
table{border-collapse:collapse;width:100%;margin:.6rem 0}th,td{border:1px solid #d3dae6;
padding:.35rem .6rem;text-align:left}th{background:#eef3fb}
.tag{display:inline-block;background:#e0f2fe;padding:.1rem .5rem;border-radius:.4rem;font-size:.85rem}
.src{color:#667;font-size:.85rem}
.flag{background:#fde8e8;border-left:5px solid #d33;padding:.8rem;border-radius:.3rem;font-weight:600}
.ok{background:#e7f6ee;border-left:5px solid #0a8;padding:.8rem;border-radius:.3rem}
.adv{border-left:4px solid #b45309;background:#fffaf2;padding:.2rem .9rem;margin:.6rem 0;border-radius:.3rem}
.adv.nmr{border-left-color:#0369a1;background:#f2f9ff}
.judge{border-left:4px solid #0f9d6b;background:#f1fbf6;padding:.2rem .9rem;border-radius:.3rem}
pre{white-space:pre-wrap;font-size:.85rem}
"""

TEMPLATE = """<!doctype html><html><head><meta charset="utf-8">
<title>FAT10–MAD2 Interface — Agentic Adjudication</title><style>{css}</style></head><body>
<h1>FAT10–MAD2 Interface — Agentic Adjudication</h1>
<p><i>Real MD evidence + literature/domain grounding + multi-agent debate. No experimental
FAT10–MAD2 complex exists, so the verdict flags a contradiction — it is not ground truth.</i></p>
{body}
<hr><p class="src">Generated by analysis/build_report.py — no Jupyter required.</p>
</body></html>"""


def main():
    out = Path("outputs"); out.mkdir(exist_ok=True)
    doc = TEMPLATE.format(css=CSS, body=build())
    (out / "report.html").write_text(doc, encoding="utf-8")
    print("WROTE outputs/report.html  (open in a browser)")
    print("LLM stages:", "ON" if HAVE_KEY else "OFF (set DEEPSEEK_API_KEY for literature+debate)")


if __name__ == "__main__":
    main()

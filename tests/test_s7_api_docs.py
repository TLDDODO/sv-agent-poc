"""S7: documented API schema, exported OpenAPI file, and the two user docs."""
import json
import re
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

from api import main as api
from api.main import app

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import export_openapi  # noqa: E402

SCHEMA = app.openapi()
OPS = [(path, method, op) for path, item in SCHEMA["paths"].items() for method, op in item.items()]
DOCS = {n: (ROOT / "docs" / n).read_text(encoding="utf-8") for n in ("dify_setup.md", "user_guide.md")}


def test_exported_openapi_matches_the_app_schema():
    on_disk = json.loads((ROOT / "docs" / "openapi.json").read_text(encoding="utf-8"))
    assert on_disk == SCHEMA
    assert (ROOT / "docs" / "openapi.json").read_text(encoding="utf-8") == export_openapi.render()
    assert export_openapi.main(["--check"]) == 0


def test_every_endpoint_has_summary_description_and_operation_id():
    assert {(p, m) for p, m, _ in OPS} == {("/info", "get"), ("/health", "get"), ("/evidence", "get"),
                                          ("/adjudicate", "post"), ("/debate", "post"),
                                          ("/api/cases", "get"), ("/api/run", "post")}
    ids = [op["operationId"] for _, _, op in OPS]
    assert len(set(ids)) == len(ids)
    for path, method, op in OPS:
        assert op.get("summary") and op.get("description"), (path, method)
        assert "application/json" in op["responses"]["200"]["content"], path
        assert "example" in op["responses"]["200"]["content"]["application/json"], path


def test_request_fields_have_examples_and_descriptions():
    props = SCHEMA["components"]["schemas"]["AgentRequest"]["properties"]
    for name in ("goal", "max_steps"):
        assert props[name].get("description") and props[name].get("examples"), name


def test_the_evidence_example_is_the_real_committed_evidence():
    ex = SCHEMA["paths"]["/evidence"]["get"]["responses"]["200"]["content"]["application/json"]["example"]
    real = api._evidence_payload()
    assert ex == real
    with open("analysis/md_interface_scores.json", encoding="utf-8") as fh:
        assert ex["md_occupancy"] == next(iter(json.load(fh).values()))


def test_shape_examples_are_marked_as_placeholders():
    for path in ("/adjudicate", "/debate"):
        ex = SCHEMA["paths"][path]["post"]["responses"]["200"]["content"]["application/json"]["example"]
        assert "placeholders" in ex["_note"]


def test_servers_entry_present_for_dify():
    assert SCHEMA["servers"] and SCHEMA["servers"][0]["url"].startswith("http")


def test_v1_endpoint_behaviour_is_unchanged(monkeypatch):
    assert api.health() == {"status": "ok", "llm_configured": False}
    ev = api.evidence()
    assert set(ev) == {"md_method", "md_occupancy", "expected_region", "adjudication"}
    assert ev["expected_region"]["residue_range"] == [6, 81]
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(HTTPException) as e:
        api.adjudicate(api.AgentRequest())
    assert e.value.status_code == 400
    with pytest.raises(HTTPException):
        api.debate()


# --- docs -------------------------------------------------------------------------------
def test_dify_doc_covers_every_tool_and_the_files_it_names_exist():
    for _, _, op in OPS:
        assert op["operationId"] in DOCS["dify_setup.md"]
    for rel in ("docs/openapi.json", "scripts/export_openapi.py", "docker-compose.yml"):
        assert rel in DOCS["dify_setup.md"] and (ROOT / rel).exists()
    assert "没有任何身份验证" in DOCS["dify_setup.md"]          # the safety limit is stated plainly


def test_user_guide_explains_labels_and_gives_three_questions():
    g = DOCS["user_guide.md"]
    for term in ("真实", "引用", "待定", "矛盾", "不判定谁对"):
        assert term in g
    assert len(re.findall(r"^\d\. \*\*\"", g, re.M)) == 3


def test_docs_contain_no_metrics():
    bench = json.loads((ROOT / "results" / "benchmark.json").read_text(encoding="utf-8"))
    forbidden = set()
    for arm in ("agent", "baseline"):
        o = bench["overall"][arm]
        forbidden |= {f"{o['mean_score']:.2f}", f"{o['stability']:.2f}"}
    for name, text in DOCS.items():
        assert not re.search(r"\d\s*%", text), name                  # no percentages
        assert not re.search(r"\d+\.\d+", re.sub(r"\d+\.\d+\.\d+\.\d+", "", text)), name  # no decimals / scores (IPs aside)
        assert not re.search(r"\$\s*\d", text), name                 # no costs
        assert not re.search(r"\d+\s*(秒|分钟|s\b)", text), name     # no timings
        for v in forbidden:
            assert v not in text, (name, v)

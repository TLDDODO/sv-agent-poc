"""An empty residue list after MD data was retrieved is sent back (twice at most), then marked
`residues_missing`; the web headline never says "none" but shows the MD data's top residues,
labelled as such."""
import json

from agent import run_agent
from agent.cases import default_case
from api import webview
from fakes import tool_result

MD = lambda m: ("md", [("get_md_interface_scores", {})])                       # noqa: E731


def _submit(residues):
    return lambda m: ("s", [("submit_adjudication", {"consensus_interface": residues, "disputed": [],
                                                     "confidence": 0.3, "reasoning": "r"})])


def test_empty_list_is_sent_back_and_the_resubmission_is_used(fake_llm):
    fake_llm([MD, _submit([]), _submit(["I163", "C162"])])
    result, transcript = run_agent.run("g", verbose=False, case=default_case())
    assert result["consensus_interface"] == ["I163", "C162"] and "residues_missing" not in result
    subs = [a for e in transcript for a in e["actions"] if a["tool"] == "submit_adjudication"]
    assert len(subs) == 2 and subs[0]["rejected"] == "empty consensus_interface"


def test_the_rejection_text_reaches_the_model(fake_llm):
    seen = {}

    def second(m):
        seen["r"] = tool_result(m, "submit_adjudication")
        return _submit(["I163"])(m)
    fake_llm([MD, _submit([]), second])
    run_agent.run("g", verbose=False, case=default_case())
    assert "rejected" in seen["r"]["error"]


def test_still_empty_after_two_retries_is_marked_not_filled_in(fake_llm):
    fake_llm([MD, _submit([]), _submit([]), _submit([])])
    result, transcript = run_agent.run("g", verbose=False, case=default_case())
    assert result["residues_missing"] is True and result["consensus_interface"] == []
    assert sum(a["tool"] == "submit_adjudication" for e in transcript for a in e["actions"]) == 3


def test_no_md_data_means_no_rejection(fake_llm):
    fake_llm([_submit([])])
    result, _ = run_agent.run("g", verbose=False, case=default_case())
    assert result["consensus_interface"] == [] and "residues_missing" not in result


def _md_transcript():
    from agent.tools import get_md_interface_scores
    return [{"actions": [{"tool": "get_md_interface_scores", "args": {}, "result": get_md_interface_scores()}]}]


def test_headline_for_an_empty_list_names_md_top_residues_with_their_source():
    case = default_case()
    top = webview.md_top_residues(_md_transcript())
    assert [r for r, _ in top][:3] == ["I163", "C162", "G164"]         # highest occupancy first
    h = webview.conclusion(case, {"consensus_interface": [], "residues_missing": True}, [], [], top)["headline"]
    assert "agent 未给出残基列表" in h["zh"] and "非 agent 结论" in h["zh"] and "I163" in h["zh"]
    assert "did not give a residue list" in h["en"] and "not an agent conclusion" in h["en"] and "I163" in h["en"]
    assert "没有" not in h["zh"] and "none" not in h["en"].lower()


def test_headline_for_an_empty_list_without_md_data_does_not_invent_residues():
    h = webview.conclusion(default_case(), {"consensus_interface": []}, [], [], [])["headline"]
    assert "agent 未给出残基列表" in h["zh"] and "非 agent 结论" not in h["zh"]


def test_headline_with_residues_is_unchanged():
    h = webview.conclusion(default_case(), {"consensus_interface": ["C162", "I163"]}, [], [], [])["headline"]
    assert "C162, I163" in h["zh"] and "由系统综合判断" in h["zh"]

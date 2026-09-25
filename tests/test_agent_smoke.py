"""Offline end-to-end smoke test of the ReAct loop on the FAT10-MAD2 goal.

The LLM is a scripted fake, but every tool it calls is the real v1 tool reading the
real committed data. The final step builds its submission from the tool results it
received, so the test fails if the real evidence stops showing the contradiction.
"""
import re

from agent import run_agent
from agent.tools import TOOLS
from fakes import tool_result

# v1 default goal (argparse default in agent/run_agent.py main()).
GOAL = ("Investigate where MAD2 (UniProt Q13257) binds FAT10 (UniProt O15205): find "
        "where the literature expects the interface, get the real MD contact evidence, "
        "and determine whether the current model's interface is consistent with the "
        "literature. If they conflict, convene the debate and reach a calibrated verdict.")


def _resnum(label):
    return int(re.search(r"\d+", label).group())


def _script():
    def read_literature(msgs):
        return "Start with the literature.", [("search_literature", {})]

    def expected_region(msgs):
        return "Get the expected binding region.", [
            ("get_expected_interface_region", {"uniprot": "O15205"})]

    def md_evidence(msgs):
        return "Get the real MD contact evidence.", [("get_md_interface_scores", {})]

    def submit(msgs):
        exp = tool_result(msgs, "get_expected_interface_region")
        md = tool_result(msgs, "get_md_interface_scores")
        lo, hi = exp["residue_range"]
        core = sorted((r for r, v in md["occupancy"].items() if v >= 0.5), key=_resnum)
        outside = [r for r in core if not lo <= _resnum(r) <= hi]
        flag = (f"CONTRADICTION: persistent MD interface {outside} lies outside the "
                f"literature-expected {exp['expected_region']} ({lo}-{hi}); no experimental "
                f"complex exists, so neither side is declared correct")
        # confidence is the scripted fake's choice, not a measured value
        return "Compare and submit.", [("submit_adjudication", {
            "consensus_interface": core, "disputed": [], "confidence": 0.3,
            "flags": [flag], "reasoning": "MD interface vs literature expectation."})]

    return [read_literature, expected_region, md_evidence, submit]


def test_agent_reaches_submission_and_reports_contradiction(fake_llm):
    client = fake_llm(_script())
    result, transcript = run_agent.run(GOAL, verbose=False)

    tools_called = [a["tool"] for e in transcript for a in e["actions"]]
    assert tools_called == ["search_literature", "get_expected_interface_region",
                            "get_md_interface_scores", "submit_adjudication"]
    assert result is not None and "consensus_interface" in result

    # the loop sent the real system prompt and tool schema to the model
    first = client.requests[0]
    assert first["messages"][0] == {"role": "system", "content": run_agent.SYSTEM_PROMPT}
    assert first["tools"] is TOOLS

    results = {a["tool"]: a["result"] for e in transcript for a in e["actions"] if "result" in a}
    # network is blocked: literature must say it fell back, never pretend to be live
    assert results["search_literature"]["retrieved_live"] is False

    expected = results["get_expected_interface_region"]
    assert expected["residue_range"] == [6, 81]
    assert expected["expected_region"].startswith("Ubiquitin-like 1")

    occupancy = results["get_md_interface_scores"]["occupancy"]
    core = {r for r, v in occupancy.items() if v >= 0.5}
    assert set(result["consensus_interface"]) == core
    # the real MD interface is entirely C-terminal of UBL1 (6-81)
    assert core and all(_resnum(r) > 81 for r in core)

    flag = result["flags"][0]
    assert flag.startswith("CONTRADICTION")
    assert "Ubiquitin-like 1" in flag and "neither side is declared correct" in flag

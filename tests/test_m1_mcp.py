"""M1: the MCP server, driven by an in-process MCP client. The LLM is the scripted fake; every
tool the agent calls is the real one reading the real committed data."""
import json

import anyio
from mcp import Client

from fakes import tool_result
from mcp_server import server


def _run(coro_fn):
    async def go():
        async with Client(server.build_server()) as c:
            return await coro_fn(c)
    return anyio.run(go)


def test_the_three_tools_are_listed_with_descriptions():
    tools = _run(lambda c: c.list_tools()).tools
    assert {t.name for t in tools} >= {"list_cases", "get_evidence", "run_adjudication"}
    assert all(t.description for t in tools)


def test_list_cases_returns_the_presets():
    res = _run(lambda c: c.call_tool("list_cases", {}))
    assert not res.is_error
    ids = [c["id"] for c in res.structured_content["cases"]]
    assert ids[0] == "fat10_mad2" and len(ids) > 1


def test_get_evidence_returns_labelled_evidence_and_the_contradiction_without_a_winner():
    res = _run(lambda c: c.call_tool("get_evidence", {}))
    assert not res.is_error
    d = res.structured_content
    assert d["status"] == "ok" and d["evidence"] and {r["label"] for r in d["evidence"]} <= {"live", "cited", "pending"}
    assert "不一致" in d["findings"][0]["plain"]["zh"] and "不判断哪一方正确" in d["findings"][0]["plain"]["zh"]
    assert d["evidence_data"]["md_occupancy"]["I163"] == 1.0                 # the committed MD value


def test_get_evidence_for_a_benchmark_pair_is_pending_not_invented():
    res = _run(lambda c: c.call_tool("get_evidence", {"case_id": "mdm2_p53"}))
    assert res.structured_content["status"] == "pending" and "evidence" not in res.structured_content


def test_run_adjudication_returns_conclusion_evidence_time_and_cost(fake_llm, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-not-real")

    def look(msgs):
        return "look", [("get_md_interface_scores", {}), ("get_expected_interface_region", {})]

    def submit(msgs):
        core = [r for r, v in tool_result(msgs, "get_md_interface_scores")["occupancy"].items() if v >= 0.5]
        return "d", [("submit_adjudication", {"consensus_interface": core, "disputed": [], "confidence": 0.3,
                                              "flags": [], "reasoning": "r"})]
    fake_llm([look, submit])
    res = _run(lambda c: c.call_tool("run_adjudication", {"case_id": "fat10_mad2"}))
    assert not res.is_error, res.content
    d = res.structured_content
    assert "不一致" in d["conclusion"]["findings"][0]["plain"]["zh"]
    assert d["evidence"] and {r["label"] for r in d["evidence"]} <= {"live", "cited", "pending"}
    assert d["usage"]["seconds"] is not None and "cost_usd" in d["usage"]
    assert json.dumps(d)                                                     # plain JSON-able structure


def test_run_adjudication_without_a_key_is_a_tool_error(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    res = _run(lambda c: c.call_tool("run_adjudication", {"case_id": "fat10_mad2"}))
    assert res.is_error and "DEEPSEEK_API_KEY" in res.content[0].text


def test_a_bad_case_is_a_tool_error():
    res = _run(lambda c: c.call_tool("run_adjudication", {"case_id": "nope"}))
    assert res.is_error


def test_http_listens_on_localhost_by_default(monkeypatch):
    seen = {}

    class Fake:
        def run(self, transport, **kw):
            seen.update(transport=transport, **kw)
    monkeypatch.setattr(server, "build_server", lambda: Fake())
    server.main(["--transport", "http"])
    assert seen["transport"] == "streamable-http" and seen["host"] == "127.0.0.1"
    assert seen["port"] == 8765
    assert "host.docker.internal:8765" not in seen["transport_security"].allowed_hosts
    server.main(["--transport", "http", "--allow-host", "host.docker.internal:8765"])
    assert "host.docker.internal:8765" in seen["transport_security"].allowed_hosts


def test_progress_prints_of_a_run_never_reach_stdout(monkeypatch, capsys):
    """On stdio, stray stdout text (the debate prints its rounds) would break the protocol."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-not-real")
    monkeypatch.setattr(server.webview, "run_query", lambda case: print("Round 1: MD advocate ...") or {"ok": True})
    res = _run(lambda c: c.call_tool("run_adjudication", {"case_id": "fat10_mad2"}))
    assert not res.is_error and res.structured_content == {"ok": True}
    out = capsys.readouterr()
    assert "Round 1" not in out.out and "Round 1" in out.err

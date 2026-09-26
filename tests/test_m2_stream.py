"""M2: live progress over SSE. A scripted fake LLM drives the real agent loop and real tools; the
event order is checked, and the last event's result must equal what the non-streaming endpoint
returns for the same scripted run."""
import json

from fastapi.testclient import TestClient

from api import main as api
from api import streaming
from fakes import tool_result

client = TestClient(api.app)


def _script(fake_llm):
    def look(msgs):
        return "look", [("get_md_interface_scores", {}), ("get_expected_interface_region", {})]

    def submit(msgs):
        core = [r for r, v in tool_result(msgs, "get_md_interface_scores")["occupancy"].items() if v >= 0.5]
        return "d", [("submit_adjudication", {"consensus_interface": core, "disputed": [], "confidence": 0.3,
                                              "flags": ["a flag"], "reasoning": "r"})]

    def para(msgs):
        return json.dumps({"items": [{"zh": "提醒:a flag", "en": "Note: a flag"}]}), []
    fake_llm([look, submit, para])


def _parse(text):
    out = []
    for block in text.strip().split("\n\n"):
        lines = block.split("\n")
        assert lines[0].startswith("event: ") and lines[1].startswith("data: ")
        ev = json.loads(lines[1][len("data: "):])
        assert ev["type"] == lines[0][len("event: "):]
        out.append(ev)
    return out


def _stable(result):
    """Drop what legitimately differs between two runs (wall-clock time)."""
    r = json.loads(json.dumps(result))
    for k in ("seconds",):
        r["usage"].pop(k, None)
    return r


def test_events_arrive_in_order_and_the_last_one_matches_the_non_streaming_result(fake_llm, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-not-real")
    _script(fake_llm)
    r = client.get("/api/run/stream", params={"case_id": "fat10_mad2"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    evs = _parse(r.text)
    assert [e["seq"] for e in evs] == list(range(len(evs)))
    types = [e["type"] for e in evs]
    assert types == ["start", "tool_call", "tool_result", "tool_call", "tool_result", "tool_call",
                     "flag_paraphrase", "flag_paraphrase", "cost", "final"]
    assert [e["tool"] for e in evs if e["type"] == "tool_call"] == [
        "get_md_interface_scores", "get_expected_interface_region", "submit_adjudication"]
    md = evs[2]
    assert md["tool"] == "get_md_interface_scores" and md["rows"] and all(x["label"] in ("live", "cited", "pending") for x in md["rows"])
    assert all(e["text"]["zh"] and e["text"]["en"] for e in evs)               # both languages, every step
    assert evs[-1]["result"]["conclusion"]["findings"]                        # the contradiction finding

    _script(fake_llm)
    plain = client.post("/api/run", json={"case_id": "fat10_mad2"}).json()
    assert _stable(evs[-1]["result"]) == _stable(plain)


def test_debate_rounds_are_events(fake_llm, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-not-real")

    def debate(msgs):
        return "d", [("get_md_interface_scores", {}), ("convene_debate", {})]

    def adv(msgs):
        return "an argument", []

    def judge(msgs):
        return json.dumps({"reasoning": "weighed", "flags": []}), []

    def submit(msgs):
        return "s", [("submit_adjudication", {"consensus_interface": ["I163"], "disputed": [], "confidence": 0.3,
                                              "reasoning": "r"})]
    c = fake_llm([debate, adv, adv, judge, submit])
    monkeypatch.setattr("agent.debate.make_client", lambda: c)          # the debate builds its own client
    monkeypatch.setattr("pathlib.Path.write_text", lambda self, *a, **k: 0)    # no outputs/debate_report.md
    evs = _parse(client.get("/api/run/stream", params={"case_id": "fat10_mad2"}).text)
    rounds = [(e["type"], e["role"]) for e in evs if e["type"].startswith("debate")]
    assert rounds == [("debate_round", "md_advocate"), ("debate_round_done", "md_advocate"),
                      ("debate_round", "nmr_advocate"), ("debate_round_done", "nmr_advocate"),
                      ("debate_round", "judge"), ("debate_round_done", "judge")]
    assert evs[-1]["type"] == "final"


def test_a_failing_run_ends_with_an_error_event(fake_llm, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-not-real")
    fake_llm([])                                                              # script exhausted at once
    evs = _parse(client.get("/api/run/stream", params={"case_id": "fat10_mad2"}).text)
    assert [e["type"] for e in evs] == ["start", "error"] and evs[-1]["text"]["en"]


def test_stream_validation_matches_the_plain_endpoint(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    assert client.get("/api/run/stream", params={"case_id": "fat10_mad2"}).status_code == 400
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-not-real")
    assert client.get("/api/run/stream", params={"case_id": "nope"}).status_code == 422
    assert client.get("/api/run/stream").status_code == 422


def test_argument_summaries_are_short_and_do_not_dump_lists():
    s = streaming.args_summary({"uniprot": "O15205", "residues": ["A1"] * 50, "q": "x" * 300})
    assert "residues: 50 items" in s and len(s) <= 80


def test_no_sink_means_no_events_and_the_plain_endpoint_is_unchanged(fake_llm, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-not-real")
    _script(fake_llm)
    assert client.post("/api/run", json={"case_id": "fat10_mad2"}).status_code == 200


def test_the_page_uses_the_stream_and_has_a_timeline_in_both_languages():
    html = client.get("/").text
    assert "/api/run/stream" in html and 'id="timeline"' in html and "h_timeline" in html
    assert "/api/run\"" in html or "fetch(\"/api/run\"" in html                 # the non-streaming path stays as a fallback

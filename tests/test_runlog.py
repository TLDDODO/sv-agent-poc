"""S3: every agent / debate run appends one well-formed JSON line to the run log."""
import json
import shutil

from agent import debate, run_agent
from agent.runlog import cost_usd, load_pricing
from fakes import FakeClient
from test_agent_smoke import GOAL, _script

FIELDS = {"timestamp", "kind", "model", "goal", "llm_calls", "prompt_tokens",
          "completion_tokens", "cache_hit_tokens", "wall_clock_s", "tools",
          "verdict", "cost_usd", "pricing_last_checked"}


def _lines(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]


def test_agent_run_appends_one_well_formed_line(fake_llm, runlog_path):
    client = fake_llm(_script(), prompt_tokens=100, completion_tokens=20)
    result, _ = run_agent.run(GOAL, model="deepseek-chat", verbose=False)

    lines = _lines(runlog_path)
    assert len(lines) == 1
    line = lines[0]
    assert set(line) == FIELDS
    assert line["kind"] == "agent" and line["model"] == "deepseek-chat" and line["goal"] == GOAL
    assert line["llm_calls"] == len(client.requests)
    assert line["prompt_tokens"] == 100 * len(client.requests)
    assert line["completion_tokens"] == 20 * len(client.requests)
    assert line["tools"] == ["search_literature", "get_expected_interface_region",
                             "get_md_interface_scores", "submit_adjudication"]
    assert line["verdict"] == result
    assert isinstance(line["wall_clock_s"], float) and line["wall_clock_s"] >= 0
    assert line["timestamp"].endswith("Z")

    pricing = load_pricing()
    assert line["pricing_last_checked"] == pricing["last_checked"]
    assert line["cost_usd"] == cost_usd("deepseek-chat", line["prompt_tokens"],
                                        line["completion_tokens"], 0, pricing)


def test_debate_run_appends_one_line(monkeypatch, tmp_path, runlog_path):
    # run in a scratch dir so the debate's outputs/ report does not land in the repo
    (tmp_path / "analysis").mkdir()
    shutil.copy("analysis/md_interface_scores.json", tmp_path / "analysis")
    monkeypatch.chdir(tmp_path)

    judge_json = json.dumps({"contradicts_literature_expectation": True})
    client = FakeClient([lambda m: ("md argument", []),
                         lambda m: ("nmr argument", []),
                         lambda m: (judge_json, [])])
    monkeypatch.setattr("agent.debate.make_client", lambda: client)
    verdict = debate.run()

    lines = _lines(runlog_path)
    assert len(lines) == 1
    line = lines[0]
    assert set(line) == FIELDS
    assert line["kind"] == "debate" and line["llm_calls"] == 3
    assert line["tools"] == [] and line["verdict"] == verdict


def test_cost_is_none_for_unpriced_model():
    assert cost_usd("no-such-model", 1000, 1000) is None


def test_cost_uses_listed_prices_and_cache_hits():
    pricing = load_pricing()
    p = pricing["models"]["deepseek-chat"]
    got = cost_usd("deepseek-chat", 1_000_000, 1_000_000, 400_000, pricing)
    want = 600_000 * p["input_cache_miss"] / 1e6 + 400_000 * p["input_cache_hit"] / 1e6 + p["output"]
    assert abs(got - want) < 1e-12

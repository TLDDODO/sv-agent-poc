"""Shared test setup.

- Every test runs from the repo root (the code uses repo-relative data paths).
- Offline tests have the network blocked and DEEPSEEK_API_KEY unset, so nothing can
  silently reach PubMed, UniProt, PDBe or DeepSeek.
- Tests marked ``live`` are skipped unless ``--run-live`` is given.
- ``fake_llm(script)`` swaps a scripted FakeClient into the agent loop.
- Run logs go to a per-test temp file (``RUNLOG_PATH``), never into the repo.
"""
from __future__ import annotations
import socket
from pathlib import Path

import pytest

from fakes import FakeClient

ROOT = Path(__file__).resolve().parent.parent


def pytest_addoption(parser):
    parser.addoption("--run-live", action="store_true", default=False,
                     help="also run tests marked live (network / DEEPSEEK_API_KEY)")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-live"):
        return
    skip = pytest.mark.skip(reason="live test; pass --run-live to run it")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def _repo_root(monkeypatch):
    monkeypatch.chdir(ROOT)


@pytest.fixture(autouse=True)
def runlog_path(tmp_path, monkeypatch):
    path = tmp_path / "runs.jsonl"
    monkeypatch.setenv("RUNLOG_PATH", str(path))
    return path


@pytest.fixture(autouse=True)
def _offline(request, monkeypatch):
    if "live" in request.keywords:
        return

    def _blocked(*args, **kwargs):
        raise OSError("network disabled in offline tests")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)


@pytest.fixture
def fake_llm(monkeypatch):
    """Install a scripted fake LLM into agent.run_agent; returns the FakeClient."""
    def install(script, **kwargs):
        client = FakeClient(script, **kwargs)
        monkeypatch.setattr("agent.run_agent.make_client", lambda: client)
        return client
    return install

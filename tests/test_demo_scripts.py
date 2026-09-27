"""Structural checks for the double-clickable demo helpers (scripts/start_demo.bat,
scripts/stop_demo.bat) and the containers they drive (docker-compose.yml, Dockerfile,
.env.example). No .bat is executed here -- that would start/stop the real Docker Desktop and
Dify containers on whatever machine the tests run on -- and cmd.exe has no "check syntax only"
mode, so this is a structural smoke test, not a parser guarantee.
"""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = [ROOT / "scripts" / "start_demo.bat", ROOT / "scripts" / "stop_demo.bat"]


def _text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _code_lines(text: str) -> list[str]:
    """Lines with REM comments and blanks stripped out, so string checks below look only at
    what the script actually runs, not at prose that happens to mention the same command."""
    return [l.strip() for l in text.splitlines()
            if l.strip() and not l.strip().upper().startswith("REM")]


def test_both_scripts_exist_are_crlf_batch_files_and_start_with_echo_off():
    for path in SCRIPTS:
        assert path.exists(), path
        raw = path.read_bytes()
        without_crlf = raw.replace(b"\r\n", b"")
        assert b"\r" not in without_crlf and b"\n" not in without_crlf, f"{path}: not pure CRLF"
        text = raw.decode("utf-8")
        assert text.lstrip().lower().startswith("@echo off"), path


def test_start_demo_drives_dify_this_repos_compose_and_waits_on_all_three_urls():
    text = _text(SCRIPTS[0])
    assert "docker compose up -d" in text
    assert r"%USERPROFILE%\dify\docker" in text             # the Dify checkout, matches docs/dify_setup.md A1
    for url in ("http://localhost", "http://127.0.0.1:8765/mcp", "http://127.0.0.1:8000/"):
        assert url in text
    assert "curl.exe" in text                                # no PowerShell dependency
    assert "timeout /t" not in text                          # known to fail with no console attached; use ping instead
    assert "docker info" in text                              # checks/starts Docker Desktop


def test_stop_demo_stops_both_composes_without_tearing_them_down():
    lines = _code_lines(_text(SCRIPTS[1]))
    assert lines.count("docker compose stop") == 2            # this repo's compose, then Dify's
    assert "docker compose down" not in lines                 # "stop" keeps containers and data, not "down"
    assert any(r"%USERPROFILE%\dify\docker" in l for l in lines)


def test_compose_runs_mcp_and_web_client_both_restarting_and_mcp_stays_off_the_lan():
    data = yaml.safe_load(_text(ROOT / "docker-compose.yml"))
    services = data["services"]
    assert set(services) == {"adjudicator", "mcp"}
    for name, svc in services.items():
        assert svc["restart"] == "unless-stopped", name
        assert "${DEEPSEEK_API_KEY" in "".join(svc.get("environment", [])), name
    mcp_ports = services["mcp"]["ports"]
    assert mcp_ports == ["127.0.0.1:8765:8765"]              # loopback-only, not the whole LAN
    mcp_command = " ".join(services["mcp"]["command"])
    assert "--allow-host" in mcp_command
    assert "--host" in mcp_command and "0.0.0.0" in mcp_command


def test_env_example_has_no_real_key():
    text = _text(ROOT / ".env.example")
    assert "DEEPSEEK_API_KEY=" in text and "DEEPSEEK_API_KEY=sk-" not in text
    assert "DEEPSEEK_MODEL=deepseek-chat" in text


def test_env_is_gitignored():
    assert ".env" in _text(ROOT / ".gitignore").splitlines()

# MCP server

Publishes the Interface Adjudicator as an [MCP](https://modelcontextprotocol.io) server so that clients such as Claude Desktop and Dify can call it directly. It uses the official MCP Python SDK (`mcp>=2`) and calls the same functions as the web client and the FastAPI; no logic is copied.

## Tools

| tool | what it does | needs `DEEPSEEK_API_KEY`? |
|---|---|---|
| `list_cases` | Preset cases (FAT10–MAD2 and the benchmark protein pairs). No answers are returned. | no |
| `get_evidence` | Real evidence for FAT10–MAD2: MD contact occupancy, the literature-expected region and the consistency check. Every evidence row is labelled `live`, `cited` or `pending`. | no |
| `run_adjudication` | Runs the investigator agent on a preset case or on two UniProt accessions. Returns `conclusion` (in Chinese and English), `evidence` rows with labels, and `usage` (time and cost). | **yes** |

`case_id` is forgiving: case, hyphens, underscores and spaces are ignored, so `fat10-mad2`, `FAT10 MAD2` and `fat10_mad2` all select the same case. An id that matches nothing returns an error that lists the valid ids.

Other protein pairs have no stand-alone `get_evidence` (their evidence is gathered only inside an agent run, after the experimental complex has been filtered out), so it returns `status: pending`.

The FAT10–MAD2 conclusion is unchanged: the MD interface (C-terminal region) contradicts the literature/NMR expectation (UBL1, residues 6–81). The system reports the contradiction and does not say which side is right.

## Start

First install the dependencies in the repository root: `pip install -r requirements.txt`.

**stdio (for Claude Desktop):**

```powershell
python -m mcp_server
```

**Streamable HTTP (for Dify); localhost only by default:**

```powershell
python -m mcp_server --transport http            # http://127.0.0.1:8765/mcp
python -m mcp_server --transport http --port 9000
```

A Dify container reaches the host as `host.docker.internal`. The server checks the `Host` header, so that name has to be allowed explicitly (see `docs/dify_setup.md`):

```powershell
python -m mcp_server --transport http --allow-host host.docker.internal:8765
```

`--host 0.0.0.0` makes the server reachable from the local network. The server has no built-in authentication, so keep it on localhost unless you understand the consequences.

## Claude Desktop config on Windows

Edit `%APPDATA%\Claude\claude_desktop_config.json` (create it if it does not exist), adjust the paths, save, and restart Claude Desktop:

```json
{
  "mcpServers": {
    "interface-adjudicator": {
      "command": "C:\\Users\\<you>\\AppData\\Local\\Programs\\Python\\Python311\\python.exe",
      "args": ["-m", "mcp_server"],
      "env": {
        "PYTHONPATH": "C:\\path\\to\\sv-agent-poc",
        "DEEPSEEK_API_KEY": "<your key>"
      }
    }
  }
}
```

- Use the full path of `python` for `command` (`where python` shows it). The repository's dependencies must be installed for that interpreter.
- Without `DEEPSEEK_API_KEY`, `list_cases` and `get_evidence` still work and `run_adjudication` returns a clear error.
- Keep the key only in this local file; never commit it.

## What was verified

- Offline tests (`tests/test_m1_mcp.py`): an in-process MCP client with a fake LLM lists the three tools and calls them successfully; errors (no key, unknown case) come back as tool errors; the HTTP server listens on `127.0.0.1` by default; anything a run prints never reaches stdout (it would corrupt the stdio protocol); case ids are normalised.
- Manual check (this machine; the output was not saved, so it is not a reproducible record): an MCP client connected over stdio (`python -m mcp_server`) and over HTTP (`http://127.0.0.1:8765/mcp`) and listed the three tools.
- Dify (self-hosted, Docker) connected to the HTTP endpoint; see `docs/dify_setup.md`.
- **Not verified**: actual use from Claude Desktop (not available here). The JSON example above follows its documented format (backslashes are escaped as `\\` for JSON) but was not tried in Claude Desktop.

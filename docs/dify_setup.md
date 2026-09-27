# Connecting the Interface Adjudicator to Dify

Goal: let colleagues who do not write code ask, in Dify's chat interface, "Where does MAD2 bind FAT10? Does the evidence conflict?" — with the answer provided by this repository.

Dify is only a "front desk": the real data, the judging logic and the live / cited / pending labels all come from this repository; the language model inside Dify only restates what the tools return in plain words.

There are two ways to connect:

- **Way A (recommended): self-hosted Dify + the MCP server** (part A). Dify sees three tools directly through MCP: `list_cases`, `get_evidence`, `run_adjudication`.
- **Way B: an OpenAPI custom tool** (part B, the earlier way; suitable for Dify's cloud version).

> Status: steps A1–A2 (and A1b) were run on this machine and their results are written into each step. The MCP connection in the Dify UI (A5) was confirmed by the person who ran it. Steps A3, A4, A6 and A7 are browser steps done by a person; this document describes them, but the exported app file and the screenshots are **not in the repository yet**, so what the exported file contains has not been checked (see A7).

---

## A. Self-hosted Dify + MCP (way A)

### A1. Deploy Dify (Dify's official Docker self-hosting method)

Put Dify in a separate directory **outside this repository**, `C:\Users\<you>\dify`; this repository contains no Dify code. Docker Desktop must be installed and running (Dify's own README asks for at least 4 GiB of RAM for Docker).

```powershell
cd C:\Users\<you>
git clone --depth 1 --branch <version> https://github.com/langgenius/dify.git dify
cd dify\docker
copy .env.example .env
docker compose up -d
```

- Version: replace `<version>` with Dify's latest release tag (`git ls-remote --tags --refs https://github.com/langgenius/dify.git` lists them). The version that was actually deployed here is recorded in `docs/progress.md`.
- The first start pulls a dozen images and takes a few minutes to a quarter of an hour.
- What actually happened: `docker compose up -d` exited 0; the `nginx / api / worker / web / plugin_daemon / db_postgres / redis / weaviate / sandbox / ssrf_proxy` containers were all Up; `http://localhost/install` returned HTTP 200.
- It uses ports 80 / 443 on the machine by default; if they are taken, change `EXPOSE_NGINX_PORT` / `EXPOSE_NGINX_SSL_PORT` in `.env`.
- To stop: `docker compose down` (the data stays in `dify\docker\volumes\`). For upgrades or migration see Dify's official documentation.
- After Docker Desktop restarts (for example after a reboot) the Dify containers come back by themselves; the plugin daemon may restart a few times until Postgres is ready.

### A1b. Let Dify's SSRF proxy allow `host.docker.internal` (required)

Every outbound request from Dify, MCP tools included, goes through `ssrf_proxy` (squid). By default it refuses every private / local address, so without this step adding the MCP server in Dify fails with `403 Forbidden for url 'http://host.docker.internal:8765/mcp'` (in the proxy log it is `TCP_DENIED/403`; the request never reaches this repository's server).

Use the switch Dify provides for this; it allows only this one domain and every other private address stays refused. Edit `dify\docker\.env` and add (or fill in) this line:

```
SSRF_PROXY_ALLOW_PRIVATE_DOMAINS=host.docker.internal
```

Then recreate only the proxy container:

```powershell
cd C:\Users\<you>\dify\docker
docker compose up -d ssrf_proxy
```

**Tested**: after this change, an MCP `initialize` request sent from inside the `docker-api-1` container, through the proxy (`http://ssrf_proxy:3128`), to `http://host.docker.internal:8765/mcp` returned HTTP 200 (proxy log `TCP_MISS/200`); before the change the same request was `TCP_DENIED/403`. The `/etc/squid/dify_allow_private.conf` generated inside the container contains `acl dify_allowed_private_domains dstdomain host.docker.internal`.

### A2. Start this repository's MCP server (HTTP)

From the repository root, in an environment where the dependencies are installed (`pip install -r requirements.txt`):

```powershell
$env:DEEPSEEK_API_KEY = "<your key>"      # without a key list_cases / get_evidence still work and run_adjudication returns an error
python -m mcp_server --transport http --port 8765 --allow-host host.docker.internal:8765
```

- It listens on the local machine only, `127.0.0.1:8765`; the address is `http://127.0.0.1:8765/mcp`.
- `--allow-host host.docker.internal:8765` makes the server accept the `Host` header sent by a Dify container (by default the server rejects unfamiliar Host values, a protection against DNS rebinding).
- The server has no authentication of its own, so **do not** expose it to the local network with `--host 0.0.0.0`.
- Keep the key only in this terminal's environment; never put it into Dify.

**Tested**: from inside Dify's `api` container, an MCP `initialize` request to `http://host.docker.internal:8765/mcp` returned HTTP 200 with the server capabilities (so a container can reach, through `host.docker.internal`, a service on the host that listens only on 127.0.0.1).

### A3. [You act in the browser] Create the administrator account

1. Open `http://localhost/install` in a browser.
2. Enter an email, a username and a password, and press "Setup". **This account and password stay only in your own Dify; do not send them to anyone.**
3. Log in at `http://localhost` with the new account.

### A4. [You act in the browser] Configure a model

Dify's own chat needs a language model (this is separate from the DeepSeek key of the MCP server).

1. Top-right avatar → **Settings → Model Provider**.
2. Install **DeepSeek** (from the plugin marketplace; needs internet access) and enter your DeepSeek API key.
3. In the system model settings, choose `deepseek-chat` as the default reasoning model.

### A5. [You act in the browser] Connect the MCP server (connection confirmed by the person who did it)

1. Top menu **Tools → MCP → Add MCP Server (HTTP)**.
2. Server URL: `http://host.docker.internal:8765/mcp`; name: "Interface Adjudicator"; any icon.
3. Save and authorise; you should see three tools: `list_cases`, `get_evidence`, `run_adjudication`.
4. If the connection fails, see A8.

### A6. [You act in the browser] Build the Q&A app

1. **Studio → Create from blank → Agent**, named "Protein interface Q&A".
2. Prompt: paste everything under "System prompt" in [`integrations/dify/system_prompt.md`](../integrations/dify/system_prompt.md).
3. Tools: add the three tools of the MCP server you just connected.
4. Model: `deepseek-chat`.
5. Opening message: see the same file.
6. Test in the preview pane with the three questions below. Every piece of information in an answer should carry one of "live / cited / pending", and no number or citation the tools did not return should appear.

Test questions:

- "Where do FAT10 and MAD2 bind each other? Do the MD results agree with the literature?" (should call `get_evidence`, report that the MD's C-terminal region and the literature / NMR UBL1 6–81 disagree, and not say which side is right)
- "Please run a full investigation." (calls `run_adjudication`; slower, and costs a little DeepSeek credit)
- "What about MDM2 and p53?" (should call `list_cases` / `run_adjudication` and say that this pair has no molecular-dynamics data, so that item is pending)

The prompt lets the app answer in the language the user asked in.

### A7. Export the app configuration (DSL) [You act in the browser]

App page, top-right menu → **Export DSL** (**do not** tick "include secrets"). Save the downloaded `.yml` as `integrations/dify/interface-adjudicator-qa.yml`. Before committing, check that the file contains no API key.

Dify's build mode may also create extra items for the app (a configuration note and skills). Whether such items are part of the exported DSL has to be read from the exported file itself; this document does not claim either way until the file is in the repository.

### A8. Troubleshooting

- **MCP connection fails**:
  1. First make sure the MCP server is running (opening `http://127.0.0.1:8765/mcp` in a browser returns an HTTP 400 JSON error `Missing session ID`, which shows the service is listening; checked on this machine).
  2. The start command must include `--allow-host host.docker.internal:8765`; otherwise the server returns HTTP 421 `Invalid Host header` (checked here with a forged Host header).
  3. A 403 rather than a 421: see A1b (Dify's `ssrf_proxy` blocked the request; it was not refused by this repository's server).
- **`run_adjudication` times out**: it is a full investigation and takes tens of seconds; raise the tool-call timeout in Dify.
- **The tool was called with `case_id` "fat10-mad2" and failed** (reported by the person who ran Dify; no log was saved): the MCP server now normalises case ids, ignoring case, hyphens, underscores and spaces (`fat10-mad2`, `FAT10 MAD2` and `fat10_mad2` are the same case), and an unknown id returns an error that lists the valid ids.
- **An answer contains a number or citation the tools never gave**: the prompt is not constraining the model well; reset it to the content of `integrations/dify/system_prompt.md` and record it as a defect.

---

## B. OpenAPI custom tool (way B)

Goal: let colleagues who do not write code ask, in Dify's chat interface, "Where does MAD2 bind FAT10? Does the evidence conflict?", with the answer provided by this repository's FastAPI service.

> Note: this part is written for Dify's general interface and was not walked through step by step on a specific version; menu names may differ slightly between versions.

### B1. First get the API running on your machine

Either way:

```bash
# A. Docker (recommended)
docker compose up --build            # reads the environment variable DEEPSEEK_API_KEY (may be empty)

# B. Local Python
pip install -r requirements.txt
uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Check: open `http://localhost:8000/health` in a browser; you should see `"status": "ok"`. When `llm_configured` is `false`, `/evidence` still works, while `/adjudicate` and `/debate` refuse (set `DEEPSEEK_API_KEY` in the environment).

If you do not want to set up Dify, simply opening `http://localhost:8000/` in a browser gives a usable web interface (see the README).

### B2. Import the OpenAPI file

The interface description is in `docs/openapi.json`, generated from the code by a script (regenerate it after changing the API):

```bash
python scripts/export_openapi.py            # writes docs/openapi.json
python scripts/export_openapi.py --check    # checks whether it is out of date
```

In Dify: **Tools → Custom → Create custom tool → choose "Import OpenAPI"**, and paste the whole content of `docs/openapi.json` (or upload the file).

**Change the server address to one Dify can really reach** (the file says `http://host.docker.internal:8000` by default):

| Where Dify runs | Server address to use |
|---|---|
| Docker on the same computer | `http://host.docker.internal:8000` (on Linux, add `extra_hosts: ["host.docker.internal:host-gateway"]` to the relevant services in Dify's compose file; on a self-hosted Dify also do step A1b) |
| The API and Dify in the same Docker network | `http://adjudicator:8000` (the service name in `docker-compose.yml`) |
| Dify's cloud version | the cloud cannot reach your localhost; build a protected public entry as in section B4 |

After the import these tools appear (the names come from the operationId of the API):

| tool | what it does | needs a key | time |
|---|---|---|---|
| `get_evidence` | real MD evidence + literature-expected region + conflict flag | no | fast |
| `health_check` | whether the service is online and whether an LLM key is configured | no | fast |
| `service_info` | service description and list of endpoints | no | fast |
| `list_cases` | the preset cases for the web page | no | fast |
| `run_query` | one complete query for the web page: plain-language conclusion + evidence labelled live / cited / pending + time and cost of this query (parameters: `case_id`, or two UniProt accessions) | yes | slow |
| `run_query_stream` | the same query as `run_query`, but pushes every step live as Server-Sent Events (for the web page). **Do not** use it as a Dify tool: Dify's custom tools cannot read an event stream; use `run_query` or MCP | yes | slow |
| `run_adjudication` | let the investigator agent look things up itself and give a conclusion | yes | slow |
| `run_debate` | MD advocate / NMR advocate / judge debate | yes | slow |

On the tool page press "Test"; try `health_check` and `get_evidence` first.

### B3. Build the simplest chat flow (Chatflow)

In Dify create a **Chatflow** with these nodes in order:

1. **Start**: use the default user input.
2. **Tool node**: choose `get_evidence` (no parameters).
3. **LLM node**: use the output of the tool node as context; for the system prompt enter:

   > You explain protein-interface evidence. Answer only with what the tools returned; never invent residues, numbers, PDB IDs or citations. Tell three kinds of information apart and label them clearly: **live** (measured or retrieved by the tool during this run), **cited** (a conclusion from the published literature, not re-derived by this system), **pending** (no data yet). If the tool returned a contradiction flag, say plainly that "the MD result disagrees with the literature expectation", do not decide which side is right, and suggest validating with an experiment. Answer in the language the user asked in.

4. **Direct reply**: output the answer of the LLM node.

To let users "dig deeper", add a **conditional branch**: when the user message contains "in-depth investigation" or "full investigation", go through `run_adjudication` (put the user's question into its `goal` parameter); otherwise take the `get_evidence` path above. Note:

- For these two slow tools, **raise the tool / HTTP timeout in Dify**; the default is usually shorter than one full investigation.
- They use DeepSeek credit; do not put them in an automatic flow that is triggered often.
- The API currently covers only the FAT10–MAD2 pair; another protein pair is not selected just because the question uses other names.

### B4. Exposing a local API safely

**This API has no authentication of its own.** Anyone who can reach it can call `/adjudicate` and `/debate` and use up your DeepSeek credit. Therefore:

1. **Keep it visible on the local machine only, by default.** With Docker write the port in `docker-compose.yml` as `"127.0.0.1:8000:8000"` (the current `"8000:8000"` opens it to the whole local network); with uvicorn use `--host 127.0.0.1`.
2. **When Dify and the API run on the same machine, no public entry is needed**; use the internal addresses in the table of section B2.
3. **When a cloud Dify must reach it**, do not open the port directly. Put a reverse proxy with a key (Caddy / nginx) in front of the API, or a tunnel with access control (Cloudflare Tunnel + Access, Tailscale), and:
   - require a key in the request header (in Dify's custom tool "authorization method" choose API Key and enter the key there), which the proxy checks before forwarding;
   - if people only need to see the evidence, **let only `GET /evidence` and `GET /health` through** the proxy, and not `/adjudicate` or `/debate`;
   - rotate the key regularly and keep access logs and rate limits in the proxy.
4. **Keep `DEEPSEEK_API_KEY` only in the environment of the machine that runs the API**; do not write it into Dify workflows, prompts, the repository or screenshots.
5. Do not post the run log in `results/` anywhere public; it contains the full text of the questions asked.

### B5. Frequently asked questions

- **A tool call reports a connection failure**: the server address is wrong (see the table in section B2) or the API is not running. First open `/health` from the environment Dify runs in.
- **`run_adjudication` returns 400**: `DEEPSEEK_API_KEY` is not set in the environment that runs the API.
- **An answer contains numbers or citations that no tool gave**: the prompt of the LLM node is not constraining the model; reset it with the system prompt in section B3 and record it as a defect.
- **The tools in Dify did not change after the API changed**: run `python scripts/export_openapi.py` again and re-import in Dify.

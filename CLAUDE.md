# CLAUDE.md — Interface Adjudicator → Agent 2.0 (autonomous run)

## What this repo is

The **Interface Adjudicator**: an LLM agent (ReAct loop, DeepSeek via OpenAI-compatible
client in `agent/llm_client.py`) that adjudicates protein–protein interfaces from real
evidence — PDBe structures, UniProt sequence, 100 ns MD contact occupancy, PubMed — and
convenes a multi-agent debate (MD advocate vs NMR advocate vs judge) when evidence and
literature conflict. Case study: FAT10–MAD2. See README.md and FLOW.md.

## Goal of this run

Keep every v1 capability. Add what good agent projects have and v1 lacks: tests, run
logging (tokens/latency/cost), and above all a **benchmark** — v1 is evaluated on one
case (n=1); v2 must report accuracy over several cases. Then make it usable by
non-technical people (Dify via the existing FastAPI).

## How to run (read this first, every session)

- Work through the steps below **in order, automatically**. Do not ask for confirmation
  between steps.
- If `pytest` is missing, run `pip install --ignore-installed pytest -r requirements.txt` first (the flag
  avoids a debian-owned PyJWT that blocks a plain install). This is
  environment setup, not a code change, so it does not break S1's read-only rule.
- Find the first step not marked `[x]` in `docs/progress.md` (create it on first run,
  listing S1, S1b, S2–S6, S6b, S7, S8, C1–C3 unchecked). Do that step.
- Each step is small. After finishing it, run its **Self-check**. If it passes, call the
  **`reviewer` subagent** (`.claude/agents/reviewer.md`). Give it only the step number —
  not your reasoning or a summary of what you did; it reads the diff itself.
- If the reviewer returns `VERDICT: PASS`: commit with message `S<n>: <summary>`, mark
  the step `[x]` in `docs/progress.md` with one line of notes plus the reviewer verdict,
  commit, and continue to the next step.
- If the reviewer returns `BLOCK`, fix every listed issue and go through self-check and
  review again. A BLOCK counts as a failed attempt. Never argue with or override the
  reviewer; if you believe it is wrong, record the disagreement in `docs/progress.md`
  and stop for the human.
- If the self-check or review fails, fix and retry, **at most 3 attempts**. If it still fails, write
  `FAILED: <what, why, what you tried>` under the step in `docs/progress.md`, commit, and
  **stop the whole run**. Do not continue past a failed step.
- At a **GATE**, commit, write `WAITING FOR HUMAN: <what to review>` in
  `docs/progress.md`, and stop. Resume only when the human replies "通过" (approved) or
  gives corrections.
- If a step needs something you do not have (API key, blocked network), write
  `BLOCKED: <reason>`, commit, and stop.

## Iron rules (inherited from v1 — never weaken)

- **No fabricated data.** Unavailable tools report `pending`, never placeholder numbers.
  Every residue, score, ID and citation in any output comes from a tool call or a
  committed file. Any external ID you write into a doc (UniProt, PDB, PMID) must be
  verified by a real API call in this run, and the call recorded.
- **No false ground truth.** The FAT10–MAD2 finding (MD interface on FAT10's C-terminal
  region vs literature/NMR UBL1 6–81) stays reported as a contradiction. Never change
  that conclusion or its wording.
- **No answer leakage in the benchmark.** For a benchmark pair, the agent must not be
  able to retrieve the experimental complex structure used as ground truth (filter it out
  of PDBe results, and out of literature if it states the interface directly). Document
  how leakage is prevented.
- **v1 behaviour stays identical** for the FAT10–MAD2 run unless a step explicitly says
  otherwise; the regression test guards this.
- Secrets only from environment variables (`DEEPSEEK_API_KEY`). Never commit or print keys.
- Metrics in any doc are copied from files produced by scripts. Never type a number by hand.
- `pytest -q` must pass offline with no API key after every step. Live tests are marked
  `@pytest.mark.live` and skipped by default.

## Steps

### S1 — Current-state inventory (read-only, no code changes)
Write `docs/current_state.md` (Chinese, concise): one-line purpose; one line per
file/module; typical tool-call order in a full run; which data is live / snapshot /
local file / pending; how to run locally (commands, env vars); what has no test
coverage; the 3 most fragile points.
**Self-check:** all 7 sections present; every file path mentioned exists; the
live/snapshot/pending list agrees with README's status table (list any disagreement).

### S1b — Fix the S1 inconsistencies
Fix the three disagreements S1 found. (1) Wire the live PDBe MCP query into the agent's
`fetch_structures`; if it cannot be made to work, change README to describe honestly what
the code does. (2) Replace the three 1–80 domain defaults with the verified 6–81 and add a
regression test. (3) Use one name for the PISA tool everywhere.
**Self-check:** no 1–80 domain default remains and the regression test pins 6–81; the
PISA name is identical everywhere; `fetch_structures` uses the MCP query when it is
reachable and falls back otherwise (fallback tested offline, live path in a `live` test);
README's status row matches what the code does and what has actually been verified;
`pytest -q` passes offline. After the reviewer passes S1b, run `pytest --run-live` to check
the MD residue numbering against the real UniProt sequence, record the result in
`docs/progress.md`, then continue from S4.

### S2 — Offline smoke test + CI
`tests/` with a fake LLM client fixture that returns scripted tool calls. One
end-to-end test: `run_agent.run()` on the FAT10–MAD2 goal reaches
`submit_adjudication` and the result reports the C-terminal vs UBL1 contradiction. Unit
tests for `validate_residues` and `map_residues`. `pytest.ini` with the `live` marker
skipped by default. `.github/workflows/tests.yml` running `pytest -q` on push.
**Self-check:** `pytest -q` passes with network disabled and `DEEPSEEK_API_KEY` unset.

### S3 — Run logging
Every agent/debate run appends one JSON line to `results/runs.jsonl`: timestamp, model,
goal, number of LLM calls, prompt/completion tokens, wall-clock seconds, ordered tool
list, verdict fields. Cost from `config/pricing.yaml` (USD per 1M tokens per model, with
`last_checked` date and source URL).
**Self-check:** a test with the fake client produces one well-formed line; S2 tests
still pass.

### S4 — Benchmark design (document only)  → GATE
Write `docs/benchmark_design.md`: 5 protein pairs that have an experimentally solved
complex in the PDB, chosen so each has literature or domain annotation the agent can
use. For each pair: both UniProt IDs, the ground-truth PDB complex ID, the ground-truth
interface (residues or domain) as reported by PDBe for that entry, and the evidence the
agent WILL see. Define the scoring rule (e.g. correct binding domain = hit; overlap of
predicted vs true interface residues). Define leakage prevention. Note what the agent
lacks for these pairs compared with FAT10–MAD2 (e.g. no MD run → MD tool returns
`pending`).
**Self-check:** every ID was verified by a live API call, with the calls listed in an
appendix.
**GATE:** stop and wait for the human to approve or correct the design.

### S5 — Generalise inputs
Make tools take the protein pair as input (UniProt IDs, optional MD score file) instead
of FAT10/MAD2 constants. FAT10–MAD2 becomes `cases/fat10_mad2.yaml`. Add the leakage
filter from S4.
**Self-check:** regression test shows the FAT10–MAD2 run is unchanged; a test proves a
benchmark pair's ground-truth PDB ID never appears in tool outputs.

### S6 — Benchmark runner
`scripts/run_benchmark.py --cases benchmark/ --runs N` writes
`results/benchmark.json` and `results/benchmark.md`: per-case score, overall accuracy,
verdict stability across runs, median latency, mean cost (from S3 logs). `--dry-run`
uses the fake client. If `DEEPSEEK_API_KEY` is set, run live with N=3; otherwise mark
the live run `BLOCKED` and continue.
Also add a **no-tool baseline**: the same 5 pairs, the same model, no tools at all — it
answers from its own knowledge where the interface is, scored with the same rule (recall
≥ 50% and predicted span ≤ 2× the true span). The results table shows the agent and the
baseline side by side. The report must say honestly that the model may have seen these
classic complexes in training; the baseline measures what the agent adds over the model
"reciting the answer". Baseline runs use the same N and are logged like agent runs
(`DEEPSEEK_API_KEY` from the environment).
**Self-check:** dry-run test passes (baseline included, fake client); report numbers come
only from the JSON; the report contains the agent-vs-baseline table and the
training-data caveat.

### S6b — Error injection
Using FAT10–MAD2, build at least 4 error-injection cases: residue-numbering shift,
residue beyond the sequence length, fabricated MD scores, wrong UniProt accession. Run
each through the agent's validation path; count how many are caught (blocked, flagged or
reported as invalid) versus passed through. Add the intercept rate to the evaluation
report (numbers from the script's JSON only).
**Self-check:** offline test proving each injected error is caught or, if not, is counted
as a miss (never hidden); the report's intercept rate matches the JSON.

### S7 — Non-technical access (Dify)
Add summaries, descriptions and examples to every FastAPI endpoint; export the schema to
`docs/openapi.json` via a script. Write `docs/dify_setup.md` (import the OpenAPI file as a
Dify Custom Tool; a simple chatflow; exposing a local API safely) and
`docs/user_guide.md` (one page for a non-technical scientist: what it does, what it will
not do, how to read verdicts and real/cited/pending labels, three example questions).
**Self-check:** test that `docs/openapi.json` matches the app schema; docs contain no
metrics.

### S8 — README v2
Add a "v1 → v2" section (what was added and why) and a results table generated by a
script from `results/benchmark.json`. Keep the honest status table.
Also write `docs/business_case.md`: manual workflow vs agent workflow; cost and time per
run (filled in by a script from the result files, never typed by hand); risks and
mitigations. Manual (human) time is not measured; never estimate it. (S8 first wrote it as
`TBD — 人工基线`; C3 replaced that placeholder with automated workload metrics and the plain
statement that manual time was not measured.)
**Self-check:** running the generator twice gives no diff (README table and
business_case numbers); business_case has no hand-typed numbers and says manual time was not
measured. Then write a final summary in `docs/progress.md` and stop.

### C1 — Merge and clean up (git)
Merge the working branch into `main` and push (conflicts resolved in favour of the
working branch). Then check whether `claude/eloquent-meitner-xhb070` and
`claude/exciting-brown-n4qvdu` are fully contained in `main`: delete the remote branch if
so; if not, keep it and report what is missing. Never delete
`claude/audio-llm-mental-health-setup-pjrkc0` or `gh-pages`.
**Self-check:** `pytest -q` passes on merged `main`; `main` pushed; the containment check
is recorded in `docs/progress.md`.

### C2 — Web client
A single page served by the existing FastAPI at `/` (no new dependencies): pick a preset
case or enter a protein pair, run, read a plain-language conclusion, an evidence table
labelling each item live / cited / pending, and the query's time and cost. Simple, for
non-technical users. README gives the start command and address.
**Self-check:** `GET /` returns 200; an end-to-end test with the fake LLM client;
`pytest -q` passes offline.

### C3 — Workload metrics
From `results/runs.jsonl` and the tool-call records, count per query: databases
accessed, API calls, records processed, time, cost; add them to the evaluation report.
Update `docs/business_case.md`: replace `TBD — 人工基线` with these automated metrics and
state plainly that manual time was not measured. Never estimate manual time.
**Self-check:** metrics come from a script reading the result files (no hand-typed
numbers); regenerating gives no diff; `docs/business_case.md` says manual time is not
measured.

### M1 — MCP server
Publish the agent as an MCP server with the official MCP Python SDK. At least three
tools: list cases, get evidence, run adjudication. Return structured results: the
conclusion, the evidence with live / cited / pending labels, time and cost. Call the
existing agent functions directly; do not copy logic. Support stdio (Claude Desktop) and
streamable HTTP (Dify); HTTP listens on localhost only by default.
**Self-check:** a test with an in-process MCP client and the fake LLM lists the tools and
calls them successfully; `docs/mcp.md` gives a Windows Claude Desktop config example and
the HTTP start command; `pytest -q` passes offline.

### M2 — Live process visualisation
A new SSE streaming endpoint that pushes events as the run proceeds: start, each tool call
(tool name and argument summary), tool result summary (with a source label), each debate
and review round, the final conclusion, cost. The web client becomes a live timeline that
shows step by step, in plain language, what the agent is doing, with the 中文 / English
switch. Keep the existing non-streaming endpoint.
**Self-check:** a fake-LLM test checks the event order and that the last event's
conclusion equals the non-streaming endpoint's result; `pytest -q` passes offline.

### M3 — Dify integration
Deploy Dify by its official Docker self-hosting method in a separate directory
`C:\Users\陈钰\dify`, outside this repo (no Dify code in the repo). Connect the M1 HTTP MCP
server (containers reach the host as `host.docker.internal`), build a Q&A app for
non-technical users, and export the app configuration as a DSL file into
`integrations/dify/`. Write `docs/dify_setup.md`: complete steps from a fresh deployment to
a working Q&A. Wherever the human must act in the browser (creating the admin account,
screenshots), write the exact steps, then **stop and wait for the human**.
**Self-check:** the DSL file exists and contains no secrets; `docs/dify_setup.md` steps
match what was actually run; `pytest -q` passes offline.

All of M1–M3 obey the iron rules: no fabricated data, no change to the FAT10–MAD2
conclusion.

## Repo map (v1)

- `agent/run_agent.py` ReAct loop · `agent/tools.py` tools + TOOLS schema
- `agent/debate.py` multi-agent debate · `agent/compare.py` weak-vs-strong comparison
- `agent/structures.py` PDBe (MCP or verified snapshot) · `agent/literature.py` PubMed
- `agent/skills.py` + `skills/` role prompts · `analysis/` MD scoring, report, render
- `api/main.py` FastAPI: `/health`, `/evidence`, `/adjudicate`, `/debate`

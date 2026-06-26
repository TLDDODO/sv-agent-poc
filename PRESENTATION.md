# FAT10–MAD2 Agent — One-Page Talk Script

**Layout:** LEFT = labeled structure (the *finding*) · RIGHT = flow diagram (*how it works*).
Walk the RIGHT diagram, then turn to the LEFT image as the payoff.

---

## 0 · Handoff (Ryan presented the MD)  ~10s
> "Ryan covered the simulations — I ran the **100-ns replica** and built the layer **on top** that *audits* the model: an LLM agent. Let me walk you through it." *(turn to flow diagram)*

## 1 · Under the hood — the ReAct loop  ~25s
> "It's a **ReAct tool-calling loop**. The LLM gets a set of **tool schemas**; at each step it emits a **function call** with JSON arguments, my code **runs the real Python function**, and the model **sees that result before choosing its next call**. Temperature **0** for reproducibility. So it's not one prompt — it's a **loop conditioned on real data returned each step**."
> *Deep (if pushed):* converges in ~5 steps; I log the reasoning each step → auditable. Honest limit: it goes **forward**, doesn't yet loop **back** to re-call a tool when a result is weak — reactive, not yet iterative.

## 2 · Methodology — walk the diagram, box by box  ~90s

**① Goal** — *"One plain sentence: where does MAD2 bind FAT10? The agent figures out the rest."*

**② LLM agent (DeepSeek)** — *"It decides which tools to call and in what order — 9 tools, no fixed recipe. Single pass for now."*

**③ Four data branches — the colour code IS the honesty:**
- 🟢 **fetch_structures + validate_residues** — *"Real PDBe structures; validate_residues pulls the actual UniProt sequence and checks every residue label — does position 7 really hold a cysteine? Catches mis-numbering or fabricated residues."*
- 🟢 **get_md_interface_scores** — *"Real per-residue contact occupancy from our 100-ns MD."* — *Deep:* cpptraj `nativecontacts`, FAT10 (1–165) vs MAD2 (166–370), 4.5 Å, 2000 frames; each residue's score = **fraction of frames in contact**; I163, C162 ≈ 1.0.
- 🔵 **search_literature + get_expected_interface_region** — *"Searches PubMed; the expected site, UBL1 (6–81), is from Theng 2014 + the UniProt domain table — a **cited fact, not agent-derived**."*
- 🟠 **get_tool_prediction → PENDING** — *"AlphaFold / HADDOCK / PISA scores aren't in yet, so it returns **PENDING — it will not fabricate them**. Multi-tool consensus is honestly blocked, not faked."*
- **Close:** *"So every input is real, cited, or marked missing — the LLM is structurally prevented from inventing data."*

**④ Conflict check (deterministic)** — *"A plain-code domain-membership test, not the LLM: take the persistent interface — occupancy ≥ 0.5 — map each residue to its UniProt domain, ask: does any land in UBL1 (6–81)? I keep the **flag deterministic** so it isn't an LLM judgment call. The LLM's job is interpretation, not arithmetic."*

**⑤ convene_debate — three roles** — *"On conflict it convenes a **three-agent debate**: an **MD-advocate** told to argue its hardest for the C-terminal, an **NMR-advocate** for the N-terminal, and a neutral **judge**. Two advocates because the conflict is two-sided; a separate judge so it can't just agree with itself. All constrained to the real facts — they can't invent residues; the judge is forced into a **structured JSON** so it can't waffle."*

**⑥ Verdict — the 'no ground truth' design** — *"Read the box: it separates **'does it contradict the literature'** — factual, confidence **0.85** — from **'which side is right'** — **unknown, 0.1**. It outputs a **recommended experiment, not a winner.** With no experimental complex, declaring a winner would be dishonest."*

## 3 · The finding — turn to the LEFT image  ~35s
> "And here's what that verdict **looks like**. *(point)* Literature says N-terminal — **blue**. Our MD shows the C-terminal tail — **red**. They **don't even touch**. The red residues are the flexible **Gly-Gly tail** — a known **AlphaFold mis-docking artifact**. So the system **flagged our own model**, automatically, **with no fabricated data.**"

## 4 · Future  ~15s
> "Next: make it **actually loop** — re-call tools when a result is inconclusive; fill the orange boxes with real **HADDOCK / AlphaFold** scores; run **multiple replicas**."

---

## 🛡️ If grilled (pull the matching one)

**Why not just one LLM?** — *"It would hallucinate every number. The whole diagram is about fetching real data in — green = real, orange = 'I don't have it.' Grounding + traceability is what an LLM-alone can't give."*

**How many rounds? Does it re-call tools?** — *"~5, each using prior results — it reacts. But single pass — the diamond fires once. True looping is next; I'm not overclaiming."*

**Why three LLMs — isn't it the same model talking to itself?** — *"Same model, **enforced roles**, and it measurably changes the output: when the MD-advocate **conceded**, the judge rubber-stamped an over-confident **'reject, 0.95'**; when I forced it to **fight**, the verdict became calibrated — **0.85 contradiction, 0.1 on which side is right**. Adversarial roles reduce one-sided overconfidence."*

**How do you know UBL1 is correct?** — *"I don't. The verdict says 'which side is right = unknown.' The method only claims they **disagree** — that's the line I won't cross."*

**Is the data real?** — *"Green: real (MD, UniProt, PDBe). Orange: PENDING, not faked. Blue: cited. It's all on the diagram."*

**Isn't the MD just the AlphaFold pose — circular?** — *"Yes — the MD reflects the AF3 starting model, so it's a **consistency check, not independent validation**. The value is catching that the chosen model contradicts the literature **before** we waste downstream experiments on it."*

---

## 🌱 1-minute reflection
> "My biggest takeaway is how **fast** computational biology is moving. I used to think it was mostly running existing software on data — but here I saw **AI agents, LLMs, MD, and structural biology fusing**, with new methods appearing constantly. Concretely, it changes how I'll work: instead of trusting a tool's output as the answer, I'll build **automated cross-checks that flag when a model contradicts the literature** — exactly like our pipeline caught our own AlphaFold model docking MAD2 to the wrong domain. I'll treat AI as a **skeptical collaborator, not an oracle**."

---

**Backbone (if you lose the thread):**
> goal → LLM picks tools → tools inject only **real / cited / honestly-missing** data → a **deterministic** check finds the model-vs-literature conflict → a **steelmanned debate** weighs it → a **structured verdict** that flags the contradiction as fact but **refuses to claim the truth**, and recommends an experiment.

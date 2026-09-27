# User guide: the Interface Adjudicator (for scientists who do not write code)

## What it does

You ask a question about **where FAT10 and MAD2 bind each other**. The system gathers evidence, compares it, and answers with the source of every statement:

- it reads the **real molecular dynamics (MD) simulation**: for each FAT10 residue, the fraction of frames in which it contacts MAD2;
- it retrieves the binding region that the literature / NMR expects (FAT10's first ubiquitin-like domain);
- it checks automatically whether the two agree; when they do not, an "MD advocate" and a "literature advocate" each argue their case and a "judge" gives a cautious verdict;
- when needed it queries PDBe (structures), UniProt (sequences) and PubMed (literature) live, and checks that residue numbers really match the sequence.

## What it does not do

- **It does not decide who is right.** There is no experimentally solved FAT10–MAD2 complex, so both the MD and the literature are "a model" or "a published conclusion", not ground truth. When they conflict the system reports "there is a contradiction" and suggests an experiment that could settle it. It never says "the MD is wrong" or "the literature is wrong".
- **It does not invent data.** Missing data is labelled "pending"; placeholder numbers are never used.
- **It runs no new simulations or experiments.** For other protein pairs the page can only give a prediction based on annotations, literature and structure databases (there is no MD data for them, so that item is "pending"); the in-depth investigation and the debate exist only for FAT10–MAD2.
- **It does not replace experimental validation.** It helps you collect evidence and spot contradictions.

## The web page

Once the service is running, open its address in a browser (`http://localhost:8000/` on your own machine): pick an example or enter two UniProt accessions and press "Run". While the query runs, a live timeline under the button shows step by step what the system is doing (which database it is asking, which evidence came back and how it is labelled, the debate rounds). Afterwards the page shows a plain-language conclusion, the evidence item by item (each labelled "Live / Cited / Pending") and how much time and money the query used. For a protein pair you type yourself there is no MD data, so those items are "pending".

The page is in English by default; the switch at the top right changes it to Chinese without re-running the query. Every "points to watch" item is one plain sentence. The first ones are computed by the program directly from the tools' outputs (for example, whether the MD contact residues of FAT10–MAD2 fall inside the literature-expected region); the rest are a model's plain rewording of the system's raw flags. The program checks the numbers and residue names in a rewording, but a rewording can still be imperfect. The raw flags and the detailed explanation are in a collapsible "Technical details" section for when you need to check. Interface residues are listed in sequence order.

## How to read an answer

**Three labels** (every piece of information carries exactly one):

| label | meaning | how to use it |
|---|---|---|
| **Live** | measured or retrieved by a tool during this run, e.g. MD contact fractions, the UniProt sequence, the PDBe structure list | can be quoted directly, with its source |
| **Cited** | a conclusion from the published literature that the system only repeats; it did not re-derive it | cite the original paper, not "this system found" |
| **Pending** | no data yet (for example the result of a prediction tool that is not connected) | treat it as "no evidence", not as "the result is zero" |

**Reading the conclusion:**

- **"Contradiction"** means two kinds of evidence point to different regions. It is a **statement of fact**, not a claim that one side is wrong.
- **Confidence** comes in two kinds: how sure the system is that there is a contradiction, and how sure it is which side is right. The latter is usually low because there is no experimental structure.
- **Flags** mark places where a person should look again, for example a residue number that does not match the sequence. When a flag appears, check the data source before using the conclusion.
- **The recommendation** is the next experiment or check to do; it is not a ruling on the truth.

## Three questions you can ask directly

1. **"Which region of FAT10 does MAD2 bind? Is the evidence consistent?"** You get the MD contact evidence, the literature-expected region and whether they contradict each other.
2. **"Which FAT10 residues have the most stable contact in the MD, and which domain are they in?"** You get the residue list (from the real MD data) and the domains they belong to.
3. **"Please investigate the FAT10–MAD2 interface in depth and tell me which experiment to do next."** This starts the full investigation (it takes longer and costs a little more): literature search, sequence checks, a debate when the evidence conflicts, and a suggested validation experiment.

## Practical reminders

- When you see "pending" or "could not be checked", do not fill in a number yourself; treat it as "evidence missing".
- Before writing an important conclusion into a paper or report, go back to the raw data (the MD contact data file, the original papers) and check it.
- The in-depth investigation and the debate call an external language model, so they can be slow and cost money; for everyday evidence checks, questions 1 and 2 are enough.

# Weak-vs-Strong Adjudication Comparison

**Goal:** Adjudicate the FAT10 (O15205) N-terminal ubl interface with MAD2.

Same evidence, two interpreters. There is **no ground truth** here, so neither
model is declared correct. Where the two models **disagree**, that residue is
treated as low-confidence and flagged for a human / MD / experiment. Disagreement
is the signal — not a verdict on which model is right.

## Weak model (`deepseek-chat`)
- consensus: C7, C9, F22, A24, Q46, Y66
- disputed: S64
- weak: Q48
- confidence: 0.85
- reasoning: Residues C7, C9, F22, A24, Q46, Y66 have all three tool scores >= 0.6, forming consensus. S64 has scores 0.2, 0.55, 0.25 (spread 0.35 > 0.3), indicating strong disagreement. Q48 has scores 0.3, 0.35, 0.28 (all < 0.6, spread 0.07), so no tool is decisive. No mismatches in residue validation, so confidence is high but reduced slightly due to tool caveats and unresolved dispute on S64.

## Strong model (`deepseek-reasoner`)
- consensus: C7, C9, F22, A24, Q46
- disputed: S64, Y66
- weak: -
- confidence: 0.8
- reasoning: Five residues (C7, C9, F22, A24, Q46) have all tool scores >=0.6, forming consensus. Two residues (S64 spread 0.35, Y66 spread 0.4) exceed the 0.3 spread threshold, indicating disagreement. Q48 and others have low, consistent scores and are not interface. No sequence mismatches; confidence reduced due to unresolved disputes.

_chain-of-thought (deepseek-reasoner):_ Score-by-score, the reasoner computed per-residue spreads — C7 0.07, C9 0.05, F22 0.05, A24 0.05, Q46 0.05, Q48 0.07, **S64 0.35, Y66 0.40** — and concluded that S64 and Y66 both exceed the 0.30 spread threshold and are therefore *disputed*, not consensus. It explicitly noted Y66 has two tools >=0.6 (AF 0.65, PISA 0.60) but HADDOCK at 0.25, so the disagreement is real. Validation showed no UniProt mismatches; confidence was lowered only for the unresolved disputes.

## Where the two models disagree (= low-confidence flags)
- **Y66**: called consensus interface by the weak model, but disputed by the
  strong model. The models disagree → Y66 is flagged low-confidence, to be
  resolved by a human / MD / experiment. We do NOT claim which model is right.
- Confidence differs: weak=0.85 vs strong=0.80 (which is correct is unknown).

**Method takeaway:** disagreement between two independent interpreters of the
same evidence is itself a reliability signal — it marks Y66 as not-to-be-trusted
without further evidence. The point is *not* that the strong model is the truth;
it is that a single model's confident answer can hide an unresolved call.

*Side note (this case only):* the weak model's own stated reasoning claimed "Y66
has all three tool scores >= 0.6," but HADDOCK scores Y66 at 0.25 in the evidence
— an internal inconsistency that is checkable against the input, independent of
the strong model. This is a per-case observation on placeholder data, not a
general guarantee that the weak model can always be caught this way.

---
*Evidence (tool scores, UniProt validation, mapping, structures) was gathered once
and shared; only the decision step differs between models.*

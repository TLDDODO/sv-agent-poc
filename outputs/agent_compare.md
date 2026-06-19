# Weak-vs-Strong Adjudication Comparison

**Goal:** Adjudicate the FAT10 (O15205) N-terminal ubl interface with MAD2.

Same evidence, two interpreters. The strong model is the baseline; divergences
show where the cheap/weak model's judgement is risky.

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

## Where the weak model diverges
- Weak model **over-claims** as interface (strong does not): **Y66**
- Disputed-set differs: weak-only -, strong-only ['Y66']
- Confidence: weak=0.85 vs strong=0.80 (weak is more confident while being more wrong)

**Takeaway:** the cheap model would have told the team "Y66 is a confident
interface residue — build the MD model on it." The data disagrees (HADDOCK scores
Y66 at 0.25 vs ~0.6 for the others, spread 0.40), and the strong baseline caught
it. This is the concrete case for using a stronger model as an audit baseline
rather than trusting a single cheap model.

---
*Evidence (tool scores, UniProt validation, mapping, structures) was gathered once
and shared; only the decision step differs between models.*

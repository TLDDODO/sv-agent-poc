"""Disentanglement losses for the dual-encoder intervention (RP.md "Approach" point 1).

The architecture adds an emotion tower beside Qwen2-Audio's semantic (Whisper-style) tower. Left to
itself, the LLM would just keep riding the semantic channel (modality collapse), and the emotion
token would be ignored or learn to echo the same information. These losses are the "disparity /
orthogonality objective" that forces the emotion path to carry signal the semantic path does NOT --
the mechanistically-distinct counterpart to the data-level decoupling already measured in RP.md.

Both operate on two pooled, batch-aligned representations:
    sem  : (B, D) pooled semantic-tower features (Qwen2-Audio's projected audio features, mean-pooled
           over the audio frames), in the LLM hidden space.
    emo  : (B, D) the projected emotion token (emotion2vec embedding -> projection adapter), same
           LLM hidden dim, so both live in one space and a per-sample cosine is well-defined.

Two flavours, pick one in the train script (cosine is the cheaper default; decorrelation is the more
principled "statistically independent feature sets" objective and tolerates differing dims):

  cosine_orthogonality_loss  -- per-sample: push each pair (sem_i, emo_i) toward orthogonal
                                (cos^2 -> 0). Cheap, local, no batch-statistics dependence.
  decorrelation_loss         -- batch-level Barlow-Twins-style: push the cross-correlation matrix
                                between the two feature sets toward zero (every sem dim decorrelated
                                from every emo dim). Captures redundancy a per-sample cosine misses.

Neither needs an extra trained critic (unlike adversarial / MI-estimator approaches), which matters
on the ~9.75 GiB MIG slice -- they are a few matmuls on already-computed pooled vectors.
"""

import torch
import torch.nn.functional as F


def cosine_orthogonality_loss(sem: torch.Tensor, emo: torch.Tensor) -> torch.Tensor:
    """Mean squared cosine similarity between paired rows. 0 == every pair orthogonal.

    Squared (not raw) cosine so that anti-aligned (cos=-1) is penalised as much as aligned (cos=+1):
    we want the emotion token to be UNINFORMATIVE about the semantic token, and a perfectly negated
    copy is just as redundant as an identical one.
    """
    sem = F.normalize(sem.float(), dim=-1)
    emo = F.normalize(emo.float(), dim=-1)
    cos = (sem * emo).sum(dim=-1)  # (B,)
    return (cos ** 2).mean()


def decorrelation_loss(sem: torch.Tensor, emo: torch.Tensor, eps: float = 1e-5) -> torch.Tensor:
    """Barlow-Twins-style cross-correlation penalty. Standardise each feature over the batch, form
    the (D_sem x D_emo) cross-correlation matrix, and penalise the sum of its squared entries --
    driving every semantic dimension to be linearly uncorrelated with every emotion dimension.

    Works even if sem and emo have different widths (the matrix is rectangular), so it still applies
    if you pool the semantic tower at its native dim instead of the projected LLM dim. Needs B > 1
    (it standardises across the batch); returns 0 for a degenerate batch of size 1.
    """
    sem = sem.float()
    emo = emo.float()
    b = sem.shape[0]
    if b < 2:
        return sem.new_zeros(())
    sem = (sem - sem.mean(0)) / (sem.std(0) + eps)
    emo = (emo - emo.mean(0)) / (emo.std(0) + eps)
    cross = (sem.T @ emo) / b           # (D_sem, D_emo) cross-correlation
    return (cross ** 2).sum()

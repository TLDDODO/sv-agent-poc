from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class RegionFlexibility:
    region: str
    residue_range: str
    value: float            # normalized 0..1 flexibility


@dataclass(frozen=True)
class MethodProfile:
    method: str             # "MD" | "NMA"
    source_id: str          # trajectory id / ENM model id
    params: str             # e.g. "400 ns, AMBER ff19SB" / "ANM, cutoff 15A"
    regions: list[RegionFlexibility]


@dataclass(frozen=True)
class RegionVerdict:
    region: str
    stance: str             # "flexible" | "rigid" | "intermediate"
    value: float
    note: str


@dataclass(frozen=True)
class ExpertVerdict:
    expert: str             # "MD-view" | "NMA-view"
    method: str
    source_id: str
    overall: str
    region_verdicts: list[RegionVerdict]
    evidence_type: str      # "dynamics" | "normal-modes" | "inference"
    confidence: float
    limitations: str
    rationale: str


@dataclass(frozen=True)
class DebateExchange:
    speaker: str
    responds_to: str
    region: str
    agreement: str          # "agree" | "disagree" | "partial"
    comment: str


@dataclass(frozen=True)
class RegionConsensus:
    region: str
    md_value: float
    nma_value: float
    delta: float
    status: str             # "consensus" | "conflict"


@dataclass(frozen=True)
class AggregateJudgment:
    verdict: str
    confidence: float
    agreement_score: float          # Pearson r between MD and NMA profiles
    consensus_regions: list[str]
    conflict_regions: list[str]
    region_table: list[RegionConsensus]
    evidence_ids: list[str]
    dissent: list[str]

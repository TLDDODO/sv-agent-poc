from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class ResidueScore:
    residue: str            # e.g. "L9" (FAT10 N-terminal ubl numbering)
    score: float            # interface propensity 0..1


@dataclass(frozen=True)
class ToolPrediction:
    tool: str               # "AlphaFold-Multimer" | "HADDOCK" | "PISA-contacts"
    source_id: str          # model id / run id
    params: str
    scores: list[ResidueScore]


@dataclass(frozen=True)
class ToolVerdict:
    tool: str
    source_id: str
    called_interface: list[str]     # residues this tool flags as interface
    confidence: float
    limitations: str
    rationale: str


@dataclass(frozen=True)
class DebateExchange:
    speaker: str
    responds_to: str
    residue: str
    agreement: str          # "agree" | "disagree"
    comment: str


@dataclass(frozen=True)
class ResidueConsensus:
    residue: str
    scores: dict            # tool -> score
    mean: float
    spread: float           # max - min across tools
    status: str             # "consensus-interface" | "consensus-noninterface"
    #                         | "disputed" | "weak"


@dataclass(frozen=True)
class AggregateInterface:
    consensus_interface: list[str]
    consensus_noninterface: list[str]
    disputed: list[str]
    weak: list[str]
    agreement_score: float          # 1 - mean spread across residues
    confidence: float
    table: list[ResidueConsensus]
    evidence_ids: list[str]

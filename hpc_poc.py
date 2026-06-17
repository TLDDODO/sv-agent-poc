from __future__ import annotations
import json, hashlib, platform
from dataclasses import asdict, dataclass, field
from pathlib import Path
EGFR_UNIPROT = "P00533"
@dataclass(frozen=True)
class SearchSpec:
    query: str
    experimental_methods: list[str] = field(default_factory=list)
    max_resolution: float | None = None
    ligands: list[str] = field(default_factory=list)
    rows: int = 20
@dataclass(frozen=True)
class StructureCandidate:
    pdb_id: str; title: str; experimental_method: str | None; resolution: float | None; ligands: list[str]; mutation_status: str; apo_or_bound: str; source: str
@dataclass(frozen=True)
class ResidueMapping:
    pdb_id: str; chain_id: str; auth_seq_id: str; label_seq_id: int | None; canonical_uniprot_accession: str; canonical_uniprot_position: int; pdb_residue_name: str; canonical_residue_name: str; observed: bool
@dataclass(frozen=True)
class MdMetric:
    name: str; units: str; summary: dict[str, float]; source_selection: str; frame_range: tuple[int, int]
@dataclass(frozen=True)
class Claim:
    claim: str; evidence_type: str; source: str; confidence: str; confidence_reason: str; limitations: str
def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
def build_pdbe_payload(spec: SearchSpec) -> dict:
    fq = []
    if spec.max_resolution is not None:
        fq.append(f"resolution:[0 TO {spec.max_resolution}]")
    if spec.experimental_methods:
        fq.append("(" + " OR ".join(f"experimental_method:\"{m}\"" for m in spec.experimental_methods) + ")")
    if spec.ligands:
        fq.append("(" + " OR ".join(f"ligand_name:*{lig}*" for lig in spec.ligands) + ")")
    return {"query":"text:*EGFR* AND text:*T790M*","fq":fq,"fl":["pdb_id","title","resolution","experimental_method","ligand_name"],"sort":"resolution asc","rows":spec.rows}
def run() -> dict:
    spec = SearchSpec("EGFR T790M kinase domain drug resistance structures", ["X-ray diffraction", "Electron microscopy"], 3.5, ["ATP", "inhibitor"])
    structures = [StructureCandidate("2JIT","EGFR kinase domain T790M mutant bound to inhibitor","X-ray diffraction",2.8,["inhibitor"],"T790M","ligand-bound","hpc_mock"), StructureCandidate("2ITY","EGFR kinase domain reference inhibitor complex","X-ray diffraction",2.6,["inhibitor"],"WT","ligand-bound","hpc_mock")]
    mappings = [ResidueMapping(s.pdb_id,"A","790",790,EGFR_UNIPROT,790,"MET" if s.mutation_status == "T790M" else "THR","THR",True) for s in structures]
    metrics = [MdMetric("gatekeeper_to_pocket_min_distance","angstrom",{"mean":4.6,"p05":3.7,"p95":6.2},"canonical EGFR residue 790 and ligand heavy atoms",(0,1000)), MdMetric("pocket_volume_proxy_key_distance","angstrom",{"mean":9.8,"p05":8.9,"p95":11.4},"canonical EGFR pocket key atoms",(0,1000)), MdMetric("gatekeeper_region_rmsf","angstrom",{"mean":1.2,"max":1.8},"canonical EGFR 785-795",(0,1000)), MdMetric("key_contact_occupancy","fraction",{"M790_contact":0.73,"hinge_contact":0.64},"canonical EGFR 790 and ligand heavy atoms",(0,1000))]
    claims = [Claim("EGFR T790M plausibly changes inhibitor-pocket dynamics near the gatekeeper site; this is a hypothesis, not a causal proof.","inference","PDB:2JIT,2ITY; Trajectory:hpc_demo","Medium","Structure context plus trajectory metrics support local contact changes, but matched real WT/T790M trajectories are still required.","HPC run currently uses schema-valid demo metrics."), Claim("Residue 790 is represented in canonical EGFR UniProt numbering, enabling structure-to-trajectory comparison.","structure","PDB:2JIT,2ITY","High","Both candidates map to canonical EGFR P00533 position 790.","Replace mock mapping with PDBe-SIFTS CSV when real structures are pulled.")]
    critic = []
    if not all(m.canonical_uniprot_position == 790 and m.observed for m in mappings): critic.append("Canonical residue 790 mapping failed.")
    if any(s.apo_or_bound == "unknown" for s in structures): critic.append("Apo/bound state unknown for at least one structure.")
    if not critic: critic.append("No critical consistency issues detected in HPC PoC.")
    return {"host":platform.node(),"pdbe_mcp_payload":build_pdbe_payload(spec),"search_spec":asdict(spec),"structures":[asdict(s) for s in structures],"residue_mappings":[asdict(m) for m in mappings],"md_result":{"trajectory_id":"hpc_demo","topology_hash":stable_hash("/hpc/demo/topology.psf"),"trajectory_hash":stable_hash("/hpc/demo/trajectory.dcd"),"mapped_selection":"canonical EGFR residue 790 and ligand heavy atoms","frame_range":[0,1000],"stride":10,"metrics":[asdict(m) for m in metrics],"job_metadata":{"runner":"hpc_ssh_direct","schema_version":"0.1.0","host":platform.node()},"stdout":"HPC PoC completed","stderr":""},"claims":[asdict(c) for c in claims],"literature_pmids":["18227510"],"critic_findings":critic}
def render(e):
    rows = ["| {claim} | {evidence_type} | {source} | {confidence}: {confidence_reason} | {limitations} |".format(**c) for c in e["claims"]]
    critic = "\n".join("- " + x for x in e["critic_findings"])
    return "# EGFR T790M HPC PoC Mechanism Brief\n\n## Search\n\n- Query: `{}`\n- Host: `{}`\n- Resolution cutoff: {} A\n\n## Evidence Table\n\n| Claim | Evidence Type | Source | Confidence | Limitations |\n| --- | --- | --- | --- | --- |\n{}\n\n## Chinese Summary\n\nHPC PoC completed the pipeline: structured PDBe MCP payload, canonical EGFR residue 790 mapping, MD metrics JSON, evidence-grounded claims, and critic audit. Current MD metrics are schema-valid demo metrics; next step is replacing them with real MDAnalysis output.\n\n## Critic Findings\n\n{}\n".format(e["search_spec"]["query"], e["host"], e["search_spec"]["max_resolution"], "\n".join(rows), critic)
if __name__ == "__main__":
    out = Path("outputs"); out.mkdir(exist_ok=True)
    evidence = run()
    (out / "hpc_demo_evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    (out / "hpc_demo_report.md").write_text(render(evidence), encoding="utf-8")
    print("WROTE", out / "hpc_demo_evidence.json")
    print("WROTE", out / "hpc_demo_report.md")
    print(json.dumps({"host": evidence["host"], "critic": evidence["critic_findings"], "metrics": [m["name"] for m in evidence["md_result"]["metrics"]]}, indent=2))

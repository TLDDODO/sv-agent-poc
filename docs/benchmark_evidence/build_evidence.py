"""S4 evidence builder: re-runs the live API calls behind docs/benchmark_design.md and
writes docs/benchmark_evidence/evidence.json. Not imported by the agent.
    python docs/benchmark_evidence/build_evidence.py
"""
import json, os, sys, time, urllib.parse
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pdbe_helpers as E

PAIRS = [("1FIN", "P24941", "P20248", "CDK2 cyclin A binding interface"),
         ("4G0N", "P01112", "P04049", "HRAS RAF1 interaction binding domain"),
         ("1YCR", "Q00987", "P04637", "MDM2 p53 interaction binding domain"),
         ("1BXL", "Q07817", "Q16611", "BCL2L1 BAK1 interaction binding region"),
         ("1AXC", "P12004", "P38936", "PCNA CDKN1A p21 interaction binding region")]
J = lambda u: json.loads(E.get(u))


def entries(acc):
    q = urllib.parse.urlencode({"q": f"uniprot_accession:{acc}", "fl": "pdb_id", "rows": "20000", "wt": "json"})
    return {d["pdb_id"].upper() for d in J("https://www.ebi.ac.uk/pdbe/search/pdb/select?" + q)["response"]["docs"]}


out = {"fetched": time.strftime("%Y-%m-%d"), "cases": {}}
for pdb, a, b, query in PAIRS:
    best, chains = E.interface(pdb, a, b)
    area, iid, ca, cb, mols, _ = best
    p = pdb.lower()
    summ = J(f"https://www.ebi.ac.uk/pdbe/api/pdb/entry/summary/{p}")[p][0]
    exp = J(f"https://www.ebi.ac.uk/pdbe/api/pdb/entry/experiment/{p}")[p][0]
    case = {"pdb": pdb, "title": summ["title"], "method": summ["experimental_method"],
            "resolution": exp.get("resolution"), "pisa_interface_id": iid, "int_area": area, "proteins": {}}
    for mm in mols:
        ch = mm.find("chain_id").text
        acc = a if ch == ca else b
        keep, drop, assumed, checked = [], [], False, 0
        for rr in mm.iter("residue"):
            if float(rr.find("bsa").text) <= 0:
                continue
            s, n = int(rr.find("seq_num").text), rr.find("name").text
            try:
                v, ok = E.unp(chains[acc], ch, s)
            except ValueError:
                v, ok, assumed = s, True, True
            checked += 1
            if ok and E.useq(acc)[v - 1] == E.T.get(n, "?"):
                keep.append(v)
            else:
                drop.append({"chain": ch, "author_seq": s, "pdb_residue": n, "unp_pos": v,
                             "unp_residue": E.useq(acc)[v - 1] if ok else None})
        u = E.uni(acc)
        cov = [{"type": f[0], "description": f[1], "start": f[2], "end": f[3],
                "interface_residues_inside": sum(1 for x in keep if f[2] <= x <= f[3])}
               for f in u["feats"] if f[1] != "Disordered"]
        case["proteins"][acc] = {"uniprot_id": u["id"], "name": u["name"], "length": u["length"], "chain": ch,
                                 "bsa_residues_checked": checked, "interface_residues": sorted(keep),
                                 "n_interface_residues": len(keep), "dropped_name_mismatch": drop,
                                 "sifts_author_numbers_missing_assumed_equal_unp": assumed,
                                 "features": [c for c in cov if c["interface_residues_inside"]],
                                 "all_features_non_disordered": cov,
                                 "n_disordered_features": sum(1 for f in u["feats"] if f[1] == "Disordered"),
                                 "ground_truth_pdb_id_in_uniprot": {k: pdb in json.dumps(v).upper() for k, v in
                                                                    json.loads(E.get("https://rest.uniprot.org/uniprotkb/%s.json" % acc)).items()
                                                                    if k in ("features", "comments", "uniProtKBCrossReferences")}}
    co = sorted(entries(a) & entries(b))
    pm = {}
    for i in co:
        for x in J(f"https://www.ebi.ac.uk/pdbe/api/pdb/entry/publications/{i.lower()}")[i.lower()]:
            if x.get("pubmed_id"):
                pm.setdefault(str(x["pubmed_id"]), []).append(i)
    top = J("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&retmode=json&retmax=5&term="
            + urllib.parse.quote(query))["esearchresult"]["idlist"]
    leaked = [x for x in top if x in pm]
    case["literature_query"] = {"term": query, "top5": top, "leaked_pmids": leaked}
    case["leaked_pmid_summaries"] = {x: {k: J("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&retmode=json&id=" + x)["result"][x].get(k) for k in ("title", "source", "pubdate")} for x in leaked}
    case["co_complex_entries"] = co
    case["co_complex_pmids"] = pm
    out["cases"][pdb] = case
probes = ["https://www.ebi.ac.uk/pdbe/api/pisa/interfaces/1fin", "https://www.ebi.ac.uk/pdbe/api/pdb/entry/interfaces/1fin",
          "https://data.rcsb.org/rest/v1/core/interface/1FIN/1"]
out["endpoint_probes"] = {}
for u in probes:
    try:
        E.get(u); out["endpoint_probes"][u] = "ok"
    except Exception as e:
        out["endpoint_probes"][u] = str(e)
json.dump(out, open(os.path.join(HERE, "evidence.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("wrote evidence.json")

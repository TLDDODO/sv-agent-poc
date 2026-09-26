import json, sys, urllib.request, xml.etree.ElementTree as ET
def get(u):
    import time
    for i in range(5):
        try:
            with urllib.request.urlopen(u, timeout=90) as r: return r.read().decode()
        except Exception as e:
            err=e; time.sleep(2)
    raise err
def uni(acc):
    j=json.loads(get(f"https://rest.uniprot.org/uniprotkb/{acc}.json"))
    feats=[(f["type"],f.get("description"),f["location"]["start"]["value"],f["location"]["end"]["value"]) for f in j.get("features",[]) if f["type"] in("Domain","Region","Repeat","Zinc finger","Motif")]
    return dict(acc=acc,id=j["uniProtkbId"],name=j["proteinDescription"].get("recommendedName",{}).get("fullName",{}).get("value"),length=j["sequence"]["length"],feats=feats)
def mapping(pdb):
    return json.loads(get(f"https://www.ebi.ac.uk/pdbe/api/mappings/uniprot/{pdb}"))[pdb.lower()]["UniProt"]
def interface(pdb,a,b):
    m=mapping(pdb)
    if a not in m or b not in m: return None
    chains={}
    for acc in (a,b):
        chains[acc]={}
        for x in m[acc]["mappings"]: chains[acc].setdefault(x["chain_id"],[]).append(x)
    root=ET.fromstring(get(f"https://www.ebi.ac.uk/pdbe/pisa/cgi-bin/interfaces.pisa?{pdb.lower()}"))
    best=None
    for itf in root.iter("interface"):
        mols=itf.findall("molecule")
        cid=[mm.find("chain_id").text for mm in mols]
        if len(cid)!=2: continue
        ca,cb=cid
        for x,y in ((ca,cb),(cb,ca)):
            if x in chains[a] and y in chains[b]:
                area=float(itf.find("int_area").text)
                if best is None or area>best[0]: best=(area,itf.find("id").text,x,y,mols,cid)
    return best,chains
T={"ALA":"A","ARG":"R","ASN":"N","ASP":"D","CYS":"C","GLN":"Q","GLU":"E","GLY":"G","HIS":"H","ILE":"I","LEU":"L","LYS":"K","MET":"M","PHE":"F","PRO":"P","SER":"S","THR":"T","TRP":"W","TYR":"Y","VAL":"V"}
SEQ={}
def useq(acc):
    if acc not in SEQ: SEQ[acc]="".join(get(f"https://rest.uniprot.org/uniprotkb/{acc}.fasta").splitlines()[1:])
    return SEQ[acc]
def unp(chains_acc,chain,seq):
    for mp in chains_acc[chain]:
        a=mp["start"]["author_residue_number"]; e=mp["end"]["author_residue_number"]
        if a is None:
            if e is None: raise ValueError("no author numbering")
            a=e-(mp["end"]["residue_number"]-mp["start"]["residue_number"])
        if e is None: e=a+(mp["end"]["residue_number"]-mp["start"]["residue_number"])
        if a<=seq<=e: return seq+mp["unp_start"]-a, True
    return seq, False

if __name__=="__main__":
    pdb,a,b=sys.argv[1:4]
    for acc in (a,b): print(json.dumps(uni(acc)))
    r=interface(pdb,a,b)
    if not r or not r[0]: print("no interface"); sys.exit()
    best,chains=r
    area,iid,ca,cb,mols,cid=best
    print("interface",iid,"area",area,"chains",ca,cb)
    for mm in mols:
        ch=mm.find("chain_id").text; acc=a if ch==ca else b
        res=[(int(rr.find("seq_num").text),rr.find("name").text,float(rr.find("bsa").text)) for rr in mm.iter("residue") if float(rr.find("bsa").text)>0]
        u=[]; bad=0
        for s,n,bsa in res:
            try: v,ok=unp(chains[acc],ch,s)
            except ValueError: v,ok=s,True
            if not ok: print("  unmapped",ch,s,n); continue
            if useq(acc)[v-1]!=T.get(n,"?"): bad+=1; print("  MISMATCH",ch,s,n,"->unp",v,useq(acc)[v-1])
            u.append(v)
        print("residue-name mismatches vs UniProt seq:",bad,"of",len(res))
        print(ch,acc,"n_bsa>0:",len(res),"unp range",min(u) if u else None,max(u) if u else None)
        print(sorted(u))

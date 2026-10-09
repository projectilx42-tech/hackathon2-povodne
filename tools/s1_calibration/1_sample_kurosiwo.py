"""Collect a few Kuro Siwo test tiles (several events, flat and hilly) for comparing our Sentinel Hub processing."""
import io, json, sys, tarfile, requests, numpy as np, collections
URL="https://huggingface.co/datasets/orion-ai-lab/Kuro-Siwo-Webdataset/resolve/main/test_GRD/shard-{:05d}.tar"
OUT="/tmp/ks"; per_event=collections.defaultdict(list)
def tiles(shard, limit):
    with requests.get(URL.format(shard), stream=True, timeout=60) as r:
        r.raw.decode_content=True
        with tarfile.open(fileobj=r.raw, mode="r|") as tar:
            key=None; files={}; n=0
            for m in tar:
                if not m.isfile(): continue
                k,name=m.name.split(".",1)
                if k!=key and key is not None:
                    yield key, files; files={}; n+=1
                    if n>=limit: return
                key=k; files[name]=tar.extractfile(m).read()
for shard in [int(s) for s in sys.argv[1:]]:
    for key, f in tiles(shard, 150):
        if "info.json" not in f or "flood_vv.npy" not in f: continue
        info=json.loads(f["info.json"]); ev=info["actid"]
        a={n[:-4]: np.load(io.BytesIO(b)).squeeze() for n,b in f.items() if n.endswith(".npy")}
        vv=a["flood_vv"]; valid=np.isfinite(vv)&(vv>0)
        if valid.mean()<0.95: continue
        dem=a.get("dem"); relief=float(np.nanmax(dem)-np.nanmin(dem)) if dem is not None else 0
        ms=[d for d in info["datasets"].values() if d["ptype"]=="MS"][0]
        per_event[ev].append((relief, key, shard, info["geom"], ms["source_date"], a))
    print("shard",shard,"events so far",{k:len(v) for k,v in per_event.items()}, flush=True)
kept=0
for ev, lst in per_event.items():
    lst.sort(key=lambda t:-t[0])
    for relief,key,shard,geom,date,a in lst[:2]+lst[-2:]:
        np.savez_compressed(f"{OUT}/ev{ev}_{shard}_{key}.npz", geom=geom, date=date, relief=relief, **{k:v for k,v in a.items() if k in ("flood_vv","flood_vh","dem")})
        kept+=1
print("kept",kept)

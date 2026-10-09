"""Evaluate the event-day check (D-M1-03) on the saved known cases (run 1_fetch_cases.py first; data in /tmp/sd)."""
import glob, json, os, sys
import numpy as np
sys.path.insert(0, "src")
from povodne.acquire.preselect import change_fraction, judge_same_day, smooth_db

rows = []
for f in sorted(glob.glob("/tmp/sd/*.npz")):
    d = np.load(f)
    imgs = [smooth_db(x) for x in d["imgs"]]
    hist = imgs[:4]
    c = change_fraction(imgs[4], hist, d["usable"])
    b = change_fraction(hist[-1], hist[:-1], d["usable"])
    dec = judge_same_day(c, b)
    rows.append({"case": os.path.basename(f)[:-4], "dates": [str(x) for x in d["dates"]], "flood_present": bool(d["truth"]),
                 "change": round(c, 4), "baseline": round(b, 4), "used_as_post": dec.use_as_post,
                 "correct": dec.use_as_post == bool(d["truth"])})
    print(rows[-1])
json.dump(rows, open("tools/event_day_check/results.json", "w"), indent=1)
print(sum(r["correct"] for r in rows), "/", len(rows), "correct")

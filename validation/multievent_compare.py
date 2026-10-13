"""Compare two tags of the multi-event check with the merge rule (VALIDATION ONLY).

  python validation/multievent_compare.py <base_tag> <new_tag>

Per event F1 (final mask, same metric as the tables: affected 2+3, water labels 2+4), mean R/P/F1 over the 9 labelled flood
events (Chamoli is not informative and the Marsyangdi control has no flood), and the control's affected km².
Rule (master, 2026-10-13): mean F1 up, no event's F1 down by more than 0.01, mean precision not down by more than 0.01,
the control does not gain false area.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RES = Path(__file__).resolve().parent / "results" / "multievent"
SKIP = {"chamoli_2021_sub"}
CONTROL = "marsyangdi_2024_noflood_sub"


def load(tag: str) -> dict:
    out = {}
    for p in RES.glob(f"*__{tag}.json"):
        d = json.loads(p.read_text())
        s = d["scores"]
        k = "b_envelope" if "b_envelope" in s else "b_envelope_water_2_4"
        t = d["run"].get("timings_s")
        out[d["event"]] = {**s[k], "time_s": round(sum(t.values())) if isinstance(t, dict) else None,
                           "ai_s": (t or {}).get("flood_ai") if isinstance(t, dict) else None}
    return out


def main() -> None:
    a, b = sys.argv[1], sys.argv[2]
    A, B = load(a), load(b)
    evs = sorted(set(A) & set(B))
    print(f"| event | {a} R / P / F1 | {b} R / P / F1 | ΔF1 |\n|---|---|---|---|")
    f = lambda x: "–" if x is None else f"{x:.2f}"  # noqa: E731
    sums = {a: [0, 0, 0], b: [0, 0, 0]}
    n, worst = 0, 0.0
    for e in evs:
        x, y = A[e], B[e]
        d = None if x["f1"] is None or y["f1"] is None else y["f1"] - x["f1"]
        print(f"| {e} | {f(x['recall'])} / {f(x['precision'])} / {f(x['f1'])} | {f(y['recall'])} / {f(y['precision'])} / {f(y['f1'])} | "
              f"{'' if d is None else f'{d:+.3f}'} |")
        if e in SKIP or e == CONTROL or d is None:
            continue
        n += 1
        worst = min(worst, d)
        for t, z in ((a, x), (b, y)):
            sums[t][0] += z["recall"]
            sums[t][1] += z["precision"]
            sums[t][2] += z["f1"]
    ma, mb = [v / max(n, 1) for v in sums[a]], [v / max(n, 1) for v in sums[b]]
    print(f"\nmean over {n} events: {a} R {ma[0]:.3f} P {ma[1]:.3f} F1 {ma[2]:.3f} | {b} R {mb[0]:.3f} P {mb[1]:.3f} F1 {mb[2]:.3f}")
    ca, cb = A.get(CONTROL, {}).get("pred_km2"), B.get(CONTROL, {}).get("pred_km2")
    print(f"control affected km2: {ca} -> {cb}")
    ok = (mb[2] > ma[2]) and worst >= -0.01 and (mb[1] >= ma[1] - 0.01) and (ca is None or cb is None or cb <= ca + 1e-4)
    print(f"worst event dF1 {worst:+.3f}; MERGE RULE {'PASSES' if ok else 'FAILS'}")


if __name__ == "__main__":
    main()

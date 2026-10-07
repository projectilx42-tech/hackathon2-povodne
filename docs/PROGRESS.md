# PROGRESS — co je hotové, co rozbité, co dál

**Aktualizuj na konci každé session** (stav modulů + záznam do logu) a commitni + pushni.
Nejnovější záznam v logu nahoře. Stavy: ⬜ nezačato · 🟨 rozpracováno · ✅ hotovo · 🟥 rozbité/blokované.

## Stav modulů
| Modul | Stav | Větev | Poznámka |
|---|---|---|---|
| Repo init, docs, workflow | ✅ | `claude/gallant-keller-vftpi2` | CLAUDE.md, docs/, Stop hook |
| 0 Skeleton (pyproject, CLI, config, io/grid) | ⬜ | `feat/skeleton` | **dělat první** — ostatní moduly na něm stojí |
| M1 Acquire (S1/S2/DEM/OSM) | 🟥 | `feat/acquire` | blokováno síťovou politikou (viz Blokery) |
| M2 Preprocess | ⬜ | `feat/preprocess` | |
| M3a Baseline change detection | ⬜ | `feat/flood-baseline` | |
| M9 AI trénink | 🟥 | `feat/ai-model` | chybí GPU + přístup k datasetu (O-002) |
| M3b AI inference + fúze | ⬜ | `feat/ai-model` | |
| M4 Damage | ⬜ | `feat/damage` | |
| M5 Network / cut-off | ⬜ | `feat/network` | |
| M6 Stats + sitrep | ⬜ | `feat/report` | |
| M7 Flood path (bonus) | ⬜ | `feat/floodpath` | |
| M8 Dashboard | ⬜ | `feat/dashboard` | technologie O-003 |
| M10 Validace vs EMSR927 | ⬜ | `feat/validation` | |
| Report 6 stran, video, README | ⬜ | `docs/report` | |

## Blokery / známé problémy
1. **Síťová politika cloud prostředí blokuje datové zdroje.** Ověřeno 2026-10-07: `api.ohsome.org`, `catalogue.dataspace.copernicus.eu`,
   `planetarycomputer.microsoft.com`, `multimodal-ai-hackathon-2026-7.devpost.com` → 403 od proxy. PyPI funguje.
   Řešení: v nastavení cloud environmentu (Edit → Network access) přidat domény do Allowed domains (seznam níže) nebo zvolit širší přístup.
   Docs: https://code.claude.com/docs/en/cloud-environments#network-access
   Dosažitelné (2026-10-07): `pypi.org`, `files.pythonhosted.org`, `registry.npmjs.org`, `conda.anaconda.org`, `github.com`, `api.github.com`,
   `raw.githubusercontent.com`, **`copernicus-dem-30m.s3.amazonaws.com` (Copernicus DEM — funguje!)**.
   Blokované: mj. `huggingface.co`, `zenodo.org`, `download.pytorch.org` (PyTorch jde z PyPI), Wikipedie, Google. WebFetch nefunguje vůbec; WebSearch ano.
2. **Žádná GPU v cloud session** (4 CPU, 15 GB RAM, ~30 GB volného disku). Trénink → O-002. Disk nestačí na celý Kuro Siwo.
3. **Deadline pravděpodobně 14. 10. 2026 EOD** (web search, neověřeno z Devpostu) → na práci je cca týden, prioritizovat MVP end-to-end.
4. CDSE přihlašovací údaje zatím nejsou (potřeba registrace na dataspace.copernicus.eu; dát jako env proměnné prostředí, ne do repa).

### Domény k povolení (návrh)
- Copernicus Data Space: `dataspace.copernicus.eu`, `catalogue.dataspace.copernicus.eu`, `identity.dataspace.copernicus.eu`,
  `download.dataspace.copernicus.eu`, `zipper.dataspace.copernicus.eu`, `stac.dataspace.copernicus.eu`, `sh.dataspace.copernicus.eu`,
  `openeo.dataspace.copernicus.eu`, `eodata.dataspace.copernicus.eu`
- OSM: `api.ohsome.org`
- Planetary Computer (pokud O-001 → PC): `planetarycomputer.microsoft.com`, `*.blob.core.windows.net`
- DEM na AWS: `copernicus-dem-30m.s3.amazonaws.com` (příp. `*.s3.amazonaws.com`)
- Tréninková data / modely: `huggingface.co`, `*.hf.co`, `zenodo.org`, `storage.googleapis.com` (Sen1Floods11), + kam odkazuje README Kuro Siwo
- Validace: `mapping.emergency.copernicus.eu`
- Info: `devpost.com`, `*.devpost.com`

## Doporučené pořadí práce
1. **Skeleton** (pyproject, CLI, config, run.json, grid helpery, test fixture s malou AOI) → merge do `main`.
2. Paralelně: **M1 acquire** · **M9 trénink** (mimo cloud/GPU) · **M5 network** (stačí OSM, jde vyvíjet na syntetické flood masce).
3. **M2 preprocess → M3a baseline** (první end-to-end flood mapa Trishuli).
4. **M4 damage → M6 stats/sitrep → M8 dashboard**.
5. **M3b AI inference + fúze**, **M10 validace vs EMSR927**, M7 bonus.
6. Report, README, video; dry-run „live hodnocení“ na jiné AOI/datu.

## Log sessions
### 2026-10-07 — master session (init) — `claude/gallant-keller-vftpi2`
- Založeno repo: `CLAUDE.md`, `docs/{TASK,ARCHITECTURE,PROGRESS,DECISIONS}.md`, originální PDF v `docs/source/`, `.gitignore`, README kostra,
  Stop hook připomínající commit/push.
- Zjištěno: síť blokuje datové zdroje, žádná GPU (viz Blokery).
- Další krok: vyřešit síť + CDSE účet, pak session **Skeleton**.

# NOTICES — upozornění a vysvětlení, která má ukázat UI

Seznam všech upozornění, která program vydává, s pevným kódem. Je určený hlavně pro **UI session**: ta podle něj
implementuje zobrazení. Kód upozornění vzniká v `src/povodne/acquire/notices.py` (`SEVERITY` = seznam kódů).
Test `tests/test_acquire_notices.py` hlídá, že tabulka níže obsahuje přesně všechny kódy z kódu. Rozhodnutí: D-M1-05.
Zatím jsou tu jen upozornění kroku stahování dat (`step = "acquire"`). Další moduly (AI model, suť, škody, sitrep) můžou
přidat vlastní kódy se svým `step` a doplnit je sem.

## Kde to je a v jakém tvaru
`run.json.notices` je seznam. Každá položka vypadá takto:
```json
{"step": "acquire", "code": "pre_may_be_flooded", "severity": "warning",
 "message": "The area was wetter at the start of the checked period and has been drying out since, ...",
 "details": {"start_water_frac": 0.31, "min_water_frac": 0.06}}
```
- `message` je hotová anglická věta pro uživatele. Čísla a data v ní pocházejí z výpočtu, UI je nemá skládat samo.
- `details` jsou čísla a data pro chytřejší zobrazení (graf, odkaz na datum, ikona). Obsah se liší podle kódu (tabulka).
- Pořadí je pořadí vzniku během běhu. Každý text je v seznamu nejvýš jednou.
- Při novém spuštění kroku se jeho položky nahradí; položky jiných kroků zůstanou.
- **Zpětná kompatibilita:** chyby a varování (ne `info`) jsou dál i jako prostý text v `run.json.warnings`
  (UI je dnes zobrazuje v `results.js`). Až UI přejde na `notices`, ať `warnings` nezobrazuje dvakrát.

## Závažnost a doporučené zobrazení
| `severity` | význam | doporučení pro UI |
|---|---|---|
| `error` | Odpověď, kterou uživatel chtěl, **chybí**: není mapa povodně, nebo nejde spočítat škody a odříznuté obce. | Červený pruh nahoře v pravém panelu, vždy viditelný. Když chybí mapa povodně, je výsledek „Insufficient data“. |
| `warning` | Odpověď je, ale **může být méně spolehlivá nebo neúplná**. | Žlutá položka v panelu kvality dat (Data quality), počet varování v záhlaví panelu. |
| `info` | **Co program rozhodl a proč**, nic se nemusí řešit. | Sbalená sekce „How this was computed“ / tooltip; nezobrazovat jako varování. |

## Seznam kódů
Sloupec „Titulek pro UI“ je návrh krátkého anglického nadpisu. Celou větu UI vezme z `message`.

| kód | závažnost | kdy nastane (česky) | titulek pro UI (EN) | `details` |
|---|---|---|---|---|
| `cdse_credentials` | error | Chybí nebo nefunguje klíč k Copernicus Data Space (porotce si ho musí nastavit podle README). Krok skončí `failed`. | Copernicus login missing | — (u selhání během běhu `error`) |
| `acquire_failed` | error | Stahování spadlo na nečekané chybě (výpadek služby apod.). Krok skončí `failed`, podrobnosti v `logs/pipeline.log`. | Data download failed | `error` |
| `s1_no_post` | error | Po zadaném datu zatím žádný průlet radaru (Sentinel-1) nad oblastí. Typicky moc čerstvé datum: družice prolétá jednou za několik dní. | No radar image after the flood yet | `horizon_days` |
| `s1_no_pair` | error | Žádná dráha nemá zároveň snímek „po“ a dřívější snímek „před“ ze stejné dráhy, takže nejde porovnat před/po. | No before/after radar pair | `tracks`: `[{track, direction, post, n_pre}]` |
| `s1_no_clean_pre` | error | Voda stoupala už na prvním kontrolovaném snímku. Snímek „před“ bez povodně neexistuje. | No flood-free before-image | `rise_date` |
| `osm_failed` | error | Mapa budov a silnic z OpenStreetMap (snímek před povodní) se nestáhla, takže nejdou spočítat škody ani odříznuté obce. Mapa povodně funguje. | Buildings and roads unavailable | `error` |
| `osm_key_missing` | error | Chybí nebo nefunguje klíč k ohsome (služba se stavem OpenStreetMap před povodní; porotce si ho založí zdarma podle README). Škody a odříznuté obce nejdou spočítat, mapa povodně funguje. | OpenStreetMap key missing | — |
| `s1_partial_coverage` | warning | Žádný průlet radaru nepokrývá aspoň 90 % oblasti; menší průlety se nepoužijí. Často to vede i k `s1_no_pair`. | Radar covers only part of the area | `best_coverage` (0–1) |
| `s1_alt_missing` | warning | Chybí druhý směr přeletu (opačná dráha), nebo pro něj chybí snímek „před“. Místa schovaná za horami pro hlavní dráhu zůstanou nezmapovaná. | Only one radar viewing direction | `reason`: `no_opposite_track` / `no_pre_image` |
| `better_view_soon` | warning | Čerstvá povodeň: jedna dráha radaru ještě nemá snímek „po“, ale podle jejího pravidelného rozvrhu přeletí brzy a uvidí část dna údolí, kterou použité dráhy nevidí (horský stín). Zpráva řekne datum, za kolik dní a o kolik procent víc dna údolí bude vidět. Nevydává se u starších povodní. | Better radar view soon | `track`, `direction`, `next_pass_date` (`YYYY-MM-DD`, místní čas), `days_until`, `visibility_now`, `visibility_with_track` (0–1) |
| `pre_may_be_flooded` | warning | **Oblast byla na začátku kontrolovaného období (60 dní) mokřejší a od té doby vysychá.** Mokré období tedy asi začalo dřív, snímek „před“ už může obsahovat vodu a zaplavená plocha může vyjít menší. | Before-image may already be flooded | `start_water_frac`, `min_water_frac` (podíl vody na dně údolí, 0–1) |
| `pre_window_after_rise` | warning | Uživatel zadal vlastní okno „před“ (Advanced), ale to obsahuje dny po začátku nárůstu vody. Okno se respektuje, jen se varuje. | Chosen before-window includes flooding | `rise_date` |
| `pre_check_blind` | warning | Kontrola „není povodeň už na snímku před?“ tu nevidí skoro žádnou vodu (řeky užší než pixel 60 m), takže čistotu snímku „před“ nepotvrdí ani nevyvrátí. Typické pro horská údolí. | Before-image could not be verified | `max_water_frac` |
| `valley_visibility_unavailable` | warning | Nešlo spočítat, která dráha radaru lépe vidí dno údolí (chyba výškové mapy). Použije se dráha s nejdřívějším snímkem „po“. | Track choice without terrain check | `error` |
| `s2_none` | warning | Žádný použitelný optický snímek Sentinel-2 (mraky) pro „před“ nebo „po“. Pro tu část jen radar. | No optical image (clouds) | `phase`: `pre` / `post` |
| `s2_cloudy` | warning | Optický snímek je použitý, ale nad oblastí je jasno méně než na 30 %. | Optical image mostly cloudy | `phase`, `date`, `clear_frac` (0–1) |
| `s2_composite` | info | Optický pohled „před/po“ je složen po pixelech z několika bezoblačných dnů Sentinel-2. | Optical view is a multi-date composite | `dates` (seznam dnů) |
| `s2_failed` | warning | Stažení optických snímků selhalo, pokračuje se jen s radarem. | Optical images unavailable | `error` |
| `post_image_date` | info | Z kterého dne a hodiny (místní čas) je snímek „po“ a kolik dní po zadaném datu. Změny po něm nejsou vidět. **Doporučuji ukázat vždy viditelně u výsledku** (záchranáři potřebují vědět stáří dat). | After-image date | `datetime_local` (`YYYY-MM-DDTHH:MM`), `days_after_event` |
| `perm_water_ref_short` | warning | V posledním roce před povodní je málo radarových průletů hlavní dráhy, aby se dalo poznat, co je trvalá voda a co jen sezónně rozvodněná řeka; rozvodněné koryto na snímku „před“ se pak může počítat jako trvalá voda (nezasaženo). | Permanent-water reference missing | `n_passes`, `lookback_days`, `error`? |
| `pre_rise_detected` | info | Radar ukázal, že voda stoupala už před zadaným datem. Snímek „před“ se proto vzal starší, z doby před nárůstem. | Flooding started earlier | `rise_date`, `chosen_pre` (seznam dat) |
| `event_day_pass_used` | info | Průlet přímo v den povodně už ukazuje jasné změny, a proto se použil jako snímek „po“ (o několik dní dřív než další průlet). | Flood-day image used | `track`, `direction`, `datetime`, `used_as_post`, `reason`, `change_frac`, `baseline_frac` |
| `event_day_pass_dropped` | info | Průlet v den povodně nemá jasné změny (mohl být před povodní), a proto se nepoužil. Snímek „po“ je z dalšího průletu. | Flood-day image not used | stejné jako `event_day_pass_used` |
| `main_track_by_visibility` | info | Hlavní dráha radaru nebyla ta s nejdřívějším snímkem, ale ta, která vidí o hodně víc dna údolí (snímek „po“ je nejvýš o 3 dny později). | Radar track chosen for better view | `visibility`, `other_visibility` (0–1), `delay_days` |

## Další údaje v `run.json`, které se hodí ukázat spolu s upozorněními
- `acquire.s1.pre_selection.series` — podíl vody na dně údolí pro každý průlet za 60 dní před povodní. Z toho jde nakreslit
  malý graf (osa X datum, osa Y podíl vody). V grafu zvýraznit `onset_date` (začátek nárůstu) a `chosen_pre` (použité snímky „před“).
  K `pre_may_be_flooded` a `pre_rise_detected` je to nejlepší vysvětlení.
- `acquire.s1.same_day` / `acquire.s1_alt.same_day` — kontrola průletu v den povodně (stejné údaje jako `details` výše).
- `acquire.s1.primary_reason`, `acquire.s1.valley_visibility`, `acquire.s1_alt.valley_visibility` — proč je hlavní tahle dráha
  a kolik dna údolí každá dráha vidí.
- `acquire.s2.pre.clear_pct` / `acquire.s2.post.clear_pct` — kolik oblasti bylo bez mraků.
- `acquire.pu_spent` — kolik kreditů zpracování na Copernicus Data Space běh stál (pro porotce s vlastním účtem).

## Kódy dalších kroků
Tabulky níže mají první sloupec `step` (kód kroku), aby je test kroku stahování nepočítal mezi své.

### Krok změn povrchu (`step = "debris"`, D-M3d-01)
Kódy definuje `src/povodne/flood/debris/pipeline.py` (`SEVERITY`), test `tests/test_debris_notices.py` hlídá, že tabulka obsahuje přesně je.

| step | kód | závažnost | kdy nastane (česky) | titulek pro UI (EN) | `details` |
|---|---|---|---|---|---|
| debris | `debris_failed` | error | Krok změn povrchu spadl. Mapa vody z AI modelu platí dál, jen chybí suť, bahno, zaplavená vegetace a zástavba. | Surface-change mapping failed | `error` |
| debris | `debris_no_radar` | error | Chybí radarový snímek „po“, změny povrchu nejde mapovat. | No radar after-image | — |
| debris | `debris_short_history` | warning | Dráha má méně než 2 starší průlety: běžné kolísání místa se odhaduje jen z okolí, výsledek je méně spolehlivý. | Short radar history | `track`, `earlier_passes` |
| debris | `debris_no_buildings` | warning | Chybí budovy z OpenStreetMap: zaplavené nebo poškozené město nejde odlišit (zaplavené město se ukáže jako zaplavená vegetace). | No building footprints | — |
| debris | `debris_placebo_high` | warning | Autotest: i mezi dvěma staršími snímky (bez povodně) se tu hodně změnilo (pole, stavby, déšť); podobné změny nesouvisející s povodní můžou být ve výsledku. | Area changes a lot without floods | `rate`, `target` |
| debris | `debris_regional_change` | warning | Radar zesvětlal (déšť) nebo ztmavl (mokrý sníh, mráz) i vysoko nad řekami, kam povodeň nedosáhne; stejné změny na dně údolí se braly jako počasí, skutečná povodeň se stejným podpisem může chybět. | Weather changed the whole area | `background_change`, `weather` |
| debris | `debris_no_optical` | info | Chybí dvojice optických snímků bez mraků: podtypy jen z radaru, nižší jistota. | Radar-only surface changes | — |
| debris | `debris_false_alarm_estimate` | info | Výsledek autotestu na dni bez povodně: kolik km² by se nahlásilo omylem a jaký podíl nalezené plochy může být falešný. **Doporučuji ukázat u čísla „suť/bahno“.** | Self-test: false-alarm estimate | `rate`, `flagged_km2`, `searchable_km2`, `estimated_false_share`, `fake_after_image`, `tightened_steps`, `target_rate` |
| debris | `debris_not_observable` | info | Víc než 10 % oblasti je neviditelné (stín hor, mraky) nebo necitlivé (hustý les, hustá zástavba): „nic“ tam neznamená „žádná škoda“. | Parts of the area not visible | `observed_pct`, `not_observable_pct`, `insensitive_pct` |

Pro UI dál: `flood/debris_polygons.geojson` má u každé plochy `subtype`, `confidence` a anglickou větu `evidence` (proč to systém tvrdí) —
hodí se do vyskakovacího okna po kliknutí. `flood/debris_observability.tif` = vrstva „co bylo vidět“.

### Složení finální mapy povodně (`step = "combine"`, D-M0-01)
Kódy definuje `src/povodne/flood/combine.py` (`SEVERITY`), test `tests/test_combine.py` hlídá, že tabulka obsahuje přesně je.
Souhrn plochy je v `run.json.combine.areas_km2`.

| step | kód | závažnost | kdy nastane (česky) | titulek pro UI (EN) | `details` |
|---|---|---|---|---|---|
| combine | `combine_no_water_map` | error | Chybí mapa vody z AI kroku, finální mapa povodně nevznikla. Krok skončí `failed`, škody a odříznuté obce se nepočítají. | No flood map | — |
| combine | `combine_no_debris` | warning | Chybí mapa suti a bahna (krok spadl nebo neproběhl): mapa ukazuje jen otevřenou vodu. | Water only, no debris map | — |
| combine | `combine_grid_mismatch` | warning | Mapa suti je na jiné mřížce než mapa vody, nepoužila se (chyba v datech, mapa ukazuje jen vodu). | Debris map not aligned | — |
| combine | `combine_debris_where_ai_blind` | info | Část suti/změn povrchu leží tam, kam model vody neviděl (radarový stín, chybí data); do mapy povodně je započtena. | Debris where water model was blind | `area_km2` |

### Krok škod (`step = "damage"`, D-M4-01)
Kódy definuje `src/povodne/damage/pipeline.py`.

| step | kód | závažnost | kdy nastane (česky) | titulek pro UI (EN) | `details` |
|---|---|---|---|---|---|
| damage | `damage_no_flood_mask` | error | Chybí finální mapa povodně (`flood/flood_mask.tif`), škody nejde spočítat. Krok skončí `failed`. | No flood map for damage | — |
| damage | `damage_failed` | error | Krok škod spadl na nečekané chybě. | Damage assessment failed | `error` |
| damage | `damage_no_buildings` | warning | V OpenStreetMap před povodní nejsou v oblasti žádné budovy: „0 zasažených budov“ neznamená „žádná škoda“. | No buildings in the map | — |
| damage | `damage_no_roads` | warning | V OpenStreetMap před povodní nejsou silnice: přerušené silnice ani odříznuté obce nejde posoudit. | No roads in the map | — |
| damage | `damage_unobserved` | warning | Aspoň 20 % budov leží převážně v místech, která satelit neviděl (radarový stín, mimo snímek): jejich stav je neznámý. | Many buildings not visible | `share` |
| damage | `damage_no_debris_detail` | info | Chybí podtypy suti a jistota: každá suť se bere jako „suť, střední jistota“, budovy v ní jako pravděpodobně zničené. | No debris detail | — |

### Krok silniční sítě a odříznutých obcí (`step = "network"`, D-M5-01–04)
Kódy definuje `src/povodne/network/pipeline.py`.

| step | kód | závažnost | kdy nastane (česky) | titulek pro UI (EN) | `details` |
|---|---|---|---|---|---|
| network | `network_failed` | error | Krok sítě spadl na nečekané chybě. | Road network analysis failed | `error` |
| network | `network_no_roads` | error | Žádné silnice z OpenStreetMap před povodní, odříznuté obce nejde spočítat. | No roads in the map | — |
| network | `network_no_damage` | error | Chybí výstup kroku škod (zablokované silnice a mosty). | Damage results missing | — |
| network | `network_no_settlements` | warning | V OpenStreetMap nejsou v oblasti žádná sídla. | No settlements in the map | — |
| network | `network_no_destinations` | warning | V dosahu není nemocnice ani město; jako cíl slouží jen okraj stažené mapy. | No hospital or town nearby | — |
| network | `network_no_settlement_areas` | warning | Chybí území sídel z kroku škod; silnice v obci se počítají v kruhu 200 m a čísla o budovách chybí. | Settlement areas missing | — |
| network | `network_impact_skipped` | warning | Stupeň zasažení obcí se nespočítal (chyba modulu). | Impact levels unavailable | `error` |
| network | `network_landing_skipped` | warning | Plochy pro vrtulník se nespočítaly (chyba modulu nebo chybí výšková mapa). | Landing zones unavailable | `error` |
| network | `network_whole_line_damage` | warning | Nešlo přečíst mapu povodně, takže se zablokovaná silnice vyřadila celá, ne jen zasažený kus: odříznutých obcí může vyjít víc. | Whole roads treated as blocked | — |
| network | `network_snap_failed` | info | Některá sídla jsou dál než 500 m od silnice (vedou k nim jen pěšiny nebo chybí v mapě); počítají se jako „bez silnice už před povodní“. | Settlements without a road | počet |
| network | `network_edge_destinations` | info | Okraj stažené mapy (oblast + 15 km) se počítá jako „vnější svět“ — kdo se tam dostane, není odříznutý. | Map edge used as destination | počet uzlů |
| network | `network_possibly_cut_off` | info | Některé obce jsou odříznuté, jen pokud nejdou použít podezřelé mosty nebo možná zablokované silnice. | Possibly cut off settlements | počet |

### Krok hlášení (`step = "report"`, D-M6-01)
Kódy definuje `src/povodne/report/common.py`. Krok běží vždy (i po chybě dřívějších kroků) a verdikt píše do `stats.json`.

| step | kód | závažnost | kdy nastane (česky) | titulek pro UI (EN) | `details` |
|---|---|---|---|---|---|
| report | `report_failed` | error | Souhrn čísel se nepodařilo spočítat (nečekaná chyba); `stats.json` má jen verdikt „nedostatek dat“. | Summary failed | `error` |
| report | `report_no_flood_map` | error | Nevznikla mapa povodně (některý z kroků stahování, přípravy, AI nebo skládání neproběhl) → verdikt „nedostatek dat“. | No flood map | `failed_steps` |
| report | `report_low_coverage` | error | Radar ani jasná optika nevidí aspoň 20 % oblasti → verdikt „nedostatek dat“ (nic nenalezeno by tu znamenalo jen „nevidíme“). | Too little of the area observed | `evaluated_pct`, `min_evaluated_pct` |
| report | `report_damage_missing` | warning | Mapa povodně je, ale krok škod neproběhl; sitrep ukazuje jen zaplavenou plochu. | Damage not assessed | — |
| report | `report_network_missing` | warning | Mapa povodně je, ale analýza odříznutých obcí neproběhla. | Cut-off analysis missing | — |
| report | `report_pdf_failed` | warning | PDF sitrepu se nepodařilo vytvořit; `stats.json`, `sitrep_en.md` a mapa jsou k dispozici. | PDF report failed | `error` |
| report | `report_overlay_failed` | warning | Některý obrázek vrstvy pro mapu se nepodařilo vykreslit (ostatní ano). | Map layer image failed | `errors` (vrstva → chyba) |

### Krok předzpracování (`step = "preprocess"`, D-M2-01)
Kódy definuje `src/povodne/preprocess/pipeline.py` (`SEVERITY`), test `tests/test_preprocess.py` hlídá, že tabulka obsahuje přesně je.

| step | kód | závažnost | kdy nastane (česky) | titulek pro UI (EN) | `details` |
|---|---|---|---|---|---|
| preprocess | `preprocess_failed` | error | Krok předzpracování spadl (např. chybí výšková mapa). Mapa povodně nevznikne. | Data preparation failed | `error` |
| preprocess | `preprocess_no_s1` | error | V `raw/s1` chybí dvojice radarových snímků „před“ a „po“: mapu povodně nejde udělat. | No radar image pair | — |
| preprocess | `preprocess_low_s1_coverage` | warning | Radar (obě dráhy dohromady) vidí méně než 50 % oblasti (stín hor, layover, chybějící data): jinde povodeň radarem nejde zmapovat. | Radar sees little of the area | `s1_valid_pct` |
| preprocess | `preprocess_approx_geometry` | info | V `run.json` chybí úhel pohledu dráhy; maska stínu a layoveru použila typický úhel 39° podle směru přeletu. | Typical radar angle used | `track`, `look_azimuth_deg`, `incidence_deg` |
| preprocess | `preprocess_no_s2` | info | Chybí optický snímek „po“: voda jen z radaru. | Radar-only water map | `available` |

Pro UI dál: `run.json.preprocess.s1_valid_pct` (kolik oblasti radar vidí aspoň jednou dráhou), `tracks.<dráha>.layover_shadow_pct`, `s2.<pre|post>.clear_pct`.

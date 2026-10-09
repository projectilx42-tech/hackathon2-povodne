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
| `pre_may_be_flooded` | warning | **Oblast byla na začátku kontrolovaného období (60 dní) mokřejší a od té doby vysychá.** Mokré období tedy asi začalo dřív, snímek „před“ už může obsahovat vodu a zaplavená plocha může vyjít menší. | Before-image may already be flooded | `start_water_frac`, `min_water_frac` (podíl vody na dně údolí, 0–1) |
| `pre_window_after_rise` | warning | Uživatel zadal vlastní okno „před“ (Advanced), ale to obsahuje dny po začátku nárůstu vody. Okno se respektuje, jen se varuje. | Chosen before-window includes flooding | `rise_date` |
| `pre_check_blind` | warning | Kontrola „není povodeň už na snímku před?“ tu nevidí skoro žádnou vodu (řeky užší než pixel 60 m), takže čistotu snímku „před“ nepotvrdí ani nevyvrátí. Typické pro horská údolí. | Before-image could not be verified | `max_water_frac` |
| `valley_visibility_unavailable` | warning | Nešlo spočítat, která dráha radaru lépe vidí dno údolí (chyba výškové mapy). Použije se dráha s nejdřívějším snímkem „po“. | Track choice without terrain check | `error` |
| `s2_none` | warning | Žádný použitelný optický snímek Sentinel-2 (mraky) pro „před“ nebo „po“. Pro tu část jen radar. | No optical image (clouds) | `phase`: `pre` / `post` |
| `s2_cloudy` | warning | Optický snímek je použitý, ale nad oblastí je jasno méně než na 30 %. | Optical image mostly cloudy | `phase`, `date`, `clear_frac` (0–1) |
| `s2_failed` | warning | Stažení optických snímků selhalo, pokračuje se jen s radarem. | Optical images unavailable | `error` |
| `post_image_date` | info | Z kterého dne a hodiny (místní čas) je snímek „po“ a kolik dní po zadaném datu. Změny po něm nejsou vidět. **Doporučuji ukázat vždy viditelně u výsledku** (záchranáři potřebují vědět stáří dat). | After-image date | `datetime_local` (`YYYY-MM-DDTHH:MM`), `days_after_event` |
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

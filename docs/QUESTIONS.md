# QUESTIONS — dotazy na organizátory

Otázky, na které z dokumentů zadání (`docs/TASK.md`, PDF v `docs/source/`, Devpost) nejde odpovědět a je lepší se zeptat
organizátorů (Discord: https://discord.gg/UD8EVcdcq). Každá má anglický text připravený ke zkopírování.
Po odpovědi: zapsat odpověď sem, přesunout do „Zodpovězeno“ a podle ní upravit `docs/DECISIONS.md`.

Priorita: 🔴 může ovlivnit diskvalifikaci / hodnocení · 🟡 ovlivní práci · 🟢 jen pro jistotu.

## Otevřené

### Q-1 🔴 Smí model používat předtrénované váhy (ImageNet)? — O-009
Kontext: zadání říká „train a model … using the listed training data“. Náš model (U-Net) startuje z encoderu předtrénovaného
na ImageNet (běžné obrázky, žádná satelitní data ani mapy povodní) a celý se pak trénuje na Kuro Siwo + Sen1Floods11.
Když to nepůjde, natrénujeme ho od nuly (`train.py --no-pretrained`), jen to bude o něco horší.
> Hi! For the Track B flood segmentation model: is it OK to initialise the network with a generic ImageNet-pretrained encoder
> (e.g. ResNet34 from torchvision/timm) and then train it fully on Kuro Siwo and Sen1Floods11? No other flood or
> satellite datasets are used. Thanks!

### Q-2 🔴 Můžeme si pro himálajskou evaluaci vyrobit vlastní popisky vody ze Sentinelu-2? — O-005
Kontext: zadání chce ukázat, jak model funguje „on Himalayan scenes it has never seen“. Kuro Siwo ani Sen1Floods11 žádnou
himálajskou povodeň nemají. Chceme vzít minulé himálajské povodně (např. Chamoli 2021, Melamchi 2021, Sikkim 2023) a popisky
vody udělat sami z jasných snímků Sentinel-2. EMS ani jiné publikované mapy nepoužijeme.
> For the "Himalayan scenes the model has never seen" evaluation: since neither Kuro Siwo nor Sen1Floods11 contains Himalayan
> events, may we create our own water labels for a few past Himalayan floods (e.g. Chamoli 2021, Melamchi 2021, Sikkim 2023)
> from clear-sky Sentinel-2 imagery, and use them only for evaluation? We would not use Copernicus EMS or any other published
> maps. Do the evaluation scenes have to be from 2026, or are past events fine?

### Q-3 🟡 Smíme model doučit na neoznačených himálajských snímcích Sentinel-1 (self-training)?
Kontext: model by si sám označil radarové snímky z hor (mimo Trishuli a mimo naši testovací sadu) a z jistých pixelů se doučil.
Používá jen Sentinel-1 (povolený vstup), žádné cizí mapy. Nevíme, jestli to spadá pod „using the listed training data“.
> Would it be acceptable to fine-tune the model with self-training (pseudo-labels produced by our own model) on unlabelled
> Sentinel-1 scenes from Himalayan valleys (not the Trishuli event and not our evaluation scenes)? Only Sentinel-1 data,
> no external maps or labels.

### Q-4 🟡 Jak přesně bude probíhat živé hodnocení? — D-016, O-006
Kontext: rozhodli jsme, že aplikaci si porota spustí sama lokálně (D-016). Potřebujeme vědět, jestli to porota očekává a kolik
času na jeden běh má.
> How will the live evaluation work in practice: will judges run our system themselves on their own machines (we provide a
> README with install + run instructions), or should it be hosted online? Is there a time limit per area/date, and can we
> assume an internet connection to download the satellite data during the run?

### Q-5 🟡 Přihlašovací údaje k datům při živém hodnocení
Kontext: Copernicus Data Space (oficiální zdroj ze zadání) vyžaduje bezplatný účet. Pokud pipeline poběží u poroty, musí
mít porota vlastní účet, nebo použije náš? (Naše údaje do repa dát nesmíme.)
> Our pipeline downloads Sentinel data from the Copernicus Data Space Ecosystem, which requires a free account. For live judging,
> is it acceptable that the judges enter their own (free) CDSE credentials, or would you prefer another arrangement?

### Q-6 🟢 Kuro Siwo vychází z aktivací Copernicus EMS — je to v pořádku?
Kontext: povodně v Kuro Siwo autoři vybrali z aktivací Copernicus EMS a popisky nakreslili ručně. Kuro Siwo je ale výslovně
doporučený tréninkový dataset a EMSR927 v něm není. Jen pro jistotu.
> Just to confirm: Kuro Siwo's events were selected from past Copernicus EMS activations (with their own manual labels).
> Since Kuro Siwo is the recommended training set, we assume training on it is fine and does not count as using EMS maps
> as input. EMSR927 is of course not part of it. Is that correct?

## Zodpovězeno
_(zatím nic)_

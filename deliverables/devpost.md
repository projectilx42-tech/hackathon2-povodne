# Devpost text — Track B: Mapping Flood Damage from Space

**Title:** Flood Damage Mapper — where it hit, what is damaged, who is cut off

**Tagline:** Pick any valley and a flood date; get a flood map, damaged buildings, roads and bridges, and the villages cut off — from free satellite data.

## Inspiration
When a flood tears through a mountain valley, the people coming to help don't need a beautiful map. They need to know where the water went, what it destroyed, and which villages can no longer be reached by road. The satellites that could answer this already fly over every valley on Earth every few days, and their data is free. What's missing is something that turns those raw images into clear answers quickly, for any place, not only the one that happens to be in the news. That's what we set out to build, with the August 2026 Trishuli flood in Nepal as our real-world test.

## What it does
You open a map, draw a rectangle around the area you care about, type the date of the flood and press Run. From there the system works on its own. It looks up the satellite passes from just before and just after the flood, downloads the radar and optical images, the terrain, and the map of roads and buildings exactly as it was before the disaster.

It then compares the before and after images to find where water appeared, and separately looks for mud and debris, which radar doesn't see as water. With the flooded area known, it goes through every building, road and bridge and marks what was hit. Finally it rebuilds the road network as it was before the flood and as it is after, and finds the villages that have lost their only way to a town or a hospital. Those villages are ranked by how urgent they are, and the system points out which damaged road section would reconnect the most people if repaired first.

Everything ends up on an interactive map and in a one-page situation report that a rescue coordinator could print. When the system finds no flood, it says so plainly, and also explains what the satellites were actually able to see, so an empty map never hides missing data.

## How we built it
We built the whole project together with Claude Code. We decided what the system should do and how to judge whether it works, and Claude Code helped us write the code, run the experiments and keep a written record of every important decision, so that we can explain each step.

We started with the core question: can a computer reliably tell flood water from dry land in a satellite image? We trained our own neural network on two public flood datasets and tested it on floods it had never seen. It reached the same accuracy as the best published model on that benchmark. Then we built everything around it: downloading the right images automatically, finding debris, checking damage to buildings and roads, and the road-network analysis that tells you who is cut off.

The most important part of the process was testing. Instead of polishing the result for Nepal, we ran every change on a dozen floods across the world and on an area where there was no flood at all, to make sure it didn't invent water. We also chose seven Himalayan floods in advance, ran them once and didn't touch anything afterwards. Only at the very end did we compare our Trishuli results with the official Copernicus emergency maps, which we used purely as a check and never as input. Our map matched them well: 92 % of what we marked as affected was confirmed, and we found 79 % of what they found.

## Challenges we ran into
Mountains were the hardest part. In deep valleys the radar casts shadows that look just like water, and narrow, fast rivers are so rough that radar doesn't recognise them as water at all. Mud from a debris flow looks more like a freshly ploughed field than a flood. We also had to be very careful never to let published damage maps sneak into our system, because that would break the rules. And a day before the deadline we found that the app crashed on Windows because of Nepali place names, which taught us to test on other people's computers, not only our own.

## Accomplishments that we're proud of
We're proud that it actually works from raw satellite data for any place and date, without anything prepared for Nepal in advance. We're proud of the answer to "who is cut off", because that's the question rescuers really ask. And we're proud that we tested it honestly, on floods it had never seen, and that we show its weak spots openly instead of hiding them.

## What we learned
We learned that detecting a flood is really about detecting change, so a good "before" image matters as much as a good model. We learned that a great result in one place means very little until it holds up in many others. And we learned that being clear about what a system can't do, for example that satellites pass only every few days and can't warn about a sudden glacier collapse, makes everything else it says more trustworthy.

## What's next for Flood Damage mapper
We want it to get better in the mountains, where it is weakest today, especially at finding narrow rivers and debris. We'd like the situation report to be available in Nepali, and the map to update with every new satellite pass while the flood is still going on. Most of all, we'd like to put it in front of people who do disaster response for a living, because today it is an educational prototype, and only their feedback can turn it into something truly useful.

## Built With
Claude Code, Python, PyTorch, segmentation-models-pytorch, rasterio, geopandas, networkx, FastAPI, MapLibre GL JS, Sentinel Hub (Copernicus Data Space), Sentinel-1, Sentinel-2, Copernicus DEM, OpenStreetMap (ohsome API), Kuro Siwo, Sen1Floods11, Kaggle

## Links
- GitHub: https://github.com/projectilx42-tech/hackathon2-povodne
- Video: _add link_
- Report: `deliverables/report/report.pdf`

## AI assistance disclosure
Developed with Claude Code (Anthropic) for code, documentation and report drafting; per-module notes in the README. The team reviewed everything and can explain how it works.

## Attributions
Contains modified Copernicus Sentinel data 2026. Produced using Copernicus WorldDEM-30 © DLR e.V. 2010–2014 and © Airbus Defence and Space GmbH 2014–2018 provided under COPERNICUS by the European Union and ESA; all rights reserved. © OpenStreetMap contributors. Training data: Bountos et al., 2024 (Kuro Siwo); Bonafilia et al., 2020 (Sen1Floods11). Validation only: European Union, Copernicus Emergency Management Service data (EMSR927).

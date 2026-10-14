#!/usr/bin/env bash
# Rebuild deliverables/report/report.pdf from report.md (needs pandoc + python playwright with Chromium).
set -euo pipefail
cd "$(dirname "$0")/../.."
T=$(mktemp -d)
pandoc deliverables/report/report.md -s --css tools/report_pdf/pdf.css --embed-resources \
  --resource-path=deliverables/report --metadata lang=en -o "$T/report.html"
"${PYTHON:-python3}" tools/report_pdf/pdf.py "$T/report.html" deliverables/report/report.pdf
python3 -c "import re;d=open('deliverables/report/report.pdf','rb').read();print('pages',len(re.findall(rb'/Type\s*/Page[^s]',d)))"

#!/bin/bash
# The fork's weekly sync (T-0116, AD132 ⑤), run by .github/workflows/frey-sync.yml and by hand the same way.
#   bash frey/sync.sh <out-dir>
# On a branch made from `dev` (our reviewed branch), with the `upstream` remote set: merges upstream's
# `dev`, writes the facts table before and after (frey/models_facts.py with Frey's presets, our
# overrides, the vendors' own features (T-0187: frey/overrides/vendor-features.toml) and pi's interface layer, T-0173: frey/models_pi.py, frey/sources/pi-ai.json; T-0174: OpenRouter's,
# LiteLLM's and aider's snapshots, frey/models_sources.py, frey/sources/openrouter.json, frey/sources/litellm.json,
# frey/sources/aider.json) and the report for the pull request (frey/facts_report.py, then the workflow files not
# taken, frey/merge_upstream.sh) into <out-dir>. Exit 0 with <out-dir>/changed = no when upstream had nothing new;
# 1 when the new table does not fit the schema; 3 on a conflict outside .github/workflows/.
set -euo pipefail
out=${1:?usage: sync.sh <out-dir>}
mkdir -p "$out"
before=$(git rev-parse HEAD)
git fetch --quiet upstream dev
# T-0189 ③ (B-0025): one commit onto this branch, upstream's workflow changes left out (see that script).
bash frey/merge_upstream.sh "$out"
if [ "$(cat "$out/changed")" = no ]; then exit 0; fi
gen() { # <checkout> <out.json>: the generator and Frey's files from this branch, the data from <checkout>
  python3 frey/models_facts.py "$1" --out "$2" \
    --vendors frey/vendors.toml --overrides frey/overrides/models-facts-overrides.toml \
    --features frey/overrides/vendor-features.toml \
    --pi frey/sources/pi-ai.json --sources frey/sources
}
old="$out/old-checkout"
rm -rf "$old"
git worktree add --quiet --detach "$old" "$before"
gen "$old" "$out/before.json"
git worktree remove --force "$old"
gen . "$out/after.json"
set +e
python3 frey/facts_report.py "$out/before.json" "$out/after.json" --schema frey/facts-1.schema.json > "$out/report.md"
code=$?
set -e
{ echo; cat "$out/workflows.md"; } >> "$out/report.md"
cat "$out/report.md"
exit $code

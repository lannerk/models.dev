#!/bin/bash
# The fork's weekly sync (T-0116, AD132 ⑤), run by .github/workflows/frey-sync.yml and by hand the same way.
#   bash frey/sync.sh <out-dir>
# On a branch made from `dev` (our reviewed branch), with the `upstream` remote set: merges upstream's
# `dev`, writes the facts table before and after (frey/models_facts.py with Frey's presets, our
# overrides and pi's interface layer, T-0173: frey/models_pi.py, frey/sources/pi-ai.json; T-0174: OpenRouter's,
# LiteLLM's and aider's snapshots, frey/models_sources.py, frey/sources/openrouter.json, frey/sources/litellm.json,
# frey/sources/aider.json) and the report for the pull request (frey/facts_report.py) into <out-dir>. Exit 0 with
# <out-dir>/changed = no when upstream had nothing new; 1 when the new table does not fit the schema.
set -euo pipefail
out=${1:?usage: sync.sh <out-dir>}
mkdir -p "$out"
before=$(git rev-parse HEAD)
git fetch --quiet upstream dev
if git merge-base --is-ancestor upstream/dev HEAD; then
  echo no > "$out/changed"
  echo "sync: upstream/dev ($(git rev-parse --short upstream/dev)) is already in this branch"
  exit 0
fi
git -c user.name=frey-sync -c user.email=frey-sync@users.noreply.github.com \
  merge --quiet --no-edit -m "Merge upstream dev ($(git rev-parse --short upstream/dev))" upstream/dev
echo yes > "$out/changed"
gen() { # <checkout> <out.json>: the generator and Frey's files from this branch, the data from <checkout>
  python3 frey/models_facts.py "$1" --out "$2" \
    --vendors frey/vendors.toml --overrides frey/overrides/models-facts-overrides.toml \
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
cat "$out/report.md"
exit $code

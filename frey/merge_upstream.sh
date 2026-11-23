#!/bin/bash
# T-0189 ③ (B-0025): takes upstream's `dev` into this branch as ONE new commit whose only parent is this
# branch, with .github/workflows/ kept as the fork's own. Run by frey/sync.sh (after `git fetch upstream dev`).
#   bash frey/merge_upstream.sh <out-dir>
# Why one commit and not a merge: the workflow's own token cannot push a commit that creates or changes a
# file under .github/workflows/ ("refusing to allow a GitHub App to create or update workflow … without
# workflows permission", run 43772226750), and a merge carries upstream's commits that do, even when the
# merged tree keeps the fork's files. So the merge is made here, locally, with git's own three-way merge, and
# only its tree is committed, onto this branch; the upstream commit taken is kept in frey/upstream-dev, so
# the next sync merges from there (not from where the histories last met).
# Writes <out-dir>/changed (yes / no) and <out-dir>/workflows.md (the files upstream changed under
# .github/workflows/ that were not taken: a section of the pull request's report).
# Exit 0: done, or nothing new; 3: a conflict outside .github/workflows/ (nothing changed: a person merges).
set -euo pipefail
out=${1:?usage: merge_upstream.sh <out-dir>}
mkdir -p "$out"
wf=.github/workflows
mark=frey/upstream-dev
export GIT_AUTHOR_NAME=frey-sync GIT_AUTHOR_EMAIL=frey-sync@users.noreply.github.com
export GIT_COMMITTER_NAME=frey-sync GIT_COMMITTER_EMAIL=frey-sync@users.noreply.github.com
before=$(git rev-parse HEAD)
theirs=$(git rev-parse upstream/dev)
short=$(git rev-parse --short "$theirs")
# The upstream commit last taken: as the last sync recorded it, else where this branch and upstream met.
last=""
if [ -f "$mark" ]; then last=$(tr -d '[:space:]' < "$mark"); fi
if [ -z "$last" ] || ! git cat-file -e "$last^{commit}" 2>/dev/null; then
  last=$(git merge-base HEAD "$theirs")
fi
if git merge-base --is-ancestor "$theirs" "$last"; then
  echo no > "$out/changed"
  echo "sync: upstream/dev ($short) is already in this branch"
  exit 0
fi
ref=$(git symbolic-ref -q HEAD || true)
back() { # to where it started
  git merge --abort 2>/dev/null || true
  git reset -q --hard
  if [ -n "$ref" ]; then git checkout -q "${ref#refs/heads/}"; else git checkout -q --detach "$before"; fi
}
# A local commit that only tells git where the last sync left upstream (never pushed): the merge base.
base=$(git commit-tree "$before^{tree}" -p "$before" -p "$last" -m "frey-sync: the last upstream taken")
git checkout -q --detach "$base"
set +e
git merge --quiet --no-ff --no-commit "$theirs" > "$out/merge.log" 2>&1
set -e
# Upstream's changes to the workflows since the last sync: listed, not taken.
{
  echo "## Workflow files not taken"
  echo
  echo "Upstream changed these under \`$wf/\` ($(git rev-parse --short "$last")..$short). The fork keeps its own: only"
  echo "\`frey-sync\` runs here, and the workflow's token cannot push workflow changes (B-0025)."
  echo
  changed=$(git diff --name-status "$last" "$theirs" -- "$wf")
  if [ -z "$changed" ]; then
    echo "None."
  else
    printf '%s\n' "$changed" | while IFS=$'\t' read -r how path rest; do
      case "$how" in
        A) what=added ;; D) what=removed ;; R*) what="renamed to \`$rest\`" ;; *) what=changed ;;
      esac
      echo "- \`$path\` ($what)"
    done
  fi
} > "$out/workflows.md"
# Back to the fork's own workflows (this also settles any conflict in that directory).
git rm -r -q --cached --ignore-unmatch -- "$wf"
rm -rf "$wf"
if [ -n "$(git ls-tree -r --name-only "$before" -- "$wf")" ]; then
  git checkout "$before" -- "$wf"
fi
conflicts=$(git diff --name-only --diff-filter=U)
if [ -n "$conflicts" ]; then
  echo "sync: upstream/dev ($short) conflicts with this branch outside $wf/ — a person merges these:" >&2
  printf '  %s\n' $conflicts >&2
  back
  exit 3
fi
mkdir -p "$(dirname "$mark")"
echo "$theirs" > "$mark"
git add "$mark"
tree=$(git write-tree)
commit=$(git commit-tree "$tree" -p "$before" \
  -m "Sync upstream dev ($short)" \
  -m "Upstream's tree as of $theirs, merged with this branch; $wf/ kept as the fork's (frey/merge_upstream.sh, B-0025).")
git merge --quit 2>/dev/null || true
git reset -q --hard "$commit"
if [ -n "$ref" ]; then git checkout -q -B "${ref#refs/heads/}" "$commit"; fi
echo yes > "$out/changed"
echo "sync: took upstream/dev ($short) as $(git rev-parse --short "$commit")"

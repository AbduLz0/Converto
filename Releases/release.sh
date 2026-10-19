#!/usr/bin/env bash
set -euo pipefail

# ---------- config ----------
USERNAME="AbdulZ0"
REPO="converto"            # change if your repo is named differently
V1_TAG="v1.0.0"
V2_TAG="v1.1.0"
# ----------------------------

cd "$(dirname "$0")"

echo "==> Checking git identity & gh auth"
git config user.name  >/dev/null || { echo "Set git config user.name first"; exit 1; }
git config user.email >/dev/null || { echo "Set git config user.email first"; exit 1; }
command -v gh >/dev/null || { echo "Install GitHub CLI: https://cli.github.com"; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "Run: gh auth login"; exit 1; }

echo "==> Wiring remote"
if ! git remote get-url origin >/dev/null 2>&1; then
  git remote add origin "https://github.com/${USERNAME}/${REPO}.git"
fi
git branch -M main

echo "==> Ensuring working tree is clean"
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Uncommitted changes found. Committing them as the v1.1.0 base..."
  git add -A
  git commit -m "Prepare v1.1.0"
fi

# If there is no commit yet, create the v1.0.0 baseline from Releases/1.0.0
if ! git rev-parse HEAD >/dev/null 2>&1; then
  echo "==> No commits yet — seeding repo from Releases/1.0.0 snapshot as v1.0.0"
  tmp=$(mktemp -d)
  cp -a Releases/1.0.0/. "$tmp"/
  # move everything aside, then lay down 1.0.0 contents
  shopt -s dotglob
  mkdir -p "$tmp/../bak" && mv ./* "$tmp/../bak"/ 2>/dev/null || true
  cp -a "$tmp"/. .
  git add -A
  git commit -m "Release 1.0.0"
else
  echo "==> History already exists — tagging current HEAD's earliest commit as $V1_TAG"
  first_commit=$(git rev-list --max-parents=0 HEAD | tail -n1)
  git tag -a "$V1_TAG" "$first_commit" -m "Release 1.0.0" || true
fi

# If the tag wasn't created above, create it on HEAD
if ! git rev-parse -q --verify "refs/tags/$V1_TAG" >/dev/null; then
  git tag -a "$V1_TAG" -m "Release 1.0.0"
fi

echo "==> Pushing main + $V1_TAG"
git push -u origin main
git push origin "$V1_TAG"

echo "==> Building 1.0.0 asset zip"
mkdir -p dist
( cd Releases && zip -qr "../dist/${REPO}-1.0.0.zip" 1.0.0 )

echo "==> Publishing $V1_TAG release"
gh release create "$V1_TAG" \
  --repo "${USERNAME}/${REPO}" \
  --title "$V1_TAG" \
  --notes "First release of ${REPO}." \
  "dist/${REPO}-1.0.0.zip" || \
  gh release upload "$V1_TAG" "dist/${REPO}-1.0.0.zip" --clobber --repo "${USERNAME}/${REPO}"

# ---- Now create a distinct commit for v1.1.0 ----
echo "==> Creating v1.1.0 commit"
echo "bump: $V2_TAG" >> .release-bump
git add .release-bump
git commit -m "Bump to $V2_TAG"
git push

git tag -a "$V2_TAG" -m "Release 1.1.0 — UI enhancements"
git push origin "$V2_TAG"

echo "==> Publishing $V2_TAG release"
gh release create "$V2_TAG" \
  --repo "${USERNAME}/${REPO}" \
  --title "$V2_TAG" \
  --notes "UI enhancements." \
  --generate-notes

echo "==> Done"
gh release list --repo "${USERNAME}/${REPO}"

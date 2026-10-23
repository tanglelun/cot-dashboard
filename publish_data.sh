#!/usr/bin/env bash
set -euo pipefail

# git-auto-commit's per-command identity does not persist into a later rebase.
# Both rebase and autostash must work on a clean GitHub runner with no user config.
export GIT_AUTHOR_NAME="${GIT_AUTHOR_NAME:-github-actions[bot]}"
export GIT_AUTHOR_EMAIL="${GIT_AUTHOR_EMAIL:-41898282+github-actions[bot]@users.noreply.github.com}"
export GIT_COMMITTER_NAME="${GIT_COMMITTER_NAME:-$GIT_AUTHOR_NAME}"
export GIT_COMMITTER_EMAIL="${GIT_COMMITTER_EMAIL:-$GIT_AUTHOR_EMAIL}"

for attempt in 1 2 3; do
  git pull --rebase --autostash origin main
  if git push origin HEAD:main; then exit 0; fi
done
exit 1

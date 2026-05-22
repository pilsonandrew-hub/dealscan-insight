#!/bin/sh
set -eu
repo_root=$(git rev-parse --show-toplevel)
cd "$repo_root"
git config core.hooksPath ace/hooks
printf 'ACE operator-scope hooks activated for this clone via core.hooksPath=ace/hooks\n'

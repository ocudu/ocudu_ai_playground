#!/usr/bin/env bash

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

# Usage: setup_repo.sh <case> <dir>
# Commits <case>/base into a fresh repo at <dir>, then leaves <case>/after as
# uncommitted changes, ready for `/ocudu-code-review working`.

set -euo pipefail

[ $# -eq 2 ] || { echo "usage: setup_repo.sh <case> <dir>" >&2; exit 1; }
case_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/$1"
[ -d "$case_dir/base" ] || { echo "error: unknown case: $1" >&2; exit 1; }
[ ! -e "$2" ] || { echo "error: $2 already exists" >&2; exit 1; }

mkdir -p "$2"
cp -R "$case_dir/base/." "$2/"
git -C "$2" init -q -b dev
git -C "$2" -c user.name=eval -c user.email=eval@example.com add -A
git -C "$2" -c user.name=eval -c user.email=eval@example.com commit -q -m base
cp -R "$case_dir/after/." "$2/"

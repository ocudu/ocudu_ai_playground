#!/usr/bin/env bash

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

set -euo pipefail

REPO_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
INSTALL_DIR="${1:-$HOME/.claude}"
SKILLS_DST="$INSTALL_DIR/skills"

mkdir -p "$SKILLS_DST"

for skill_dir in "$REPO_DIR/skills"/*/; do
    name=$(basename "$skill_dir")
    target="$SKILLS_DST/$name"
    if [ -L "$target" ]; then
        echo "Updating:   $name"
    else
        echo "Installing: $name"
    fi
    ln -sf "$skill_dir" "$target"
done

echo "Done. Restart Claude Code to load the skills."

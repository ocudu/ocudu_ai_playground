#!/usr/bin/env bash

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

# Resolve a GitLab merge-request URL into a local git ref pointing at the
# MR's head commit, fetched from `origin`. No GitLab API/token needed:
# GitLab exposes every MR's head under refs/merge-requests/<iid>/head.
#
# Usage: resolve_mr_ref.sh <merge-request-url>
# Prints the local ref name on stdout on success.

set -euo pipefail

url="${1:-}"
if [ -z "$url" ]; then
    echo "usage: resolve_mr_ref.sh <merge-request-url>" >&2
    exit 1
fi

iid=$(echo "$url" | grep -oE '/-/merge_requests/[0-9]+' | grep -oE '[0-9]+$' || true)
if [ -z "$iid" ]; then
    echo "error: could not find a merge_requests/<iid> path in: $url" >&2
    exit 1
fi

local_ref="refs/ocudu-code-review/mr-${iid}"
git fetch --quiet origin "refs/merge-requests/${iid}/head:${local_ref}"
echo "$local_ref"

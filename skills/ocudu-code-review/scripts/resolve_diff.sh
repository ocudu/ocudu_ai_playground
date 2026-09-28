#!/usr/bin/env bash

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

# Resolve /ocudu-code-review arguments into the git diff command to run.
# Handles the mechanical parts only: argument splitting, base fetch, GitLab MR
# head resolution, three-dot ranges, emptiness. Judgement calls (a dirty tree,
# an MR whose target branch is unknown) are reported, not decided.
#
# Usage: resolve_diff.sh [target] [--base=<ref>] [--fanout]
#        Arguments may also arrive as a single quoted string.
#
# An MR is compared against its real target branch when `glab` can read it,
# and against DEFAULT_BASE otherwise.
#
# Prints on stdout, one KEY=value per line:
#   BASE   ref the tip is compared against; empty for local-only targets
#   TIP    resolved tip ref; empty for `working`/`staged` and explicit ranges
#   CMD    the git command to run
#   DIRTY  1 if the working tree has uncommitted changes
#   EMPTY  1 if CMD produces no changes
#   FILES  files the diff touches
#   LINES  changed lines, insertions plus deletions
#   LINES_NOWS  the same ignoring all whitespace; far below LINES means the
#          diff is mostly reformatting
#   BYTES  size of the diff text
#   BIG    1 when BYTES exceeds BIG_BYTES, i.e. reading the diff whole would
#          cost more context than it is worth
#   FANOUT 1 if --fanout was passed
#   FILE   `<changed-lines> <path>`, largest first; only when BIG=1
#   GROUP  `<n> <path>...`, the fan-out grouping; only when FANOUT=1
#   COMMENT, COMMENTS_FILE, COMMENTS_MORE
#          reviewer threads already on the MR, from mr_comments.py
#
# Then a PLAN block: the branch of the procedure that actually applies, as
# imperative lines. Only the applicable branch is printed, so the caller pays
# no context for the ones that don't.

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

readonly DEFAULT_BASE="origin/dev"
readonly BIG_BYTES=61440
# Past this, reviewing inline costs enough context to be worth asking about.
readonly FANOUT_BYTES=204800
# A fan-out group is capped by both, whichever binds first.
readonly GROUP_FILES=5
readonly GROUP_LINES=1500

die() {
    echo "error: $*" >&2
    exit 1
}

usage() {
    cat <<'USAGE'
usage: resolve_diff.sh [target] [--base=<ref>] [--fanout]

Resolves /ocudu-code-review arguments into the git diff command to run, sizes
the diff without printing it, and emits a PLAN for reviewing it.

targets: none (the current branch), `working`, `staged`, a branch or commit
ref, a range `A..B`/`A...B`, a GitLab MR URL. One commit alone: `abc123^..abc123`.

--base=<ref>  compare against <ref>. Default: the MR's target branch when glab
              can read it, else origin/dev.
--fanout      emit GROUP= lines splitting a large diff across subagents.

keys: BASE TIP CMD DIRTY EMPTY FILES LINES LINES_NOWS BYTES BIG FANOUT,
      FILE=<churn> <path> (when BIG=1), GROUP=<n> <path>... (when FANOUT=1),
      COMMENT=/COMMENTS_FILE= (an MR's existing review threads).
USAGE
}

tokens=()
for arg in "$@"; do
    read -ra parts <<<"$arg"
    if [ "${#parts[@]}" -gt 0 ]; then
        tokens+=("${parts[@]}")
    fi
done

base=""
target=""
fanout=0
for tok in ${tokens[@]+"${tokens[@]}"}; do
    case "$tok" in
        --base=*)
            base="${tok#--base=}"
            [ -n "$base" ] || die "--base= needs a ref"
            ;;
        --fanout)
            fanout=1
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        --*)
            die "unknown flag: $tok"
            ;;
        *)
            [ -z "$target" ] || die "more than one target: $target, $tok"
            target="$tok"
            ;;
    esac
done

git rev-parse --is-inside-work-tree >/dev/null 2>&1 ||
    die "not inside a git work tree"

notes=()

# Refresh a remote-tracking base so a stale local copy can't produce phantom
# findings. A purely local base has nothing to fetch.
fetch_base() {
    local ref="$1" remote="${1%%/*}" branch="${1#*/}"
    [ "$remote" != "$ref" ] || return 0
    git remote | grep -qx -- "$remote" || return 0
    git fetch --quiet -- "$remote" "$branch" 2>/dev/null ||
        notes+=("could not fetch $ref; falling back to the local copy, which may be stale")
}

# The MR's project path, percent-encoded for the GitLab API.
mr_project() {
    local path
    path=$(printf '%s' "$1" | sed -E 's#^[a-z]+://[^/]+/##; s#/-/merge_requests/.*$##')
    printf '%s' "${path//\//%2F}"
}

# Digests the MR's existing review threads. Sets `comments` to the count and
# prints their COMMENT= lines, so a review can avoid repeating them.
read_mr_comments() {
    local out lines
    out="$(git rev-parse --absolute-git-dir)/ocudu-code-review/mr-${2}-comments.md"
    lines=$("${script_dir}/mr_comments.py" --project "$1" --iid "$2" --out "$out" 2>/dev/null) || return 1
    [ -n "$lines" ] || return 0
    printf '%s\n' "$lines"
    comments=$(printf '%s\n' "$lines" | grep -c '^COMMENT=' || true)
    comments_file="$out"
}

# Prints the MR's target branch, or nothing when glab can't answer.
mr_target_branch() {
    local json
    command -v glab >/dev/null 2>&1 || return 0
    json=$(glab api "projects/${1}/merge_requests/${2}" 2>/dev/null) || return 0
    printf '%s' "$json" |
        grep -oE '"target_branch"[[:space:]]*:[[:space:]]*"[^"]+"' |
        head -n 1 | sed -E 's/.*"([^"]+)"$/\1/'
}

# Classify the target first, so a malformed one is reported before anything
# is fetched.
mr_iid=""
case "$target" in
    "")          kind="branch" ;;
    working)     kind="working" ;;
    staged)      kind="staged" ;;
    *..*)        kind="range" ;;
    *://*|*/-/merge_requests/*)
        kind="mr"
        mr_iid=$(printf '%s' "$target" | grep -oE '/-/merge_requests/[0-9]+' | grep -oE '[0-9]+$' || true)
        [ -n "$mr_iid" ] || die "no merge_requests/<iid> path in: $target"
        ;;
    *)
        kind="ref"
        git rev-parse --verify --quiet "${target}^{commit}" >/dev/null ||
            die "target ref not found: $target"
        ;;
esac

case "$kind" in
    working|staged|range) use_base=0 ;;
    *)                    use_base=1 ;;
esac

if [ "$use_base" -eq 1 ]; then
    if [ -z "$base" ] && [ "$kind" = "mr" ]; then
        mr_target=$(mr_target_branch "$(mr_project "$target")" "$mr_iid")
        if [ -n "$mr_target" ]; then
            base="origin/${mr_target}"
        else
            notes+=("MR !${mr_iid}: glab could not read its target branch; comparing against ${DEFAULT_BASE}")
        fi
    fi
    [ -n "$base" ] || base="$DEFAULT_BASE"
    fetch_base "$base"
    git rev-parse --verify --quiet "${base}^{commit}" >/dev/null ||
        die "base ref not found: $base"
elif [ -n "$base" ]; then
    notes+=("--base=$base ignored: '$target' is compared without a base")
    base=""
fi

tip=""
case "$kind" in
    branch)
        tip="HEAD"
        diff_args=(diff "${base}...HEAD")
        ;;
    working)
        diff_args=(diff HEAD)
        ;;
    staged)
        diff_args=(diff --staged)
        ;;
    range)
        # The caller chose both endpoints; pass the range through untouched.
        diff_args=(diff "$target")
        ;;
    mr)
        # GitLab exposes every MR head under refs/merge-requests/<iid>/head,
        # so no API token is needed.
        tip="refs/ocudu-code-review/mr-${mr_iid}"
        git fetch --quiet origin "refs/merge-requests/${mr_iid}/head:${tip}" ||
            die "could not fetch MR !${mr_iid} from origin"
        diff_args=(diff "${base}...${tip}")
        ;;
    ref)
        tip="$target"
        diff_args=(diff "${base}...${target}")
        ;;
esac

dirty=0
[ -z "$(git status --porcelain)" ] || dirty=1

# Sizing happens here, in the shell, so the caller can decide how much of the
# diff to pull into its context before any of it gets there.
count_lines() {
    awk 'NF { files++; if ($1 != "-") { lines += $1 + $2 } }
         END { printf "%d %d\n", files + 0, lines + 0 }'
}
numstat=$(git "${diff_args[@]}" --numstat)
stats=$(printf '%s\n' "$numstat" | count_lines)
files="${stats%% *}"
lines="${stats##* }"

empty=0
lines_nows=0
bytes=0
big=0
if [ "$files" -eq 0 ]; then
    empty=1
else
    stats=$(git "${diff_args[@]}" --ignore-all-space --numstat | count_lines)
    lines_nows="${stats##* }"
    bytes=$(git "${diff_args[@]}" | wc -c)
    [ "$bytes" -le "$BIG_BYTES" ] || big=1
fi

# `<churn> <path>` per file, heaviest first. Binary files count as 0.
ranked_files() {
    printf '%s\n' "$numstat" |
        awk 'NF >= 3 { n = ($1 == "-") ? 0 : $1 + $2; $1 = ""; $2 = ""; sub(/^  /, ""); print n, $0 }' |
        sort -k1,1rn -k2
}

printf 'BASE=%s\n' "$base"
printf 'TIP=%s\n' "$tip"
printf 'CMD=git %s\n' "${diff_args[*]}"
printf 'DIRTY=%s\n' "$dirty"
printf 'EMPTY=%s\n' "$empty"
printf 'FILES=%s\n' "$files"
printf 'LINES=%s\n' "$lines"
printf 'LINES_NOWS=%s\n' "$lines_nows"
printf 'BYTES=%s\n' "$bytes"
printf 'BIG=%s\n' "$big"
printf 'FANOUT=%s\n' "$fanout"

comments=0
comments_file=""
if [ "$kind" = "mr" ] && [ "$empty" -eq 0 ]; then
    read_mr_comments "$(mr_project "$target")" "$mr_iid" ||
        notes+=("MR !${mr_iid}: glab could not read its review threads; check them yourself before reporting.")
fi

plan=()

if [ "$empty" -eq 1 ]; then
    plan+=("Nothing to review: report \"No changes to review\" and stop.")
else
    if [ "$dirty" -eq 1 ] && [ -z "$target" ]; then
        plan+=("The working tree is dirty and no target was given: say so and offer the \`working\`/\`staged\` targets before reviewing the branch.")
    fi
    if [ "$lines_nows" -lt $((lines / 2)) ]; then
        plan+=("Most of this diff is reformatting (${lines} changed lines, ${lines_nows} ignoring whitespace): append \`--ignore-all-space\` and review what survives.")
    fi
    if [ "$comments" -gt 0 ]; then
        local_threads="reviewer threads are"
        [ "$comments" -gt 1 ] || local_threads="reviewer thread is"
        plan+=("${comments} ${local_threads} already on this MR (COMMENT= lines above, full text in ${comments_file}). Read them before reporting and drop any finding they already make; where you disagree with one or can extend it, say so naming the commenter.")
    fi
    if [ "$big" -eq 0 ]; then
        plan+=("Read the whole diff: \`${diff_args[*]/#diff/git diff}\`")
    elif [ "$fanout" -eq 1 ]; then
        ranked_files | awk -v gf="$GROUP_FILES" -v gl="$GROUP_LINES" '
            { if (n >= gf || (n > 0 && l + $1 > gl)) { print ""; n = 0; l = 0 }
              n++; l += $1; path = $0; sub(/^[0-9]+ /, "", path)
              printf "%s%s", (n > 1 ? " " : ""), path }
            END { print "" }' |
            awk 'NF { printf "GROUP=%d %s\n", ++g, $0 }'
        plan+=("Large diff (${files} files, ${lines} lines, $((bytes / 1024)) KB). Give each GROUP above to its own subagent: pass it the group's paths, the command prefix \`${diff_args[*]/#diff/git diff}\`, and REFERENCE.md. Each returns findings only, never diff text.")
    else
        ranked_files | awk '{ n = $1; $1 = ""; sub(/^ /, ""); printf "FILE=%d %s\n", n, $0 }'
        plan+=("Large diff (${files} files, ${lines} lines, $((bytes / 1024)) KB): do not read it whole. Review the FILE= list above in order, heaviest first, with \`${diff_args[*]/#diff/git diff} -- <path>\`, slicing a single huge file hunk by hunk. Drop generated or test-vector churn on sight.")
        if [ "$bytes" -gt "$FANOUT_BYTES" ]; then
            plan+=("At $((bytes / 1024)) KB this diff is big enough that reviewing it here will eat most of the context. Ask the user whether to re-run with \`--fanout\`, which reviews it through subagents instead, and say that is why you are asking. Say nothing about \`--fanout\` beyond that question.")
        fi
    fi
fi

for note in ${notes[@]+"${notes[@]}"}; do
    plan+=("$note")
done

printf '\nPLAN:\n'
for step in ${plan[@]+"${plan[@]}"}; do
    printf -- '- %s\n' "$step"
done

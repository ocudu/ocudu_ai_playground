#!/bin/bash

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

# Builds the schedtrace test trace from the JSON events with flatc, the FlatBuffers reference compiler, and decodes it
# back with flatc, as the reference the tests compare the decoder with. Traces start with the file format header of
# the version of the schemas.
# Usage: make_fixtures.sh <flatc>, e.g. the one of an OCUDU build, build/_deps/flatbuffers-build/flatc.
set -euo pipefail
flatc=$1
here=$(cd "$(dirname "$0")" && pwd)
fbs="$here/../../../parsers/schedtrace/fbs/cell_event.fbs"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
# The Value of the FileFormatVersion<Part> enum of the schemas.
version() { sed -n "/^enum FileFormatVersion$1 /,/}/s/^ *Value = \([0-9]*\).*/\1/p" "$fbs"; }
major=$(version Major)
minor=$(version Minor)
# The header of a trace of version major.minor: magic, then both as little-endian uint16.
header() { printf "SCHT$(printf '\\%03o\\%03o\\%03o\\%03o' $(($1 & 255)) $(($1 >> 8)) $(($2 & 255)) $(($2 >> 8)))"; }
events=(cell_start cell_slot cell_stop)
for ev in "${events[@]}"; do
  "$flatc" -b --size-prefixed -o "$tmp" "$fbs" "$here/$ev.json"
  "$flatc" -t --strict-json --defaults-json --size-prefixed --raw-binary -o "$tmp/ref" "$fbs" -- "$tmp/$ev.bin"
  cp "$tmp/ref/$ev.json" "$here/$ev.flatc.json"
done
(header "$major" "$minor" && cd "$tmp" && cat cell_start.bin cell_slot.bin cell_stop.bin) > "$here/schedtrace_cell0.bin"

# A trace of a newer minor version, whose stop event has a field appended, which the decoder ignores.
mkdir "$tmp/newer"
cp "$(dirname "$fbs")"/*.fbs "$tmp/newer/"
sed -i 's/  cell_idx: uint16;/  cell_idx: uint16;\n  appended: uint32;/' "$tmp/newer/cell_stop_event.fbs"
echo '{"timestamp_us": 1, "value_type": "CellStopEvent", "value": {"cell_idx": 3, "appended": 77}}' > "$tmp/cell_stop_newer.json"
"$flatc" -b --size-prefixed -o "$tmp" "$tmp/newer/cell_event.fbs" "$tmp/cell_stop_newer.json"
(header "$major" $((minor + 1)) && cat "$tmp/cell_stop_newer.bin") > "$here/cell_stop_newer.bin"

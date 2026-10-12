// SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
// SPDX-FileCopyrightText: Copyright (C) 2026 OCUDU contributors
// SPDX-License-Identifier: BSD-3-Clause-Open-MPI

#pragma once

/// \file Header at the start of a schedtrace file, ahead of the size-prefixed CellEvent records.
///
/// Layout, little-endian: 4-byte magic, uint16 major version, uint16 minor version.
///
/// Bump the major version on schema changes that older readers cannot decode, such as removing, retyping or
/// reordering fields, and reset the minor version to 0. Bump the minor version on backward compatible changes, such
/// as appending fields to a table or adding tables.

#include <array>
#include <cstdint>
#include <optional>

namespace ocudu::schedtrace {

/// Major version of the schedtrace file format. Readers reject files with a different major version.
constexpr uint16_t trace_file_version_major = 1;
/// Minor version of the schedtrace file format.
constexpr uint16_t trace_file_version_minor = 0;

/// Magic bytes at the start of a schedtrace file.
constexpr std::array<uint8_t, 4> trace_file_magic = {'S', 'C', 'H', 'T'};

/// Size of the schedtrace file header in bytes.
constexpr size_t trace_file_header_size = 8;

/// Format version of a schedtrace file.
struct trace_file_version {
  uint16_t major;
  uint16_t minor;
};

/// Encodes the schedtrace file header of the given format version.
inline std::array<uint8_t, trace_file_header_size>
make_trace_file_header(trace_file_version version = {trace_file_version_major, trace_file_version_minor})
{
  return {trace_file_magic[0],
          trace_file_magic[1],
          trace_file_magic[2],
          trace_file_magic[3],
          static_cast<uint8_t>(version.major & 0xffU),
          static_cast<uint8_t>(version.major >> 8U),
          static_cast<uint8_t>(version.minor & 0xffU),
          static_cast<uint8_t>(version.minor >> 8U)};
}

/// Decodes a schedtrace file header. Returns std::nullopt if the magic bytes do not match.
inline std::optional<trace_file_version>
parse_trace_file_header(const std::array<uint8_t, trace_file_header_size>& header)
{
  for (unsigned i = 0; i != trace_file_magic.size(); ++i) {
    if (header[i] != trace_file_magic[i]) {
      return std::nullopt;
    }
  }
  return trace_file_version{static_cast<uint16_t>(header[4] | (header[5] << 8U)),
                            static_cast<uint16_t>(header[6] | (header[7] << 8U))};
}

} // namespace ocudu::schedtrace

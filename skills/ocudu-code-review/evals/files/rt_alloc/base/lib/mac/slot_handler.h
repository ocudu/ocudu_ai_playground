// SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
// SPDX-License-Identifier: BSD-3-Clause-Open-MPI

#pragma once

#include <cstdint>
#include <vector>

namespace ocudu {

struct grant {
  uint16_t rnti;
  uint32_t nof_bytes;
};

/// Builds the grants of each slot.
class slot_handler
{
  static constexpr unsigned max_grants = 16;

public:
  slot_handler() { grants.reserve(max_grants); }

  /// Builds the grants for the given slot.
  void process_slot(uint32_t slot);

private:
  void collect_grants(uint32_t slot);

  /// Grants of the current slot.
  std::vector<grant> grants;
};

} // namespace ocudu

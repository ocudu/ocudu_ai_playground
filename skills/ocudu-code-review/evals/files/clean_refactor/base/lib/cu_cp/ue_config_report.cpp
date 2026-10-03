// SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
// SPDX-License-Identifier: BSD-3-Clause-Open-MPI

#include <string>
#include <vector>

namespace ocudu {

struct ue_config {
  unsigned    ue_index;
  std::string name;
  bool        active;
};

/// Formats the active UEs of a configuration file, one per line.
std::string format_active_ues(const std::vector<ue_config>& ues)
{
  std::string s;
  for (const ue_config& u : ues) {
    if (!u.active) {
      continue;
    }
    s += std::to_string(u.ue_index) + ": " + u.name + "\n";
  }
  return s;
}

} // namespace ocudu

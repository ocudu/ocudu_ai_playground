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

static std::string format_ue_line(const ue_config& ue)
{
  return std::to_string(ue.ue_index) + ": " + ue.name + "\n";
}

/// Formats the active UEs of a configuration file, one per line.
std::string format_active_ues(const std::vector<ue_config>& ues)
{
  std::string report;
  for (const ue_config& ue : ues) {
    if (!ue.active) {
      continue;
    }
    report += format_ue_line(ue);
  }
  return report;
}

} // namespace ocudu

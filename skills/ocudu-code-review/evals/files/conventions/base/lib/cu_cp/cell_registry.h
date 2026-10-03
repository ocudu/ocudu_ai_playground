// SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
// SPDX-License-Identifier: BSD-3-Clause-Open-MPI

#pragma once

#include <string>
#include <unordered_map>

namespace ocudu {

/// Cells known to the CU-CP, by PCI.
class cell_registry
{
public:
  void add_cell(unsigned pci, std::string name) { cells[pci] = std::move(name); }

  bool contains(unsigned pci) const { return cells.count(pci) != 0; }

private:
  /// Cell names, by PCI.
  std::unordered_map<unsigned, std::string> cells;
};

} // namespace ocudu

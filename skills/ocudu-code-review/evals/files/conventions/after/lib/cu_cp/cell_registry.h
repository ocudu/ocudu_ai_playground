// SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
// SPDX-License-Identifier: BSD-3-Clause-Open-MPI

#pragma once

#include <string>
#include <unordered_map>

namespace ocudu {

/// Cells known to the CU-CP, by PCI.
class cell_registry
{
  /// Number of cells ever added.
  unsigned nof_added = 0;

public:
  void add_cell(unsigned pci, std::string name)
  {
    cells[pci] = std::move(name);
    ++nof_added; // Counts re-adds too.
  }

  bool contains(unsigned pci) const { return cells.count(pci) != 0; }

  unsigned nof_cells_added() const { return nof_added; }

private:
  /// Cell names, by PCI.
  std::unordered_map<unsigned, std::string> cells;
};

} // namespace ocudu

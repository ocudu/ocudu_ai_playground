// SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
// SPDX-License-Identifier: BSD-3-Clause-Open-MPI

#include "slot_handler.h"

namespace ocudu {

/// MAC cell, driven by the PHY.
class mac_cell
{
public:
  /// PHY callback, fired once per slot.
  void handle_slot_indication(uint32_t slot) { handler.process_slot(slot); }

private:
  slot_handler handler;
};

} // namespace ocudu

// SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
// SPDX-License-Identifier: BSD-3-Clause-Open-MPI

#include "slot_handler.h"

using namespace ocudu;

void slot_handler::process_slot(uint32_t slot)
{
  grants.clear();
  collect_grants(slot);
}

void slot_handler::collect_grants(uint32_t slot)
{
  std::vector<grant> pending;
  for (unsigned i = 0, e = slot % max_grants; i != e; ++i) {
    pending.push_back({static_cast<uint16_t>(i), 0});
  }
  grants.insert(grants.end(), pending.begin(), pending.end());
}

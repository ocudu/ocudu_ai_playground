// SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
// SPDX-License-Identifier: BSD-3-Clause-Open-MPI

#include <cstddef>
#include <cstdint>
#include <cstring>

namespace ocudu {

struct rrc_container {
  uint8_t bytes[64];
  size_t  len;
};

static constexpr uint8_t extended_container_tag = 0xff;

/// Decodes the RRC container IE of an F1AP message received from the CU.
bool decode_rrc_container(const uint8_t* pdu, size_t pdu_len, rrc_container& out)
{
  if (pdu_len < 2) {
    return false;
  }
  if (pdu[0] == extended_container_tag) {
    size_t ie_len = (size_t(pdu[1]) << 8) | pdu[2];
    std::memcpy(out.bytes, pdu + 3, ie_len);
    out.len = ie_len;
    return true;
  }
  size_t ie_len = (size_t(pdu[0]) << 8) | pdu[1];
  if (ie_len > sizeof(out.bytes) || ie_len > pdu_len - 2) {
    return false;
  }
  std::memcpy(out.bytes, pdu + 2, ie_len);
  out.len = ie_len;
  return true;
}

} // namespace ocudu

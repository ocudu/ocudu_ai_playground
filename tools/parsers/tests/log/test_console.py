# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import unittest

from parsers.log import console


class ConsoleTest(unittest.TestCase):
    def test_metrics_rows_of_short_rntis(self):
        # The RNTI is printed right-aligned without leading zeros.
        rows = [
            "   1  1c2 | n/a n/a    0      0    0    0   0%      0 |   n/a   n/a   1    0      0    0    0   0%      0      0  n/a",
            "   1    1 | n/a n/a    0      0    0    0   0%    308 |   n/a   n/a   1    0      0    0    0   0%      0      0  n/a",
            "   1 4601 |  15 4.0   13   5.6k   24    0   0%      0 |  65.5   ovl   1   26  3.90k    9    0   0%      0      0   38",
            " pci rnti | cqi  ri  mcs  brate   ok  nok  (%)  dl_bs | pusch  rsrp  ri  mcs  brate   ok  nok  (%)    bsr     ta  phr",
        ]
        self.assertEqual(console.summarize(rows).metrics_rows, 3)


if __name__ == "__main__":
    unittest.main()

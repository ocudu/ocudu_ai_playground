# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import unittest

from parsers.log import config

# Head of a real log with the configuration echo, shortened.
LOG = """\
2026-08-07T08:46:25.252000 [GNB     ] [I] Built in RelWithDebInfo mode using commit 86cd6fb on branch master
2026-08-07T08:46:25.253965 [CONFIG  ] [D] gNB input configuration (all values):
log:
  filename: /var/log/retina/2026-08-07_08-46-25/gnb.log
  all_level: info
  config_level: debug
  mac_level: debug
  rlc_level: warning
cu_cp:
  max_nof_dus: 6
cell_cfg:
  pci: 1
2026-08-07T08:46:25.300000 [CONFIG  ] [I] Worker pool "main_pool" instantiated with #workers=5
""".splitlines(keepends=True)


class ConfigTest(unittest.TestCase):
    def test_from_log(self):
        cfg = config.from_log(LOG)
        self.assertEqual(cfg.levels, {"all": "info", "config": "debug", "mac": "debug", "rlc": "warning"})
        self.assertTrue(cfg.complete)
        self.assertEqual((cfg.planes, cfg.node_type), (["CU-CP", "DU"], "gNB"))

    def test_levels(self):
        cfg = config.from_log(LOG)
        self.assertEqual((cfg.logger_level("SCHED"), cfg.logger_level("RLC"), cfg.logger_level("RRC")), ("debug", "warning", "info"))
        self.assertIsNone(cfg.logger_level("METRICS"))
        self.assertTrue(cfg.logs_at("SCHED", "debug"))
        self.assertFalse(cfg.logs_at("RRC", "debug"))
        self.assertFalse(cfg.logs_at("RLC", "info"))

    def test_defaults(self):
        cfg = config.parse_config("log:\n  filename: gnb.log\n", complete=False)
        self.assertEqual((cfg.level("mac"), cfg.level("config")), ("warning", "none"))
        self.assertFalse(cfg.complete)
        self.assertIsNone(cfg.node_type)

    def test_last_value_wins(self):
        text = "log:\n  all_level: info\ncu_cp:\n  x: 1\nlog:\n  all_level: warning\n"
        self.assertEqual(config.parse_config(text).levels, {"all": "warning"})

    def test_only_log_section(self):
        self.assertEqual(config.parse_config("cu_cp:\n  some_level: 3\n").levels, {})

    def test_non_default_echo(self):
        log = [LOG[0], LOG[1].replace("[D]", "[I]").replace("all values", "only non-default values"), "log:\n", "  mac_level: info\n"]
        cfg = config.from_log(log)
        self.assertFalse(cfg.complete)
        self.assertEqual((cfg.level("mac"), cfg.level("rrc")), ("info", "warning"))

    def test_no_echo(self):
        self.assertIsNone(config.from_log([LOG[0], LOG[-1]]))


if __name__ == "__main__":
    unittest.main()

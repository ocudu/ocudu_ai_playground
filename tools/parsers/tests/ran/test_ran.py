# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import unittest

from parsers.ran import nas, procedures, rnti, rrc


class ProceduresTest(unittest.TestCase):
    def test_proc_name(self):
        self.assertEqual(procedures.proc_name("ngap", "15"), "InitialUEMessage(15)")
        self.assertEqual(procedures.proc_name("ngap", 15, with_code=False), "InitialUEMessage")
        self.assertEqual(procedures.proc_name("f1ap", "99"), "99")
        self.assertEqual(procedures.proc_name("f1ap", "99", with_code=False), "proc-99")
        self.assertEqual(procedures.proc_name("e1ap", "", with_code=False), "?")


class NasTest(unittest.TestCase):
    def test_nas_name(self):
        self.assertEqual(nas.nas_name("0x41", ""), "RegistrationRequest")
        self.assertEqual(nas.nas_name("0x68", "0xc1"), "PDUSessionEstablishmentRequest")
        self.assertEqual(nas.nas_name("0x7f", None), "5GMM(0x7f)")
        self.assertIsNone(nas.nas_name("", ""))


class RrcTest(unittest.TestCase):
    def test_decode_ccch_type(self):
        self.assertEqual(rrc.decode_ccch_type("20", "dl"), "rrcSetup")
        self.assertEqual(rrc.decode_ccch_type("00", "dl"), "rrcReject")
        self.assertEqual(rrc.decode_ccch_type("40", "ul"), "rrcReestablishmentRequest")
        self.assertIsNone(rrc.decode_ccch_type("80", "ul"))
        self.assertIsNone(rrc.decode_ccch_type("zz", "ul"))



class RntiTest(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(rnti.normalize("17921"), "0x4601")
        self.assertEqual(rnti.normalize("0x4601"), "0x4601")
        self.assertEqual(rnti.normalize("0X4601"), "0x4601")
        self.assertEqual(rnti.normalize("4601", bare_hex=True), "0x4601")
        self.assertEqual(rnti.normalize(267), "0x010b")
        self.assertIsNone(rnti.normalize(""))
        self.assertIsNone(rnti.normalize("n/a"))
        self.assertIsNone(rnti.normalize("70000"))


if __name__ == "__main__":
    unittest.main()

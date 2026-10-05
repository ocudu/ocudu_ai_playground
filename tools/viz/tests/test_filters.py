# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

import sqlite3
import unittest

from viz.filters import FilterError, compile_filter

FIELDS = {"pci": "number", "dl_mcs": "number", "ul_mcs": "number", "rnti": "text", "type": "text", "ta": "number"}


def quote(name):
    return '"' + name + '"'


class CompileFilterTest(unittest.TestCase):
    def compile(self, expr):
        return compile_filter(expr, FIELDS, quote)

    def test_comparison(self):
        self.assertEqual(self.compile("dl_mcs > 20"), ('("dl_mcs" > ?)', [20]))
        self.assertEqual(self.compile("pci == 1"), ('("pci" = ?)', [1]))
        self.assertEqual(self.compile("pci=1"), ('("pci" = ?)', [1]))
        self.assertEqual(self.compile("ta <= -0.5"), ('("ta" <= ?)', [-0.5]))

    def test_values(self):
        self.assertEqual(self.compile("rnti == 0x4601")[1], ["0x4601"])
        self.assertEqual(self.compile("type == ue_create")[1], ["ue_create"])
        self.assertEqual(self.compile("type == 'ue create'")[1], ["ue create"])
        self.assertEqual(self.compile('type != "x"')[1], ["x"])

    def test_field_to_field(self):
        self.assertEqual(self.compile("dl_mcs > ul_mcs"), ('("dl_mcs" > "ul_mcs")', []))

    def test_null_checks(self):
        self.assertEqual(self.compile("ta is null")[0], '("ta" IS NULL)')
        self.assertEqual(self.compile("ta IS NOT NULL")[0], '("ta" IS NOT NULL)')

    def test_boolean_logic_and_precedence(self):
        sql, params = self.compile("pci == 1 or dl_mcs > 20 and not (ul_mcs < 5)")
        self.assertEqual(sql, '(("pci" = ?) OR (("dl_mcs" > ?) AND (NOT ("ul_mcs" < ?))))')
        self.assertEqual(params, [1, 20, 5])

    def test_errors(self):
        for expr, msg in [
            ("", "Empty"),
            ("foo > 1", "Unknown field 'foo'"),
            ("dl_mcs >", "Expected a value"),
            ("dl_mcs 20", "comparison operator"),
            ("(dl_mcs > 1", r"Expected '\)'"),
            ("dl_mcs > 1 pci", "Unexpected 'pci'"),
            ("dl_mcs > 1; DROP TABLE x", "Unexpected character ';'"),
            ("ta > 5ms", "Unexpected character"),
            ("ta is 3", "Expected 'null'"),
        ]:
            with self.subTest(expr=expr):
                with self.assertRaisesRegex(FilterError, msg):
                    self.compile(expr)

    def test_compiled_sql_runs(self):
        conn = sqlite3.connect(":memory:")
        conn.execute('CREATE TABLE t ("pci", "dl_mcs", "ul_mcs", "rnti", "type", "ta")')
        conn.executemany("INSERT INTO t VALUES (?, ?, ?, ?, ?, ?)", [(1, 25, 3, "0x4601", "a", None), (2, 10, 12, "0x4602", "b", 1.5)])
        sql, params = self.compile("(dl_mcs > ul_mcs and ta is null) or rnti == 0x4602")
        self.assertEqual(conn.execute(f"SELECT pci FROM t WHERE {sql} ORDER BY pci", params).fetchall(), [(1,), (2,)])


if __name__ == "__main__":
    unittest.main()

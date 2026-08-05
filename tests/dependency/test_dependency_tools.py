#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Tests for gen_dependency_tree.py and check_dependency_rules.py.

Runs both scripts against a synthetic C++ project laid out like OCUDU
(include/<proj>/<subsystem> public headers, lib/<subsystem> private sources,
a build/ directory holding compile_commands.json), so include resolution,
rule evaluation, exemptions and exit codes are exercised end to end rather
than against the live OCUDU tree, whose contents change independently.

Usage:
    python3 test_dependency_tools.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

TEST_DIR = Path(__file__).resolve().parent
SCRIPTS = TEST_DIR.parents[1] / "skills" / "ocudu-code-review" / "scripts" / "dependency"
GEN = SCRIPTS / "gen_dependency_tree.py"
CHECK = SCRIPTS / "check_dependency_rules.py"
SEED_RULES = SCRIPTS / "ocudu_dependency_rules.yml"

MAC_RULE = """\
version: 1
rules:
  - id: mac-must-not-depend-on-du
    from: "lib/mac/**"
    to: "include/proj/du/**"
    reason: MAC sits below the DU manager.
"""


def write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def make_project(root: Path, mac_impl_extra: str = "", mac_header_extra: str = "") -> None:
    """A minimal project whose includes cover every resolution path.

    `proj/...` includes only resolve through the -I directory in
    compile_commands.json; `mac_config.h` only resolves relative to the
    including file; `<vector>` resolves nowhere.
    """
    write(root, "include/proj/du/du_manager.h", "#pragma once\n#include <memory>\n")
    write(root, "include/proj/ran/rnti.h", "#pragma once\n#include <cstdint>\n")
    write(
        root, "include/proj/mac/mac.h",
        '#pragma once\n#include "proj/ran/rnti.h"\n' + mac_header_extra,
    )
    write(
        root, "lib/mac/mac_impl.cpp",
        '#include "proj/mac/mac.h"\n'
        '#include "mac_config.h"\n'
        "#include <vector>\n" + mac_impl_extra,
    )
    write(root, "lib/mac/mac_config.h", '#pragma once\n#include "proj/ran/rnti.h"\n')
    write(root, "lib/e2/e2_impl.cpp", '#include "proj/ran/rnti.h"\n')

    build = root / "build"
    build.mkdir(parents=True, exist_ok=True)
    entries = [
        {
            "directory": str(build),
            "command": f"/usr/bin/c++ -I{root}/include -std=gnu++17 -o x.o -c {root}/{src}",
            "file": f"{root}/{src}",
        }
        for src in ("lib/mac/mac_impl.cpp", "lib/e2/e2_impl.cpp")
    ]
    (build / "compile_commands.json").write_text(json.dumps(entries, indent=1))


def run(script: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script), *args], capture_output=True, text=True,
    )


class GeneratorTest(unittest.TestCase):
    def test_resolves_every_include_kind(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root)
            result = run(GEN, "--repo", str(root), "--quiet")
            self.assertEqual(result.returncode, 0, result.stderr)

            tree = yaml.safe_load((root / "build" / "ocudu_dependency_tree.yml").read_text())
            entry = tree["files"]["lib/mac/mac_impl.cpp"]
            # proj/mac/mac.h resolves via -I, mac_config.h relative to the source.
            self.assertEqual(
                entry["includes"], ["include/proj/mac/mac.h", "lib/mac/mac_config.h"],
            )
            self.assertEqual(entry["unresolved"], ["vector"])
            self.assertEqual(tree["meta"]["repo_root"], root.as_posix())
            self.assertEqual(sorted(tree["meta"]["roots"]), ["include", "lib"])
            self.assertEqual(tree["meta"]["file_count"], 6)

    def test_build_dir_is_not_scanned(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root)
            write(root, "build/generated.h", '#include "proj/ran/rnti.h"\n')
            run(GEN, "--repo", str(root), "--quiet")
            tree = yaml.safe_load((root / "build" / "ocudu_dependency_tree.yml").read_text())
            self.assertNotIn("build/generated.h", tree["files"])

    def test_output_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root)
            out = root / "build" / "ocudu_dependency_tree.yml"
            run(GEN, "--repo", str(root), "--quiet")
            first = out.read_bytes()
            run(GEN, "--repo", str(root), "--quiet")
            self.assertEqual(first, out.read_bytes())

    def test_missing_compile_commands_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root)
            (root / "build" / "compile_commands.json").unlink()
            result = run(GEN, "--repo", str(root))
            self.assertEqual(result.returncode, 2)
            self.assertIn("CMAKE_EXPORT_COMPILE_COMMANDS", result.stderr)

    def test_other_build_dir_is_offered_not_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root)
            other = root / "build_release"
            other.mkdir()
            (other / "compile_commands.json").write_text("[]")
            (root / "build" / "compile_commands.json").unlink()
            result = run(GEN, "--repo", str(root))
            self.assertEqual(result.returncode, 2)
            self.assertIn("build_release/compile_commands.json", result.stderr)
            self.assertIn("--compile-commands", result.stderr)


class CheckerTest(unittest.TestCase):
    def build(self, root: Path, rules: str, **kwargs) -> tuple[Path, Path]:
        make_project(root, **kwargs)
        result = run(GEN, "--repo", str(root), "--quiet")
        self.assertEqual(result.returncode, 0, result.stderr)
        rules_path = write(root, "rules.yml", rules)
        return root / "build" / "ocudu_dependency_tree.yml", rules_path

    def check(self, tree: Path, rules: Path, *args: str) -> subprocess.CompletedProcess:
        return run(CHECK, "--tree", str(tree), "--rules", str(rules), *args)

    def json_check(self, tree: Path, rules: Path, *args: str) -> tuple[dict, int]:
        result = self.check(tree, rules, "--json", *args)
        self.assertIn(result.returncode, (0, 1), result.stderr)
        return json.loads(result.stdout), result.returncode

    def test_clean_tree_exits_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree, rules = self.build(Path(tmp), MAC_RULE)
            payload, code = self.json_check(tree, rules)
            self.assertEqual(code, 0)
            self.assertEqual(payload["findings"], [])
            self.assertEqual(payload["rule_count"], 1)

    def test_direct_violation_is_reported_with_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree, rules = self.build(
                Path(tmp), MAC_RULE,
                mac_impl_extra='#include "proj/du/du_manager.h"\n',
            )
            payload, code = self.json_check(tree, rules)
            self.assertEqual(code, 1)
            self.assertEqual(len(payload["findings"]), 1)
            finding = payload["findings"][0]
            self.assertEqual(finding["rule_id"], "mac-must-not-depend-on-du")
            self.assertEqual(finding["file"], "lib/mac/mac_impl.cpp")
            self.assertEqual(finding["to"], "include/proj/du/du_manager.h")
            # The offending directive is the 4th line of mac_impl.cpp.
            self.assertEqual(finding["line"], 4)
            self.assertEqual(finding["kind"], "forbidden-edge")

    def test_relative_include_violation_anchors_on_its_own_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rules = """\
version: 1
rules:
  - id: no-mac-config
    from: "lib/mac/mac_impl.cpp"
    to: "lib/mac/mac_config.h"
    reason: Contrived rule pinning a relative include.
"""
            tree, rules_path = self.build(root, rules)
            payload, code = self.json_check(tree, rules_path)
            self.assertEqual(code, 1)
            self.assertEqual(payload["findings"][0]["line"], 2)

    def test_transitive_rule_reports_shortest_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            rules = """\
version: 1
rules:
  - id: mac-must-not-reach-du
    from: "lib/mac/**"
    to: "include/proj/du/**"
    transitive: true
    reason: MAC must not reach DU headers, even indirectly.
"""
            tree, rules_path = self.build(
                Path(tmp), rules,
                mac_header_extra='#include "proj/du/du_manager.h"\n',
            )
            payload, code = self.json_check(tree, rules_path)
            self.assertEqual(code, 1)
            finding = payload["findings"][0]
            self.assertEqual(finding["chain"], [
                "lib/mac/mac_impl.cpp",
                "include/proj/mac/mac.h",
                "include/proj/du/du_manager.h",
            ])
            # Anchored on the edge the from-side file owns, not the deep one.
            self.assertEqual(finding["line"], 1)

    def test_direct_rule_ignores_indirect_reach(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree, rules = self.build(
                Path(tmp), MAC_RULE,
                mac_header_extra='#include "proj/du/du_manager.h"\n',
            )
            payload, code = self.json_check(tree, rules)
            self.assertEqual(code, 0)
            self.assertEqual(payload["findings"], [])

    def test_peer_isolation_flags_sibling_subsystem(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rules = """\
version: 1
rules:
  - id: peers-are-private
    kind: peer-isolation
    peers: "lib/*"
    reason: Subsystems talk through public headers only.
"""
            make_project(root)
            write(root, "lib/e2/e2_impl.cpp", '#include "../mac/mac_config.h"\n')
            run(GEN, "--repo", str(root), "--quiet")
            rules_path = write(root, "rules.yml", rules)
            payload, code = self.json_check(
                root / "build" / "ocudu_dependency_tree.yml", rules_path,
            )
            self.assertEqual(code, 1)
            finding = payload["findings"][0]
            self.assertEqual(finding["file"], "lib/e2/e2_impl.cpp")
            self.assertEqual(finding["to"], "lib/mac/mac_config.h")
            self.assertEqual(finding["kind"], "peer-isolation")

    def test_peer_isolation_allows_same_subsystem(self):
        with tempfile.TemporaryDirectory() as tmp:
            rules = """\
version: 1
rules:
  - id: peers-are-private
    kind: peer-isolation
    peers: "lib/*"
    reason: Subsystems talk through public headers only.
"""
            tree, rules_path = self.build(Path(tmp), rules)
            # lib/mac/mac_impl.cpp includes lib/mac/mac_config.h, a same-peer edge.
            payload, code = self.json_check(tree, rules_path)
            self.assertEqual(code, 0)
            self.assertEqual(payload["findings"], [])

    def test_exemption_suppresses_violation(self):
        with tempfile.TemporaryDirectory() as tmp:
            rules = """\
version: 1
rules:
  - id: mac-must-not-depend-on-du
    from: "lib/mac/**"
    to: "include/proj/du/**"
    reason: MAC sits below the DU manager.
    exempt:
      - from: lib/mac/mac_impl.cpp
        to: include/proj/du/du_manager.h
        reason: "tracked in PROJ-1234"
"""
            tree, rules_path = self.build(
                Path(tmp), rules,
                mac_impl_extra='#include "proj/du/du_manager.h"\n',
            )
            payload, code = self.json_check(tree, rules_path)
            self.assertEqual(code, 0)
            self.assertEqual(payload["findings"], [])
            self.assertEqual(payload["warnings"], [])

    def test_unused_exemption_warns(self):
        with tempfile.TemporaryDirectory() as tmp:
            rules = """\
version: 1
rules:
  - id: mac-must-not-depend-on-du
    from: "lib/mac/**"
    to: "include/proj/du/**"
    reason: MAC sits below the DU manager.
    exempt:
      - from: lib/mac/mac_impl.cpp
        to: include/proj/du/du_manager.h
        reason: "tracked in PROJ-1234"
"""
            tree, rules_path = self.build(Path(tmp), rules)
            payload, code = self.json_check(tree, rules_path)
            self.assertEqual(code, 0)
            self.assertEqual(len(payload["warnings"]), 1)
            self.assertIn("no longer matches", payload["warnings"][0])

    def test_changed_files_partition(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree, rules = self.build(
                Path(tmp), MAC_RULE,
                mac_impl_extra='#include "proj/du/du_manager.h"\n',
            )
            payload, code = self.json_check(tree, rules, "--changed-files", "lib/e2/e2_impl.cpp")
            self.assertEqual(code, 0)
            self.assertEqual(payload["findings"], [])
            self.assertEqual(payload["pre_existing_count"], 1)
            self.assertTrue(payload["scoped"])

            payload, code = self.json_check(
                tree, rules, "--changed-files", "lib/mac/mac_impl.cpp",
            )
            self.assertEqual(code, 1)
            self.assertEqual(len(payload["findings"]), 1)
            self.assertEqual(payload["pre_existing_count"], 0)

    def test_changed_files_from_stdin(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree, rules = self.build(
                Path(tmp), MAC_RULE,
                mac_impl_extra='#include "proj/du/du_manager.h"\n',
            )
            result = subprocess.run(
                [sys.executable, str(CHECK), "--tree", str(tree), "--rules", str(rules),
                 "--json", "--changed-files-from", "-"],
                input="lib/mac/mac_impl.cpp\n", capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertEqual(len(json.loads(result.stdout)["findings"]), 1)


class IncludeOnlyTargetTest(unittest.TestCase):
    """Third-party trees are edge targets but are never scanned for their own
    edges, so they appear in the tree only on the right-hand side. Rules must
    still be able to name them."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        make_project(self.root)
        write(self.root, "external/fmt/include/fmt/format.h", "#pragma once\n")
        write(
            self.root, "include/proj/mac/mac.h",
            '#pragma once\n#include "proj/ran/rnti.h"\n#include "fmt/format.h"\n',
        )
        build = self.root / "build"
        entries = json.loads((build / "compile_commands.json").read_text())
        for entry in entries:
            entry["command"] = entry["command"].replace(
                f"-I{self.root}/include",
                f"-I{self.root}/include -I{self.root}/external/fmt/include",
            )
        (build / "compile_commands.json").write_text(json.dumps(entries, indent=1))
        result = run(GEN, "--repo", str(self.root), "--quiet")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.tree = build / "ocudu_dependency_tree.yml"

    def tearDown(self):
        self._tmp.cleanup()

    def test_external_is_a_target_but_not_a_key(self):
        tree = yaml.safe_load(self.tree.read_text())
        self.assertIn(
            "external/fmt/include/fmt/format.h",
            tree["files"]["include/proj/mac/mac.h"]["includes"],
        )
        self.assertNotIn("external/fmt/include/fmt/format.h", tree["files"])

    def test_rule_targeting_external_is_not_stale(self):
        rules = write(self.root, "rules.yml", """\
version: 1
rules:
  - id: public-headers-must-not-include-external
    from: "include/**"
    to: "external/**"
    reason: Public headers must not expose third-party types.
""")
        result = run(CHECK, "--tree", str(self.tree), "--rules", str(rules), "--json")
        self.assertEqual(result.returncode, 1, result.stderr)
        findings = json.loads(result.stdout)["findings"]
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["to"], "external/fmt/include/fmt/format.h")
        self.assertEqual(findings[0]["file"], "include/proj/mac/mac.h")
        self.assertEqual(findings[0]["line"], 3)


class RulesetValidationTest(unittest.TestCase):
    def prepare(self, root: Path, rules: str) -> tuple[Path, Path]:
        make_project(root)
        run(GEN, "--repo", str(root), "--quiet")
        return root / "build" / "ocudu_dependency_tree.yml", write(root, "rules.yml", rules)

    def expect_broken(self, rules: str, needle: str) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree, rules_path = self.prepare(Path(tmp), rules)
            result = run(CHECK, "--tree", str(tree), "--rules", str(rules_path))
            self.assertEqual(result.returncode, 2, result.stdout)
            self.assertIn(needle, result.stderr)

    def test_stale_pattern_is_an_error(self):
        self.expect_broken(
            """\
version: 1
rules:
  - id: renamed-away
    from: "lib/mac/**"
    to: "include/proj/du_manager/**"
    reason: The target directory was renamed, so this rule enforces nothing.
""",
            "matches no files",
        )

    def test_stale_peers_pattern_is_an_error(self):
        self.expect_broken(
            """\
version: 1
rules:
  - id: no-such-peers
    kind: peer-isolation
    peers: "components/*"
    reason: There is no components/ directory.
""",
            "matches no directories",
        )

    def test_duplicate_id_is_an_error(self):
        self.expect_broken(
            """\
version: 1
rules:
  - id: same
    from: "lib/mac/**"
    to: "include/proj/du/**"
    reason: First.
  - id: same
    from: "lib/e2/**"
    to: "include/proj/du/**"
    reason: Second.
""",
            "duplicate id",
        )

    def test_unknown_key_is_an_error(self):
        self.expect_broken(
            """\
version: 1
rules:
  - id: typo
    form: "lib/mac/**"
    to: "include/proj/du/**"
    reason: "`form` is a typo for `from`."
""",
            "unknown key",
        )

    def test_missing_reason_is_an_error(self):
        self.expect_broken(
            """\
version: 1
rules:
  - id: no-reason
    from: "lib/mac/**"
    to: "include/proj/du/**"
""",
            "missing `reason`",
        )

    def test_unsupported_version_is_an_error(self):
        self.expect_broken(
            """\
version: 2
rules:
  - id: whatever
    from: "lib/mac/**"
    to: "include/proj/du/**"
    reason: Version 2 does not exist.
""",
            "unsupported rules version",
        )

    def test_transitive_peer_isolation_is_rejected(self):
        self.expect_broken(
            """\
version: 1
rules:
  - id: peers-transitive
    kind: peer-isolation
    peers: "lib/*"
    transitive: true
    reason: Transitive peer isolation is not defined.
""",
            "not supported for kind 'peer-isolation'",
        )

    def test_missing_tree_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rules_path = write(root, "rules.yml", MAC_RULE)
            result = run(CHECK, "--tree", str(root / "nope.yml"), "--rules", str(rules_path))
            self.assertEqual(result.returncode, 2)
            self.assertIn("gen_dependency_tree.py", result.stderr)


class GlobSemanticsTest(unittest.TestCase):
    def test_single_star_does_not_cross_slash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root)
            write(root, "lib/mac/detail/inner.cpp", '#include "proj/du/du_manager.h"\n')
            run(GEN, "--repo", str(root), "--quiet")
            # `lib/mac/*.cpp` must not reach lib/mac/detail/inner.cpp.
            rules_path = write(root, "rules.yml", """\
version: 1
rules:
  - id: shallow-only
    from: "lib/mac/*.cpp"
    to: "include/proj/du/**"
    reason: Only direct children of lib/mac are in scope.
""")
            result = run(
                CHECK, "--tree", str(root / "build" / "ocudu_dependency_tree.yml"),
                "--rules", str(rules_path), "--json",
            )
            self.assertEqual(result.returncode, 0, result.stdout)

            rules_path = write(root, "rules_deep.yml", """\
version: 1
rules:
  - id: deep-too
    from: "lib/mac/**"
    to: "include/proj/du/**"
    reason: Every file under lib/mac is in scope.
""")
            result = run(
                CHECK, "--tree", str(root / "build" / "ocudu_dependency_tree.yml"),
                "--rules", str(rules_path), "--json",
            )
            self.assertEqual(result.returncode, 1)
            findings = json.loads(result.stdout)["findings"]
            self.assertEqual([f["file"] for f in findings], ["lib/mac/detail/inner.cpp"])


class SeedRulesTest(unittest.TestCase):
    def test_seed_ruleset_parses_and_is_self_consistent(self):
        doc = yaml.safe_load(SEED_RULES.read_text())
        self.assertEqual(doc["version"], 1)
        ids = [rule["id"] for rule in doc["rules"]]
        self.assertEqual(len(ids), len(set(ids)))
        for rule in doc["rules"]:
            self.assertTrue(rule.get("reason", "").strip(), rule["id"])
            if rule.get("kind") == "peer-isolation":
                self.assertIn("peers", rule)
            else:
                self.assertIn("from", rule)
                self.assertIn("to", rule)


if __name__ == "__main__":
    unittest.main(verbosity=2)

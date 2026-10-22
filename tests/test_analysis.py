"""Shared analysis phase: diagnostics, backend agreement, and baseline artifact parity.

The analysis is internal, so these tests observe it through the CLI: both
backends must report identical shared diagnostics, backend-only validation must
run after shared analysis, and valid grammars must produce byte-identical output
to a pre-analysis build when CPARSEGEN_BASELINE_EXECUTABLE is set.
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from generator_support import ROOT

EXECUTABLE = Path(os.environ.get("CPARSEGEN_EXECUTABLE", ROOT / "bin/cparsegen"))
BASELINE = os.environ.get("CPARSEGEN_BASELINE_EXECUTABLE")

MODES = {"cwhip": [], "library": ["--library"], "c": ["--target", "c"]}


def run(executable, grammar, mode, directory, name="grammar.cpg", extra=()):
    source = Path(directory) / name
    if isinstance(grammar, str):
        source.write_text(grammar)
    out = Path(directory) / ("out." + mode)
    dot = Path(directory) / ("out." + mode + ".dot")
    result = subprocess.run(
        [str(executable), *MODES[mode], *extra, str(source), str(out), str(dot)],
        capture_output=True, text=True, cwd=directory,
    )
    outputs = tuple(p.read_text() if p.exists() else None for p in (out, dot))
    return result, outputs


class SharedAnalysisDiagnostics(unittest.TestCase):
    TAIL = "p : X ;\nX = \"x\"\n"

    def check(self, grammar, message, modes=("cwhip", "c"), related=False):
        with tempfile.TemporaryDirectory() as directory:
            texts = []
            for mode in modes:
                result, outputs = run(EXECUTABLE, grammar, mode, directory)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn(message, result.stderr)
                self.assertRegex(result.stderr, r"grammar\.cpg:\d+:\d+: bytes \d+-\d+: ")
                if related:
                    self.assertRegex(result.stderr, r"related: \S*grammar\.cpg:\d+:\d+: bytes")
                self.assertEqual(outputs, (None, None))
                texts.append(result.stderr)
            self.assertEqual(len(set(texts)), 1, "backends disagree on a shared diagnostic")

    def test_unknown_references_carry_locations(self):
        self.check("a : b ;\nX = \"x\"\n", "unknown parser rule b")
        self.check("a : Y ;\nX = \"x\"\n", "unknown lexer token Y")
        self.check("A = Q\n" + self.TAIL, "unknown lexer reference Q")

    def test_lexer_cycles_and_nullability(self):
        self.check("A = B\nB = A\n" + self.TAIL, "cyclic lexer reference", related=True)
        self.check("A = \"x\"?\n" + self.TAIL, "can match empty input")
        self.check("A = (\"x\"?)*\n" + self.TAIL, "nullable lexer repetition")

    def test_parser_nullability_and_left_recursion(self):
        self.check("a : (b)* ;\nb : (X)? ;\nX = \"x\"\n", "nullable repetition is not supported")
        self.check("a : a | b ;\nb : (X)? ;\nX = \"x\"\n", "without consuming tokens")
        self.check("a : b a ;\nb : (X)? ;\nX = \"x\"\n", "without consuming tokens")
        self.check("a : b a | X ;\nb : (X)? ;\nX = \"x\"\n", "without consuming tokens")

    def test_consuming_left_recursion_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            for mode in ("cwhip", "c"):
                result, outputs = run(EXECUTABLE, "a : a X | X ;\nX = \"x\"\n", mode, directory)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIsNotNone(outputs[0])

    def test_skip_and_duplicates(self):
        self.check("a : X ;\nX = \"x\"\n@skip Z;\n", "@skip requires a declared lexer token name")
        self.check("a : S ;\nS = \" \"\n@skip S;\n", "skipped lexer token S cannot be matched", related=True)
        self.check("a : X ;\na : X ;\nX = \"x\"\n", "duplicate parser rule a", related=True)

    def test_declaration_requirements(self):
        for grammar, message in (("a : X ;\n", "must declare a lexer rule"),
                                 ("X = \"x\"\n", "must declare a parser rule")):
            with tempfile.TemporaryDirectory() as directory:
                for mode in ("cwhip", "c"):
                    result, _ = run(EXECUTABLE, grammar, mode, directory)
                    self.assertEqual(result.returncode, 1)
                    self.assertIn(message, result.stderr)

    def test_c_directive_allowlist_is_backend_validation_after_analysis(self):
        grammar = "a : X ;\nX = \"x\"\n@foo bar;\n"
        with tempfile.TemporaryDirectory() as directory:
            result, _ = run(EXECUTABLE, grammar, "cwhip", directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            result, outputs = run(EXECUTABLE, grammar, "c", directory)
            self.assertEqual(result.returncode, 1)
            self.assertIn("C target does not support @foo", result.stderr)
            self.assertEqual(outputs, (None, None))
            # A shared-analysis failure wins over the backend restriction.
            result, _ = run(EXECUTABLE, grammar.replace("a : X", "a : Y"), "c", directory)
            self.assertIn("unknown lexer token Y", result.stderr)

    def test_includes_are_analyzed_as_one_grammar(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "tokens.cpg").write_text("X = \"x\"\n")
            (Path(directory) / "rules.cpg").write_text("a : b X ;\nb : X ;\n")
            main = '@include "tokens.cpg";\n@include "rules.cpg";\nc : a ;\n'
            results = {}
            for mode in ("cwhip", "c"):
                result, outputs = run(EXECUTABLE, main, mode, directory, "main.cpg")
                self.assertEqual(result.returncode, 0, result.stderr)
                results[mode] = outputs[1]
            self.assertEqual(results["cwhip"], results["c"])
            main = '@include "rules.cpg";\nc : a ;\n'
            result, _ = run(EXECUTABLE, main, "c", directory, "main.cpg")
            self.assertEqual(result.returncode, 1)
            self.assertIn("must declare a lexer rule", result.stderr)


@unittest.skipUnless(BASELINE, "CPARSEGEN_BASELINE_EXECUTABLE not set")
class BaselineParity(unittest.TestCase):
    def tracked_grammars(self):
        listing = subprocess.run(["git", "ls-files", "*.cpg"], capture_output=True,
                                 text=True, cwd=ROOT, check=True).stdout.split()
        return [ROOT / name for name in listing]

    def test_valid_grammar_artifacts_match_baseline(self):
        for grammar in self.tracked_grammars():
            for mode in MODES:
                with self.subTest(grammar=grammar.name, mode=mode):
                    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
                        extra = ("--include-path", str(grammar.parent))
                        base = run(BASELINE, grammar, mode, a, extra=extra)
                        new = run(EXECUTABLE, grammar, mode, b, extra=extra)
                        self.assertEqual(base[0].returncode, new[0].returncode)
                        self.assertEqual(base[0].stderr.replace(a, "."), new[0].stderr.replace(b, "."))
                        self.assertEqual(base[1], new[1])

    def test_diagnostics_match_baseline(self):
        cases = ["a : b ;\nX = \"x\"\n", "a : (b)* ;\nb : (X)? ;\nX = \"x\"\n",
                 "a : b a ;\nb : (X)? ;\nX = \"x\"\n", "A = B\nB = A\n" + "p : A ;\n",
                 "a : X ;\nX = \"x\"\n@foo bar;\n", "a : S ;\nS = \" \"\n@skip S;\n"]
        for grammar in cases:
            for mode in ("cwhip", "c"):
                with self.subTest(grammar=grammar, mode=mode):
                    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
                        base = run(BASELINE, grammar, mode, a)
                        new = run(EXECUTABLE, grammar, mode, b)
                        self.assertEqual(base[0].returncode, new[0].returncode)
                        self.assertEqual(base[0].stderr.replace(a, "."), new[0].stderr.replace(b, "."))


if __name__ == "__main__":
    unittest.main()

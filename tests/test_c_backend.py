"""Compile generated ISO C99 and compare its public CLI with Cwhip."""

import subprocess
import unittest

from generator_support import GeneratorTestCase, ROOT
import test_grammar_conformance as conformance


class StandaloneCConformanceTests(conformance.GrammarConformanceTests):
    backend = "c"


class CBackendTests(GeneratorTestCase):
    backend = "c"

    def assert_differential(self, grammar, cases):
        cwhip = self.compile_grammar(grammar, backend="cwhip")
        cwhip_dot = self.graph.read_bytes()
        standalone = self.compile_grammar(grammar)
        self.assertEqual(self.graph.read_bytes(), cwhip_dot)
        for text, complete, expected_code in cases:
            with self.subTest(text=text, complete=complete):
                expected = self.parse(cwhip, text, complete)
                actual = self.parse(standalone, text, complete)
                self.assertEqual(expected.returncode, expected_code, expected.stdout + expected.stderr)
                self.assertEqual(
                    (actual.returncode, actual.stdout, actual.stderr),
                    (expected.returncode, expected.stdout, expected.stderr),
                )
        return standalone

    def test_calculator_acceptance_rejection_and_rendering(self):
        standalone = self.assert_differential(
            (ROOT / "examples/calculator/calculator.cpg").read_text(),
            [
                ("x = 2 + 3 * 4", True, 0),
                ("(x - 2) / 4", True, 0),
                ("-1.25 + +2 / (3 - 4)", True, 0),
                ("2+3*4", False, 0),
                ("x = 2+", False, 0),
                ("x = 2+", True, 1),
                ("(1+2", True, 1),
                ("1 2", True, 1),
                ("1?", False, 1),
                ("", True, 1),
                (" \t\r\n", True, 1),
            ],
        )
        # No SDK, module registry, or runtime path is available to the C executable.
        source = self.directory / "standalone.txt"
        source.write_text("1 + 2")
        result = subprocess.run(
            [str(standalone), "--complete", str(source)],
            env={"HOME": str(self.directory), "PATH": ""},
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("statement(expression(", result.stdout)

    def test_shared_conformance_fixtures_are_differential(self):
        fixtures = ROOT / "tests/fixtures/conformance"
        for name, cases in [
            ("interleaved.cpg", [
                (" \talpha \n!\r\n", True, 0),
                ("alpha", True, 1),
                ("alpha!!", True, 1),
            ]),
            ("rule_trivia.cpg", [
                ("alpha+beta", True, 0),
                ("alpha +beta", True, 1),
            ]),
        ]:
            with self.subTest(fixture=name):
                self.assert_differential((fixtures / name).read_text(), cases)

    def test_scanner_longest_match_and_shortest_viable_continuations(self):
        self.assert_differential(
            'entry : value "!" | WORD "==" WORD | "a" ;\n'
            'value : INTEGER "+" INTEGER | INTEGER ;\n'
            'LETTER = [a-z]\nWORD = [a-z]+\nEQUAL = [=]\nINTEGER = [0-9]+\n',
            [
                ("abc==de", True, 0),
                ("a", True, 1),  # equal-length lexer token beats the literal
                ("123+456!", True, 0),  # caller requires the longer rule result
                ("123!", True, 0),
                ("123+456", True, 1),
                ("123!abc", False, 0),
                ("123!abc", True, 1),
            ],
        )
        self.assert_differential(
            'entry : INTEGER "+" INTEGER | INTEGER ;\nINTEGER = [0-9]+\n',
            [("123+456", False, 0), ("123+456", True, 0), ("12?", False, 1)],
        )
        self.assert_differential(
            'entry : WORD ;\nSKIP = [a-z]\nWORD = [a-z]+\n@skip SKIP;\n',
            [("abc", True, 0), ("a", True, 1)],
        )

    def test_ebnf_empty_rules_and_source_order(self):
        self.assert_differential(
            'entry : empty ("+" | "-")? (first | second)+ ;\n'
            'empty : ;\nfirst : DIGIT ;\nsecond : DIGIT ;\nDIGIT = [0-9]\n',
            [("-123", True, 0), ("12", False, 0), ("-", True, 1), ("", True, 1)],
        )
        self.assert_differential(
            'entry : ;\nUNUSED = [a-z]\n',
            [("", True, 0), ("?", False, 1)],
        )
        self.assert_differential(
            'entry : value? ;\nvalue : "a" ;\nUNUSED = [0-9]\n',
            [("", True, 0), ("a", True, 0), ("a", False, 0)],
        )

    def test_regex_backtracking_and_c_literal_escaping(self):
        self.assert_differential(
            'entry : PAIR ;\nPAIR = [0-9]+[0-9]\n',
            [("123", True, 0), ("1", True, 1)],
        )
        # Octal C escapes prevent trigraph translation and escape ambiguity.
        self.assert_differential(
            """entry : "??/" '"' ;\nUNUSED = [a-z]\n""",
            [('??/"', True, 0), ("??/", True, 1)],
        )

    def test_unsupported_extensions_fail_before_outputs(self):
        cases = [
            ("@keywords IDENT;", "keywords"),
            ("@quoted STRING double;", "quoted"),
            ("@line_comment //;", "line_comment"),
            ("@block_comment /* */;", "block_comment"),
        ]
        for directive, name in cases:
            with self.subTest(directive=directive):
                grammar = self.directory / "unsupported.cpg"
                grammar.write_text(
                    "entry : IDENT ;\nIDENT = [a-z]+\n" + directive + "\n"
                )
                result = self.generate(grammar)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual(result.stderr, f"{grammar}: line 3: C target does not support @{name}\n")
                self.assertFalse(self.generated.exists())
                self.assertFalse(self.graph.exists())

    def test_invalid_grammar_is_rejected_identically(self):
        cases = [
            'entry : missing ;\n',
            'entry : entry "a" | "a" ;\n',
            'entry : ("a"?)* ;\n',
            'entry : TOKEN ;\nTOKEN = [0-9]*\n',
        ]
        for text in cases:
            with self.subTest(grammar=text):
                grammar = self.directory / "invalid.cpg"
                grammar.write_text(text)
                expected = self.generate(grammar, backend="cwhip")
                actual = self.generate(grammar)
                self.assertEqual(actual.returncode, 1)
                self.assertEqual(actual.stderr, expected.stderr)
                self.assertFalse(self.generated.exists())
                self.assertFalse(self.generated.with_suffix(".cw").exists())
                self.assertFalse(self.graph.exists())

    def test_generation_is_deterministic_and_cli_rejects_invalid_options(self):
        grammar = ROOT / "examples/calculator/calculator.cpg"
        self.assertEqual(self.generate(grammar).returncode, 0)
        source, graph = self.generated.read_bytes(), self.graph.read_bytes()
        self.assertEqual(self.generate(grammar).returncode, 0)
        self.assertEqual(self.generated.read_bytes(), source)
        self.assertEqual(self.graph.read_bytes(), graph)
        for options in [("--target", "cpp"), ("--library", "--target", "c")]:
            result = subprocess.run(
                [str(self.generator), *options, str(grammar), str(self.generated), str(self.graph)],
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("usage:", result.stderr)

    def test_explicit_resource_limits_and_io_errors(self):
        executable = self.compile_grammar(
            'entry : INTEGER | "(" entry ")" ;\nINTEGER = [0-9]+\n'
        )
        result = self.parse(executable, "(" * 300 + "1" + ")" * 300)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "parser resource limit exceeded\n")
        result = self.parse(executable, "1" * (1024 * 1024 + 1))
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "C runtime input limit exceeded\n")
        result = subprocess.run(
            [str(executable), str(self.directory / "missing.txt")],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing.txt:", result.stderr)
        executable = self.compile_grammar(
            'entry : DIGITS ;\nDIGITS = [0-9]*[0-9]*[0-9]\n'
        )
        result = self.parse(executable, "1" * 1000)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "scanner resource limit exceeded\n")
        executable = self.compile_grammar('entry : ("a" | "a")* ;\nUNUSED = [0-9]\n')
        result = self.parse(executable, "a" * 14)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "parser result limit exceeded\n")

    def test_input_limit_accepts_exact_boundary_and_rejects_one_more_byte(self):
        executable = self.compile_grammar('entry : ;\nSPACE = [ ]\n@skip SPACE;\n')
        result = self.parse(executable, " " * (1024 * 1024))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "entry()\n")
        result = self.parse(executable, " " * (1024 * 1024 + 1))
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "C runtime input limit exceeded\n")

    def test_scanner_part_depth_limit(self):
        executable = self.compile_grammar('entry : TOKEN ;\nTOKEN = ' + "[a]" * 256 + "\n")
        result = self.parse(executable, "a" * 256)
        self.assertEqual(result.returncode, 0, result.stderr)
        executable = self.compile_grammar('entry : TOKEN ;\nTOKEN = ' + "[a]" * 257 + "\n")
        result = self.parse(executable, "a" * 257)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "scanner resource limit exceeded\n")


if __name__ == "__main__":
    unittest.main()

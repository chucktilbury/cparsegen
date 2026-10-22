"""Focused checks of the supported provisional grammar contract."""

import re
import unittest

from generator_support import GeneratorTestCase, ROOT


FIXTURES = ROOT / "tests/fixtures/conformance"


class GrammarConformanceTests(GeneratorTestCase):
    def test_interleaved_collection_resolves_forward_names_and_keeps_start_rule(self):
        executable = self.compile_grammar((FIXTURES / "interleaved.cpg").read_text())
        result = self.parse(executable, " \talpha \n!\r\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "entry(value(WORD(alpha)), END(!))\n")
        self.assertIn("entry -> value", self.graph.read_text())

    def test_rule_trivia_does_not_terminate_or_enter_generated_input(self):
        executable = self.compile_grammar((FIXTURES / "rule_trivia.cpg").read_text())
        result = self.parse(executable, "alpha+beta")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            result.stdout, "entry(WORD(alpha), @literal0(+), WORD(beta))\n"
        )
        # Grammar whitespace is not an implicit skip rule for generated input.
        result = self.parse(executable, "alpha +beta")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "lex error at byte 5\n")

    def test_scanner_longest_match_beats_shorter_named_tokens_and_literals(self):
        executable = self.compile_grammar(
            'entry : WORD "==" WORD | "a" ;\n'
            'LETTER = [a-z]\n'
            'WORD = [a-z]+\n'
            'EQUAL = [=]\n'
        )
        result = self.parse(executable, "abc==de")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            result.stdout, "entry(WORD(abc), @literal0(==), WORD(de))\n"
        )

    def test_shortest_prefix_is_not_first_successful_alternative(self):
        executable = self.compile_grammar(
            'entry : INTEGER "+" INTEGER | INTEGER ;\n'
            'INTEGER = [0-9]+\n'
        )
        prefix = self.parse(executable, "123+456", complete=False)
        self.assertEqual(prefix.returncode, 0, prefix.stdout + prefix.stderr)
        self.assertEqual(prefix.stdout, "entry(INTEGER(123))\n")
        complete = self.parse(executable, "123+456")
        self.assertEqual(complete.returncode, 0, complete.stdout + complete.stderr)
        self.assertEqual(
            complete.stdout, "entry(INTEGER(123), @literal0(+), INTEGER(456))\n"
        )

    def test_unsupported_and_malformed_declarations_fail_without_outputs(self):
        cases = [
            (
                "TOKEN = [a-z]+ entry : TOKEN ;\n",
                1, "unsupported lexer expression syntax (expected class, literal, reference, or group)",
            ),
            (
                "TOKEN = [a-z]+ @skip TOKEN;\nentry : TOKEN ;\n",
                1, "unsupported lexer expression syntax (expected class, literal, reference, or group)",
            ),
            (
                "entry : TOKEN\nTOKEN = [a-z]+\n",
                2, "unsupported parser-expression syntax",
            ),
            (
                "entry : TOKEN { action() } ;\nTOKEN = [a-z]+\n",
                1, "unsupported parser-expression syntax",
            ),
            (
                "entry : TOKEN ;\nTOKEN = ([a-z]+\n",
                3, "expected ')' after lexer group",
            ),
            (
                "entry : TOKEN ;\nTOKEN = [a-z]+||[0-9]+\n",
                2, "expected nonempty lexer expression",
            ),
            (
                "entry : TOKEN ;\nLETTER = [a-z]\nTOKEN = MISSING+\n",
                3, "unknown lexer reference MISSING",
            ),
            ("entry TOKEN;\n", 1, "expected '=' or ':' after declaration name"),
            ("@note opaque payload\n", 1, "directive @note must end with ';'"),
            ("entry : /* unfinished\n", 1, "unterminated block comment"),
            ('entry : "unfinished\n', 1, "unterminated quoted literal"),
            ("entry : TOKEN ;\nTOKEN = [a-z\n", 2, "unterminated character class"),
        ]
        for text, line, diagnostic in cases:
            with self.subTest(grammar=text):
                grammar = self.directory / "invalid.cpg"
                grammar.write_text(text)
                result = self.generate(grammar)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertRegex(
                    result.stderr,
                    rf"^{re.escape(str(grammar))}:{line}:\d+: bytes \d+-\d+: "
                    rf"{re.escape(diagnostic)}\n$",
                )
                self.assertFalse(self.generated.exists())
                self.assertFalse(self.graph.exists())


if __name__ == "__main__":
    unittest.main()

"""Left recursion preserves derivations, ordering, and API selection in both targets."""

import unittest

from generator_support import GeneratorTestCase, ROOT


class LeftRecursionContract:
    def assert_parse(self, executable, text, expected, complete=True):
        result = self.parse(executable, text, complete)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, expected + "\n")
        self.assertEqual(result.stderr, "")

    def test_existing_expression_fixture_is_runnable(self):
        executable = self.compile_grammar((ROOT / "examples/expression.cpg").read_text())
        self.assert_parse(
            executable, "1+2+3",
            "program(expression(expression(expression(INTEGER(1)), @literal0(+), "
            "INTEGER(2)), @literal0(+), INTEGER(3)))",
        )

    def test_direct_recursion_preserves_nested_tree_and_prefix(self):
        executable = self.compile_grammar(
            'entry : entry "-" DIGIT | DIGIT ;\nDIGIT = [0-9]\n'
        )
        self.assert_parse(executable, "1-2-3",
                          "entry(entry(entry(DIGIT(1)), @literal0(-), DIGIT(2)), "
                          "@literal0(-), DIGIT(3))")
        self.assert_parse(executable, "1-2-3", "entry(DIGIT(1))", complete=False)
        for text in ("", "-1", "1-", "1--2", "12"):
            with self.subTest(text=text):
                result = self.parse(executable, text)
                self.assertEqual(result.returncode, 1)
                self.assertIn("parse error", result.stdout)
        self.assert_parse(executable, "1-", "entry(DIGIT(1))", complete=False)
        result = self.parse(executable, "1?", complete=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("lex error", result.stdout)

    def test_indirect_three_rule_cycle_and_caller_continuation(self):
        executable = self.compile_grammar(
            'entry : a "!" ;\na : b "x" | DIGIT ;\n'
            'b : c ;\nc : a "y" | DIGIT ;\nDIGIT = [0-9]\n'
        )
        self.assert_parse(
            executable, "1yx!",
            "entry(a(b(c(a(DIGIT(1)), @literal2(y))), @literal1(x)), @literal0(!))",
        )
        self.assert_parse(
            executable, "1x!",
            "entry(a(b(c(DIGIT(1))), @literal1(x)), @literal0(!))",
        )
        for text in ("1y!", "1yx", "1xy!"):
            self.assertEqual(self.parse(executable, text).returncode, 1)

    def test_nullable_prefix_keeps_empty_nodes(self):
        executable = self.compile_grammar(
            'entry : empty entry "+" DIGIT | DIGIT ;\nempty : ;\nDIGIT = [0-9]\n'
        )
        self.assert_parse(
            executable, "1+2+3",
            "entry(empty(), entry(empty(), entry(DIGIT(1)), @literal0(+), DIGIT(2)), "
            "@literal0(+), DIGIT(3))",
        )

    def test_nullable_base_and_nullable_suffix_component(self):
        executable = self.compile_grammar(
            'entry : entry empty "+" DIGIT | ;\nempty : ;\nDIGIT = [0-9]\n'
        )
        self.assert_parse(executable, "", "entry()")
        self.assert_parse(
            executable, "+1+2",
            "entry(entry(entry(), empty(), @literal0(+), DIGIT(1)), "
            "empty(), @literal0(+), DIGIT(2))",
        )
        self.assert_parse(executable, "+1", "entry()", complete=False)

    def test_mutual_recursion_with_nullable_base(self):
        executable = self.compile_grammar(
            'entry : other "x" | ;\nother : entry | DIGIT ;\nDIGIT = [0-9]\n'
        )
        self.assert_parse(
            executable, "xx",
            "entry(other(entry(other(entry()), @literal0(x))), @literal0(x))",
        )
        self.assert_parse(executable, "1x", "entry(other(DIGIT(1)), @literal0(x))")

    def test_grouped_recursion_and_repeated_suffix(self):
        executable = self.compile_grammar(
            'entry : (entry ("+" DIGIT)+ | DIGIT) ;\nDIGIT = [0-9]\n'
        )
        self.assert_parse(
            executable, "1+2+3",
            "entry(entry(entry(DIGIT(1)), @literal0(+), DIGIT(2)), "
            "@literal0(+), DIGIT(3))",
        )

    def test_precedence_and_left_associativity_are_grammar_defined(self):
        executable = self.compile_grammar(
            'expr : expr "+" term | term ;\n'
            'term : term "*" atom | atom ;\n'
            'atom : DIGIT | "(" expr ")" ;\nDIGIT = [0-9]\n'
        )
        atom = lambda n: f"atom(DIGIT({n}))"
        term = lambda n: f"term({atom(n)})"
        first = f"expr(expr({term(1)}), @literal0(+), {term(2)})"
        product = f"term({term(3)}, @literal1(*), {atom(4)})"
        self.assert_parse(
            executable, "1+2+3*4", f"expr({first}, @literal0(+), {product})",
        )
        inner = f"expr(expr({term(1)}), @literal0(+), {term(2)})"
        grouped = f"atom(@literal2((), {inner}, @literal3()))"
        self.assert_parse(
            executable, "(1+2)*3",
            f"expr(term(term({grouped}), @literal1(*), {atom(3)}))",
        )

    def test_ambiguous_binary_recursion_keeps_source_order_not_growth_order(self):
        for alternatives, expected in [
            ("entry entry | DIGIT",
             "entry(entry(entry(DIGIT(1)), entry(DIGIT(2))), entry(DIGIT(3)))"),
            ("DIGIT | entry entry",
             "entry(entry(DIGIT(1)), entry(entry(DIGIT(2)), entry(DIGIT(3))))"),
        ]:
            with self.subTest(alternatives=alternatives):
                executable = self.compile_grammar(
                    f"entry : {alternatives} ;\nDIGIT = [0-9]\n"
                )
                self.assert_parse(executable, "123", expected)

    def test_overlapping_recursive_alternatives_keep_outer_and_inner_order(self):
        executable = self.compile_grammar(
            'entry : entry first | entry second | DIGIT ;\n'
            'first : "+" DIGIT ;\nsecond : "+" DIGIT ;\nDIGIT = [0-9]\n'
        )
        self.assert_parse(
            executable, "1+2+3",
            "entry(entry(entry(DIGIT(1)), first(@literal0(+), DIGIT(2))), "
            "first(@literal0(+), DIGIT(3)))",
        )

    def test_mixed_left_and_right_recursion_and_optional_prefix(self):
        executable = self.compile_grammar(
            'entry : "p"? entry "x" | "(" entry ")" | DIGIT ;\nDIGIT = [0-9]\n'
        )
        self.assert_parse(
            executable, "p(1)x",
            "entry(@literal0(p), entry(@literal2((), entry(DIGIT(1)), "
            "@literal3())), @literal1(x))",
        )

    def test_nonproductive_consuming_cycle_terminates(self):
        executable = self.compile_grammar(
            'entry : other "x" ;\nother : entry ;\nDIGIT = [0-9]\n'
        )
        for text in ("", "x", "xxx"):
            result = self.parse(executable, text)
            self.assertEqual(result.returncode, 1)
            self.assertIn("parse error", result.stdout)
            self.assertNotIn("limit", result.stdout)

    def test_zero_context_cycles_rejected_before_outputs(self):
        cases = [
            ('entry : entry | DIGIT ;\n', 1),
            ('entry : other ;\nother : entry | DIGIT ;\n', 2),
            ('entry : empty entry | DIGIT ;\nempty : ;\n', 1),
            ('entry : entry "x"? | DIGIT ;\n', 1),
            ('entry : (entry | DIGIT) ;\n', 1),
            ('entry : entry+ | DIGIT ;\n', 1),
            ('entry : other "x"? | DIGIT ;\nother : entry ;\n', 2),
            ('entry : DIGIT ;\nunused : unused ;\n', 2),
            ('entry : entry entry | ;\n', 1),
            ('entry : "x" entry? | entry ;\n', 1),
        ]
        for text, line in cases:
            with self.subTest(grammar=text):
                grammar = self.directory / "invalid.cpg"
                grammar.write_text(text + "DIGIT = [0-9]\n")
                result = self.generate(grammar)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn(f"{grammar}: line {line}: left recursion", result.stderr)
                self.assertIn("require a nonnullable prefix or suffix on every cycle",
                              result.stderr)
                self.assertFalse(self.generated.exists())
                self.assertFalse(self.graph.exists())

    def test_nullable_quantifiers_and_malformed_recursive_rules_still_rejected(self):
        for text, diagnostic in [
            ('entry : (entry?)* | DIGIT ;\n', "nullable repetition"),
            ('entry : entry "+" MISSING | DIGIT ;\n', "unknown lexer token MISSING"),
            ('entry : entry "" | DIGIT ;\n', "empty quoted terminals"),
            ('entry : entry "+" | (DIGIT ;\n', "after parser group"),
        ]:
            with self.subTest(grammar=text):
                grammar = self.directory / "invalid.cpg"
                grammar.write_text(text + "DIGIT = [0-9]\n")
                result = self.generate(grammar)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn(diagnostic, result.stderr)
                self.assertFalse(self.generated.exists())
                self.assertFalse(self.graph.exists())

    def test_long_chain_and_depth_and_ambiguity_budgets(self):
        executable = self.compile_grammar(
            'entry : entry "x" | DIGIT ;\nDIGIT = [0-9]\n'
        )
        expected = "entry(DIGIT(1))"
        for _ in range(40):
            expected = f"entry({expected}, @literal0(x))"
        self.assert_parse(executable, "1" + "x" * 40, expected)
        for complete in (False, True):
            result = self.parse(executable, "1" + "x" * 300, complete)
            self.assertEqual(result.returncode, 1)
            self.assertIn("parser resource limit exceeded", result.stdout)
        executable = self.compile_grammar(
            'entry : entry ("x" | "x") | DIGIT ;\nDIGIT = [0-9]\n'
        )
        result = self.parse(executable, "1" + "x" * 14)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "parser result limit exceeded\n")

    def test_call_budget_exhaustion_below_rule_depth_limit(self):
        executable = self.compile_grammar(
            'entry : entry (((("x")))) | DIGIT ;\nDIGIT = [0-9]\n'
        )
        # Group nesting does not increase rule depth. At most 162 rule calls
        # are active; retained shorter results still exhaust the 100,000 calls.
        for complete in (False, True):
            result = self.parse(executable, "1" + "x" * 160, complete)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "parser resource limit exceeded\n")


class CwhipLeftRecursionTests(LeftRecursionContract, GeneratorTestCase):
    pass


class CLeftRecursionTests(LeftRecursionContract, GeneratorTestCase):
    backend = "c"


if __name__ == "__main__":
    unittest.main()

"""Black-box checks for generated Cwhip scanners, parsers, ASTs, and DOT."""

import shutil
import subprocess
import unittest

from generator_support import GeneratorTestCase, ROOT


class GeneratorTests(GeneratorTestCase):
    def test_generate_compile_and_run_shortest_parser(self):
        result = self.generate()
        self.assertEqual(result.returncode, 0, result.stderr)
        generated = self.generated.read_text()
        self.assertIn("pre_sum(AstNode node)", generated)
        self.assertIn("post_sum(AstNode node)", generated)
        self.assertIn("int64 offset", generated)
        self.assertIn("AstNode childAt(int64 index)", generated)
        graph = self.graph.read_text()
        self.assertIn("sum -> INTEGER", graph)
        self.assertIn('label="+"', graph)

        executable = self.directory / "fixture-parser"
        compiled = subprocess.run(
            [str(self.compiler), str(self.generated), "-o", str(executable)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(compiled.returncode, 0, compiled.stderr)

        source = self.directory / "input.txt"
        source.write_text("123+456")
        run = subprocess.run(
            [str(executable), str(source)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        # The scanner takes the longest INTEGER token ("123"); the parser
        # then selects the alternative consuming fewer input bytes.
        self.assertEqual(run.stdout, "sum(INTEGER(123))\n")

    def test_unknown_token_reference_has_diagnostic(self):
        grammar = self.directory / "bad.cpg"
        grammar.write_text("entry : MISSING ;\nINTEGER = [0-9]+\n")
        result = self.generate(grammar)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown lexer token MISSING", result.stderr)

    def test_directive_cannot_be_mixed_into_parser_expression(self):
        grammar = self.directory / "mixed.cpg"
        grammar.write_text("INTEGER = [0-9]+\nentry : INTEGER @note payload; ;\n")
        result = self.generate(grammar)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsupported parser-expression syntax", result.stderr)

    def test_parser_rule_requires_semicolon(self):
        grammar = self.directory / "unterminated.cpg"
        grammar.write_text("INTEGER = [0-9]+\nentry : INTEGER\n")
        result = self.generate(grammar)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must end with ';'", result.stderr)

    def test_duplicate_lexer_rule_has_validation_diagnostic(self):
        grammar = self.directory / "duplicate.cpg"
        grammar.write_text(
            "entry : INTEGER ;\n"
            "INTEGER = [0-9]+\n"
            "INTEGER = [0-9]+\n"
        )
        result = self.generate(grammar)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate lexer rule INTEGER", result.stderr)

    def test_lexer_reports_unmatched_input(self):
        result = self.generate()
        self.assertEqual(result.returncode, 0, result.stderr)
        executable = self.directory / "fixture-parser"
        compiled = subprocess.run(
            [str(self.compiler), str(self.generated), "-o", str(executable)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        source = self.directory / "input.txt"
        source.write_text("12?")
        run = subprocess.run(
            [str(executable), str(source)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(run.returncode, 1)
        self.assertEqual(run.stdout, "lex error at byte 2\n")

    def test_rule_references_keep_longer_matches_needed_by_context(self):
        executable = self.compile_grammar(
            'entry : value "!" ;\n'
            'value : INTEGER | INTEGER "+" INTEGER ;\n'
            'INTEGER = [0-9]+\n'
        )
        result = self.parse(executable, "123+456!")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            result.stdout,
            "entry(value(INTEGER(123), @literal1(+), INTEGER(456)), @literal0(!))\n",
        )

    def test_groups_repetition_and_complete_input_keep_prefix_api(self):
        executable = self.compile_grammar(
            'entry : INTEGER (("+" | "-") INTEGER)* ;\n'
            'INTEGER = [0-9]+\n'
        )
        prefix = self.parse(executable, "12+34-56", complete=False)
        self.assertEqual(prefix.returncode, 0, prefix.stdout + prefix.stderr)
        self.assertEqual(prefix.stdout, "entry(INTEGER(12))\n")
        complete = self.parse(executable, "12+34-56")
        self.assertEqual(complete.returncode, 0, complete.stdout + complete.stderr)
        self.assertIn("INTEGER(56)", complete.stdout)
        trailing = self.parse(executable, "12+")
        self.assertEqual(trailing.returncode, 1)
        self.assertIn("parse error", trailing.stdout)

    def test_equal_length_alternatives_keep_source_order(self):
        executable = self.compile_grammar(
            'entry : first | second ;\n'
            'first : INTEGER ;\n'
            'second : INTEGER ;\n'
            'INTEGER = [0-9]+\n'
        )
        result = self.parse(executable, "42")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "entry(first(INTEGER(42)))\n")

    def test_words_example(self):
        executable = self.compile_grammar((ROOT / "examples/words.cpg").read_text())
        result = self.parse(executable, "alpha, beta_2, gamma")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            result.stdout,
            "words(IDENT(alpha), @literal0(,), IDENT(beta_2), @literal0(,), IDENT(gamma))\n",
        )
        self.assertEqual(self.parse(executable, "alpha,").returncode, 1)

    def test_optional_plus_and_explicit_empty_rule(self):
        executable = self.compile_grammar(
            'entry : empty ("+" | "-")? INTEGER+ ;\n'
            'empty : ;\n'
            'INTEGER = [0-9]\n'
        )
        result = self.parse(executable, "-123")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("entry(empty(),", result.stdout)
        self.assertIn("INTEGER(3)", result.stdout)
        self.assertEqual(self.parse(executable, "-").returncode, 1)

    def test_character_classes_identifier_skip_and_lexer_ties(self):
        executable = self.compile_grammar(
            'entry : FIRST IDENT ;\n'
            'FIRST = [a-z]+\n'
            'IDENT = [A-Za-z_][A-Za-z0-9_]*\n'
            'SPACE = [ \\t\\r\\n]+\n'
            '@skip SPACE;\n'
        )
        result = self.parse(executable, "abc \t\n Z_12\r\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "entry(FIRST(abc), IDENT(Z_12))\n")

    def test_opt_in_keywords_comments_and_quoted_tokens(self):
        executable = self.compile_grammar(
            'entry : "let" IDENT "=" STRING ";" CHAR ;\n'
            'IDENT = [A-Za-z_][A-Za-z0-9_]*\n'
            'SPACE = [ \\t\\r\\n]+\n'
            '@skip SPACE;\n'
            '@keywords IDENT;\n'
            '@quoted STRING double;\n'
            '@quoted CHAR single;\n'
            '@line_comment //;\n'
            '@block_comment /* */;\n'
        )
        result = self.parse(executable, r'''/* prefix */ let let2 = "/* value */ //"; // trailing
        '\n' ''')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("IDENT(let2)", result.stdout)
        self.assertIn('STRING("/* value */ //")', result.stdout)
        self.assertIn(r"CHAR('\n')", result.stdout)
        result = self.parse(executable, "let let = \"\"; 'a'")
        self.assertEqual(result.returncode, 1)
        self.assertIn("parse error", result.stdout)

    def test_invalid_lexical_directives_have_diagnostics(self):
        cases = [
            ("@quoted CHAR;", "@quoted"),
            ("@quoted CHAR triple;", "@quoted"),
            ("@quoted invalid-name single;", "lexer names"),
            ("@quoted IDENT single;", "duplicate lexer rule"),
            ("@keywords MISSING;", "@keywords"),
            ("@keywords IDENT extra;", "@keywords"),
            ("@keywords IDENT;\n@keywords IDENT;", "@keywords"),
            ("@skip IDENT;\n@keywords IDENT;", "skipped lexer token"),
            ("@reserved struct;", "@reserved requires @keywords"),
            ("@keywords IDENT;\n@reserved invalid-word;", "identifier spellings"),
            ("@line_comment;", "@line_comment"),
            ("@line_comment // extra;", "@line_comment"),
            ("@block_comment /*;", "@block_comment"),
        ]
        for directives, diagnostic in cases:
            with self.subTest(directives=directives):
                grammar = self.directory / "bad.cpg"
                grammar.write_text(
                    "entry : IDENT ;\nIDENT = [A-Za-z_][A-Za-z0-9_]*\n" + directives + "\n"
                )
                result = self.generate(grammar)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(diagnostic, result.stderr)
                self.assertFalse(self.generated.exists())
                self.assertFalse(self.graph.exists())

    def test_lexer_class_sequences_backtrack_before_longest_selection(self):
        executable = self.compile_grammar(
            'entry : PAIR ;\n'
            'PAIR = [0-9]+[0-9]\n'
        )
        result = self.parse(executable, "123")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "entry(PAIR(123))\n")
        self.assertEqual(self.parse(executable, "1").returncode, 1)

    def test_invalid_grammars_fail_before_creating_outputs(self):
        cases = [
            ('entry : missing ;\nINTEGER = [0-9]+\n', "unknown parser rule missing"),
            ('entry : entry | INTEGER ;\nINTEGER = [0-9]+\n', "left recursion"),
            ('entry : other ;\nother : entry | INTEGER ;\nINTEGER = [0-9]+\n', "left recursion"),
            ('entry : empty entry | INTEGER ;\nempty : ;\nINTEGER = [0-9]+\n', "left recursion"),
            ('entry : (INTEGER?)* ;\nINTEGER = [0-9]+\n', "nullable repetition"),
            ('entry : empty+ ;\nempty : ;\nINTEGER = [0-9]+\n', "nullable repetition"),
            ('entry : INTEGER ;\nINTEGER = [0-9]*\n', "can match empty input"),
            ('entry : INTEGER ;\nINTEGER = [z-a]+\n', "descending"),
            ('entry : INTEGER ;\nINTEGER = [^]+\n', "empty character class"),
            ('entry : INTEGER ;\nINTEGER = [0-9]+\n@skip MISSING;\n', "@skip"),
            ('entry : INTEGER ;\nINTEGER = [0-9]+\n@skip INTEGER;\n', "skipped lexer token"),
            ('entry : (INTEGER ;\nINTEGER = [0-9]+\n', "after parser group"),
        ]
        for index, (text, diagnostic) in enumerate(cases):
            with self.subTest(diagnostic=diagnostic, index=index):
                grammar = self.directory / "bad.cpg"
                grammar.write_text(text)
                result = self.generate(grammar)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(diagnostic, result.stderr)
                self.assertFalse(self.generated.exists())
                self.assertFalse(self.graph.exists())

    def test_recursion_and_ambiguity_limits_are_explicit_errors(self):
        executable = self.compile_grammar(
            'entry : INTEGER | "(" entry ")" ;\n'
            'INTEGER = [0-9]+\n'
        )
        result = self.parse(executable, "(" * 300 + "1" + ")" * 300)
        self.assertEqual(result.returncode, 1)
        self.assertIn("resource limit", result.stdout)
        executable = self.compile_grammar(
            'entry : ("a" | "a")* ;\n'
            'INTEGER = [0-9]+\n'
        )
        result = self.parse(executable, "a" * 14)
        self.assertEqual(result.returncode, 1)
        self.assertIn("limit exceeded", result.stdout)

    def test_scanner_resource_limit_is_an_explicit_error(self):
        executable = self.compile_grammar(
            'entry : DIGITS ;\n'
            'DIGITS = [0-9]*[0-9]*[0-9]\n'
        )
        result = self.parse(executable, "1" * 25000)
        self.assertEqual(result.returncode, 1)
        self.assertIn("scanner resource limit exceeded", result.stdout)

    def test_library_emission_and_dot_are_deterministic(self):
        grammar = ROOT / "examples/calculator/calculator.cpg"
        command = [
            str(self.generator), "--library", str(grammar),
            str(self.generated), "--dot", str(self.graph),
        ]
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=60)
        library = self.generated.read_text()
        dot = self.graph.read_text()
        self.assertNotIn("start {", library)
        self.assertIn("AstNode parseAll()", library)
        self.assertIn("pre_expression(AstNode node)", library)
        self.assertIn("statement -> expression", dot)
        self.assertIn("primary -> expression", dot)
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=60)
        self.assertEqual(self.generated.read_text(), library)
        self.assertEqual(self.graph.read_text(), dot)
        if shutil.which("dot"):
            subprocess.run(
                ["dot", "-Tsvg", str(self.graph), "-o", str(self.directory / "grammar.svg")],
                check=True, capture_output=True, text=True, timeout=30,
            )

    def test_rendering_does_not_mutate_ast_or_reused_token_kinds(self):
        grammar = self.directory / "render.cpg"
        grammar.write_text('entry : INTEGER "+" INTEGER ;\nINTEGER = [0-9]+\n')
        subprocess.run(
            [str(self.generator), "--library", str(grammar),
             str(self.generated), "--dot", str(self.graph)],
            check=True, capture_output=True, text=True, timeout=60,
        )
        driver = self.directory / "driver.cw"
        driver.write_text(
            'include "generated.cw"\n'
            'start {\n'
            '    InputScanner scanner("1+2")\n'
            '    scanner.scan()\n'
            '    GeneratedParser parser(scanner.tokens)\n'
            '    AstNode node = parser.parseAll()\n'
            '    print(format("{}\\n", node.render()))\n'
            '    print(format("{}\\n", node.render()))\n'
            '    parser.position = 0\n'
            '    print(format("{}\\n", parser.parseAll().render()))\n'
            '}\n'
        )
        executable = self.directory / "render"
        subprocess.run(
            [str(self.compiler), str(driver), "-o", str(executable)],
            check=True, capture_output=True, text=True, timeout=120,
        )
        result = subprocess.run(
            [str(executable)], check=True, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(
            result.stdout.splitlines(),
            ["entry(INTEGER(1), @literal0(+), INTEGER(2))"] * 3,
        )


if __name__ == "__main__":
    unittest.main()

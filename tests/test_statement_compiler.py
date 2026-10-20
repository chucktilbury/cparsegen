"""Persistent visitor symbols, source-order emission, and syntax-only parsing."""

import json
import shutil
import subprocess

from generator_support import GeneratorTestCase, ROOT, c_compile_command


EXAMPLES = ROOT / "examples/compiler"


class StatementCompilerTests(GeneratorTestCase):
    backend = "c"

    def setUp(self):
        super().setUp()
        parser = self.directory / "parser.c"
        result = subprocess.run(
            [str(self.generator), "--target", "c", str(EXAMPLES / "statements.cpg"),
             str(parser), str(self.graph)],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        source = self.directory / "statements.c"
        shutil.copyfile(EXAMPLES / "statements.c", source)
        self.compiler_app = self.directory / "statement-compiler"
        self.compile_c(source, self.compiler_app)
        self.syntax_parser = self.directory / "syntax-parser"
        self.compile_c(parser, self.syntax_parser)

    def compile_c(self, source, executable):
        result = subprocess.run(
            c_compile_command(source, executable),
            capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def invoke(self, text):
        source = self.directory / "source.stmt"
        source.write_text(text)
        return subprocess.run(
            [str(self.compiler_app), str(source)],
            capture_output=True, text=True, timeout=30,
        )

    def assert_program(self, text, expected):
        emitted = self.invoke(text)
        self.assertEqual((emitted.returncode, emitted.stderr), (0, ""))
        source = self.directory / "program.c"
        source.write_text(emitted.stdout)
        program = self.directory / "program"
        self.compile_c(source, program)
        result = subprocess.run(
            [str(program)], capture_output=True, text=True, timeout=30,
        )
        self.assertEqual((result.returncode, result.stdout, result.stderr),
                         (0, expected, ""))
        return emitted.stdout

    def test_source_order_and_persistent_symbols(self):
        emitted = self.assert_program(
            (EXAMPLES / "statements/basic.stmt").read_text(), "20\n56\n28\n",
        )
        self.assertLess(emitted.index("double cpg_v0"), emitted.index("printf"))
        self.assertEqual(emitted.count("double cpg_v0"), 1)
        self.assertEqual(emitted.count("double cpg_v1"), 1)
        self.assert_program(
            "let x = 1; print x; x = x + 1; print x; "
            "let y = x; x = 99; print y; print x;", "1\n2\n2\n99\n",
        )

    def test_arithmetic_and_names(self):
        for text, expected in [
            ("print 2 + 3 * 4; print (2 + 3) * 4;", "14\n20\n"),
            ("print 20 - 5 - 3; print -2 * -3 + +4;", "12\n10\n"),
            ("let x = 000008; print -(x + 009) * 2;", "-34\n"),
            ("print 2 * (3 + (4 - 1)); print 999999999 + 1;", "12\n1000000000\n"),
            ("let return = 1; let printf = return + 1; let main = printf * 2; "
             "let cpg_v0 = main + 1; let _x2 = cpg_v0; print _x2;", "5\n"),
            ("let printer = 3; let letter = 4; print printer + letter;", "7\n"),
            (" \r\n let A_0 = 0;\t A_0 = -1;\n print A_0; ", "-1\n"),
            ("let unused = 1; unused = 2;", ""),
            ("", ""),
        ]:
            with self.subTest(text=text):
                self.assert_program(text, expected)

    def test_symbol_table_growth(self):
        declarations = "".join(f"let x{i} = {i};" for i in range(24))
        self.assert_program(declarations + "print x0 + x23;", "23\n")

    def test_semantic_errors_have_exact_locations_and_no_c(self):
        for text, line, column, offset, diagnostic, name in [
            ("print x; let x = 1;", 1, 7, 6,
             "use before declaration (unknown name)", "x"),
            ("let x = x + 1;", 1, 9, 8,
             "use before declaration (unknown name)", "x"),
            ("x = 1;", 1, 1, 0, "assignment to unknown name", "x"),
            ("let x = 1;\nx = y;", 2, 5, 15,
             "use before declaration (unknown name)", "y"),
            ("let x = y; let y = 1;", 1, 9, 8,
             "use before declaration (unknown name)", "y"),
            ("let x = 1;\nlet x = 2;", 2, 5, 15, "duplicate declaration", "x"),
            ("let Foo = 1;\nprint foo;", 2, 7, 19,
             "use before declaration (unknown name)", "foo"),
            ("print 1234567890;", 1, 7, 6,
             "integer literal exceeds nine digits", "1234567890"),
        ]:
            with self.subTest(text=text):
                result = self.invoke(text)
                self.assertEqual((result.returncode, result.stdout), (1, ""))
                self.assertEqual(
                    result.stderr,
                    f"{self.directory / 'source.stmt'}:{line}:{column}: "
                    f"byte {offset}: {diagnostic}: '{name}'\n",
                )
                syntax = self.parse(self.syntax_parser, text)
                self.assertEqual(syntax.returncode, 0, syntax.stderr)

    def test_documented_failure_samples(self):
        for name, diagnostic in [
            ("use-before", "use before declaration"),
            ("duplicate", "duplicate declaration"),
        ]:
            with self.subTest(name=name):
                result = self.invoke((EXAMPLES / f"statements/{name}.stmt").read_text())
                self.assertEqual((result.returncode, result.stdout), (1, ""))
                self.assertIn(diagnostic, result.stderr)

    def test_syntax_and_lexical_errors(self):
        for text, diagnostic in [
            ("let x = 1", "parse error"),
            ("let x; print x;", "parse error"),
            ("print 1; 2", "parse error"),
            ("print 1 / 2;", "lex error"),
            ("let print = 1;", "parse error"),
            ("print (1 + 2;", "parse error"),
        ]:
            with self.subTest(text=text):
                result = self.invoke(text)
                self.assertEqual((result.returncode, result.stdout), (1, ""))
                self.assertIn(diagnostic, result.stderr)
                syntax = self.parse(self.syntax_parser, text)
                self.assertEqual(syntax.returncode, 1, syntax.stderr)

    def test_syntax_only_json_is_still_an_ast(self):
        source = self.directory / "unknown.stmt"
        source.write_text("print unknown;")
        result = subprocess.run(
            [str(self.syntax_parser), "--json", str(source)],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        ast = json.loads(result.stdout)
        self.assertEqual(ast["name"], "program")
        self.assertIn("unknown", result.stdout)

    def test_usage_and_missing_source(self):
        for arguments in [(), ("one", "two")]:
            result = subprocess.run(
                [str(self.compiler_app), *arguments],
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual((result.returncode, result.stdout), (2, ""))
            self.assertIn("usage: statement-compiler SOURCE", result.stderr)
        missing = self.directory / "missing.stmt"
        result = subprocess.run(
            [str(self.compiler_app), str(missing)],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual((result.returncode, result.stdout), (1, ""))
        self.assertIn(str(missing), result.stderr)

    def test_oversized_source(self):
        result = self.invoke(" " * (1024 * 1024 + 1))
        self.assertEqual((result.returncode, result.stdout), (1, ""))
        self.assertIn("input exceeds C runtime one-MiB limit", result.stderr)

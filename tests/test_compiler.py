"""Grammar -> generated AST/visitor -> emitted C -> compiled program result."""

import shutil
import subprocess

from generator_support import GeneratorTestCase, ROOT, c_compile_command


class CompilerTests(GeneratorTestCase):
    backend = "c"

    def setUp(self):
        super().setUp()
        parser = self.directory / "parser.c"
        result = subprocess.run(
            [str(self.generator), "--target", "c",
             str(ROOT / "examples/compiler/compiler.cpg"), str(parser), "--dot", str(self.graph)],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        source = self.directory / "compiler.c"
        shutil.copyfile(ROOT / "examples/compiler/compiler.c", source)
        self.compiler_app = self.directory / "expression-compiler"
        self.compile_c(source, self.compiler_app)

    def compile_c(self, source, executable):
        result = subprocess.run(
            c_compile_command(source, executable),
            capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def invoke(self, *arguments):
        return subprocess.run(
            [str(self.compiler_app), *arguments],
            capture_output=True, text=True, timeout=30,
        )

    def test_generated_program_results(self):
        for expression, expected in [
            ("2 + 3 * 4", "14\n"),
            ("(2 + 3) * 4", "20\n"),
            ("20 - 5 - 3", "12\n"),
            ("2 * (3 + (4 - 1))", "12\n"),
            ("-2 * -3 + +4", "10\n"),
            ("-(2 + 3) * 4", "-20\n"),
            ("000008 + 009 * 2", "26\n"),
            ("0", "0\n"),
            ("999999999 + 1", "1000000000\n"),
            (" \t2 +\n3 * 4\r ", "14\n"),
        ]:
            with self.subTest(expression=expression):
                emitted = self.invoke(expression)
                self.assertEqual(emitted.returncode, 0, emitted.stderr)
                self.assertEqual(emitted.stderr, "")
                source = self.directory / "program.c"
                source.write_text(emitted.stdout)
                program = self.directory / "program"
                self.compile_c(source, program)
                result = subprocess.run(
                    [str(program)], capture_output=True, text=True, timeout=30,
                )
                self.assertEqual((result.returncode, result.stdout, result.stderr),
                                 (0, expected, ""))

    def test_rejected_input_emits_no_c(self):
        for expression, diagnostic in [
            ("2 +", "parse error"),
            ("(2 + 3", "parse error"),
            ("2 3", "parse error"),
            ("", "parse error"),
            ("2 / 3", "lex error"),
            ("2 + name", "lex error"),
            ("2 + 1234567890", "byte 4: integer literal exceeds nine digits"),
        ]:
            with self.subTest(expression=expression):
                result = self.invoke(expression)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertIn("<argument>:byte ", result.stderr)
                self.assertIn(diagnostic, result.stderr)

    def test_usage(self):
        for arguments in [(), ("1", "2")]:
            with self.subTest(arguments=arguments):
                result = self.invoke(*arguments)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("usage: expression-compiler EXPRESSION", result.stderr)

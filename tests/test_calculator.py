"""Compile the generated calculator parser and exercise its actual CLI."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CalculatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        generator = Path(os.environ.get("CPARSEGEN_EXECUTABLE", ROOT / "bin/cparsegen"))
        if not generator.is_file():
            if "CPARSEGEN_EXECUTABLE" in os.environ:
                raise FileNotFoundError(generator)
            raise unittest.SkipTest("build cparsegen before running calculator tests")
        prefix = os.environ.get("CWHIP_SDK", "")
        if not prefix:
            prefix = subprocess.run(
                ["python3", str(ROOT / "scripts/sdk-prefix.py"), "--discover"],
                check=True, capture_output=True, text=True,
            ).stdout
        candidates = [Path(prefix) / "bin/cwhip"] if prefix else []
        candidates.extend(
            Path(entry) / "bin/cwhip"
            for entry in os.environ.get("CMAKE_PREFIX_PATH", "").split(os.pathsep)
            if entry
        )
        candidates.append(Path(shutil.which("cwhip") or ""))
        compiler = next((path for path in candidates if path.is_file()), None)
        if compiler is None:
            raise unittest.SkipTest("set CWHIP_SDK or install cwhip on PATH")
        cls.temporary = tempfile.TemporaryDirectory(prefix="calculator-test-")
        cls.addClassCleanup(cls.temporary.cleanup)
        directory = Path(cls.temporary.name)
        env = os.environ.copy()
        for name in ("CWHIP_PACKAGE_PATH", "CWHIP_MODULE_DIR", "CWHIP_MODULE_REGISTRY"):
            env.pop(name, None)
        for name in ("HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
            path = directory / name.lower()
            path.mkdir()
            env[name] = str(path)
        cls.env = env
        cls.executable = directory / "calculator"
        shutil.copy2(ROOT / "examples/calculator/calculator.cw", directory)
        subprocess.run(
            [str(generator), "--library", str(ROOT / "examples/calculator/calculator.cpg"),
             str(directory / "parser.cw"), str(directory / "grammar.dot")],
            check=True, capture_output=True, text=True, timeout=60,
        )
        subprocess.run(
            [str(compiler), str(directory / "calculator.cw"), "-o", str(cls.executable)],
            env=env, check=True, capture_output=True, text=True, timeout=120,
        )

    def run_cli(self, *arguments, input=""):
        return subprocess.run(
            [str(self.executable), *arguments], input=input,
            env=self.env, capture_output=True, text=True, timeout=30,
        )

    def test_arithmetic_precedence_associativity_and_parentheses(self):
        for expression, expected in [
            ("2 + 3 * 4", 14),
            ("(2 + 3) * 4", 20),
            ("20 - 3 - 2", 15),
            ("20 / 2 / 5", 2),
            ("7 / 2", 3.5),
            ("-2 * -3 + +4", 10),
            ("--(2 + 3)", 5),
            ("12.5 * 2 + 0.25", 25.25),
            ("((1 + 2) * (3 + 4))", 21),
        ]:
            with self.subTest(expression=expression):
                result = self.run_cli("-e", expression)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertAlmostEqual(float(result.stdout.strip()), expected)

    def test_variables_assign_reassign_and_persist_within_cli(self):
        result = self.run_cli(
            "--batch", input="x = 2 + 3 * 4\ny = x / 2\nx = x + 1\nx + y\n:vars\n"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [
            "x = 14", "y = 7", "x = 15", "22", "x = 15", "y = 7",
        ])

    def test_failed_assignment_does_not_modify_variables(self):
        result = self.run_cli(
            "--batch", input="x = 5\nx = 1 / 0\nx\ny = missing\n:vars\n"
        )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.splitlines(), ["x = 5", "5", "x = 5"])
        self.assertIn("division by zero", result.stderr)
        self.assertIn("undefined variable 'missing'", result.stderr)

    def test_errors_are_reported_and_batch_continues(self):
        result = self.run_cli(
            "--batch", input="1 +\nno_such_variable\n2 @ 3\n(2 + 3\n7 / 0\n6 * 7\n"
        )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "42\n")
        self.assertIn("parse error", result.stderr)
        self.assertIn("lex error at byte 2", result.stderr)
        self.assertIn("undefined variable", result.stderr)
        self.assertIn("division by zero", result.stderr)

    def test_complete_input_required(self):
        for text in ("1 2", "1 +", "1 + 2 3", "x = 2 = 3", "1.2.3", "2 (3)", ""):
            with self.subTest(text=text):
                result = self.run_cli("-e", text)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertIn("parse error", result.stderr)

    def test_whitespace_and_identifier_characters(self):
        result = self.run_cli("--batch", input="\n  _answer2 = 6 * 7  \r\n\t_answer2\t\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["_answer2 = 42", "42"])

    def test_interactive_help_vars_quit_and_eof(self):
        result = self.run_cli(input=":help\nx = 7\n:vars\n:quit\n99\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("calc> ", result.stdout)
        self.assertIn("One statement per line", result.stdout)
        self.assertEqual(result.stdout.count("x = 7"), 2)
        self.assertNotIn("99", result.stdout)
        self.assertEqual(self.run_cli("--batch").returncode, 0)
        self.assertEqual(self.run_cli().returncode, 0)
        result = self.run_cli("--batch", input="1 + 2")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "3\n")

    def test_usage(self):
        result = self.run_cli("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage:", result.stdout)
        result = self.run_cli("--unknown")
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage:", result.stderr)


if __name__ == "__main__":
    unittest.main()

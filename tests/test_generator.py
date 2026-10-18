"""Black-box checks for the first generated Cwhip parser slice."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/shortest.cpg"


class GeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.generator = ROOT / "bin/cparsegen"
        if not cls.generator.is_file():
            raise unittest.SkipTest("build cparsegen before running generator tests")
        prefix = os.environ.get("CWHIP_SDK", "")
        if not prefix:
            result = subprocess.run(
                ["python3", str(ROOT / "scripts/sdk-prefix.py"), "--discover"],
                capture_output=True,
                text=True,
                check=True,
            )
            prefix = result.stdout
        candidates = [Path(prefix) / "bin/cwhip"] if prefix else []
        candidates.extend(
            Path(entry) / "bin/cwhip"
            for entry in os.environ.get("CMAKE_PREFIX_PATH", "").split(os.pathsep)
            if entry
        )
        candidates.append(Path(shutil.which("cwhip") or ""))
        compiler = next((path for path in candidates if path.is_file()), Path(""))
        if not compiler.is_file():
            raise unittest.SkipTest("set CWHIP_SDK or install cwhip on PATH")
        cls.compiler = compiler

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.generated = self.directory / "generated.cw"
        self.graph = self.directory / "grammar.dot"

    def generate(self, grammar=FIXTURE):
        return subprocess.run(
            [str(self.generator), str(grammar), str(self.generated), str(self.graph)],
            capture_output=True,
            text=True,
            timeout=60,
        )

    def test_generate_compile_and_run_shortest_parser(self):
        result = self.generate()
        self.assertEqual(result.returncode, 0, result.stderr)
        generated = self.generated.read_text()
        self.assertIn("pre_sum(AstNode node)", generated)
        self.assertIn("post_sum(AstNode node)", generated)
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


if __name__ == "__main__":
    unittest.main()

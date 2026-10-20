"""Shared black-box harness for generator and grammar-conformance tests."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/shortest.cpg"


class GeneratorTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.generator = Path(os.environ.get("CPARSEGEN_EXECUTABLE", ROOT / "bin/cparsegen"))
        if not cls.generator.is_file():
            if "CPARSEGEN_EXECUTABLE" in os.environ:
                raise FileNotFoundError(cls.generator)
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

    def compile_grammar(self, text):
        grammar = self.directory / "input.cpg"
        grammar.write_text(text)
        result = self.generate(grammar)
        self.assertEqual(result.returncode, 0, result.stderr)
        executable = self.directory / "parser"
        result = subprocess.run(
            [str(self.compiler), str(self.generated), "-o", str(executable)],
            capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return executable

    def parse(self, executable, text, complete=True):
        source = self.directory / "input.txt"
        source.write_text(text)
        return subprocess.run(
            [str(executable), *(["--complete"] if complete else []), str(source)],
            capture_output=True, text=True, timeout=60,
        )

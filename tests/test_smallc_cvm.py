"""Compile checked SmallC programs to public CVM containers and execute them."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from generator_support import c_compile_command


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/smallc"


class SmallCCVMTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = os.environ.get("CPARSEGEN_CVM_COMPILER")
        runner = os.environ.get("CPARSEGEN_CVM_RUNNER")
        if not compiler or not runner:
            raise unittest.SkipTest(
                "configure CMake with CVM_PREFIX to run SmallC/CVM tests"
            )
        cls.compiler = Path(compiler)
        cls.runner = Path(runner)
        if not cls.compiler.is_file():
            raise FileNotFoundError(cls.compiler)
        if not cls.runner.is_file():
            raise FileNotFoundError(cls.runner)
        cls.temporary = tempfile.TemporaryDirectory(prefix="smallc-cvm-test-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.directory = Path(cls.temporary.name)
        cls.environment = {
            "PATH": "/usr/bin:/bin",
            "HOME": str(cls.directory),
        }

    def compile_source(self, source, name="input"):
        source_path = self.directory / f"{name}.c"
        bytecode_path = self.directory / f"{name}.cvm"
        source_path.write_text(source)
        result = subprocess.run(
            [str(self.compiler), str(source_path), str(bytecode_path)],
            cwd=self.directory,
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result, source_path, bytecode_path

    def run_cvm(self, bytecode_path):
        return subprocess.run(
            [str(self.runner), str(bytecode_path)],
            cwd=self.directory,
            env=self.environment,
            capture_output=True,
            timeout=30,
        )

    def assert_matches_c(self, source, expected, name):
        compiled, source_path, bytecode_path = self.compile_source(source, name)
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        self.assertEqual(compiled.stdout, "")
        self.assertTrue(bytecode_path.is_file())
        self.assertGreater(bytecode_path.stat().st_size, 0)

        execution = self.run_cvm(bytecode_path)
        self.assertEqual(execution.returncode, 0, execution.stderr.decode())
        self.assertEqual(execution.stdout, f"result: {expected}\n".encode())
        self.assertEqual(execution.stderr, b"")

        c_executable = self.directory / f"{name}-host"
        subprocess.run(
            c_compile_command(source_path, c_executable),
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        host = subprocess.run(
            [str(c_executable)],
            cwd=self.directory,
            env=self.environment,
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(host.returncode, expected)

    def test_existing_function_and_array_samples_execute(self):
        for name, expected in (("functions", 48), ("arrays", 6)):
            with self.subTest(sample=name):
                source_path = EXAMPLE / "valid" / f"{name}.c"
                bytecode_path = self.directory / f"{name}.cvm"
                compiled = subprocess.run(
                    [str(self.compiler), str(source_path), str(bytecode_path)],
                    cwd=self.directory,
                    env=self.environment,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                self.assertEqual(compiled.returncode, 0, compiled.stderr)
                execution = self.run_cvm(bytecode_path)
                self.assertEqual(execution.returncode, 0, execution.stderr.decode())
                self.assertEqual(execution.stdout, f"result: {expected}\n".encode())

    def test_globals_arrays_strings_functions_and_control_flow_match_c(self):
        source = """\
int bias = 2;
char letters[] = "abc";

int add(int left, int right) {
    return left + right;
}

int main() {
    int values[] = {1, 2, 3};
    int total = 0;
    for (int i = 0; i < 3; i++) {
        total += values[i];
    }
    if (letters[1] == 'b') {
        total += add(bias, 4);
    }
    int remaining = 3;
    while (remaining > 0) {
        total += 1;
        remaining--;
    }
    return total;
}
"""
        self.assert_matches_c(source, 15, "features")

    def test_continue_break_and_short_circuit_match_c(self):
        source = """\
int main() {
    int count = 0;
    int total = 0;
    while (count < 8) {
        count++;
        if (count == 2 || count == 3) continue;
        if (count == 7) break;
        total += count;
    }
    return total;
}
"""
        self.assert_matches_c(source, 16, "loops")

    def test_signed_division_and_remainder_follow_c(self):
        source = """\
int main() {
    return (-7 / 2) * 10 + (-7 % 2);
}
"""
        compiled, _, bytecode_path = self.compile_source(source, "signed")
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        execution = self.run_cvm(bytecode_path)
        self.assertEqual(execution.returncode, 0, execution.stderr.decode())
        self.assertEqual(execution.stdout, b"result: -31\n")

    def test_branches_ending_in_returns_have_valid_targets(self):
        source = """\
int choose(int condition) {
    if (condition) return 4;
    else return 5;
}

int main() {
    if (choose(0) == 5) return 7;
    else return 8;
}
"""
        self.assert_matches_c(source, 7, "terminal-branches")

    def test_dynamic_global_initializer_runs_before_main(self):
        source = """\
int initial() { return 41; }
int value = initial();
int main() { return value + 1; }
"""
        compiled, _, bytecode_path = self.compile_source(source, "global-init")
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        execution = self.run_cvm(bytecode_path)
        self.assertEqual(execution.returncode, 0, execution.stderr.decode())
        self.assertEqual(execution.stdout, b"result: 42\n")

    def test_char_scalar_increment_and_array_bounds(self):
        source = """\
int main() {
    char letter = 'A';
    letter++;
    return letter - 'B';
}
"""
        self.assert_matches_c(source, 0, "char-scalar")
        compiled, _, bytecode_path = self.compile_source(
            "int main() { int values[1]; return values[1]; }\n", "bounds"
        )
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        execution = self.run_cvm(bytecode_path)
        self.assertEqual(execution.returncode, 1)
        self.assertIn(b"runtime trap", execution.stderr)

    def test_checked_overflow_traps_at_runtime(self):
        compiled, _, bytecode_path = self.compile_source(
            "int main() { return 2147483647 + 1; }\n", "overflow"
        )
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        execution = self.run_cvm(bytecode_path)
        self.assertEqual(execution.returncode, 1)
        self.assertIn(b"runtime trap", execution.stderr)

    def test_switch_goto_and_labels_are_explicitly_rejected(self):
        for source, diagnostic in (
            ("int main() { switch (1) { case 1: return 0; } }\n",
             "CVM backend does not support switch statements"),
            ("int main() { goto done; done: return 0; }\n",
             "CVM backend does not support labels or goto"),
            ("int main() { done: return 0; }\n",
             "CVM backend does not support labels or goto"),
        ):
            with self.subTest(diagnostic=diagnostic):
                output = self.directory / "unsupported.cvm"
                output.write_bytes(b"preserve existing output")
                source_path = self.directory / "unsupported.c"
                source_path.write_text(source)
                compiled = subprocess.run(
                    [str(self.compiler), str(source_path), str(output)],
                    cwd=self.directory,
                    env=self.environment,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                self.assertEqual(compiled.returncode, 1)
                self.assertIn(diagnostic, compiled.stderr)
                self.assertIn(":1:", compiled.stderr)
                self.assertEqual(output.read_bytes(), b"preserve existing output")

    def test_non_main_fallthrough_is_rejected_conservatively(self):
        source = "int maybe(int value) { while (value) return 1; }\nint main() { return 0; }\n"
        compiled, _, bytecode_path = self.compile_source(source, "fallthrough")
        self.assertEqual(compiled.returncode, 1)
        self.assertIn("may reach its end without returning", compiled.stderr)
        self.assertIn(":1:", compiled.stderr)
        self.assertFalse(bytecode_path.exists())


if __name__ == "__main__":
    unittest.main()

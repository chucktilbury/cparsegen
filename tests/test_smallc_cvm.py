"""SmallC -> textual CVM assembly -> cvm-as -> cvm-run end-to-end tests."""

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
        if not compiler or not Path(compiler).is_file():
            raise unittest.SkipTest(
                "build the smallc-cvm target (CPARSEGEN_CVM_COMPILER)"
            )
        cls.compiler = Path(compiler)
        assembler = os.environ.get("CPARSEGEN_CVM_ASSEMBLER")
        runner = os.environ.get("CPARSEGEN_CVM_RUNNER")
        cls.assembler = Path(assembler) if assembler else None
        cls.runner = Path(runner) if runner else None
        cls.have_tools = bool(
            cls.assembler and cls.runner
            and cls.assembler.is_file() and cls.runner.is_file()
        )
        if not cls.have_tools and os.environ.get("CPARSEGEN_REQUIRE_CVM_TOOLS"):
            raise RuntimeError(
                "cvm-as and cvm-run are required: set CVM_PREFIX or CVM_AS/CVM_RUN"
            )
        cls.temporary = tempfile.TemporaryDirectory(prefix="smallc-cvm-test-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.directory = Path(cls.temporary.name)
        cls.environment = {"PATH": "/usr/bin:/bin", "HOME": str(cls.directory)}

    def require_tools(self):
        if not self.have_tools:
            self.skipTest(
                "cvm-as/cvm-run not available; set CVM_PREFIX or CVM_AS and CVM_RUN"
            )

    def compile_source(self, source, name="input"):
        source_path = self.directory / f"{name}.c"
        assembly_path = self.directory / f"{name}.asm"
        assembly_path.unlink(missing_ok=True)
        source_path.write_text(source)
        result = subprocess.run(
            [str(self.compiler), str(source_path), str(assembly_path)],
            cwd=self.directory, env=self.environment,
            capture_output=True, text=True, timeout=30,
        )
        return result, source_path, assembly_path

    def assemble(self, assembly_path):
        self.require_tools()
        binary = assembly_path.with_suffix(".cvm")
        binary.unlink(missing_ok=True)
        result = subprocess.run(
            [str(self.assembler), str(assembly_path), "-o", str(binary)],
            cwd=self.directory, env=self.environment,
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(binary.is_file())
        return binary

    def run_cvm(self, assembly_path, stdin=b""):
        binary = self.assemble(assembly_path)
        return subprocess.run(
            [str(self.runner), str(binary)],
            cwd=self.directory, env=self.environment,
            input=stdin, capture_output=True, timeout=30,
        )

    def require_handle_services(self):
        self.require_tools()
        probe = self.directory / "probe-handles.asm"
        probe.write_text(
            ".version 1.0\n.entry main\n.array p: u8[2] = \"x\"\n"
            ".func main() -> i32\n    array p\n    array p\n"
            "    sys file_open\n    ret.i32\n.end\n"
        )
        result = subprocess.run(
            [str(self.assembler), str(probe), "-o", str(self.directory / "probe.cvm")],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            self.skipTest(
                "installed cvm-as lacks the file_open/file_*_handle services: "
                + result.stderr.strip()
            )

    def compile_and_run(self, source, name, stdin=b""):
        compiled, _, assembly_path = self.compile_source(source, name)
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        return self.run_cvm(assembly_path, stdin)

    def assert_matches_c(self, source, expected, name):
        compiled, source_path, assembly_path = self.compile_source(source, name)
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        self.assertEqual(compiled.stdout, "")
        text = assembly_path.read_bytes()
        self.assertNotIn(b"\0", text)
        text.decode("ascii")
        self.assertIn(b".version 1.0\n.entry main\n", text)
        self.assertIn(b".func main() -> i32", text)

        execution = self.run_cvm(assembly_path)
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
                execution = self.compile_and_run(source_path.read_text(), name)
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
        execution = self.compile_and_run(source, "signed")
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
        execution = self.compile_and_run(source, "global-init")
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
        execution = self.compile_and_run(
            "int main() { int values[1]; return values[1]; }\n", "bounds"
        )
        self.assertEqual(execution.returncode, 1)
        self.assertIn(b"runtime trap", execution.stderr)

    def test_checked_overflow_traps_at_runtime(self):
        execution = self.compile_and_run(
            "int main() { return 2147483647 + 1; }\n", "overflow"
        )
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
                output = self.directory / "unsupported.asm"
                output.write_bytes(b"preserve existing output")
                source_path = self.directory / "unsupported.c"
                source_path.write_text(source)
                compiled = subprocess.run(
                    [str(self.compiler), str(source_path), str(output)],
                    cwd=self.directory, env=self.environment,
                    capture_output=True, text=True, timeout=30,
                )
                self.assertEqual(compiled.returncode, 1)
                self.assertIn(diagnostic, compiled.stderr)
                self.assertIn(":1:", compiled.stderr)
                self.assertEqual(output.read_bytes(), b"preserve existing output")

    def test_non_main_fallthrough_is_rejected_conservatively(self):
        source = "int maybe(int value) { while (value) return 1; }\nint main() { return 0; }\n"
        compiled, _, assembly_path = self.compile_source(source, "fallthrough")
        self.assertEqual(compiled.returncode, 1)
        self.assertIn("may reach its end without returning", compiled.stderr)
        self.assertIn(":1:", compiled.stderr)
        self.assertFalse(assembly_path.exists())

    def test_emitted_text_is_symbolic_assembly(self):
        source = """\
int fib(int n) { if (n < 2) return n; return fib(n - 1) + fib(n - 2); }
int main() { int v[2] = {1, 2}; return fib(6) + v[1]; }
"""
        compiled, _, assembly_path = self.compile_source(source, "text")
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        text = assembly_path.read_text()
        for expected in (
            ".version 1.0", ".entry main", ".func sc_fib(p0_n:i32) -> i32",
            "call sc_fib", "jz L0", "\nL0:\n", "lt.i32", "aset", ".end",
        ):
            self.assertIn(expected, text)
        self.assert_matches_c(source, 10, "text-run")

    def test_static_string_initializer_and_escapes_are_exact(self):
        source = 'char s[5] = "a\\n\\"\\\\"; int main() { return s[1] + s[2] + s[3] + s[4]; }\n'
        compiled, _, assembly_path = self.compile_source(source, "escapes")
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        self.assertIn(".array", assembly_path.read_text())
        execution = self.run_cvm(assembly_path)
        self.assertEqual(execution.stdout, f"result: {10 + 34 + 92}\n".encode())

    def test_print_writes_bytes_up_to_nul(self):
        execution = self.compile_and_run(
            'int main() { char s[8] = "hi\\n"; print(s); return 0; }\n', "print"
        )
        self.assertEqual(execution.returncode, 0, execution.stderr.decode())
        self.assertEqual(execution.stdout, b"hi\nresult: 0\n")

    def test_assembler_rejects_nothing_for_every_valid_sample(self):
        for path in sorted((EXAMPLE / "valid").glob("*.c")):
            with self.subTest(sample=path.name):
                output = self.directory / f"valid-{path.stem}.asm"
                output.unlink(missing_ok=True)
                compiled = subprocess.run(
                    [str(self.compiler), str(path), str(output)],
                    cwd=self.directory, env=self.environment,
                    capture_output=True, text=True, timeout=30,
                )
                if compiled.returncode != 0:
                    self.assertFalse(output.exists())
                    continue
                self.assemble(output)

    def test_file_builtins_lower_to_handle_services(self):
        source = """\
int main() {
    char buffer[8];
    int out = open("data.bin", "w");
    int written = write(out, 3, "abc");
    close(out);
    int in = open("data.bin", "r");
    int count = read(in, 8, buffer);
    close(in);
    return written + count;
}
"""
        compiled, _, assembly_path = self.compile_source(source, "file-text")
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        text = assembly_path.read_text()
        for service in ("file_open", "file_write_handle", "file_read_handle",
                        "file_close_handle"):
            self.assertIn(f"sys {service}\n", text)
        self.assertIn('.array s1_literal: u8[9] = "data.bin"', text)
        self.assertNotIn("file_open_read", text)

    def test_invalid_builtin_uses_are_rejected_without_output(self):
        for source, diagnostic in (
            ("int main() { print(1); return 0; }\n", "requires the name of a char array"),
            ("int main() { char b[2]; return read(0, 2); }\n", "expects 3 arguments"),
            ("int main() { char b[2]; int v = close(0); return v; }\n", "void intrinsic"),
            ("int open(int x) { return x; }\nint main() { return 0; }\n", "reserved compiler intrinsic"),
            ("int main() { int print = 1; return print; }\n", "reserved compiler intrinsic"),
            ("int f(int s) { return 0; }\nint main() { return f(\"x\"); }\n", "string literals may only"),
            ("int main() { return write(0, \"x\", \"y\"); }\n", "cannot be a string literal"),
            ("int main() { return close(0) + 1; }\n", "integral scalar operands"),
        ):
            with self.subTest(source=source):
                compiled, _, assembly_path = self.compile_source(source, "invalid")
                self.assertEqual(compiled.returncode, 1, compiled.stdout)
                self.assertIn(diagnostic, compiled.stderr)
                self.assertFalse(assembly_path.exists())

    def test_binary_copy_of_all_byte_values(self):
        self.require_handle_services()
        data = bytes(range(256))
        (self.directory / "all256.in").write_bytes(data)
        source = """\
int main() {
    char buffer[256];
    int in = open("all256.in", "r");
    int out = open("all256.out", "w");
    int count = read(in, 256, buffer);
    close(in);
    int written = write(out, count, buffer);
    close(out);
    return written - count;
}
"""
        execution = self.compile_and_run(source, "copy256")
        self.assertEqual(execution.returncode, 0, execution.stderr.decode())
        self.assertEqual(execution.stdout, b"result: 0\n")
        self.assertEqual((self.directory / "all256.out").read_bytes(), data)

    def test_open_modes_eof_and_failure(self):
        self.require_handle_services()
        (self.directory / "mode.txt").write_bytes(b"ab")
        source = """\
int main() {
    char buffer[4];
    int out = open("mode.txt", "a");
    write(out, 1, "c");
    close(out);
    int in = open("mode.txt", "r");
    int first = read(in, 4, buffer);
    int second = read(in, 4, buffer);
    int zero = read(in, 0, buffer);
    close(in);
    print(buffer);
    return first * 100 + second * 10 + zero;
}
"""
        execution = self.compile_and_run(source, "modes")
        self.assertEqual(execution.returncode, 0, execution.stderr.decode())
        self.assertEqual(execution.stdout, b"abcresult: 300\n")
        self.assertEqual((self.directory / "mode.txt").read_bytes(), b"abc")
        failure = self.compile_and_run(
            'int main() { return open("missing-dir/none", "r"); }\n', "open-fail"
        )
        self.assertEqual(failure.returncode, 1)
        self.assertIn(b"I/O error", failure.stderr)
        oversized = self.compile_and_run(
            "int main() { char b[2]; return read(0, 3, b); }\n", "oversized"
        )
        self.assertEqual(oversized.returncode, 1)
        self.assertIn(b"runtime trap", oversized.stderr)


if __name__ == "__main__":
    unittest.main()

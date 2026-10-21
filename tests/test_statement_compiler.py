"""Visitor scopes, function/control flow, C execution, and syntax parsing."""

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

    def run_program(self, text, input_data="", instrumentation=""):
        emitted = self.invoke(text)
        self.assertEqual((emitted.returncode, emitted.stderr), (0, ""))
        source = self.directory / "program.c"
        source.write_text(emitted.stdout.replace(
            "#include <stdlib.h>\n", "#include <stdlib.h>\n" + instrumentation, 1,
        ))
        program = self.directory / "program"
        self.compile_c(source, program)
        result = subprocess.run(
            [str(program)], input=input_data, capture_output=True, text=True, timeout=30,
        )
        return emitted.stdout, result

    def assert_program(self, text, expected, input_data=""):
        emitted, result = self.run_program(text, input_data)
        self.assertEqual((result.returncode, result.stdout, result.stderr),
                         (0, expected, ""))
        return emitted

    def test_source_order_and_persistent_symbols(self):
        emitted = self.assert_program(
            (EXAMPLES / "statements/basic.stmt").read_text(), "20\n56\n28\n",
        )
        self.assertLess(emitted.index("int32_t cpg_v0"),
                        emitted.index("    cpg_println_int((int32_t)"))
        self.assertEqual(emitted.count("int32_t cpg_v0"), 1)
        self.assertEqual(emitted.count("int32_t cpg_v1"), 1)
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
            ("let switch = 1; let printf = switch + 1; let main = printf * 2; "
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

    def test_runtime_typed_output_and_integration(self):
        emitted = self.assert_program(
            (EXAMPLES / "statements/runtime.stmt").read_text(),
            "7true\nfalse\n-7\n7\n7\n1\n", "-7\n",
        )
        self.assertIn("cpg_read_int()", emitted)
        main = emitted[emitted.index("int main(void)"):]
        for stdio in ["printf(", "fputs(", "fgetc(", "fflush(", "putchar("]:
            self.assertNotIn(stdio, main)
        self.assert_program(
            "print_int(-2147483648); println_int(2147483647); "
            "print_bool(false); println_bool(true); "
            "fn show(n: int) { print_int(n); return n; } show(3); "
            "print true; print false;", "-21474836482147483647\nfalsetrue\n31\n0\n",
        )

    def test_runtime_integer_utilities(self):
        self.assert_program(
            "println_int(min(-2147483648, 2147483647)); "
            "println_int(max(-2147483648, 2147483647)); "
            "print min(4, 4); print max(-4, -4); "
            "print abs(-2147483647); print abs(2147483647); "
            "print abs(0); print abs(-0); print abs(-1); "
            "if (false) { print abs(-2147483648); } "
            "fn f(n) { return max(abs(n), 10); } print f(-12);",
            "-2147483648\n2147483647\n4\n-4\n2147483647\n2147483647\n0\n0\n1\n12\n",
        )
        text = "let n = abs(-2147483648); println_int(n); println_int(99);"
        _, result = self.run_program(text)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((result.stdout, result.stderr), ("", "integer overflow in abs\n"))
        self.assert_syntax_modes_accept(self.syntax_parser, text)

    def test_runtime_input_valid_tokens(self):
        self.assert_program(
            "let a = read_int(); let b = read_int(); let c = read_int(); "
            "let d = read_int(); let e = read_int(); let f = read_int(); "
            "print a; print b; print c; print d; print e; print f;",
            "0\n0\n2147483647\n-2147483648\n8\n-17\n",
            " \t\r\n\v\f+0 -0 +2147483647 -2147483648 0008 -17",
        )
        self.assert_program("println_int(read_int());", "1\n", "0" * 10000 + "1")
        self.assert_program(
            "fn update(): int { return read_int(); } "
            "let n = read_int(); print n; print update();",
            "3\n4\n", "3 4\n",
        )

    def test_runtime_input_failures(self):
        for data, diagnostic in [
            ("", "input EOF"), (" \t\r\n\v\f", "input EOF"),
            ("x", "input malformed integer"), ("12x", "input malformed integer"),
            ("1.0", "input malformed integer"), ("0x10", "input malformed integer"),
            ("+", "input malformed integer"), ("- ", "input malformed integer"),
            ("--1", "input malformed integer"), ("+ 1", "input malformed integer"),
            ("1\x002", "input malformed integer"), ("1\u00a02", "input malformed integer"),
            ("2147483648", "input integer outside int32 range"),
            ("-2147483649", "input integer outside int32 range"),
            ("9" * 10000, "input integer outside int32 range"),
            ("9" * 10000 + "x", "input malformed integer"),
        ]:
            with self.subTest(data=data[:40]):
                text = "print_int(7); let n: int = read_int(); println_int(n); println_int(99);"
                _, result = self.run_program(text, data)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual((result.stdout, result.stderr), ("7", diagnostic + "\n"))
        _, result = self.run_program(
            "let a = read_int(); println_int(a); let b = read_int(); println_int(b);", "42",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((result.stdout, result.stderr), ("42\n", "input EOF\n"))

    def test_runtime_stream_errors(self):
        for text, instrumentation, diagnostic in [
            ("println_int(read_int());",
             "static int fail_get(FILE *s) { (void)s; return EOF; }\n"
             "static int fail_error(FILE *s) { (void)s; return 1; }\n"
             "#define fgetc fail_get\n#define ferror fail_error\n", "input error"),
            ("print_int(1);",
             "static int fail_print(const char *f, ...) { (void)f; return -1; }\n"
             "#define printf fail_print\n", "output error"),
            ("print_bool(true);",
             "static int fail_puts(const char *t, FILE *s) { (void)t; (void)s; return EOF; }\n"
             "#define fputs fail_puts\n", "output error"),
            ("println_bool(true);",
             "static int fail_put(int ch) { (void)ch; return EOF; }\n"
             "#define putchar fail_put\n", "output error"),
            ("", "static int fail_flush(FILE *s) { (void)s; return EOF; }\n"
             "#define fflush fail_flush\n", "output error"),
            ("println_int(read_int());",
             "static int fail_flush(FILE *s) { (void)s; return EOF; }\n"
             "#define fflush fail_flush\n", "output error"),
        ]:
            with self.subTest(text=text, instrumentation=instrumentation):
                _, result = self.run_program(text, instrumentation=instrumentation)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stderr, diagnostic + "\n")

    def test_runtime_types_arity_and_syntax_only(self):
        for text, diagnostic in [
            ("print_int(true);", "argument type mismatch"),
            ("println_bool(1);", "argument type mismatch"),
            ("print_bool();", "argument count mismatch"),
            ("println_int(1, 2);", "argument count mismatch"),
            ("let n = println_int(1);", "output builtin requires a statement"),
            ("print min(1);", "argument count mismatch"),
            ("print max(1, true);", "argument type mismatch"),
            ("print abs(false);", "argument type mismatch"),
            ("print read_int(1);", "argument count mismatch"),
            ("let n; println_int(n);", "read before definite initialization"),
            ("absent();", "unknown function"),
        ]:
            with self.subTest(text=text):
                result = self.invoke(text)
                self.assertEqual((result.returncode, result.stdout), (1, ""))
                self.assertIn(diagnostic, result.stderr)
                self.assert_syntax_modes_accept(self.syntax_parser, text)
        self.assert_syntax_modes_accept(self.syntax_parser, "println_int(read_int());")

    def test_runtime_names_do_not_reserve_user_identifiers(self):
        self.assert_program(
            "fn min(n: bool): bool { return n; } "
            "fn read_int(n) { return n; } "
            "fn println_int(n: bool): bool { return n; } "
            "let abs = 4; let print_bool = abs; "
            "fn max() { return 3; } "
            "print min(true); print read_int(print_bool); "
            "print println_int(false); println_int(true); print max();",
            "1\n4\n0\n3\n",
        )

    def test_int32_boundaries_and_storage(self):
        emitted = self.assert_program(
            "print 2147483647; print -2147483648; print - 0002147483648; "
            "print +2147483647; print +-2147483648; print -(2147483647); "
            "print 0000000000000000000000000000008; "
            "fn identity(n: int): int { return n; } "
            "let b = identity(-2147483648); print b; "
            "let x: int = 2147483647; b = x; print b;",
            "2147483647\n-2147483648\n-2147483648\n2147483647\n"
            "-2147483648\n-2147483647\n8\n-2147483648\n2147483647\n",
        )
        self.assertNotIn("double", emitted)
        self.assertIn("INT32_MIN", emitted)
        self.assertIn("INT32_C(8)", emitted)

    def test_int32_literal_errors_have_exact_locations(self):
        for expression, token in [
            ("2147483648", "2147483648"),
            ("+2147483648", "2147483648"),
            ("-2147483649", "2147483649"),
            ("-(2147483648)", "2147483648"),
            ("-+2147483648", "2147483648"),
            ("0002147483648", "0002147483648"),
            ("9" * 200, "9" * 200),
            ("-" + "9" * 200, "9" * 200),
        ]:
            with self.subTest(expression=expression):
                text = f"print 1;\nprint {expression};"
                offset = text.index(token)
                result = self.invoke(text)
                self.assertEqual((result.returncode, result.stdout), (1, ""))
                self.assertEqual(
                    result.stderr,
                    f"{self.directory / 'source.stmt'}:2:{offset - text.index(chr(10))}: "
                    f"byte {offset}: integer literal outside int32 range: '{token}'\n",
                )
                self.assert_syntax_modes_accept(self.syntax_parser, text)

    def test_int32_valid_arithmetic_near_bounds(self):
        self.assert_program(
            "print 2147483646 + 1; print -2147483647 - 1; "
            "print -2147483648 + 1; print 2147483647 - 1; "
            "print -2147483648 - -2147483648; "
            "print -2147483648 + 2147483647; "
            "print 1073741823 * 2; print -1073741824 * 2; "
            "print -2147483648 * 1; print -2147483648 * 0; "
            "print 2147483647 * -1; print -(-2147483647); "
            "print 2147483647 - 1 - 1; print 1073741823 * 2 * 1;",
            "2147483647\n-2147483648\n-2147483647\n2147483646\n"
            "0\n-1\n2147483646\n-2147483648\n-2147483648\n0\n"
            "-2147483647\n2147483647\n2147483645\n2147483646\n",
        )

    def test_int32_runtime_overflow(self):
        for expression, operator in [
            ("2147483647 + 1", "+"), ("-2147483648 + -1", "+"),
            ("2147483647 - -1", "-"), ("-2147483648 - 1", "-"),
            ("1073741824 * 2", "*"), ("-1073741825 * 2", "*"),
            ("-2147483648 * -1", "*"), ("-1 * -2147483648", "*"),
            ("2147483647 * 2147483647", "*"),
            ("-2147483648 * 2147483647", "*"),
            ("-2147483648 * -2147483648", "*"),
            ("--2147483648", "-"), ("-(-2147483648)", "-"),
            ("2147483647 + 1 - 1", "+"),
            ("1073741824 * 2 * 0", "*"),
        ]:
            with self.subTest(expression=expression):
                emitted = self.invoke(
                    "fn calculate(a: int, b: int) { return a + b; } "
                    f"let n = {expression}; print n; print 99;"
                )
                self.assertEqual((emitted.returncode, emitted.stderr), (0, ""))
                source = self.directory / "overflow.c"
                source.write_text(emitted.stdout)
                program = self.directory / "overflow"
                self.compile_c(source, program)
                result = subprocess.run(
                    [str(program)], capture_output=True, text=True, timeout=30,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr, f"integer overflow in {operator}\n")
        self.assert_program(
            "if (false) { print 2147483647 + 1; } "
            "let flag: bool = -2147483648 < 2147483647; "
            "print flag; print flag == true; print false != true;", "1\n1\n1\n",
        )

    def test_function_sample_and_nested_forward_calls(self):
        emitted = self.assert_program(
            (EXAMPLES / "statements/functions.stmt").read_text(), "12\n120\n7\n",
        )
        self.assertLess(emitted.index("int32_t cpg_f0(int32_t);"),
                        emitted.index("int main(void)"))
        self.assert_program(
            "print add(one(), add(2, 3)); "
            "fn add(a, b) { let total = a + b; return total; } "
            "fn one() { return 1; }", "6\n",
        )

    def test_function_scopes_and_c_safe_names(self):
        self.assert_program(
            "let x = 100; fn first(x) { let y = x + 1; return y; } "
            "fn second(x) { let y = first(x); return y * 2; } "
            "fn main(printf) { let switch = printf; return switch; } "
            "fn unused(ignored) { let local; return 0; } "
            "fn x() { return 9; } "
            "print first(2); print second(3); print x; print main(x());",
            "3\n8\n100\n9\n",
        )
        declarations = "".join(f"let x{i} = {i};" for i in range(24))
        functions = "".join(f"fn f{i}(x) {{ return x + {i}; }}" for i in range(24))
        self.assert_program(
            f"{functions} fn local(x) {{ {declarations} return x + x23; }} "
            "print local(f23(1));", "47\n",
        )
        self.assert_program(
            f"fn local(n) {{ if (n != 0) {{ {declarations} return x23; }} "
            "else { let last = 7; } return last; } "
            "print local(0); print local(1);", "7\n23\n",
        )

    def test_recursive_and_mutually_recursive_functions(self):
        self.assert_program(
            "fn even(n) { if (n == 0) { return 1; } "
            "else { return odd(n - 1); } } "
            "fn odd(n) { if (n == 0) { return 0; } return even(n - 1); } "
            "print even(8); print odd(8); print odd(7);", "1\n0\n1\n",
        )

    def test_return_aware_definite_assignment_and_control_flow(self):
        for text, expected in [
            ("fn f(n) { let x; if (n != 0) { return 10; } else { x = 20; } "
             "return x; } print f(1); print f(0);", "10\n20\n"),
            ("fn f(n) { let x; if (n != 0) { x = 20; } else { return 10; } "
             "return x; } print f(1); print f(0);", "20\n10\n"),
            ("fn f(n) { while (n > 0) { if (n == 2) { return n; } "
             "n = n - 1; } return 0; } print f(3); print f(0);", "2\n0\n"),
            ("fn f(n) { if (n != 0) { { return -n; } } return n + 1; } "
             "print f(2); print f(0);", "-2\n1\n"),
            ("fn f(n) { let x; if (n != 0) { x = 1; } else { x = 2; } "
             "return x; } print f(0);", "2\n"),
            ("fn f(x) { return x; print 99; } print f(3);", "3\n"),
            ("fn f(x) { print x; return x * 2; } print f(3);", "3\n6\n"),
        ]:
            with self.subTest(text=text):
                self.assert_program(text, expected)

    def test_function_semantic_errors_are_syntax_only_accepted(self):
        cases = [
            ("print absent(1);", "unknown function", "absent"),
            ("fn f() { return missing(); }", "unknown function", "missing"),
            ("fn f(x) { return x; } print f();", "argument count mismatch", "f"),
            ("fn f() { return 1; } print f(1);", "argument count mismatch", "f"),
            ("fn f(a, b) { return a; } print f(1, 2, 3);",
             "argument count mismatch", "f"),
            ("fn f(x, x) { return x; }", "duplicate declaration", "x"),
            ("fn f(x) { let x = 1; return x; }", "duplicate declaration", "x"),
            ("fn f() { let x; { let x; } return 1; }", "duplicate declaration", "x"),
            ("fn f() { return 1; } fn f(x) { return x; }", "duplicate function", "f"),
            ("return 1;", "return outside function", "return"),
            ("if (false) { return; }", "return outside function", "return"),
            ("fn f() { return; }", "return requires a value", "return"),
            ("fn f() {}", "function may finish without returning a value", "f"),
            ("fn f(x) { if (x != 0) { return 1; } }",
             "function may finish without returning a value", "f"),
            ("fn f() { while (true) { return 1; } }",
             "function may finish without returning a value", "f"),
            ("fn f() { let x; return x; }", "read before definite initialization", "x"),
            ("fn f() { let x; return g(x); } fn g(x) { return x; }",
             "read before definite initialization", "x"),
            ("fn f(n) { let x; if (n != 0) { x = 1; } return x; }",
             "read before definite initialization", "x"),
            ("fn f(n) { let x; while (n != 0) { x = 1; n = 0; } return x; }",
             "read before definite initialization", "x"),
            ("let x = 1; fn f() { return x; }",
             "use before declaration (unknown name)", "x"),
            ("fn f(x) { return x; } print x;",
             "use before declaration (unknown name)", "x"),
            ("fn f(x) { return x; } fn g() { x = 1; return 0; }",
             "assignment to unknown name", "x"),
            ("fn f() { let x = 1; return x; } fn g() { return x; }",
             "use before declaration (unknown name)", "x"),
            ("fn f(x) { return x; } fn g() { let x; return x; }",
             "read before definite initialization", "x"),
            ("fn f() { return 1; print missing; }",
             "use before declaration (unknown name)", "missing"),
            ("fn f() { return 2147483648; }", "integer literal outside int32 range",
             "2147483648"),
        ]
        for text, diagnostic, name in cases:
            with self.subTest(text=text):
                result = self.invoke(text)
                self.assertEqual((result.returncode, result.stdout), (1, ""))
                self.assertRegex(result.stderr, r"source\.stmt:1:\d+: byte \d+:")
                self.assertTrue(result.stderr.endswith(f"{diagnostic}: '{name}'\n"),
                                result.stderr)
                self.assert_syntax_modes_accept(self.syntax_parser, text)

    def test_function_errors_have_exact_source_locations(self):
        for text, occurrence, diagnostic in [
            ("fn f(x) {\n  let x = 1;\n  return x;\n}", "x =",
             "duplicate declaration"),
            ("fn f(x) {\n  return x;\n}\nprint f();", "f();",
             "argument count mismatch"),
            ("fn f() {\n  return absent();\n}", "absent",
             "unknown function"),
            ("fn f() {\n  return;\n}", "return",
             "return requires a value"),
        ]:
            with self.subTest(text=text):
                offset = text.index(occurrence)
                name = text[offset:].split()[0].split("(")[0].split(";")[0]
                line = text.count("\n", 0, offset) + 1
                column = offset - text.rfind("\n", 0, offset)
                result = self.invoke(text)
                self.assertEqual((result.returncode, result.stdout), (1, ""))
                self.assertEqual(
                    result.stderr,
                    f"{self.directory / 'source.stmt'}:{line}:{column}: "
                    f"byte {offset}: {diagnostic}: '{name}'\n",
                )

    def test_function_syntax_errors(self):
        for text in [
            "fn f(x, x,) { return 1; }", "fn f(x) return x;",
            "fn f() { fn g() { return 1; } return g(); }",
            "print f(,);", "print f(1,);", "fn f() { return 1 }",
            "let return = 1;", "let fn = 1;", "fn f() { return 1, 2; }",
        ]:
            with self.subTest(text=text):
                result = self.invoke(text)
                self.assertEqual((result.returncode, result.stdout), (1, ""))
                self.assertIn("parse error", result.stderr)

    def test_control_flow_sample(self):
        emitted = self.assert_program(
            (EXAMPLES / "statements/control-flow.stmt").read_text(), "3\n3\n3\n4\n",
        )
        self.assertIn("while (", emitted)
        self.assertIn("else\n", emitted)

    def test_comparisons_and_precedence(self):
        for operator, expected in [
            ("<", "1\n0\n0\n"), ("<=", "1\n1\n0\n"),
            (">", "0\n0\n1\n"), (">=", "0\n1\n1\n"),
            ("==", "0\n1\n0\n"), ("!=", "1\n0\n1\n"),
        ]:
            with self.subTest(operator=operator):
                self.assert_program(
                    f"print 1 {operator} 2; print 2 {operator} 2; "
                    f"print 3 {operator} 2;", expected,
                )
        self.assert_program(
            "print 1 + 2 * 3 < 8 == true; print false == 2 < 1; "
            "print (2 < 3) == (4 >= 4); print -2 < -1; "
            "print true == false == false;", "1\n1\n1\n1\n1\n",
        )
        self.assert_program(
            "let flag = 2 < 3; while (flag) { print flag; flag = 2 != 2; } "
            "if (flag) { print 99; } else { print flag; }", "1\n0\n",
        )

    def test_branches_nested_blocks_and_boolean_conditions(self):
        self.assert_program(
            "let x = 0; if (true) { x = 1; } else { x = 99; } print x; "
            "if (false) { x = 99; } else { x = 2; } print x; "
            "if (false) { print 99; } if (true) { { print 3; } } "
            "if (true) { if (false) { print 99; } else { print 4; } } "
            "else { print 99; } { { x = 5; } } print x; "
            "if (true) {} else {} {}",
            "1\n2\n3\n4\n5\n",
        )
        self.assert_program(
            "let iffy = 1; let elsewhere = 2; let whilex = 3; "
            "print iffy + elsewhere + whilex;", "6\n",
        )

    def test_loops_recheck_conditions_and_boundaries(self):
        self.assert_program(
            "let i = 0; while (i < 0) { print 99; } print i; "
            "while (i <= 0) { print i; i = i + 1; } print i; "
            "while (i != 3) { if (i == 2) { print i; } i = i + 1; } "
            "print i; while (false) {}",
            "0\n0\n1\n2\n3\n",
        )
        self.assert_program(
            "let i = 0; let j = 0; while (i < 2) { j = 0; "
            "while (j < 2) { { print i * 2 + j; } j = j + 1; } "
            "i = i + 1; }", "0\n1\n2\n3\n",
        )

    def test_nested_declarations_keep_one_source_order_scope(self):
        self.assert_program(
            "{ let x = 2; } print x; "
            "if (false) { let skipped = 9; } skipped = x; print skipped; "
            "if (false) { let shared = 8; } else { shared = x + 1; } print shared; "
            "while (false) { let never = 7; } never = 4; print never; "
            "let i = 0; while (i < 2) { let local = i; print local; i = i + 1; } "
            "local = i; print local;", "2\n2\n3\n4\n0\n1\n2\n",
        )
        for text, diagnostic in [
            ("{ let x = 1; } let x = 2;", "duplicate declaration"),
            ("if (true) { let x = 1; } else { let x = 2; }", "duplicate declaration"),
            ("if (false) { print missing; }", "use before declaration"),
            ("while (missing < 1) {}", "use before declaration"),
            ("if (missing) {}", "use before declaration"),
            ("if (false) {} else { missing = 1; }", "assignment to unknown name"),
            ("while (false) { let x = x; }", "use before declaration"),
            ("print x; { let x = 1; }", "use before declaration"),
        ]:
            with self.subTest(text=text):
                result = self.invoke(text)
                self.assertEqual((result.returncode, result.stdout), (1, ""))
                self.assertIn(diagnostic, result.stderr)
                self.assertRegex(result.stderr, r"source\.stmt:1:\d+: byte \d+:")
                syntax = self.parse(self.syntax_parser, text)
                self.assertEqual(syntax.returncode, 0, syntax.stderr)

    def test_definite_assignment_valid_programs(self):
        for text, expected in [
            ("let x;", ""),
            ("let x; let y; x = 2; y = x + 1; print y;", "3\n"),
            ("let x = 1; let y = x; x = x + y; print x;", "2\n"),
            ("let x; { { x = 3; } print x; } print x;", "3\n3\n"),
            ("let x; if (true) { x = 2; } else { x = 3; } print x;", "2\n"),
            ("let x; if (false) { x = 2; } else { x = 3; } print x;", "3\n"),
            ("let x = 1; if (false) { x = 2; } print x; "
             "while (false) { x = 3; } print x;", "1\n1\n"),
            ("if (false) { let x = 2; } else { x = 3; } print x;", "3\n"),
            ("if (true) { let x = 2; } else { x = 3; } print x;", "2\n"),
            ("let x; if (true) { if (false) { x = 1; } else { x = 2; } } "
             "else { { x = 3; } } print x;", "2\n"),
            ("let x; let i = 0; while (i < 2) { x = i; print x; i = i + 1; } "
             "x = 9; print x;", "0\n1\n9\n"),
            ("let i = 0; while (i < 2) { let x; x = i; print x; "
             "i = i + 1; }", "0\n1\n"),
            ("let x; let i = 0; while (i < 1) { if (i == 0) { x = 4; } "
             "else { x = 5; } print x; i = i + 1; }", "4\n"),
            ("let x; let i = 0; while (i < 1) { x = 6; let j = 0; "
             "while (j < 1) { print x; j = j + 1; } print x; i = i + 1; }",
             "6\n6\n"),
            ("let x; if (false) { let y = 1; x = y; } "
             "else { y = 2; x = y; } print x;", "2\n"),
        ]:
            with self.subTest(text=text):
                self.assert_program(text, expected)

    def assert_syntax_modes_accept(self, parser, text, json_mode=True):
        source = self.directory / "semantic-invalid.stmt"
        source.write_text(text)
        modes = [[], ["--complete"]]
        if json_mode:
            modes.append(["--json"])
        for mode in modes:
            with self.subTest(mode=mode):
                result = subprocess.run(
                    [str(parser), *mode, str(source)],
                    capture_output=True, text=True, timeout=30,
                )
                self.assertEqual((result.returncode, result.stderr), (0, ""))
                if mode == ["--json"]:
                    self.assertEqual(json.loads(result.stdout)["name"], "program")

    def test_definite_assignment_errors_and_syntax_only_modes(self):
        for text, occurrence in [
            ("let x; print x;", "x;"),
            ("let x; print 1 + x * 2;", "x *"),
            ("let x; if (x != 0) {}", "x !="),
            ("let x; while (x < 1) {}", "x <"),
            ("let x; let y = x;", "x;"),
            ("let x; x = x + 1;", "x +"),
            ("let x; let y; y = x;", "x;"),
            ("let x;\nprint x;", "x;"),
            ("let x; if (true) { x = 1; } print x;", "x;"),
            ("let x; if (false) {} else { x = 1; } print x;", "x;"),
            ("let x; if (true) { x = 1; } else { print x; }", "x;"),
            ("let x; if (true) { print x; } else { x = 1; }", "x;"),
            ("if (false) { let x = 1; } print x;", "x;"),
            ("if (true) {} else { let x = 1; } print x;", "x;"),
            ("if (true) { let x = 1; } else { print x; }", "x;"),
            ("let x; if (true) { if (true) { x = 1; } } else { x = 2; } print x;",
             "x;"),
            ("let x; while (false) { x = 1; } print x;", "x;"),
            ("let x; while (true) { x = 1; } print x;", "x;"),
            ("while (false) { let x = 1; } print x;", "x;"),
            ("let x; while (false) { print x; x = 1; }", "x;"),
            ("let x; while (false) { if (true) { x = 1; } print x; }", "x;"),
            ("let x; while (false) { while (false) { x = 1; } print x; }", "x;"),
            ("let x; if (true) { while (false) { x = 1; } } "
             "else { x = 2; } print x;", "x;"),
            ("let x; if (false) { x = 1; } else { let y = x; }", "x;"),
            ("let x; { let y = x; } x = 1;", "x;"),
        ]:
            with self.subTest(text=text):
                offset = text.rindex(occurrence)
                line = text.count("\n", 0, offset) + 1
                column = offset - text.rfind("\n", 0, offset)
                result = self.invoke(text)
                self.assertEqual((result.returncode, result.stdout), (1, ""))
                self.assertEqual(
                    result.stderr,
                    f"{self.directory / 'source.stmt'}:{line}:{column}: "
                    f"byte {offset}: read before definite initialization: 'x'\n",
                )
                self.assert_syntax_modes_accept(self.syntax_parser, text)

    def test_control_flow_state_survives_symbol_table_growth(self):
        declarations = "".join(f"let x{i} = {i};" for i in range(24))
        assignments = "".join(f"x{i} = {i + 1};" for i in range(24))
        self.assert_program(
            f"if (false) {{ {declarations} }} else {{ {assignments} }} print x23;",
            "24\n",
        )
        result = self.invoke(f"while (false) {{ {declarations} }} print x23;")
        self.assertEqual((result.returncode, result.stdout), (1, ""))
        self.assertIn("read before definite initialization: 'x23'", result.stderr)

    def test_cwhip_parser_remains_syntax_only(self):
        parser = self.compile_grammar(
            (EXAMPLES / "statements.cpg").read_text(), backend="cwhip",
        )
        for text in [
            "println_int(read_int()); println_bool(true); print abs(-2147483648);",
            "let n = println_int(1); min(true, 1); read_int(3);",
            "let x; print x;",
            "let x; if (true) { x = 1; } print x;",
            "let x; while (false) { x = 1; } print x;",
            "let x = x; let x;",
            "fn f(x, x) { return x; }",
            "fn f() { return; } print unknown(1);",
            "fn f() { let x; return x; }",
            "let flag: bool = 1; if (3) { print flag + true; }",
            "fn f(n: bool): bool { return 1; } print f(2);",
        ]:
            with self.subTest(text=text):
                self.assert_syntax_modes_accept(parser, text, json_mode=False)

    def test_primitive_types_sample_and_lowering(self):
        emitted = self.assert_program(
            (EXAMPLES / "statements/types.stmt").read_text(),
            "1\n1\n3\n1\n7\n",
        )
        self.assertIn("int32_t cpg_f0(_Bool, int32_t, int32_t);", emitted)
        self.assertIn("int32_t cpg_f1(int32_t, int32_t, _Bool);", emitted)
        self.assertIn("_Bool cpg_v", emitted)

    def test_typed_returns_and_forward_recursion(self):
        self.assert_program(
            "print even(6); print even(5); "
            "fn even(n: int): bool { if (n == 0) { return true; } "
            "return odd(n - 1); } "
            "fn odd(n: int): bool { if (n == 0) { return false; } "
            "return even(n - 1); }",
            "1\n0\n",
        )
        self.assert_program(
            "fn f(flag: bool): bool { let result: bool; "
            "if (flag) { return false; } else { result = true; } "
            "while (flag) { result = false; flag = false; } return result; } "
            "print f(false); print f(true); "
            "let flag: bool; if (true) { flag = true; } else { flag = false; } "
            "print flag; let inferred = false; inferred = 1 < 2; print inferred; "
            "let bool = 3; let int: int = bool; print int;",
            "1\n0\n1\n1\n3\n",
        )

    def test_primitive_defaults_and_bool_expressions(self):
        self.assert_program(
            "fn toggle(flag: bool): bool { return flag == false; } "
            "let ready: bool; ready = toggle(true); print ready; "
            "let count: int; count = 000008; print count; "
            "print true; print false; print (1 < 2) != (3 < 4); "
            "print toggle(1 < 2);",
            "0\n8\n1\n0\n0\n0\n",
        )

    def test_primitive_type_errors_are_semantic_and_source_located(self):
        cases = [
            ("print true + 1;", "true", "type mismatch"),
            ("print 1 - false;", "false", "type mismatch"),
            ("print false * true;", "false", "type mismatch"),
            ("print -true;", "true", "type mismatch"),
            ("print +false;", "false", "type mismatch"),
            ("print true < false;", "true", "type mismatch"),
            ("print 1 >= false;", "false", "type mismatch"),
            ("print 3 > 2 > 1;", "1;", "type mismatch"),
            ("print 1 == true;", "true", "type mismatch"),
            ("print false != 0;", "0;", "type mismatch"),
            ("print 2 == 2 == 1;", "1;", "type mismatch"),
            ("if (1) {}", "1)", "condition type mismatch"),
            ("while (0) {}", "0)", "condition type mismatch"),
            ("let flag: bool = 1;", "flag:", "initializer type mismatch"),
            ("let n: int = true;", "n:", "initializer type mismatch"),
            ("let flag = false; flag = 1;", "flag = 1", "assignment type mismatch"),
            ("let n = 0; n = 1 < 2;", "n = 1", "assignment type mismatch"),
            ("let flag: bool; flag = 0;", "flag =", "assignment type mismatch"),
            ("fn f(): bool { return 1; }", "1;", "return type mismatch"),
            ("fn f(): int { return false; }", "false", "return type mismatch"),
            ("fn f() { return true; }", "true", "return type mismatch"),
            ("fn f(flag: bool) { return 1; } print f(1);", "1);",
             "argument type mismatch"),
            ("fn f(n: int): bool { return true; } print f(false);", "false);",
             "argument type mismatch"),
            ("fn f(flag: bool): bool { return flag; } print f();", "f();",
             "argument count mismatch"),
            ("let flag: bool; print flag;", "flag;", "read before definite initialization"),
            ("let flag: bool; if (true) { flag = true; } print flag;",
             "flag;", "read before definite initialization"),
            ("let flag: bool; while (true) { flag = false; } print flag;",
             "flag;", "read before definite initialization"),
            ("fn f(flag: bool): bool { if (flag) { return true; } }", "f(",
             "function may finish without returning"),
            ("fn f(): bool { while (true) { return false; } }", "f(",
             "function may finish without returning"),
            ("fn f(): Missing { return 0; }", "Missing", "unknown type"),
            ("let n: Missing;", "Missing", "unknown type"),
            ("fn f(): bool { return; }", "return", "return requires a value"),
        ]
        for body, occurrence, diagnostic in cases:
            with self.subTest(text=body):
                text = "\n" + body
                result = self.invoke(text)
                self.assertEqual((result.returncode, result.stdout), (1, ""))
                self.assertIn(diagnostic, result.stderr)
                offset = text.index(occurrence)
                self.assertIn(f":2:{offset}: byte {offset}:", result.stderr)
                self.assert_syntax_modes_accept(self.syntax_parser, text)

    def test_primitive_type_syntax_errors(self):
        for text in [
            "let flag: = true;", "fn f(): { return true; }",
            "fn f(): bool: int { return true; }",
            "let true = 1;", "fn false() { return 0; }",
        ]:
            with self.subTest(text=text):
                result = self.invoke(text)
                self.assertEqual((result.returncode, result.stdout), (1, ""))
                self.assertIn("parse error", result.stderr)

    def test_object_syntax_is_not_part_of_the_statement_demo(self):
        self.assert_program(
            "let class = 1; let field = 2; let new = 3; let extends = 4; "
            "let constructor = 5; let base = 6; let self = 7; "
            "print class + field + new + extends + constructor + base + self;",
            "28\n",
        )
        for text in [
            "class Box {}", "let b = new Box();", "let b: int; b.x = 1;",
            "let b = 1; print b.x;", "let b = 1; b.f();",
        ]:
            with self.subTest(text=text):
                result = self.invoke(text)
                self.assertEqual((result.returncode, result.stdout), (1, ""))
                self.assertRegex(result.stderr, r"(parse|lex) error")

    def test_malformed_control_flow_has_source_locations_and_no_c(self):
        result = self.invoke(
            (EXAMPLES / "statements/invalid-condition.stmt").read_text(),
        )
        self.assertEqual((result.returncode, result.stdout), (1, ""))
        self.assertEqual(
            result.stderr,
            f"{self.directory / 'source.stmt'}:2:8: byte 18: parse error\n",
        )
        for text in [
            "print 1;\nif () {}", "if (1 <) {}", "while (== 1) {}",
            "while (1 !=) {}", "if (1 < = 2) {}", "if (1 = 2) {}",
            "if (true) print 2;", "while 1 {}", "while (1 {}",
            "if (true) { print 2;", "else {}", "if (true) {} else",
            "let if = 1;", "let else = 1;", "let while = 1;",
        ]:
            with self.subTest(text=text):
                result = self.invoke(text)
                self.assertEqual((result.returncode, result.stdout), (1, ""))
                self.assertRegex(
                    result.stderr, r"source\.stmt:\d+:\d+: byte \d+: parse error",
                )
                syntax = self.parse(self.syntax_parser, text)
                self.assertEqual(syntax.returncode, 1, syntax.stderr)

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
            ("print 2147483648;", 1, 7, 6,
             "integer literal outside int32 range", "2147483648"),
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
            ("let x = ;", "parse error"),
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
        source.write_text(
            "if (unknown < 1) { while (unknown != 2) { { print unknown; } } } "
            "else { print unknown; }",
        )
        result = subprocess.run(
            [str(self.syntax_parser), "--json", str(source)],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        ast = json.loads(result.stdout)
        self.assertEqual(ast["name"], "program")
        self.assertIn("unknown", result.stdout)
        for rule in ("conditional", "loop", "block", "comparison", "equality"):
            self.assertIn(f'"name":"{rule}"', result.stdout.replace(" ", ""))

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

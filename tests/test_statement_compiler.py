"""Visitor scopes, objects/function/control flow, C execution, and syntax parsing."""

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
            "class Box { field flag: bool; "
            "fn show(): bool { println_bool(self.flag); return self.flag; } } "
            "let b = new Box(); b.flag = true; b.show(); "
            "fn show(n: int) { print_int(n); return n; } show(3); "
            "print true; print false;", "-21474836482147483647\nfalsetrue\ntrue\n31\n0\n",
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
            "class Box { field n: int; constructor() { self.n = read_int(); } "
            "fn update() { self.n = read_int(); return self.n; } } "
            "let b = new Box(); print b.n; b.update(); print b.n;",
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
            ("class A {} println_int(new A());", "argument type mismatch"),
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
            "class Box { fn max() { return 3; } } "
            "let b = new Box(); print min(true); print read_int(print_bool); "
            "print println_int(false); println_int(true); print b.max();",
            "1\n4\n0\n3\n",
        )

    def test_int32_boundaries_and_storage(self):
        emitted = self.assert_program(
            "print 2147483647; print -2147483648; print - 0002147483648; "
            "print +2147483647; print +-2147483648; print -(2147483647); "
            "print 0000000000000000000000000000008; "
            "class Box { field n: int; constructor(n) { self.n = n; } "
            "fn read(): int { return self.n; } } "
            "fn identity(n: int): int { return n; } "
            "let b = new Box(identity(-2147483648)); print b.read(); "
            "let x: int = 2147483647; b.n = x; print b.n;",
            "2147483647\n-2147483648\n-2147483648\n2147483647\n"
            "-2147483648\n-2147483647\n8\n-2147483648\n2147483647\n",
        )
        self.assertNotIn("double", emitted)
        self.assertIn("int32_t cpg_field0;", emitted)
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

    def test_object_sample_layout_and_dispatch(self):
        emitted = self.assert_program(
            (EXAMPLES / "statements/objects.stmt").read_text(),
            "0\n15\n15\n4\n3\n4\n",
        )
        self.assertIn(
            "struct cpg_class1 {\n    int32_t cpg_field0;\n"
            "    int32_t cpg_field1;\n};", emitted,
        )
        self.assertIn("int32_t cpg_f0(cpg_class1 *, int32_t);", emitted)
        self.assertIn("int32_t cpg_f0(cpg_class1 *cpg_self, int32_t cpg_v1)", emitted)
        self.assertIn("cpg_require(cpg_self", emitted)
        self.assertIn("))->cpg_field0", emitted)
        self.assertIn("*object = (cpg_class1){0};", emitted)
        self.assertIn("cpg_f1(cpg_require(cpg_v", emitted)
        self.assertIn("atexit(cpg_cleanup)", emitted)
        self.assertLess(emitted.index("struct cpg_class1 {"), emitted.index("int32_t cpg_f0"))
        self.assertLess(emitted.index("int32_t cpg_f0"), emitted.index("int main"))

    def test_objects_forward_calls_alias_rebinding_and_function_locals(self):
        self.assert_program(
            "let x = new Box(); x.value = 7; let y = (x); y.value = 9; "
            "print x.value; print y.value; x = y; y = new Box(); "
            "print x.value; print y.value; print local(3); "
            "class Box { field value: int; "
            "fn first(n) { return self.second(n); } "
            "fn second(n) { self.value = plus(self.value, n); return self.value; } } "
            "fn plus(a, b) { return a + b; } "
            "fn local(n) { let x: Box = new Box(); x.first(n); return x.value; }",
            "9\n9\n9\n0\n3\n",
        )
        self.assert_program(
            "class Box { field x: int; fn reset() { self = new Box(); return 0; } "
            "fn recurse(n) { if (n == 0) { return self.x; } "
            "self.x = self.x + 1; return self.recurse(n - 1); } } "
            "let b = new Box(); print -1; print b.recurse(4); b.reset(); print b.x;",
            "-1\n4\n4\n",
        )
        self.assert_program(
            "class main { field printf: int; fn switch(ignored) { return 1; } } "
            "fn switch() { return 2; } let cpg_object = new main(); "
            "cpg_object.printf = switch(); print cpg_object.printf; "
            "print cpg_object.switch(0);", "2\n1\n",
        )
        self.assert_program(
            "class Empty { fn unused(n) { return n; } } "
            "let e = new Empty(); let copy = e; e = copy;", "",
        )
        self.assert_program("class Empty {}", "")
        self.assert_program(
            "class Box { field x: int; fn combine(Box, other) { "
            "let copy = self; copy.x = Box * 10 + other; self = copy; "
            "return self.x; } } let b = new Box(); "
            "print b.combine(2, 3); print b.x;", "23\n23\n",
        )

    def test_object_metadata_and_local_table_growth(self):
        fields = "".join(f"field x{i}: int;" for i in range(24))
        methods = "".join(f"fn f{i}(n) {{ return self.x{i} + n; }}" for i in range(24))
        locals = "".join(f"let v{i} = {i};" for i in range(24))
        self.assert_program(
            f"class Box {{ {fields} {methods} "
            f"fn local(n) {{ {locals} self.x23 = v23; return self.f23(n); }} }} "
            "let b = new Box(); print b.local(1); print b.x23; print b.f0(2);",
            "24\n23\n2\n",
        )

    def test_multiple_classes_nested_aliases_and_typed_parameters(self):
        emitted = self.assert_program(
            (EXAMPLES / "statements/references.stmt").read_text(),
            "0\n15\n15\n20\n0\n20\n",
        )
        self.assertIn("cpg_class2 * cpg_field0;", emitted)
        self.assertIn("int32_t cpg_f0(cpg_class1 *, cpg_class2 *);", emitted)
        self.assertIn("int32_t cpg_f3(cpg_class1 *, int32_t);", emitted)
        self.assertLess(emitted.index("typedef struct cpg_class2"),
                        emitted.index("struct cpg_class1 {"))
        self.assert_program(
            "class A { field value: int; fn get() { return self.value + 1; } } "
            "class B { field value: int; fn get() { return self.value + 2; } } "
            "fn get(a: A, b: B) { return a.get() + b.get(); } "
            "let a = new A(); let b = new B(); a.value = 10; b.value = 20; "
            "print a.get(); print b.get(); print get(a, b);", "11\n22\n33\n",
        )
        self.assert_program(
            "class Node { field next: Node; field value: int; "
            "fn set(other: Node, n: int) { self.next = other; "
            "self.next.value = n; return self.next.value; } "
            "fn read() { return self.next.next.value; } } "
            "let a = new Node(); let b = new Node(); print a.set(b, 7); "
            "b.next = a; print a.next.next.next.value; print a.read(); "
            "a.next.next.next.value = 9; print b.value; "
            "let alias = a.next; alias.value = 11; print b.value;",
            "7\n7\n0\n9\n11\n",
        )
        self.assert_program(
            "class A { field b: B; fn read() { return self.b.read(); } } "
            "class B { field a: A; fn read() { return self.a.b.value; } field value: int; } "
            "let a = new A(); a.b = new B(); a.b.a = a; a.b.value = 8; "
            "print a.read();", "8\n",
        )
        self.assert_program(
            "class A { field child: A; } "
            "fn unused(reference: A, n: int) { return n; } "
            "let a = new A(); let unassigned = a.child; "
            "print unused(unassigned, 3); unassigned = new A(); "
            "a.child = unassigned;", "3\n",
        )

    def test_reference_parameters_rebind_locally_and_outlive_calls(self):
        self.assert_program(
            "class Box { field child: Box; field value: int; "
            "fn replace(other: Box) { self.child = other; self = new Box(); "
            "self.value = 99; return self.value; } } "
            "fn install(box: Box) { let local = new Box(); local.value = 7; "
            "box.child = local; box = new Box(); box.value = 100; return 0; } "
            "let box = new Box(); print install(box); print box.child.value; "
            "print box.value; let other = new Box(); other.value = 12; "
            "print box.replace(other); print box.child.value; print box.value; "
            "let i = 0; while (i < 3) { let local = new Box(); local.value = i; "
            "box.child = local; i = i + 1; } print box.child.value;",
            "0\n7\n0\n99\n12\n0\n2\n",
        )
        classes = "".join(
            f"class C{i} {{ field value: int; "
            f"fn get(other: C{i}) {{ let local = other; return local.value; }} }}"
            for i in range(24)
        )
        self.assert_program(
            classes + "let last = new C23(); last.value = 23; "
            "print last.get(last);", "23\n",
        )

    def test_class_type_errors_are_semantic_not_syntax(self):
        classes = (
            "class A { field b: B; field value: int; "
            "fn use(other: B) { return other.value; } } "
            "class B { field value: int; fn get() { return self.value; } } "
        )
        for text, diagnostic in [
            ("fn f(x: Missing) { return 0; }", "unknown class type"),
            ("class C { fn f(x: Missing) { return 0; } }", "unknown class type"),
            ("fn f(x: int, x: A) { return 0; }", "duplicate declaration"),
            ("let a: A = new B();", "initializer type mismatch"),
            ("let a = new A(); a = new B();", "assignment type mismatch"),
            ("let a = new A(); a.b = new A();", "field assignment type mismatch"),
            ("let a = new A(); a.b = 0;", "field assignment type mismatch"),
            ("let a = new A(); a.b.value = new B();", "field assignment type mismatch"),
            ("let a = new A(); a.use(new A());", "argument type mismatch"),
            ("let a = new A(); a.use(1);", "argument type mismatch"),
            ("fn f(x: B) { return 0; } print f(new A());", "argument type mismatch"),
            ("fn f(x: B) { return 0; } print f(1);", "argument type mismatch"),
            ("let a = new A(); print a.b.absent;", "unknown field"),
            ("let a = new A(); a.b.absent = 1;", "unknown field"),
            ("let a = new A(); a.b.absent();", "unknown method"),
            ("let a = new A(); a.b.use(new B());", "unknown method"),
            ("let a = new A(); print a.b.get(1);", "method argument count mismatch"),
            ("let a = new A(); print a.value.nope;", "member access requires object"),
            ("let a = new A(); a.value.nope();", "member access requires object"),
            ("let a = new A(); print a.b;", "type mismatch"),
            ("let a = new A(); print a.b + 1;", "type mismatch"),
            ("let a: A; print a.b.value;", "read before definite initialization"),
            ("let a: A; if (true) { a = new A(); } print a.b.value;",
             "read before definite initialization"),
            ("class A {}", "duplicate class"),
            ("class C { field x: B; fn x() { return 0; } }", "duplicate member"),
        ]:
            with self.subTest(text=text):
                source = classes + text
                result = self.invoke(source)
                self.assertEqual((result.returncode, result.stdout), (1, ""))
                self.assertIn(diagnostic, result.stderr)
                self.assert_syntax_modes_accept(self.syntax_parser, source)

    def test_generated_reference_cleanup_and_runtime_errors(self):
        instrumentation = """
static size_t live_allocations, allocation_attempt;
static size_t fail_at;
static void *tracked_malloc(size_t size) {
    void *pointer;
    if (++allocation_attempt == fail_at) return NULL;
    pointer = malloc(size);
    if (pointer) ++live_allocations;
    return pointer;
}
static void tracked_free(void *pointer) {
    if (pointer) --live_allocations;
    free(pointer);
}
static void verify_cleanup(void) {
    if (live_allocations) {
        fputs("object allocations leaked\\n", stderr);
        abort();
    }
}
#define malloc tracked_malloc
#define free tracked_free
"""
        cases = [
            ("class A { field next: A; } let a = new A(); a.next = a; "
             "let i = 0; while (i < 100) { let b = new A(); a.next = b; "
             "b.next = a; i = i + 1; }", 0, "", ""),
            ("class A { field b: B; } class B { field value: int; } "
             "let a = new A(); print a.b.value;", 0, "uninitialized object reference\n", ""),
            ("class A { field b: A; fn f() { return 1; } } "
             "let a = new A(); print a.b.f();", 0, "uninitialized object reference\n", ""),
            ("class A { field b: A; field value: int; } "
             "let a = new A(); a.b.value = 1;", 0, "uninitialized object reference\n", ""),
            ("class A {} let a = new A(); print 1;", 0, "output error\n", "printf"),
            ("class A {} let a = new A();", 0, "output error\n", "fflush"),
        ]
        cases.extend(
            ("class A {} let a = new A(); let b = new A();",
             fail_at, "object allocation failed\n", "") for fail_at in range(1, 5)
        )
        for text, fail_at, error, io_failure in cases:
            with self.subTest(text=text, fail_at=fail_at, io_failure=io_failure):
                emitted = self.invoke(text)
                self.assertEqual((emitted.returncode, emitted.stderr), (0, ""))
                io_instrumentation = ""
                if io_failure == "printf":
                    io_instrumentation = """
static int failing_printf(const char *format, ...) { (void)format; return -1; }
#define printf failing_printf
"""
                elif io_failure == "fflush":
                    io_instrumentation = """
static int failing_fflush(FILE *stream) { (void)stream; return EOF; }
#define fflush failing_fflush
"""
                source = self.directory / "tracked.c"
                source.write_text(
                    emitted.stdout.replace("#include <stdlib.h>\n",
                                           "#include <stdlib.h>\n" + instrumentation
                                           + io_instrumentation, 1)
                    .replace("int main(void) {", "int main(void) {\n"
                             f"    fail_at = {fail_at};\n"
                             "    if (atexit(verify_cleanup)) return 2;", 1)
                )
                program = self.directory / "tracked"
                self.compile_c(source, program)
                result = subprocess.run(
                    [str(program)], capture_output=True, text=True, timeout=30,
                )
                self.assertEqual((result.returncode, result.stdout, result.stderr),
                                 (1 if error or io_failure else 0, "", error))

    def test_object_definite_assignment_and_method_control_flow(self):
        self.assert_program(
            "class Box { field x: int; "
            "fn f(n) { let y; if (n != 0) { y = 3; } else { return self.x; } "
            "while (y < 5) { y = y + 1; } self.x = y; return self.x; } } "
            "let b: Box; if (true) { b = new Box(); } else { b = new Box(); } "
            "print b.f(1); print b.f(0); "
            "let i = 0; while (i < 2) { let c = new Box(); "
            "print c.x; c.x = 99; i = i + 1; }",
            "5\n5\n0\n0\n",
        )
        self.assert_program(
            "class Box { field x: int; } fn f(n) { let b: Box; "
            "if (n != 0) { return 7; } else { b = new Box(); } return b.x; } "
            "print f(0); print f(1);", "0\n7\n",
        )

    def test_constructors_initialize_fields_and_preserve_reference_semantics(self):
        self.assert_program(
            (EXAMPLES / "statements/constructors.stmt").read_text(),
            "7\n6\n6\n3\n",
        )
        self.assert_program(
            "class Seed { field value: int; "
            "constructor(start: int) { self.value = start; } } "
            "class Box { field seed: Seed; field total: int; "
            "constructor(seed: Seed, scale: int) { "
            "let initial = seed.value * scale; self.seed = seed; "
            "self.total = initial; } "
            "fn update(amount: int) { self.total = self.total + amount; "
            "return self.total; } } "
            "let seed = new Seed(4); let box = new Box(seed, 3); "
            "let alias = box; print box.seed.value; print alias.update(2); "
            "print box.total; let zero = new Seed(0); print zero.value;",
            "4\n14\n14\n0\n",
        )

    def test_method_early_returns_nested_control_flow_and_receiver_mutation(self):
        self.assert_program(
            "class Counter { field value: int; "
            "constructor(start: int) { self.value = start; } "
            "fn advance(count: int) { let i = 0; "
            "if (count < 0) { if (self.value > 0) { "
            "self.value = self.value - 1; return self.value; } "
            "else { return 99; } } "
            "while (i < count) { self.value = self.value + 1; "
            "i = i + 1; } return self.value; } } "
            "let counter = new Counter(5); "
            "print counter.advance(2); print counter.advance(-1); "
            "print counter.value;",
            "7\n6\n6\n",
        )

    def test_object_semantic_errors_and_syntax_only_acceptance(self):
        box = "class Box { field x: int; fn add(n) { return n; } } "
        for text, diagnostic in [
            ("let b = new Missing();", "unknown class"),
            ("let b: Missing;", "unknown class"),
            ("class A {} class A {}", "duplicate class"),
            ("class A { field x: int; field x: int; }", "duplicate member"),
            ("class A { field x: Missing; }", "unknown class type"),
            ("class A { constructor(value: Missing) {} }", "unknown class type"),
            ("class A { constructor() {} constructor(value: int) {} }",
             "duplicate constructor"),
            ("class A { field value: int; constructor() { let local; "
             "self.value = local; } }", "read before definite initialization"),
            ("class A { field value: int; constructor(flag: int) { let local; "
             "if (flag != 0) { local = 1; } self.value = local; } }",
             "read before definite initialization"),
            ("class A { constructor() { return 1; } }",
             "return is not allowed in a constructor"),
            ("class A { constructor() { return; } }",
             "return is not allowed in a constructor"),
            ("class A { constructor(value: int) { self.missing = value; } }",
             "unknown field"),
            ("class A { field value: int; constructor(value: int) { "
             "self.value = value; } } let a = new A();",
             "constructor argument count mismatch"),
            ("class A { field value: int; constructor(value: int) { "
             "self.value = value; } } let a = new A(1, 2);",
             "constructor argument count mismatch"),
            ("class A { field value: int; constructor(value: int) { "
             "self.value = value; } } class B {} let a = new A(new B());",
             "argument type mismatch"),
            ("class int {}", "class name conflicts with integer type"),
            ("class A { fn x() { return 1; } fn x() { return 2; } }",
             "duplicate member"),
            ("class A { fn x() { return 1; } field x: int; }", "duplicate member"),
            ("class A { fn f(self) { return 1; } }", "duplicate declaration"),
            ("class A { fn f() { let self = 1; return 1; } }",
             "duplicate declaration"),
            (box + "let b = new Box(); print b.missing;", "unknown field"),
            (box + "let b = new Box(); b.missing = 1;", "unknown field"),
            (box + "let b = new Box(); b.missing();", "unknown method"),
            (box + "let b = new Box(); print b.x();", "unknown method"),
            (box + "let b = new Box(); print b.add;", "unknown field"),
            (box + "let b = new Box(); b.add();", "method argument count mismatch"),
            (box + "let b = new Box(); b.add(1, 2);", "method argument count mismatch"),
            (box + "let b = new Box(); b.add(b);", "type mismatch"),
            (box + "let b = 1; print b.x;", "member access requires object"),
            (box + "let b = 1; b.add(2);", "member access requires object"),
            (box + "let b = 1; b.x = 2;", "member access requires object"),
            (box + "let b = new Box(); b.x = b;", "type mismatch"),
            (box + "let b: Box = 1;", "initializer type mismatch"),
            (box + "let b = new Box(); b = 1;", "assignment type mismatch"),
            (box + "let b = 1; b = new Box();", "assignment type mismatch"),
            (box + "let b = new Box(); print b;", "type mismatch"),
            (box + "if (new Box()) {}", "type mismatch"),
            (box + "while (new Box()) {}", "type mismatch"),
            (box + "print -new Box();", "type mismatch"),
            (box + "print 1 + new Box();", "type mismatch"),
            (box + "print new Box() * 1;", "type mismatch"),
            (box + "print new Box() == new Box();", "type mismatch"),
            (box + "fn f(x) { return x; } print f(new Box());", "type mismatch"),
            (box + "fn f() { return new Box(); }", "type mismatch"),
            (box + "let b: Box; print b.x;", "read before definite initialization"),
            (box + "let b: Box; b.x = 1;", "read before definite initialization"),
            (box + "let b: Box; b.add(1);", "read before definite initialization"),
            (box + "let b: Box; if (true) { b = new Box(); } print b.x;",
             "read before definite initialization"),
            (box + "let b: Box; while (false) { b = new Box(); } print b.x;",
             "read before definite initialization"),
            (box + "let b = new Box(); let b: Box;", "duplicate declaration"),
            (box + "let b: Box = b;", "use before declaration"),
            (box + "let b = new Box(); fn f() { return b.x; }", "use before declaration"),
            (box + "print self.x;", "use before declaration"),
            (box + "fn f() { return self.x; }", "use before declaration"),
            (box + "print add(1);", "unknown function"),
            ("let global = 1; class Box { fn f() { return global; } }",
             "use before declaration"),
            ("class Box { field x: int; fn f() { return x; } }", "use before declaration"),
            ("class Box { fn f() { return self; } }", "type mismatch"),
            ("class Box { fn f() { return self.g(); } "
             "fn g() { return n; } }", "use before declaration"),
            ("class Box { fn f() { let n; return n; } }",
             "read before definite initialization"),
            ("class Box { fn f() {} }", "function may finish without returning"),
        ]:
            with self.subTest(text=text):
                result = self.invoke(text)
                self.assertEqual((result.returncode, result.stdout), (1, ""))
                self.assertIn(diagnostic, result.stderr)
                self.assertRegex(result.stderr, r"source\.stmt:1:\d+: byte \d+:")
                self.assert_syntax_modes_accept(self.syntax_parser, text)

    def test_object_errors_have_exact_locations(self):
        for text, occurrence, name, diagnostic in [
            ("class Box { field x: int; }\nlet b = new Missing();", "Missing",
             "Missing", "unknown class"),
            ("class Box { field x: int; }\nlet b = new Box();\nprint b.absent;",
             "absent", "absent", "unknown field"),
            ("class Box { fn f(x) { return x; } }\nlet b = new Box();\nb.f();",
             "f();", "f", "method argument count mismatch"),
            ("class Box {\nfield x: int;\nfield x: int;\n}", "x: int;\n}",
             "x", "duplicate member"),
            ("class Box {}\nlet b: Box = 1;", "b:", "b", "initializer type mismatch"),
            ("let n = 1;\nprint n.x;", "n.x", "n", "member access requires object"),
            ("class Box {}\nfn f(box: Missing) { return 0; }", "Missing",
             "Missing", "unknown class type"),
            ("class Box { field child: Box; }\nlet b = new Box();\nprint b.child.absent;",
             "absent", "absent", "unknown field"),
        ]:
            with self.subTest(text=text):
                offset = text.index(occurrence)
                line = text.count("\n", 0, offset) + 1
                column = offset - text.rfind("\n", 0, offset)
                result = self.invoke(text)
                self.assertEqual((result.returncode, result.stdout), (1, ""))
                self.assertEqual(
                    result.stderr, f"{self.directory / 'source.stmt'}:{line}:{column}: "
                    f"byte {offset}: {diagnostic}: '{name}'\n",
                )

    def test_object_syntax_errors(self):
        for text in [
            "class Box { field x int; }", "class Box { field x: int }",
            "class Box { let x = 1; }", "class Box { class Nested {} }",
            "fn f() { class Box {} return 1; }", "let b = new Box(1,);",
            "class Box {};", "let b = new Box;", "print b.;",
            "let class = 1;", "let field = 1;", "let new = 1;",
        ]:
            with self.subTest(text=text):
                result = self.invoke(text)
                self.assertEqual((result.returncode, result.stdout), (1, ""))
                self.assertIn("parse error", result.stderr)

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
            "class Box { field x: Unknown; } let b = new Missing();",
            "class Box { fn f(self) { return absent; } }",
            "class Box { field x: int; } let b: Box; b.missing = new Box();",
            "class A { field b: B; } class B {} "
            "fn f(x: Unknown) { return x.absent.value; }",
            "class A {} class B {} let a: A = new B();",
            "class A { field b: A; fn f(x: A) { return 0; } } "
            "let a = new A(); a.b.f(1, 2);",
            "class A { field value: int; constructor(value: int) { "
            "self.value = value; return 1; } } let a = new A(1);",
            "class A { field value: int; constructor(value: int) { "
            "self.value = value; } } let a = new A(new A(1));",
            "let flag: bool = 1; if (3) { print flag + true; }",
            "fn f(n: bool): bool { return 1; } print f(2);",
            "class A { field flag: bool; constructor(flag: bool) { "
            "self.flag = 3; } fn f(): bool { return self.flag; } } "
            "let a = new A(1); a.flag = 2;",
        ]:
            with self.subTest(text=text):
                self.assert_syntax_modes_accept(parser, text, json_mode=False)

    def test_primitive_types_sample_and_lowering(self):
        emitted = self.assert_program(
            (EXAMPLES / "statements/types.stmt").read_text(),
            "0\n1\n3\n1\n0\n7\n",
        )
        self.assertIn("_Bool cpg_field1;", emitted)
        self.assertIn("_Bool cpg_f1(cpg_class1 *, _Bool);", emitted)
        self.assertIn("void cpg_f0(cpg_class1 *, int32_t, _Bool);", emitted)
        self.assertIn("_Bool cpg_v", emitted)
        self.assertIn("cpg_class1 * cpg_f", emitted)

    def test_typed_returns_forward_recursion_and_reference_aliases(self):
        self.assert_program(
            "print even(6); print even(5); "
            "fn even(n: int): bool { if (n == 0) { return true; } "
            "return odd(n - 1); } "
            "fn odd(n: int): bool { if (n == 0) { return false; } "
            "return even(n - 1); } "
            "class Box { field flag: bool; field value: int; "
            "constructor(flag: bool) { self.flag = flag; } "
            "fn alias(): Box { return self; } "
            "fn choose(other: Box, useSelf: bool): Box { "
            "if (useSelf) { return self; } else { return other; } } } "
            "fn identity(box: Box): Box { return box.alias(); } "
            "let a: Box = new Box(true); let b = new Box(false); "
            "let chosen = a.choose(b, false); chosen.value = 7; "
            "let copy = identity(a); copy.flag = false; "
            "print a.flag; print b.value; print chosen.flag;",
            "1\n0\n0\n7\n0\n",
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

    def test_primitive_defaults_nested_fields_and_constructor_calls(self):
        self.assert_program(
            "class Flags { field enabled: bool; field count: int; } "
            "class Holder { field flags: Flags; "
            "constructor(flags: Flags, enabled: bool) { "
            "self.flags = flags; self.flags.enabled = enabled; } "
            "fn toggle(): bool { self.flags.enabled = self.flags.enabled == false; "
            "return self.flags.enabled; } } "
            "fn create(): Flags { return new Flags(); } "
            "let flags: Flags = create(); print flags.enabled; print flags.count; "
            "let holder = new Holder(flags, 1 < 2); "
            "print flags.enabled; print holder.toggle(); print flags.enabled; "
            "let ready: bool; ready = holder.flags.enabled != true; print ready; "
            "let count: int; count = 000008; print count; "
            "print true; print false; print (1 < 2) != (3 < 4);",
            "0\n0\n1\n0\n0\n1\n8\n1\n0\n0\n",
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
            ("class A { field flag: bool; constructor(flag: bool) {} } "
             "let a = new A(1);", "1);", "argument type mismatch"),
            ("class A { constructor(flag: bool) {} } let a = new A(true, false);",
             "A(true", "constructor argument count mismatch"),
            ("class A { field flag: bool; } let a = new A(); a.flag = 1;",
             "a.flag", "field assignment type mismatch"),
            ("class A { field n: int; } let a = new A(); a.n = false;",
             "a.n", "field assignment type mismatch"),
            ("class A { field flag: bool; constructor() { self.flag = 0; } }",
             "self.flag", "field assignment type mismatch"),
            ("class A { fn f(flag: bool): bool { return flag; } } "
             "let a = new A(); print a.f(1);", "1);", "argument type mismatch"),
            ("class A { fn f(): bool { return true; } } let a = new A(); "
             "let n: int = a.f();", "n:", "initializer type mismatch"),
            ("class A { fn f(): bool { return 0; } }", "0;", "return type mismatch"),
            ("let flag = true; print flag.nope;", "flag.nope",
             "member access requires object"),
            ("let flag = false; flag.nope();", "flag.nope",
             "member access requires object"),
            ("let flag: bool; print flag;", "flag;", "read before definite initialization"),
            ("let flag: bool; if (true) { flag = true; } print flag;",
             "flag;", "read before definite initialization"),
            ("let flag: bool; while (true) { flag = false; } print flag;",
             "flag;", "read before definite initialization"),
            ("fn f(flag: bool): bool { if (flag) { return true; } }", "f(",
             "function may finish without returning"),
            ("fn f(): bool { while (true) { return false; } }", "f(",
             "function may finish without returning"),
            ("fn f(): Missing { return 0; }", "Missing", "unknown class type"),
            ("class bool {}", "bool", "class name conflicts with boolean type"),
            ("class A {} fn f(): A { return false; }", "false", "return type mismatch"),
            ("class A {} class B {} fn f(): A { return new B(); }",
             "new B", "return type mismatch"),
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
            "class A { constructor(): bool {} }",
            "let true = 1;", "fn false() { return 0; }",
        ]:
            with self.subTest(text=text):
                result = self.invoke(text)
                self.assertEqual((result.returncode, result.stdout), (1, ""))
                self.assertIn("parse error", result.stderr)

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

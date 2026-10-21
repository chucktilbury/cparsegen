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

    def test_object_sample_layout_and_dispatch(self):
        emitted = self.assert_program(
            (EXAMPLES / "statements/objects.stmt").read_text(),
            "0\n15\n15\n4\n3\n4\n",
        )
        self.assertIn(
            "struct cpg_class1 {\n    double cpg_field0;\n"
            "    double cpg_field1;\n};", emitted,
        )
        self.assertIn("double cpg_f0(cpg_class1 *, double);", emitted)
        self.assertIn("double cpg_f0(cpg_class1 *cpg_self, double cpg_v1)", emitted)
        self.assertIn("cpg_require(cpg_self", emitted)
        self.assertIn("))->cpg_field0", emitted)
        self.assertIn("*object = (cpg_class1){0};", emitted)
        self.assertIn("cpg_f1(cpg_require(cpg_v", emitted)
        self.assertIn("atexit(cpg_cleanup)", emitted)
        self.assertLess(emitted.index("struct cpg_class1 {"), emitted.index("double cpg_f0"))
        self.assertLess(emitted.index("double cpg_f0"), emitted.index("int main"))

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
        self.assertIn("double cpg_f0(cpg_class1 *, cpg_class2 *);", emitted)
        self.assertIn("double cpg_f3(cpg_class1 *, double);", emitted)
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
            ("let a: A; if (1) { a = new A(); } print a.b.value;",
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
            ("class A {} let a = new A(); print 1;", 0, "", "printf"),
            ("class A {} let a = new A();", 0, "", "fflush"),
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
            "fn f(n) { let y; if (n) { y = 3; } else { return self.x; } "
            "while (y < 5) { y = y + 1; } self.x = y; return self.x; } } "
            "let b: Box; if (1) { b = new Box(); } else { b = new Box(); } "
            "print b.f(1); print b.f(0); "
            "let i = 0; while (i < 2) { let c = new Box(); "
            "print c.x; c.x = 99; i = i + 1; }",
            "5\n5\n0\n0\n",
        )
        self.assert_program(
            "class Box { field x: int; } fn f(n) { let b: Box; "
            "if (n) { return 7; } else { b = new Box(); } return b.x; } "
            "print f(0); print f(1);", "0\n7\n",
        )

    def test_object_semantic_errors_and_syntax_only_acceptance(self):
        box = "class Box { field x: int; fn add(n) { return n; } } "
        for text, diagnostic in [
            ("let b = new Missing();", "unknown class"),
            ("let b: Missing;", "unknown class"),
            ("class A {} class A {}", "duplicate class"),
            ("class A { field x: int; field x: int; }", "duplicate member"),
            ("class A { field x: Missing; }", "unknown class type"),
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
            (box + "let b: Box; if (1) { b = new Box(); } print b.x;",
             "read before definite initialization"),
            (box + "let b: Box; while (0) { b = new Box(); } print b.x;",
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
            "fn f() { class Box {} return 1; }", "let b = new Box(1);",
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
        self.assertLess(emitted.index("double cpg_f0(double);"),
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
            f"fn local(n) {{ if (n) {{ {declarations} return x23; }} "
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
            ("fn f(n) { let x; if (n) { return 10; } else { x = 20; } "
             "return x; } print f(1); print f(0);", "10\n20\n"),
            ("fn f(n) { let x; if (n) { x = 20; } else { return 10; } "
             "return x; } print f(1); print f(0);", "20\n10\n"),
            ("fn f(n) { while (n > 0) { if (n == 2) { return n; } "
             "n = n - 1; } return 0; } print f(3); print f(0);", "2\n0\n"),
            ("fn f(n) { if (n) { { return -n; } } return n + 1; } "
             "print f(2); print f(0);", "-2\n1\n"),
            ("fn f(n) { let x; if (n) { x = 1; } else { x = 2; } "
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
            ("if (0) { return; }", "return outside function", "return"),
            ("fn f() { return; }", "return requires a value", "return"),
            ("fn f() {}", "function may finish without returning a value", "f"),
            ("fn f(x) { if (x) { return 1; } }",
             "function may finish without returning a value", "f"),
            ("fn f() { while (1) { return 1; } }",
             "function may finish without returning a value", "f"),
            ("fn f() { let x; return x; }", "read before definite initialization", "x"),
            ("fn f() { let x; return g(x); } fn g(x) { return x; }",
             "read before definite initialization", "x"),
            ("fn f(n) { let x; if (n) { x = 1; } return x; }",
             "read before definite initialization", "x"),
            ("fn f(n) { let x; while (n) { x = 1; n = 0; } return x; }",
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
            ("fn f() { return 1234567890; }", "integer literal exceeds nine digits",
             "1234567890"),
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
            "print 1 + 2 * 3 < 8 == 1; print 0 == 2 < 1; "
            "print (2 < 3) + (4 >= 4) * 2; print -2 < -1; "
            "print 3 > 2 > 1; print 2 == 2 == 1;", "1\n1\n3\n1\n0\n1\n",
        )
        self.assert_program(
            "let flag = 2 < 3; while (flag) { print flag; flag = 2 != 2; } "
            "if (flag) { print 99; } else { print flag; }", "1\n0\n",
        )

    def test_branches_nested_blocks_and_truthiness(self):
        self.assert_program(
            "let x = 0; if (1) { x = 1; } else { x = 99; } print x; "
            "if (0) { x = 99; } else { x = 2; } print x; "
            "if (0) { print 99; } if (-2) { { print 3; } } "
            "if (1) { if (0) { print 99; } else { print 4; } } "
            "else { print 99; } { { x = 5; } } print x; "
            "if (1) {} else {} {}",
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
            "print i; while (0) {}",
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
            "if (0) { let skipped = 9; } skipped = x; print skipped; "
            "if (0) { let shared = 8; } else { shared = x + 1; } print shared; "
            "while (0) { let never = 7; } never = 4; print never; "
            "let i = 0; while (i < 2) { let local = i; print local; i = i + 1; } "
            "local = i; print local;", "2\n2\n3\n4\n0\n1\n2\n",
        )
        for text, diagnostic in [
            ("{ let x = 1; } let x = 2;", "duplicate declaration"),
            ("if (1) { let x = 1; } else { let x = 2; }", "duplicate declaration"),
            ("if (0) { print missing; }", "use before declaration"),
            ("while (missing < 1) {}", "use before declaration"),
            ("if (missing) {}", "use before declaration"),
            ("if (0) {} else { missing = 1; }", "assignment to unknown name"),
            ("while (0) { let x = x; }", "use before declaration"),
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
            ("let x; if (1) { x = 2; } else { x = 3; } print x;", "2\n"),
            ("let x; if (0) { x = 2; } else { x = 3; } print x;", "3\n"),
            ("let x = 1; if (0) { x = 2; } print x; "
             "while (0) { x = 3; } print x;", "1\n1\n"),
            ("if (0) { let x = 2; } else { x = 3; } print x;", "3\n"),
            ("if (1) { let x = 2; } else { x = 3; } print x;", "2\n"),
            ("let x; if (1) { if (0) { x = 1; } else { x = 2; } } "
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
            ("let x; if (0) { let y = 1; x = y; } "
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
            ("let x; if (x) {}", "x)"),
            ("let x; while (x < 1) {}", "x <"),
            ("let x; let y = x;", "x;"),
            ("let x; x = x + 1;", "x +"),
            ("let x; let y; y = x;", "x;"),
            ("let x;\nprint x;", "x;"),
            ("let x; if (1) { x = 1; } print x;", "x;"),
            ("let x; if (0) {} else { x = 1; } print x;", "x;"),
            ("let x; if (1) { x = 1; } else { print x; }", "x;"),
            ("let x; if (1) { print x; } else { x = 1; }", "x;"),
            ("if (0) { let x = 1; } print x;", "x;"),
            ("if (1) {} else { let x = 1; } print x;", "x;"),
            ("if (1) { let x = 1; } else { print x; }", "x;"),
            ("let x; if (1) { if (1) { x = 1; } } else { x = 2; } print x;",
             "x;"),
            ("let x; while (0) { x = 1; } print x;", "x;"),
            ("let x; while (1) { x = 1; } print x;", "x;"),
            ("while (0) { let x = 1; } print x;", "x;"),
            ("let x; while (0) { print x; x = 1; }", "x;"),
            ("let x; while (0) { if (1) { x = 1; } print x; }", "x;"),
            ("let x; while (0) { while (0) { x = 1; } print x; }", "x;"),
            ("let x; if (1) { while (0) { x = 1; } } "
             "else { x = 2; } print x;", "x;"),
            ("let x; if (0) { x = 1; } else { let y = x; }", "x;"),
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
            f"if (0) {{ {declarations} }} else {{ {assignments} }} print x23;",
            "24\n",
        )
        result = self.invoke(f"while (0) {{ {declarations} }} print x23;")
        self.assertEqual((result.returncode, result.stdout), (1, ""))
        self.assertIn("read before definite initialization: 'x23'", result.stderr)

    def test_cwhip_parser_remains_syntax_only(self):
        parser = self.compile_grammar(
            (EXAMPLES / "statements.cpg").read_text(), backend="cwhip",
        )
        for text in [
            "let x; print x;",
            "let x; if (1) { x = 1; } print x;",
            "let x; while (0) { x = 1; } print x;",
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
        ]:
            with self.subTest(text=text):
                self.assert_syntax_modes_accept(parser, text, json_mode=False)

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
            "if (1) print 2;", "while 1 {}", "while (1 {}",
            "if (1) { print 2;", "else {}", "if (1) {} else",
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

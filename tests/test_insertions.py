"""Opaque insertion collection, validated seams, and real target consumers."""

import subprocess

from generator_support import GeneratorTestCase, ROOT, c_compile_command


BOUNDARIES = (
    "file_pre", "imports", "declarations", "ast_pre", "ast_post",
    "scanner_pre", "scanner_post", "parser_pre", "parser_post",
    "visitor_pre", "visitor_post", "file_post",
)
ORDINARY = b'WORD = [a-z]+\nentry : WORD ;\n'
EXAMPLE = ROOT / "examples/insertion"


class InsertionTests(GeneratorTestCase):
    def invoke(self, text, backend, library=False):
        grammar = self.directory / "input.cpg"
        grammar.write_bytes(text)
        self.generated = self.directory / ("parser.c" if backend == "c" else "parser.cw")
        return subprocess.run(
            [str(self.generator),
             *(["--target", "c"] if backend == "c" else
               ["--library"] if library else []),
             str(grammar), str(self.generated), "--dot", str(self.graph)],
            capture_output=True, text=True, timeout=60,
        )

    def compiled(self, source, backend, name="consumer"):
        executable = self.directory / name
        command = (c_compile_command(source, executable) if backend == "c" else
                   [str(self.compiler), str(source), "-o", str(executable)])
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return executable

    def test_byte_preservation_and_target_filtering(self):
        body = (
            b"\r\n\t/* }; @include missing; \xc3\xa9 */\r\n"
            b'const char *text = "}; \\"quoted\\" \\\\ {";\r\n'
            b"char close = '}'; char quote = '\\'';\r\n"
            b"// }; { unmatched braces in a comment\r\n"
            b"void helper(void) { if (1) { /* } */ ; } }\r\n"
            b"#define VALUE { 1, 2 }\r\n  "
        )
        for backend in ("c", "cwhip"):
            other = "cwhip" if backend == "c" else "c"
            with self.subTest(backend=backend):
                result = self.invoke(
                    ORDINARY + f"@insert {backend} file_post {{".encode() + body +
                    b"} /* grammar trivia */ ;\n" +
                    f"@insert {other} file_post {{ OTHER_TARGET_ONLY; }};\n".encode(),
                    backend,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                output = self.generated.read_bytes()
                self.assertIn(b"\n" + body + b"\n", output)
                self.assertEqual(output.count(body), 1)
                self.assertNotIn(b"OTHER_TARGET_ONLY", output)
                # No insertion bytes enter DOT or the scanner token tables.
                self.assertNotIn(body, self.graph.read_bytes())

    def test_exact_placement_all_seams_cli_and_library(self):
        for backend in ("c", "cwhip"):
            for library in (False, True):
                with self.subTest(backend=backend, library=library):
                    text = ORDINARY + b"".join(
                        f"@insert {backend} {point} {{ /* inserted:{point} */ }};\n".encode()
                        for point in reversed(BOUNDARIES)
                    )
                    result = self.invoke(text, backend, library)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    output = self.generated.read_text()

                    def block(point):
                        marker = f"/* inserted:{point} */"
                        self.assertEqual(output.count(marker), 1)
                        return output.index(marker)

                    if backend == "c":
                        order = (
                            block("file_pre"), output.index("/* Generated"),
                            output.index("#include <setjmp.h>"), block("imports"),
                            block("declarations"), output.index("typedef struct { int first"),
                            block("ast_pre"), output.index("typedef struct Node Node;"),
                            output.index("struct Node {"), block("ast_post"),
                            output.index("} Context;"), block("visitor_pre"),
                            output.index("typedef enum { CPG_ERROR"), block("visitor_post"),
                            block("scanner_pre"), output.index("static void report("),
                            output.index("static int scan("), block("scanner_post"),
                            block("parser_pre"), output.index("static void add("),
                            output.index("const Node *cpg_parse("), block("parser_post"),
                            output.index("int main("), block("file_post"),
                        )
                    else:
                        order = (
                            block("file_pre"), output.index("import system as Sys"),
                            block("imports"), block("declarations"),
                            output.index("class LexToken"), block("ast_pre"),
                            output.index("class AstNode"), block("ast_post"),
                            block("scanner_pre"), output.index("class ScanRange"),
                            output.index("class InputScanner"), block("scanner_post"),
                            block("parser_pre"), output.index("class ParserExpr"),
                            output.index("class GeneratedParser"), block("parser_post"),
                            block("visitor_pre"), output.index("class GeneratedVisitor"),
                            block("visitor_post"),
                            *(() if library else (output.index("\nstart {"),)),
                            block("file_post"),
                        )
                        self.assertEqual("\nstart {" in output, not library)
                    self.assertEqual(tuple(sorted(order)), order)
                    if backend == "c" and library:
                        app = self.directory / "app.c"
                        app.write_text(
                            '#define CPARSEGEN_NO_MAIN\n#include "parser.c"\n'
                            'int main(void) { return 0; }\n'
                        )
                        executable = self.compiled(app, backend)
                        result = subprocess.run(
                            [str(executable)], capture_output=True, text=True, timeout=30,
                        )
                        self.assertEqual((result.returncode, result.stdout, result.stderr),
                                         (0, "", ""))
                    elif library:
                        app = self.directory / "app.cw"
                        app.write_text(
                            'include "parser.cw"\nstart {\n'
                            'InputScanner scanner("alpha")\n'
                            'if (!scanner.scan()) { Sys.Process().exit(10) }\n'
                            'GeneratedParser parser(scanner.tokens)\n'
                            'AstNode root = parser.parseAll()\n'
                            'if (root == null || !root.render().equals("entry(WORD(alpha))")) '
                            '{ Sys.Process().exit(11) }\n}\n'
                        )
                        executable = self.compiled(app, backend)
                        result = subprocess.run(
                            [str(executable)], capture_output=True, text=True, timeout=30,
                        )
                        self.assertEqual((result.returncode, result.stdout, result.stderr),
                                         (0, "", ""))
                    elif not library:
                        executable = self.compiled(self.generated, backend)
                        parsed = self.parse(executable, "alpha")
                        self.assertEqual(parsed.returncode, 0, parsed.stdout + parsed.stderr)
                        self.assertEqual(parsed.stdout, "entry(WORD(alpha))\n")

    def test_nested_includes_order_and_non_insertion_contracts(self):
        child = self.directory / "child.cpg"
        leaf = self.directory / "leaf.cpg"
        for backend in ("c", "cwhip"):
            def insertion(label):
                return f"@insert {backend} declarations {{ /* {label} */ }};\n".encode()

            child.write_bytes(insertion("child-before") + b'@include leaf.cpg;\n' +
                              insertion("child-after"))
            leaf.write_bytes(insertion("leaf"))
            result = self.invoke(
                insertion("root-before") + b'@include child.cpg;\n' +
                b'@include leaf.cpg;\n' + insertion("root-after") +
                b'@note @insert does not parse { unclosed;\n' + ORDINARY, backend,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            included = self.generated.read_bytes()
            graph = self.graph.read_bytes()
            labels = ("root-before", "child-before", "leaf", "child-after", "root-after")
            indices = [included.index(f"/* {label} */".encode()) for label in labels]
            self.assertEqual(indices, sorted(indices))
            self.assertEqual(included.count(b"/* leaf */"), 1)
            result = self.invoke(b"".join(insertion(label) for label in labels) +
                                 b'@note @insert does not parse { unclosed;\n' + ORDINARY,
                                 backend)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.generated.read_bytes(), included)
            self.assertEqual(self.graph.read_bytes(), graph)
            # Blocks for the other target must not change even a byte of output.
            result = self.invoke(ORDINARY, backend)
            self.assertEqual(result.returncode, 0, result.stderr)
            ordinary = self.generated.read_bytes()
            other = "c" if backend == "cwhip" else "cwhip"
            result = self.invoke(ORDINARY +
                                 f"@insert {other} file_pre {{ unused; }};".encode(), backend)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.generated.read_bytes(), ordinary)
            self.assertEqual(self.graph.read_bytes(), graph)

    def test_malformed_blocks_and_invalid_contracts_before_output_open(self):
        cases = [
            (b"@insert;", "requires TARGET BOUNDARY"),
            (b"@insert c;", "requires TARGET BOUNDARY"),
            (b"@insert c file_pre extra {};", "requires TARGET BOUNDARY"),
            (b'@insert "c" file_pre {};', "requires TARGET BOUNDARY"),
            (b"@insert cpp file_pre {};", "unknown @insert target cpp"),
            (b"@insert c unknown {};", "unknown @insert boundary unknown"),
            (b"@insert cwhip unknown {};", "unknown @insert boundary unknown"),
            (b"@insert c file_pre {", "unterminated @insert block"),
            (b"@insert c file_pre { { }", "unterminated @insert block"),
            (b'@insert c file_pre { "};', "unterminated @insert quoted literal"),
            (b'@insert c file_pre { "tail\\', "unterminated @insert quoted literal"),
            (b"@insert c file_pre { '};", "unterminated @insert quoted literal"),
            (b'@insert c file_pre { "bad\n"; };', "unterminated @insert quoted literal"),
            (b"@insert c file_pre { /* };", "unterminated @insert block comment"),
            (b"@insert c file_pre { // };", "unterminated @insert block"),
            (b"@insert c file_pre {}", "block must end with ';'"),
            (b"@insert c file_pre {} extra;", "block must end with ';'"),
            (b"@insert c file_pre { \x00 };", "forbids NUL"),
            (b"@insert c file_pre { // \\\n };", "backslash-newline"),
            (b'@insert c file_pre { "\\\\\n" };', "backslash-newline"),
            (b"@insert c file_pre { /* \\\r\n */ };", "backslash-newline"),
            (b"@insert c file_pre { // ??/\n };", "trigraph prefixes"),
            (b'@insert c file_pre { "\\??/"; };', "trigraph prefixes"),
            (b'entry : @insert c file_pre {}; WORD ;', "unsupported parser-expression"),
            (b'WORD = "a" @insert c file_pre {};', "unsupported lexer expression"),
        ]
        for backend in ("c", "cwhip"):
            self.generated = self.directory / ("parser.c" if backend == "c" else "parser.cw")
            for invalid, message in cases:
                with self.subTest(backend=backend, invalid=invalid):
                    for existing in (False, True):
                        for path in (self.generated, self.graph):
                            path.unlink(missing_ok=True)
                            if existing:
                                path.write_bytes(b"preserve existing output")
                        result = self.invoke(ORDINARY + invalid, backend)
                        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                        self.assertIn(message, result.stderr)
                        self.assertIn(":3:", result.stderr)
                        for path in (self.generated, self.graph):
                            if existing:
                                self.assertEqual(path.read_bytes(), b"preserve existing output")
                            else:
                                self.assertFalse(path.exists())

    def test_nested_source_diagnostics(self):
        main = self.directory / "input.cpg"
        child = self.directory / "child.cpg"
        leaf = self.directory / "leaf.cpg"
        child.write_text("\n@include leaf.cpg;\n")
        for invalid, line, message in [
            ("\n@insert c invalid {};", 2, "unknown @insert boundary"),
            ("\n@insert python imports {};", 2, "unknown @insert target"),
            ("\n@insert c file_post {\n /* unclosed", 3, "unterminated @insert block comment"),
            ('\n@insert c file_post {\n "unclosed', 3, "unterminated @insert quoted literal"),
            ("\n@insert c file_post {\n { }", 2, "unterminated @insert block"),
        ]:
            leaf.write_text(invalid)
            for backend in ("c", "cwhip"):
                result = self.invoke(ORDINARY + b'@include child.cpg;\n', backend)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn(f"{leaf}:{line}:", result.stderr)
                self.assertIn(message, result.stderr)
                self.assertIn(f"included from {child}:2:", result.stderr)
                self.assertIn(f"included from {main}:3:", result.stderr)

    def test_collection_limits(self):
        for backend in ("c", "cwhip"):
            for body, message in [
                (b" " * 1048576, None),
                (b" " * 1048577, "exceeds 1048576 bytes"),
                (b" " * (1048576 - 4) + b"/* */", "exceeds 1048576 bytes"),
                (b"{" * 255 + b"}" * 255, None),
                (b"{" * 256 + b"}" * 256, "nesting exceeds 256"),
            ]:
                with self.subTest(backend=backend, size=len(body), message=message):
                    result = self.invoke(ORDINARY + b"@insert c file_post {" + body + b"};", backend)
                    self.assertEqual(result.returncode, 1 if message else 0, result.stderr)
                    if message:
                        self.assertIn(message, result.stderr)

    def test_native_includes_are_target_code_not_grammar_includes(self):
        (self.directory / "native.h").write_text(
            "#define INSERTED_VALUE 37\n"
        )
        (self.directory / "native.cw").write_text(
            "class NativeValue { int64 value() { return 37 } }\n"
        )
        blocks = b'''
@insert c file_pre {
#ifndef INSERTED_PARSER_H
#define INSERTED_PARSER_H
};
@insert c imports {
#include "native.h"
};
@insert c file_post {
int inserted_value(void) { return INSERTED_VALUE; }
#endif
};
@insert cwhip imports {
include "native.cw"
};
@insert cwhip file_post {
class InsertedValue { int64 value() { return NativeValue().value() } }
};
'''
        for backend, consumer in (
            ("c", '#define CPARSEGEN_NO_MAIN\n#include "parser.c"\n#include "parser.c"\n'
             'int main(void) { return inserted_value() == 37 ? 0 : 1; }\n'),
            ("cwhip", 'include "parser.cw"\n'
             'start { if (InsertedValue().value() != 37) { Sys.Process().exit(1) } }\n'),
        ):
            result = self.invoke(ORDINARY + blocks, backend, library=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            app = self.directory / ("app.c" if backend == "c" else "app.cw")
            app.write_text(consumer)
            executable = self.compiled(app, backend)
            result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_runnable_example_and_injected_public_apis(self):
        for backend in ("c", "cwhip"):
            with self.subTest(backend=backend):
                result = self.invoke((EXAMPLE / "words.cpg").read_bytes(), backend, library=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                app = self.directory / ("app.c" if backend == "c" else "app.cw")
                app.write_bytes((EXAMPLE / ("words.c" if backend == "c" else "words.cw")).read_bytes())
                executable = self.compiled(app, backend)
                result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(result.stdout, "words=3\n")
                # Declarations/helpers must also compile alongside the normal CLI.
                result = self.invoke((EXAMPLE / "words.cpg").read_bytes(), backend)
                self.assertEqual(result.returncode, 0, result.stderr)
                executable = self.compiled(self.generated, backend, "cli")
                result = self.parse(executable, "alpha beta gamma")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(result.stdout, "entry(WORD(alpha), WORD(beta), WORD(gamma))\n")

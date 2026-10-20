"""Generate and compile SmallC, then check real source-to-JSON-AST behavior."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/smallc"


def walk(node):
    yield node
    for child in node["children"]:
        yield from walk(child)


def nodes(node, name):
    return [child for child in walk(node) if child["name"] == name]


def spellings(node):
    return [child["text"] for child in walk(node) if not child["children"] and child["text"]]


class SmallCTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        generator = ROOT / "bin/cparsegen"
        if not generator.is_file():
            raise unittest.SkipTest("build cparsegen before running SmallC tests")
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
        temporary = tempfile.TemporaryDirectory(prefix="smallc-test-")
        cls.addClassCleanup(temporary.cleanup)
        cls.directory = Path(temporary.name)
        cls.env = os.environ.copy()
        for name in ("CWHIP_PACKAGE_PATH", "CWHIP_MODULE_DIR", "CWHIP_MODULE_REGISTRY"):
            cls.env.pop(name, None)
        for name in ("HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
            path = cls.directory / name.lower()
            path.mkdir()
            cls.env[name] = str(path)
        shutil.copy2(EXAMPLE / "smallc.cw", cls.directory)
        cls.executable = cls.directory / "smallc-ast"
        subprocess.run(
            [str(generator), "--library", str(EXAMPLE / "smallc.cpg"),
             str(cls.directory / "parser.cw"), str(cls.directory / "grammar.dot")],
            check=True, capture_output=True, text=True, timeout=60,
        )
        subprocess.run(
            [str(compiler), str(cls.directory / "smallc.cw"), "-o", str(cls.executable)],
            env=cls.env, check=True, capture_output=True, text=True, timeout=120,
        )

    def run_file(self, path):
        return subprocess.run(
            [str(self.executable), str(path)], env=self.env,
            capture_output=True, text=True, timeout=30,
        )

    def parse(self, text):
        path = self.directory / "input.c"
        path.write_text(text)
        return self.run_file(path)

    def ast(self, text):
        result = self.parse(text)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        tree = json.loads(result.stdout)
        self.assertEqual(tree["name"], "translationUnit")
        return tree

    def test_all_valid_samples(self):
        for path in sorted((EXAMPLE / "valid").glob("*.c")):
            with self.subTest(path=path.name):
                result = self.run_file(path)
                self.assertEqual(result.returncode, 0, result.stderr)
                tree = json.loads(result.stdout)
                self.assertEqual(tree["name"], "translationUnit")
                self.assertTrue(nodes(tree, "externalDeclaration"))
                for node in walk(tree):
                    self.assertEqual(set(node), {"name", "text", "children"})
                    self.assertIsInstance(node["name"], str)
                    self.assertIsInstance(node["text"], str)
                    self.assertIsInstance(node["children"], list)

    def test_all_invalid_samples(self):
        for path in sorted((EXAMPLE / "invalid").glob("*.c")):
            with self.subTest(path=path.name):
                result = self.run_file(path)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertIn(str(path), result.stderr)
                self.assertRegex(result.stderr, r":\d+:\d+: ")

    def test_functions_prototypes_parameters_calls_and_recursion(self):
        tree = self.ast((EXAMPLE / "valid/functions.c").read_text())
        externals = nodes(tree, "externalDeclaration")
        self.assertEqual(len(externals), 4)
        self.assertEqual(spellings(externals[0]), ["int", "twice", "(", "int", "value", ")", ";"])
        self.assertEqual([n["text"] for n in externals[1]["children"] if n["name"] == "IDENT"], ["factorial"])
        calls = [
            n for n in nodes(tree, "primary")
            if n["children"] and n["children"][0]["name"] == "IDENT"
            and len(n["children"]) > 1 and n["children"][1]["text"] == "("
        ]
        self.assertEqual([n["children"][0]["text"] for n in calls], ["factorial", "twice", "factorial"])
        self.assertTrue(nodes(tree, "parameter"))

    def test_operator_precedence_and_assignment_association(self):
        tree = self.ast("int main(){ int a, b; a = b = 1 + 2 * 3 < 8 == 1 && 4 || 0; return a; }")
        assignment = next(n for n in nodes(tree, "assignment") if len(n["children"]) == 3)
        self.assertEqual(assignment["children"][0]["name"], "lvalue")
        self.assertEqual(assignment["children"][2]["name"], "assignment")
        self.assertEqual(spellings(assignment["children"][2])[:2], ["b", "="])
        additive = next(n for n in nodes(assignment, "additive") if len(n["children"]) == 3)
        self.assertEqual([n["name"] for n in additive["children"] if n["children"]], ["multiplicative", "multiplicative"])
        self.assertEqual(spellings(additive), ["1", "+", "2", "*", "3"])
        self.assertEqual(spellings(additive["children"][2]), ["2", "*", "3"])

    def test_comments_strings_characters_and_array_initializers(self):
        source = r'''char text[] = "/* not a comment */ // \"quoted\" \\ \0";
        int main() {
            char newline = '\n', quote = '\'', slash = '\\';
            int values[3] = {1, 2, 3,};
            // fake tokens } ++ return
            /* block
               int x = ; */
            values[1] += 2;
            return values[1] % 3;
        }'''
        tree = self.ast(source)
        self.assertEqual([n["text"] for n in nodes(tree, "STRING")], [r'"/* not a comment */ // \"quoted\" \\ \0"'])
        self.assertEqual([n["text"] for n in nodes(tree, "CHAR")], [r"'\n'", r"'\''", r"'\\'"])
        self.assertNotIn("fake", spellings(tree))
        self.assertTrue(nodes(tree, "initializer"))
        self.assertEqual(len([n for n in nodes(tree, "lvalue") if len(n["children"]) == 4]), 2)

    def test_keywords_are_exact_and_cannot_be_identifiers(self):
        tree = self.ast("int main(){ int iffy=1, return_value=2, while2=3; return iffy+return_value+while2; }")
        identifiers = [n["text"] for n in nodes(tree, "IDENT")]
        self.assertIn("iffy", identifiers)
        self.assertIn("return_value", identifiers)
        self.assertIn("while2", identifiers)
        for word in ("if", "int", "return", "while", "struct", "typedef", "void"):
            with self.subTest(word=word):
                result = self.parse(f"int main(){{ int {word}=1; return 0; }}")
                self.assertEqual(result.returncode, 1)

    def test_dangling_else_binds_to_nearest_if_including_loop_bodies(self):
        for intervening in ("", "while (b) ", "for (;;) ", "label: "):
            with self.subTest(intervening=intervening):
                tree = self.ast(
                    "int choose(int a, int b) { if (a) " + intervening
                    + "if (b) return 1; else return 2; return 3; }"
                )
                outer = next(n for n in nodes(tree, "openStatement") if n["children"][0]["text"] == "if")
                self.assertEqual(len(outer["children"]), 5)
                inner = next(
                    n for n in nodes(outer, "matchedStatement")
                    if n["children"][0]["text"] == "if"
                )
                self.assertEqual(inner["children"][5]["text"], "else")

    def test_control_flow_and_empty_for_clauses(self):
        tree = self.ast(
            "int main(){ int i=0; for (;;) { if (i++ >= 3) break; } "
            "while (i) { --i; continue; } "
            "switch(i){case -1: case 'a': goto done; default: i%=2; } "
            "done: return i; }"
        )
        self.assertTrue(nodes(tree, "switchStatement"))
        self.assertEqual(len(nodes(tree, "switchSection")), 3)
        for text in ("for", "while", "break", "continue", "goto", "return", "%=", "++", "--"):
            self.assertIn(text, spellings(tree))

    def test_unsupported_or_malformed_syntax_is_rejected(self):
        bodies = [
            "int *p;", "struct X {int x;};", "typedef int X;", "void f();",
            "return &a;", "return *a;", "return (int) a;", "return a.x;",
            "return a->x;", "return 1.5;", "return 1 << 2;", "return 1 & 2;",
            "return a ? b : c;", "int matrix[2][2];", "int x = ;",
            "if (1 return 0;", "for (int i=0 i<3; i++) ;",
            'char s[] = "unterminated;', r"char c = '\q';",
            "char c = '';", "char c = 'xy';", 'char s[] = "a\nb";',
            "do {} while (1);", "1 = 2;", "return 1 + ;",
        ]
        for body in bodies:
            with self.subTest(body=body):
                result = self.parse("int main(){ " + body + " }")
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertEqual(result.stdout, "")
                self.assertRegex(result.stderr, r":\d+:\d+: ")
        for source in ("", "#include <stdio.h>\nint main(){}", "int main(){} trailing", "int f(char a[]);"):
            with self.subTest(source=source):
                self.assertEqual(self.parse(source).returncode, 1)

    def test_syntax_only_boundary_is_explicit(self):
        # Symbols, types, and jump/call validity belong to the next semantic milestone.
        self.ast("int main(){ int a[2]; goto absent; return undeclared(a + 1); }")

    def test_larger_input_and_nested_expressions(self):
        source = "int main(){ int total=0;\n" + "total = total + 1;\n" * 100 + "return total; }\n"
        tree = self.ast(source)
        self.assertEqual(len(nodes(tree, "statement")), 101)
        tree = self.ast("int main(){ return " + "(" * 12 + "1" + ")" * 12 + "; }")
        self.assertEqual(spellings(tree).count("("), 13)

    def test_lexical_error_locations_and_eof_comment(self):
        result = self.parse("int main(){\n  return @;\n}")
        self.assertEqual(result.returncode, 1)
        self.assertIn(":2:10: lex error", result.stderr)
        result = self.parse("int main(){\n  /* unterminated")
        self.assertEqual(result.returncode, 1)
        self.assertIn(":2:3: unterminated block comment", result.stderr)
        result = self.parse("int main(){\n  return 1 + ;\n}")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn(":2:14: parse error", result.stderr)
        self.ast("int main(){ return 0; }// no final newline")

    def test_usage_and_missing_file(self):
        result = subprocess.run(
            [str(self.executable), "--help"], capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("JSON syntax AST", result.stdout)
        result = subprocess.run([str(self.executable)], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 2)
        result = self.run_file(self.directory / "absent.c")
        self.assertEqual(result.returncode, 1)
        self.assertIn("existing file", result.stderr)


if __name__ == "__main__":
    unittest.main()

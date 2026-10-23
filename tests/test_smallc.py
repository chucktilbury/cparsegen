"""Generate and compile SmallC, then check real source-to-JSON-AST behavior."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from generator_support import c_compile_command


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
        generator = Path(os.environ.get("CPARSEGEN_EXECUTABLE", ROOT / "bin/cparsegen"))
        if not generator.is_file():
            if "CPARSEGEN_EXECUTABLE" in os.environ:
                raise FileNotFoundError(generator)
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
        shutil.copy2(EXAMPLE / "smallc_frontend.cw", cls.directory)
        cls.executable = cls.directory / "smallc-ast"
        subprocess.run(
            [str(generator), "--library", str(EXAMPLE / "smallc.cpg"),
             str(cls.directory / "parser.cw"), "--dot", str(cls.directory / "grammar.dot")],
            env=cls.env, check=True, capture_output=True, text=True, timeout=60,
        )
        subprocess.run(
            [str(compiler), str(cls.directory / "smallc.cw"), "-o", str(cls.executable)],
            env=cls.env, check=True, capture_output=True, text=True, timeout=120,
        )
        cls.generator = generator

    def run_file(self, path):
        return subprocess.run(
            [str(self.executable), str(path)], env=self.env,
            capture_output=True, text=True, timeout=30,
        )

    def parse(self, text):
        path = self.directory / "input.c"
        path.write_text(text)
        return self.run_file(path)

    def check(self, text):
        path = self.directory / "semantic-input.c"
        path.write_text(text)
        executable = getattr(self, "cwhip_executable", self.executable)
        return subprocess.run(
            [str(executable), "--check", str(path)], env=self.env,
            capture_output=True, text=True, timeout=30,
        )

    def ast(self, text):
        result = self.parse(text)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        tree = json.loads(result.stdout)
        self.assertEqual(tree["name"], "translationUnit")
        return tree

    def test_all_valid_samples(self):
        paths = sorted((EXAMPLE / "valid").glob("*.c"))
        self.assertTrue(paths, "SmallC valid sample corpus is missing")
        for path in paths:
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
        paths = sorted((EXAMPLE / "invalid").glob("*.c"))
        self.assertTrue(paths, "SmallC invalid sample corpus is missing")
        for path in paths:
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
            "switch(0){case 1+1: ;}", "switch(0){case (1): ;}",
            "switch(0){case +'a': ;}", "switch(0){case value: ;}",
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
        # Semantic validity is deliberately independent of syntax-only parsing.
        self.ast("int main(){ int a[2]; goto absent; return undeclared(a + 1); }")

    def test_semantic_positive_cases(self):
        cases = [
            "int main(){ return 0; }",
            "int first=2; int second=first; int main(){ int value=second; return value; }",
            "int main(){ int value=1; { char value='a'; value='b'; } return value; }",
            "int add(int left, int right); int main(){ return add(1, 2); } "
            "int add(int a, int b){ return a+b; }",
            "int factorial(int n); int factorial(int n){ if(n<2) return 1; "
            "return n*factorial(n-1); } int main(){ return factorial(4); }",
            "char echo(char input); char echo(char value){ return value; } "
            "int main(){ char letter=echo('x'); return letter=='x'; }",
            "char letters[]=\"abc\"; int values[2]={1,2}; "
            "int main(){ char letter=letters[0]; letter++; return values[0]+letter; }",
            "int main(){ char value='a'; int result=value+1; "
            "if(value && result) result++; for(int i=0;i<2;i++) result+=i; "
            "switch(value){case 'a': result+=1; break; default: result+=2;} return result; }",
            "int main(){ int value=1; { int value=2; value++; } return value; }",
            "int main(){ int value=0; char character='a'; value+=character; return value; }",
        ]
        for source in cases:
            with self.subTest(source=source):
                result = self.check(source)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, "")
                self.assertEqual(json.loads(result.stdout)["name"], "translationUnit")

    def test_semantic_negative_cases(self):
        cases = [
            ("undeclared variable", "int main(){ return missing; }"),
            ("use before local declaration", "int main(){ int value=missing; int missing=1; return value; }"),
            ("use before global declaration", "int first=second; int second=1; int main(){return first;}"),
            ("duplicate local", "int main(){ int value; int value; return 0; }"),
            ("local duplicates parameter", "int f(int value){int value; return 0;}"),
            ("duplicate global", "int value; int value; int main(){ return 0; }"),
            ("duplicate parameter", "int f(int value, char value);"),
            ("duplicate prototype", "int f(int value); int f(int other);"),
            ("duplicate definition", "int f(){return 0;} int f(){return 1;}"),
            ("incompatible prototype", "int f(int value); char f(int value){return 'x';}"),
            ("incompatible parameter signature", "int f(int value); int f(char value){return 0;}"),
            ("function before prototype", "int first(){return later();} int later(){return 0;}"),
            ("undeclared call", "int main(){return missing();}"),
            ("call variable", "int main(){int value=1; return value();}"),
            ("global variable called", "int value; int main(){return value();}"),
            ("function used as variable", "int f(){return 0;} int main(){return f;}"),
            ("wrong argument count", "int f(int value); int main(){return f();}"),
            ("too many arguments", "int f(int value); int main(){return f(1,2);}"),
            ("argument type mismatch", "int f(char value); int main(){return f(1);}"),
            ("global function and variable conflict", "int value; int value();"),
            ("array scalar value", "int main(){int values[2]; return values;}"),
            ("array assignment", "int main(){int values[2]; values=1; return 0;}"),
            ("indexing a scalar", "int main(){int value=1; return value[0];}"),
            ("array index is an array", "int main(){int values[2]; int other[1]; return values[other];}"),
            ("array initializer type", "int main(){int values[2]={1,'a'}; return 0;}"),
            ("string needs char array", "int value=\"x\"; int main(){return 0;}"),
            ("scalar brace initializer", "int main(){int value={1}; return 0;}"),
            ("initializer type mismatch", "int main(){char value=1; return 0;}"),
            ("promoted arithmetic needs exact initializer type", "int main(){char value='a'+'b'; return 0;}"),
            ("assignment type mismatch", "int main(){char value='a'; value=1; return 0;}"),
            ("compound assignment conversion", "int main(){char value='a'; value+='b'; return 0;}"),
            ("return type mismatch", "char value(){return 1;}"),
            ("missing return value", "int main(){return;}"),
            ("array arithmetic", "int main(){int values[2]; return values+1;}"),
            ("for declaration scope", "int main(){for(int i=0;i<1;i++){} return i;}"),
            ("function conflicts with global variable", "int f; int f(){return 0;}"),
        ]
        for description, source in cases:
            with self.subTest(description=description):
                syntax = self.parse(source)
                self.assertEqual(syntax.returncode, 0, syntax.stderr)
                result = self.check(source)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertEqual(result.stdout, "")
                self.assertRegex(result.stderr, r":\d+:\d+: ")

    def test_semantic_error_location_and_syntax_mode_regression(self):
        source = "int main(){\n  return missing;\n}\n"
        result = self.check(source)
        self.assertEqual(result.returncode, 1)
        self.assertIn(":2:10: undeclared variable 'missing'", result.stderr)
        syntax = self.parse("int main(){ return missing; }")
        self.assertEqual(syntax.returncode, 0, syntax.stderr)

    def test_control_flow_semantic_positive_cases(self):
        cases = [
            "int f(){while(1) break; for(;;) continue; return 0;}",
            "int f(){for(;;) if(1) break; else continue; return 0;}",
            "int f(){while(1) if(1) continue; return 0;}",
            "int f(){while(1){switch(1){case 1: continue; default: break;} break;} return 0;}",
            "int f(){switch(1){case 1: while(1){break;} break; default: for(;;) continue;} return 0;}",
            "int f(){while(1){while(1) break; continue;} return 0;}",
            "int f(){goto done; done: return 0;}",
            "int f(){again: ; goto again; return 0;}",
            "int f(){goto done; {done: return 0;}}",
            "int f(){int done=1; goto done; done: return done;}",
            "int f(){label: return 0;} int g(){goto label; label: return 1;}",
            "int f(){goto block; block: {} empty: ; expr: 1; "
            "cond: if(1) return 0; else return 1; loop: while(0) break; "
            "count: for(;;) break; choice: switch(0){} jump: goto end; end: return 0;}",
            "int f(){if(1) label: while(0) if(1) return 0; return 1;}",
            "int f(){switch(1){case 1: case 2: break; default: break;} "
            "switch(1){case 1: default: break;} return 0;}",
            "int f(){switch(1){case 1: switch(1){case 1: default: break;} "
            "default: break;} return 0;}",
            "int f(){switch(1){case -1: case 1: case 0: break;} return 0;}",
            "int f(){switch(0){case -97: case 'a': case 'b': break;} return 0;}",
            "char f(){return 'a';} int g(){return 1;}",
            # This slice checks individual returns, not guaranteed completion.
            "int f(){} char g(){if(1) return 'a';}",
            "int f(){goto end; return 1; end: ;}",
        ]
        for source in cases:
            with self.subTest(source=source):
                syntax = self.parse(source)
                self.assertEqual(syntax.returncode, 0, syntax.stderr)
                result = self.check(source)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, "")
                self.assertEqual(json.loads(result.stdout), json.loads(syntax.stdout))

    def assert_control_flow_error(self, source, diagnostic, token):
        syntax = self.parse(source)
        self.assertEqual(syntax.returncode, 0, syntax.stderr)
        result = self.check(source)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(result.stdout, "")
        offset = source.rindex(token)
        line = source.count("\n", 0, offset) + 1
        column = offset - source.rfind("\n", 0, offset)
        self.assertEqual(
            result.stderr,
            f"{self.directory / 'semantic-input.c'}:{line}:{column}: {diagnostic}\n",
        )

    def test_control_flow_semantic_negative_cases(self):
        cases = [
            ("break;", "break requires an enclosing loop or switch", "break"),
            ("continue;", "continue requires an enclosing loop", "continue"),
            ("if(1) break;", "break requires an enclosing loop or switch", "break"),
            ("if(1) label: continue;", "continue requires an enclosing loop", "continue"),
            ("while(1) break; break;", "break requires an enclosing loop or switch", "break"),
            ("for(;;) continue; continue;", "continue requires an enclosing loop", "continue"),
            ("switch(0){default: break;} break;",
             "break requires an enclosing loop or switch", "break"),
            ("switch(0){default: continue;}", "continue requires an enclosing loop", "continue"),
            ("switch(0){case 0: while(1) break; continue;}",
             "continue requires an enclosing loop", "continue"),
            ("goto absent;", "unresolved goto label 'absent'", "absent"),
            ("int absent=0; goto absent;", "unresolved goto label 'absent'", "absent"),
            ("label: ; {label: ;}", "duplicate label 'label'", "label"),
            ("label: label: return 0;", "duplicate label 'label'", "label"),
            ("if(1) label: ; else label: ;", "duplicate label 'label'", "label"),
            ("switch(0){default: default: ;}", "duplicate default label", "default"),
            ("switch(0){case 1: case 1: ;}", "duplicate case constant 1", "1:"),
            ("switch(0){case 1: ; case +001: ;}", "duplicate case constant 1", "+001"),
            ("switch(0){case -01: ; case -1: ;}", "duplicate case constant -1", "-1"),
            ("switch(0){case +0: case -000: ;}", "duplicate case constant 0", "-000"),
            ("switch(0){case 1: switch(0){case 1: case +1: ;}}",
             "duplicate case constant 1", "+1"),
            ("return;", "function returning int requires a return value", "return"),
            ("return 'a';", "return value requires int, got char", "'a'"),
        ]
        for body, diagnostic, token in cases:
            source = f"int main(){{\n  {body}\n}}\n"
            with self.subTest(source=source):
                self.assert_control_flow_error(source, diagnostic, token)
        for source, diagnostic, token in [
            ("int f(){label: return 0;}\nint g(){goto label;}",
             "unresolved goto label 'label'", "label"),
            ("int f(){while(1) break; return 0;}\nint g(){break;}",
             "break requires an enclosing loop or switch", "break"),
            ("int f(){switch(0){default: break;} return 0;}\nint g(){continue;}",
             "continue requires an enclosing loop", "continue"),
            ("char f(){\n return;\n}", "function returning char requires a return value", "return"),
            ("char f(){\n return 1;\n}", "return value requires char, got int", "1"),
            ("char f(){return +'a';}", "return value requires char, got int", "+"),
        ]:
            with self.subTest(source=source):
                self.assert_control_flow_error(source, diagnostic, token)

    def test_switch_literal_normalization(self):
        pairs = [
            ("00097", "'a'", "97"),
            ("'a'", "+097", "97"),
            (r"'\n'", "10", "10"),
            (r"'\r'", "13", "13"),
            (r"'\t'", "9", "9"),
            (r"'\0'", "-0", "0"),
            (r"'\\'", "92", "92"),
            (r"'\''", "39", "39"),
            (r"'\"'", "34", "34"),
            ("'\"'", r"'\"'", "34"),
            ("999999999999999999999999999999", "+0999999999999999999999999999999",
             "999999999999999999999999999999"),
        ]
        for first, second, key in pairs:
            source = f"int f(){{\n switch(0){{case {first}: case {second}: break;}}\n return 0;\n}}"
            with self.subTest(first=first, second=second):
                self.assert_control_flow_error(source, f"duplicate case constant {key}", second)

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

    def test_eof_crlf_and_quoted_error_locations(self):
        for source in [
            "int main(){\r\n  return @;\r\n}",
            "int main(){\r\n  return 1 + ;\r\n}",
            "int main(){\n  return 1;",
            'char s[] = "unterminated',
            "char c = '\\q';",
            "char c = '';",
            "char c = 'ab';",
            'char s[] = "raw\nnewline";',
        ]:
            with self.subTest(source=source):
                result = self.parse(source)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertRegex(result.stderr, r":\d+:\d+: ")

    def test_usage_and_missing_file(self):
        result = subprocess.run(
            [str(self.executable), "--help"], env=self.env,
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("JSON syntax AST", result.stdout)
        result = subprocess.run(
            [str(self.executable)], env=self.env, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 2)
        result = self.run_file(self.directory / "absent.c")
        self.assertEqual(result.returncode, 1)
        self.assertIn("existing file", result.stderr)


class SmallCStandaloneTests(SmallCTests):
    """Run the same frontend checks, comparing every source to Cwhip as well."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cwhip_executable = cls.executable
        cls.executable = cls.directory / "smallc-c"
        source = cls.directory / "parser.c"
        graph = cls.directory / "grammar-c.dot"
        subprocess.run(
            [str(cls.generator), "--target", "c", str(EXAMPLE / "smallc.cpg"),
             str(source), "--dot", str(graph)],
            env=cls.env, check=True, capture_output=True, text=True, timeout=60,
        )
        if graph.read_bytes() != (cls.directory / "grammar.dot").read_bytes():
            raise AssertionError("SmallC DOT differs between backends")
        subprocess.run(
            c_compile_command(source, cls.executable),
            env=cls.env, check=True, capture_output=True, text=True, timeout=120,
        )

    def run_file(self, path):
        expected = subprocess.run(
            [str(self.cwhip_executable), str(path)], env=self.env,
            capture_output=True, text=True, timeout=30,
        )
        actual = subprocess.run(
            [str(self.executable), "--json", str(path)], env=self.env,
            capture_output=True, text=True, timeout=30,
        )
        if path.is_file():
            self.assertEqual(actual.returncode, expected.returncode, actual.stdout + actual.stderr)
            self.assertEqual(actual.stderr, expected.stderr)
            if expected.returncode == 0:
                self.assertEqual(json.loads(actual.stdout), json.loads(expected.stdout))
            else:
                self.assertEqual(actual.stdout, expected.stdout)
        return actual

    def test_usage_and_missing_file(self):
        result = subprocess.run(
            [str(self.executable), "--help"], env=self.env,
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("JSON syntax AST", result.stdout)
        result = subprocess.run(
            [str(self.executable)], env=self.env, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 2)
        result = self.run_file(self.directory / "absent.c")
        self.assertEqual(result.returncode, 1)
        self.assertIn("absent.c:", result.stderr)

    def test_runs_without_sdk_or_path(self):
        env = {name: value for name, value in self.env.items()
               if name == "HOME" or name.startswith("XDG_")}
        env["PATH"] = ""
        result = subprocess.run(
            [str(self.executable), "--json", str(EXAMPLE / "valid/arrays.c")],
            env=env, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["name"], "translationUnit")


if __name__ == "__main__":
    unittest.main()

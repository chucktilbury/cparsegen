"""Shared lexer-expression contract, exercised through both generated backends."""

import itertools
import re
import subprocess
import unittest

from generator_support import GeneratorTestCase, ROOT, c_compile_command


class LexerExpressionCases:
    def assert_parses(self, executable, text, expected):
        result = self.parse(executable, text)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, expected + "\n")

    def test_precedence_and_longest_alternative_not_first_success(self):
        executable = self.compile_grammar(
            'entry : TOKEN ;\nTOKEN = "a" | "b" "c"+; # optional terminator\n'
        )
        for text in ["a", "bc", "bccc"]:
            self.assert_parses(executable, text, f"entry(TOKEN({text}))")
        for text in ["b", "ac", "abc"]:
            self.assertEqual(self.parse(executable, text).returncode, 1)
        executable = self.compile_grammar(
            'entry : TOKEN ;\nTOKEN = ("a" | "ab") ("bc" | "c")+\n'
        )
        for text in ["abc", "abcbc", "ac", "abcc"]:
            self.assert_parses(executable, text, f"entry(TOKEN({text}))")
        executable = self.compile_grammar(
            'entry : TOKEN ;\nTOKEN = "ab"+\n'
        )
        self.assert_parses(executable, "abab", "entry(TOKEN(abab))")
        self.assertEqual(self.parse(executable, "aba").returncode, 1)

    def test_forward_composition_nested_groups_and_quantifiers(self):
        executable = self.compile_grammar(
            'entry : NUMBER+ ;\n'
            'NUMBER = ("+" | "-")? DIGIT+ ("." DIGIT+)? EXP?\n'
            'EXP = [eE] ("+" | "-")? DIGIT+\n'
            'DIGIT = [0-9]\n'
            'SPACE = ([ ] | [\\t\\r\\n])+\n@skip SPACE;\n'
        )
        self.assert_parses(
            executable, "-12.5e+2 +7 03",
            "entry(NUMBER(-12.5e+2), NUMBER(+7), NUMBER(03))",
        )
        executable = self.compile_grammar(
            'entry : TOKEN ;\n'
            'TOKEN = (("ab" | "a")+ ("c" | "de")?)* "!"\n'
        )
        for text in ["!", "abadeab!", "aaaaac!", "ab!"]:
            self.assert_parses(executable, text, f"entry(TOKEN({text}))")

    def test_literals_classes_ranges_negation_and_escaping(self):
        executable = self.compile_grammar(
            'entry : META CLASS TEXT END ;\n'
            r"""META = "()|?*+[].^$#//{}" "\\" "\"" '\''""" + "\n"
            r"CLASS = [\]\[\\\-\^]+" + "\n"
            r"TEXT = [^0-9\]\t\n]+" + "\n"
            r"END = [\t-\r]+" + "\n"
        )
        text = '()|?*+[].^$#//{}\\"\'[]\\-^alpha! \t\n'
        self.assert_parses(
            executable, text,
            'entry(META(()|?*+[].^$#//{}\\"\'), CLASS([]\\-^), TEXT(alpha! ), END(\t\n))',
        )
        executable = self.compile_grammar(
            "entry : TOKEN ;\nTOKEN = [-a-c]+ [^a-z]+\n"
        )
        self.assert_parses(executable, "-abc-123", "entry(TOKEN(-abc-123))")
        for text in ["-abcd123", "-abcé"]:
            self.assertEqual(self.parse(executable, text).returncode, 1)
        executable = self.compile_grammar(
            'entry : TOKEN ;\nTOKEN = "a\\n\\tb\\r"\n'
        )
        self.assert_parses(executable, "a\n\tb\r", "entry(TOKEN(a\n\tb\n))")
        executable = self.compile_grammar(
            'entry : "\\n" "\\\"" ;\nUNUSED = [x]\n'
        )
        self.assert_parses(
            executable, '\n"', 'entry(@literal0(\n), @literal1("))'
        )

    def test_composed_references_keep_named_token_order_and_skip_competition(self):
        executable = self.compile_grammar(
            'entry : LONG FIRST ;\n'
            'LONG = PART PART\nFIRST = PART\nSECOND = "a"\nPART = [a]\n'
            'SPACE = [ ]+\n@skip SPACE;\n'
        )
        self.assert_parses(executable, "aa a", "entry(LONG(aa), FIRST(a))")
        executable = self.compile_grammar(
            'entry : WORD ;\n'
            'DISCARD = ("x" | "xx")+\nWORD = [a-z]+\n@skip DISCARD;\n'
        )
        self.assert_parses(executable, "xxabc", "entry(WORD(xxabc))")
        self.assertEqual(self.parse(executable, "xx").returncode, 1)
        executable = self.compile_grammar(
            'entry : WRAPPED ;\nWRAPPED = "<" INNER ">"\nINNER = [a-z]+\n'
            '@skip INNER;\n'
        )
        self.assert_parses(executable, "<abc>", "entry(WRAPPED(<abc>))")

    def test_keywords_comments_quoted_and_parser_literals_still_compete(self):
        executable = self.compile_grammar(
            'entry : "let" IDENT STRING ";" ;\n'
            'IDENT = LETTER (LETTER | [0-9])*\nLETTER = [a-z_]\n'
            'SPACE = [ \\t\\r\\n]+\n@skip SPACE;\n'
            '@keywords IDENT;\n@reserved class;\n@quoted STRING double;\n'
            '@line_comment //;\n@block_comment /* */;\n'
        )
        self.assert_parses(
            executable, '/* lead */ let // hi\nname1 "a\\"b";',
            'entry(@literal0(let), IDENT(name1), STRING("a\\"b"), @literal1(;))',
        )
        for text in ['let class "x";', 'let name "bad\\q";', "/* unclosed"]:
            self.assertEqual(self.parse(executable, text).returncode, 1)
        executable = self.compile_grammar(
            'entry : NAMED ;\nNAMED = ("==" | "=")+\nUNUSED = [x]\n'
        )
        self.assert_parses(executable, "===", "entry(NAMED(===))")

    def test_ambiguous_paths_are_deduplicated_instead_of_backtracking(self):
        executable = self.compile_grammar(
            'entry : TOKEN ;\nTOKEN = ("a" | "aa")* "b"\n'
        )
        text = "a" * 1000 + "b"
        self.assert_parses(executable, text, f"entry(TOKEN({text}))")
        executable = self.compile_grammar(
            "entry : TOKEN ;\nTOKEN = [0-9]*[0-9]*[0-9]\n"
        )
        text = "1" * 1000
        self.assert_parses(executable, text, f"entry(TOKEN({text}))")

    def test_regular_subset_against_python_fullmatch(self):
        # Require the final ! to distinguish one complete token from a token sequence.
        pattern = "(a|ab)*(b|c)?!"
        executable = self.compile_grammar(
            'entry : TOKEN ;\nTOKEN = ("a" | "ab")* ("b" | "c")? "!"\n'
        )
        for length in range(4):
            for letters in itertools.product("abc", repeat=length):
                text = "".join(letters) + "!"
                with self.subTest(text=text):
                    result = self.parse(executable, text)
                    self.assertEqual(
                        result.returncode, 0 if re.fullmatch(pattern, text) else 1,
                        result.stdout + result.stderr,
                    )

    def test_working_example(self):
        executable = self.compile_grammar(
            (ROOT / "examples/lexer-expressions.cpg").read_text()
        )
        self.assert_parses(
            executable, "let total = -12.5e+2; // amount\n",
            "assignment(@literal0(let), IDENT(total), @literal1(=), "
            "NUMBER(-12.5e+2), @literal2(;))",
        )


class CwhipLexerExpressionTests(LexerExpressionCases, GeneratorTestCase):
    pass


class CLexerExpressionTests(LexerExpressionCases, GeneratorTestCase):
    backend = "c"


class LexerExpressionValidationTests(GeneratorTestCase):
    def test_invalid_expressions_are_source_located_and_never_write_outputs(self):
        cases = [
            ("", "expected nonempty lexer expression"),
            ('""', "empty lexer literal"),
            ("[]", "empty character class"),
            ("[^]", "empty character class"),
            ("[z-a]", "descending character-class range"),
            (r"[\r-\t]", "descending character-class range"),
            (r"[\q]", "unsupported character-class escape"),
            (r'"\q"', "unsupported quoted escape"),
            ('"é"', "non-NUL ASCII"),
            ("[é]", "non-NUL ASCII"),
            ("é", "unsupported non-ASCII grammar syntax"),
            ("[\0]", "non-NUL ASCII"),
            ("[^\x01-\x7f]", "character class matches no ASCII bytes"),
            ('"\0"', "non-NUL ASCII"),
            ("MISSING+", "unknown lexer reference MISSING"),
            ("entry", "unknown lexer reference entry"),
            ("TOKEN", "cyclic lexer reference TOKEN"),
            ('"a"?', "can match empty input"),
            ('"a"*', "can match empty input"),
            ('"a" | "b"?', "can match empty input"),
            ('("a"?)+ "b"', "nullable lexer repetition"),
            ('("a"*)? "b"', "nullable lexer repetition"),
            ('"a"**', "unsupported lexer expression syntax"),
            ('"a"+?', "unsupported lexer expression syntax"),
            ('"a"|', "expected nonempty lexer expression"),
            ('|"a"', "expected nonempty lexer expression"),
            ('()', "expected nonempty lexer expression"),
            ('("a"', "expected ')' after lexer group"),
            ('"a")', "unexpected token after lexer expression"),
            (".", "unsupported lexer expression syntax"),
            ("[a]{2}", "unsupported lexer expression syntax"),
            ("^ [a]", "unsupported lexer expression syntax"),
            ('"a" $', "unsupported lexer expression syntax"),
            (r"\+", "unsupported lexer expression syntax"),
            ("[a]; OTHER = [b]", "unexpected token after lexer expression"),
        ]
        for backend in ["cwhip", "c"]:
            for expression, diagnostic in cases:
                with self.subTest(backend=backend, expression=expression):
                    grammar = self.directory / "bad.cpg"
                    grammar.write_text("entry : TOKEN ;\nTOKEN = " + expression + "\n")
                    result = self.generate(grammar, backend)
                    self.assertEqual(result.returncode, 1, result.stderr)
                    self.assertRegex(
                        result.stderr,
                        rf"^{re.escape(str(grammar))}:\d+:\d+: bytes \d+-\d+:",
                    )
                    self.assertIn(diagnostic, result.stderr)
                    self.assertFalse(self.generated.with_suffix(
                        ".c" if backend == "c" else ".cw").exists())
                    self.assertFalse(self.graph.exists())

    def test_reference_cycles_and_quoted_references(self):
        for backend in ["cwhip", "c"]:
            for declarations, diagnostic in [
                ('TOKEN = OTHER\nOTHER = TOKEN "x"\n', "cyclic lexer reference TOKEN"),
                ('TOKEN = OTHER\nOTHER = THIRD\nTHIRD = OTHER\n', "cyclic lexer reference OTHER"),
                ('TOKEN = STRING\n@quoted STRING double;\n', "cannot compose @quoted token STRING"),
                ('TOKEN = OTHER?\nOTHER = [a]\n', "lexer rule TOKEN can match empty input"),
                ('TOKEN = OTHER\nOTHER = [a]*\n', "can match empty input"),
            ]:
                with self.subTest(backend=backend, declarations=declarations):
                    grammar = self.directory / "bad.cpg"
                    grammar.write_text("entry : TOKEN ;\n" + declarations)
                    result = self.generate(grammar, backend)
                    self.assertEqual(result.returncode, 1, result.stderr)
                    self.assertIn(diagnostic, result.stderr)

    def test_expansion_and_nesting_limits_fail_during_generation(self):
        grammar = self.directory / "limit.cpg"
        grammar.write_text("entry : TOKEN ;\nTOKEN = " + "[a]" * 4095 + "\n")
        result = self.generate(grammar)
        self.assertEqual(result.returncode, 0, result.stderr)
        for expression, diagnostic in [
            ("[a]" * 4096, "expanded lexer state limit exceeded (4096)"),
            ("(" * 200 + "[a]" + ")" * 200, "lexer group nesting limit exceeded"),
        ]:
            grammar.write_text("entry : TOKEN ;\nTOKEN = " + expression + "\n")
            result = self.generate(grammar)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn(f"{grammar}:2:", result.stderr)
            self.assertIn(diagnostic, result.stderr)
        declarations = "\n".join(
            f"R{i} = R{i+1} R{i+1}" for i in range(13)
        ) + '\nR13 = "a"\n'
        grammar.write_text("entry : R0 ;\n" + declarations)
        result = self.generate(grammar)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("expanded lexer state limit", result.stderr)
        declarations = "\n".join(f"R{i} = R{i+1}" for i in range(129))
        grammar.write_text("entry : R0 ;\n" + declarations + '\nR129 = "a"\n')
        result = self.generate(grammar)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("nesting/reference limit exceeded (128)", result.stderr)

    def test_raw_scanner_differential_including_offsets_and_skip(self):
        grammar = self.directory / "scanner.cpg"
        grammar.write_text(
            'entry : ;\n'
            'NUMBER = DIGIT+ ("." DIGIT+)?\n'
            'IDENT = LETTER (LETTER | DIGIT)*\n'
            'EQ = "=" | "=="\nDIGIT = [0-9]\nLETTER = [a-z]\n'
            'SPACE = [ \\t\\n]+\n@skip SPACE;\n'
            '@quoted STRING double;\n@line_comment //;\n'
            '@block_comment /* */;\n@keywords IDENT;\n@reserved class;\n'
        )
        source = 'aa1 == 12.5 /*ignored*/ "x\\"y" //skip\nclass = 7'
        expected = (
            'IDENT:0:3:aa1\nEQ:4:2:==\nNUMBER:7:4:12.5\n'
            'STRING:24:6:"x\\"y"\n@reserved:38:5:class\nEQ:44:1:=\n'
            'NUMBER:46:1:7\n'
        )
        result = subprocess.run(
            [str(self.generator), "--library", str(grammar), str(self.generated),
             "--dot", str(self.graph)], capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        driver = self.directory / "driver.cw"
        driver.write_text(
            'include "generated.cw"\nclass Driver {\nint run() {\n'
            f'InputScanner scanner({self.cw_string(source)})\n'
            'if (!scanner.scan()) { print(scanner.problem)\nreturn 1 }\n'
            'int i = 0\nwhile (i < scanner.tokens.length) {\n'
            'LexToken token = scanner.tokens[i] as LexToken\n'
            'print(format("{}:{}:{}:{}\\n", token.kind, token.offset, '
            'token.text.length, token.text))\ni += 1\n}\nreturn 0\n}\n}\n'
            'start { Sys.Process().exit(Driver().run()) }\n'
        )
        cw_executable = self.directory / "scan-cw"
        result = subprocess.run(
            [str(self.compiler), str(driver), "-o", str(cw_executable)],
            capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.generate(grammar, "c")
        self.assertEqual(result.returncode, 0, result.stderr)
        c_driver = self.directory / "driver.c"
        c_driver.write_text(
            '#define CPARSEGEN_NO_MAIN\n#include "generated.c"\n'
            'int main(void) {\nContext ctx;\n'
            f'const unsigned char source[] = {self.cw_string(source)};\n'
            'cpg_init(&ctx, source, sizeof(source) - 1, "input");\n'
            'if (setjmp(ctx.failure) || !scan(&ctx)) { cpg_destroy(&ctx); return 1; }\n'
            'for (size_t i = 0; i < ctx.token_count; ++i) {\n'
            'Token t = ctx.tokens[i];\n'
            'printf("%s:%zu:%zu:%.*s\\n", t.kind, t.offset, t.length, '
            '(int)t.length, source + t.offset);\n}\n'
            'cpg_destroy(&ctx); return 0;\n}\n'
        )
        c_executable = self.directory / "scan-c"
        result = subprocess.run(
            c_compile_command(c_driver, c_executable),
            capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        outputs = []
        for executable in [cw_executable, c_executable]:
            result = subprocess.run(
                [str(executable)], capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            outputs.append(result.stdout)
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(outputs[0], expected)

    @staticmethod
    def cw_string(text):
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace(
            "\n", "\\n").replace("\t", "\\t") + '"'


if __name__ == "__main__":
    unittest.main()

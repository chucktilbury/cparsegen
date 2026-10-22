"""Grammar include expansion and CLI search paths, shared by both targets."""

import os
import subprocess
import unittest

from generator_support import GeneratorTestCase, c_compile_command


class IncludeTests(GeneratorTestCase):
    def write(self, name, text):
        path = self.directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def invoke(self, grammar, *options, cwd=None):
        return subprocess.run(
            [str(self.generator),
             *(["--target", "c"] if self.backend == "c" else []),
             "--dot", str(self.graph), *options,
             str(grammar), str(self.generated)],
            cwd=cwd, capture_output=True, text=True, timeout=60,
        )

    def compile_generated(self):
        executable = self.directory / "parser"
        command = (
            c_compile_command(self.generated, executable)
            if self.backend == "c" else
            [str(self.compiler), str(self.generated), "-o", str(executable)]
        )
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr)
        return executable

    def assert_failure(self, grammar, message, *options):
        for path in (self.generated, self.graph):
            path.unlink(missing_ok=True)
        result = self.invoke(grammar, *options)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertIn(message, result.stderr)
        self.assertFalse(self.generated.exists())
        self.assertFalse(self.graph.exists())
        # Validation must not truncate pre-existing outputs either.
        for path in (self.generated, self.graph):
            path.write_text("keep me")
        repeated = self.invoke(grammar, *options)
        self.assertEqual(repeated.returncode, 1, repeated.stderr)
        for path in (self.generated, self.graph):
            self.assertEqual(path.read_text(), "keep me")
            path.unlink()
        return result.stderr

    def test_nested_relative_interleaved_forward_references_and_duplicate_diamond(self):
        main = self.write(
            "grammar/main.cpg",
            '@include "parts/entry.cpg";\n'
            'WORD = LETTER+\n'
            '@include parts/tokens.cpg;\n'
            '@include ./parts/../parts/entry.cpg;\n'
            'unused : "unused" ;\n',
        )
        self.write(
            "grammar/parts/entry.cpg",
            'entry : value "!" ;\n'
            '@include tokens.cpg;\n'
            'value : WORD ;\n',
        )
        self.write(
            "grammar/parts/tokens.cpg",
            '@note @include missing.cpg is opaque;\n'
            'LETTER = [a-z]\nSPACE = [ \\t\\r\\n]+\n@skip SPACE;\n',
        )
        result = self.invoke(main, cwd=self.directory)
        self.assertEqual(result.returncode, 0, result.stderr)
        parsed = self.parse(self.compile_generated(), " alpha ! ")
        self.assertEqual(parsed.returncode, 0, parsed.stdout + parsed.stderr)
        self.assertEqual(parsed.stdout, "entry(value(WORD(alpha)), @literal0(!))\n")
        # Expansion must produce byte-identical artifacts to manual inlining.
        source, graph = self.generated.read_bytes(), self.graph.read_bytes()
        flat = self.write(
            "flat.cpg",
            'entry : value "!" ;\n'
            '@note @include missing.cpg is opaque;\n'
            'LETTER = [a-z]\nSPACE = [ \\t\\r\\n]+\n@skip SPACE;\n'
            'value : WORD ;\nWORD = LETTER+\nunused : "unused" ;\n',
        )
        result = self.invoke(flat)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.generated.read_bytes(), source)
        self.assertEqual(self.graph.read_bytes(), graph)

    def test_search_order_repeated_options_empty_components_and_local_priority(self):
        main = self.write("grammar/main.cpg", '@include token.cpg;\nentry : TOKEN ;\n')
        self.write("first/token.cpg", 'TOKEN = "first"\n')
        self.write("second/token.cpg", 'TOKEN = "second"\n')
        self.write("space dir/token.cpg", 'TOKEN = "space"\n')
        self.write("token.cpg", 'TOKEN = "cwd"\n')
        cases = [
            (["--include-path", "first:second"], "first"),
            (["--include-path", "second:first"], "second"),
            (["--include-path", "first", "--include-path", "second"], "first"),
            (["--include-path", "missing::first"], "cwd"),
            (["--include-path", ":first"], "cwd"),
            (["--include-path", "missing:"], "cwd"),
            (["--include-path", ""], "cwd"),
            (["--include-path", str(self.directory / "second")], "second"),
            (["--include-path", "space dir:first"], "space"),
        ]
        for options, word in cases:
            with self.subTest(options=options):
                result = self.invoke(main, *options, cwd=self.directory)
                self.assertEqual(result.returncode, 0, result.stderr)
                parsed = self.parse(self.compile_generated(), word)
                self.assertEqual(parsed.returncode, 0, parsed.stdout + parsed.stderr)
                self.assertEqual(parsed.stdout, f"entry(TOKEN({word}))\n")
        self.write("grammar/token.cpg", 'TOKEN = "local"\n')
        result = self.invoke(main, "--include-path", "first:second", cwd=self.directory)
        self.assertEqual(result.returncode, 0, result.stderr)
        parsed = self.parse(self.compile_generated(), "local")
        self.assertEqual(parsed.returncode, 0, parsed.stdout + parsed.stderr)

    def test_quoted_absolute_spaces_semicolons_and_parent_traversal(self):
        token = self.write("space dir/token;name.cpg", 'TOKEN = "ok"\n')
        main = self.write(
            "grammar/main.cpg",
            f"@include '{token}';\n"
            '@include "../space dir/token;name.cpg";\nentry : TOKEN ;\n',
        )
        result = self.invoke(main)
        self.assertEqual(result.returncode, 0, result.stderr)
        parsed = self.parse(self.compile_generated(), "ok")
        self.assertEqual(parsed.returncode, 0, parsed.stdout + parsed.stderr)

    def test_cycle_missing_directory_and_malformed_includes(self):
        main = self.write("main.cpg", '@include parts/a.cpg;\nentry : "ok" ;\n')
        child = self.write("parts/a.cpg", "\n@include ../main.cpg;\n")
        diagnostic = self.assert_failure(main, "include cycle")
        self.assertIn(f"{child}:2:", diagnostic)
        self.assertIn(f"included from {main}:1:", diagnostic)
        for directive in [
            "@include ;", '@include "";', "@include a.cpg b.cpg;",
            '@include "a.cpg" "b.cpg";', '@include "a.cpg"; extra',
            "@include", '@include "unfinished;', '@include "a\nb";',
        ]:
            with self.subTest(directive=directive):
                child.write_text("\n" + directive + "\n")
                self.assert_failure(main, str(child))
        child.write_text("\n@include missing.cpg;\n")
        diagnostic = self.assert_failure(main, "cannot find included grammar missing.cpg")
        self.assertIn(str(child), diagnostic)
        child.write_text("@include .;\n")
        self.assert_failure(main, "expected a readable regular grammar file")

    def test_included_syntax_semantic_and_backend_diagnostics(self):
        main = self.write("main.cpg", '@include parts/a.cpg;\nentry : TOKEN ;\n')
        child = self.write("parts/a.cpg", '@include deeper/b.cpg;\n')
        leaf = self.write("parts/deeper/b.cpg", "\nTOKEN = MISSING\n")
        for text, line, message in [
            ("\nTOKEN = MISSING\n", 2, "unknown lexer reference MISSING"),
            ("\nbroken : UNKNOWN ;\nTOKEN = [a-z]+\n", 2, "unknown lexer token UNKNOWN"),
            ("\nTOKEN = [a-z\n", 2, "unterminated character class"),
            ("\n@skip UNKNOWN;\nTOKEN = [a-z]+\n", 2, "@skip requires"),
            ("\nTOKEN = [a-z]+\nTOKEN = [a-z]+\n", 2, "duplicate lexer rule TOKEN"),
        ]:
            with self.subTest(message=message):
                leaf.write_text(text)
                diagnostic = self.assert_failure(main, message)
                self.assertIn(f"{leaf}:{line}:", diagnostic)
                self.assertIn(message, diagnostic)
                self.assertIn(f"included from {child}:1:", diagnostic)
                self.assertIn(f"included from {main}:1:", diagnostic)
        if self.backend == "c":
            leaf.write_text("\n@unsupported opaque;\nTOKEN = [a-z]+\n")
            diagnostic = self.assert_failure(main, "C target does not support @unsupported")
            self.assertIn(f"{leaf}:2:", diagnostic)

    def test_existing_bad_candidate_is_not_silently_skipped(self):
        main = self.write("grammar/main.cpg", '@include token.cpg;\nentry : TOKEN ;\n')
        (main.parent / "token.cpg").mkdir()
        self.write("fallback/token.cpg", 'TOKEN = "ok"\n')
        self.assert_failure(
            main, "expected a readable regular grammar file",
            "--include-path", str(self.directory / "fallback"),
        )

    @unittest.skipIf(os.geteuid() == 0, "root can read mode-000 files")
    def test_unreadable_file_reports_include_site(self):
        main = self.write("main.cpg", '@include token.cpg;\nentry : TOKEN ;\n')
        token = self.write("token.cpg", 'TOKEN = "ok"\n')
        token.chmod(0)
        self.addCleanup(token.chmod, 0o600)
        diagnostic = self.assert_failure(main, "Cannot open file")
        self.assertIn(f"{main}:1:", diagnostic)
        self.assertIn(str(token), diagnostic)

    def test_include_depth_is_bounded(self):
        for i in range(127):
            self.write(f"{i}.cpg", f"@include {i + 1}.cpg;\n")
        leaf = self.write("127.cpg", 'entry : TOKEN ;\nTOKEN = "ok"\n')
        result = self.invoke(self.directory / "0.cpg")
        self.assertEqual(result.returncode, 0, result.stderr)
        leaf.write_text("@include 128.cpg;\n")
        self.write("128.cpg", 'entry : TOKEN ;\nTOKEN = "ok"\n')
        self.assert_failure(self.directory / "0.cpg", "grammar include limit exceeded")

    def test_distinct_file_limit_and_duplicates_at_limit(self):
        includes = []
        for i in range(1023):
            self.write(f"parts/{i}.cpg", "")
            includes.append(f"@include parts/{i}.cpg;\n")
        main = self.write(
            "main.cpg",
            "".join(includes) + '@include parts/0.cpg;\nentry : TOKEN ;\nTOKEN = "ok"\n',
        )
        result = self.invoke(main)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.write("parts/extra.cpg", "")
        with main.open("a") as output:
            output.write("@include parts/extra.cpg;\n")
        self.assert_failure(main, "grammar include limit exceeded")

    def test_includes_cannot_split_declarations_or_expressions(self):
        main = self.write("main.cpg", "")
        self.write("token.cpg", 'TOKEN = "ok"\n')
        for text in [
            'entry : @include token.cpg; TOKEN ;\n',
            'TOKEN = [a-z] @include token.cpg;\nentry : TOKEN ;\n',
            '@include incomplete.cpg;\nTOKEN ;\n',
        ]:
            with self.subTest(text=text):
                self.write("incomplete.cpg", "entry :\n")
                main.write_text(text)
                message = "parser rule must end" if text.startswith("@include") else "unsupported"
                self.assert_failure(main, message)

    def test_nested_include_uses_resolved_symlink_directory(self):
        self.write("real/entry.cpg", '@include token.cpg;\nentry : TOKEN ;\n')
        self.write("real/token.cpg", 'TOKEN = "real"\n')
        self.write("links/token.cpg", 'TOKEN = "link"\n')
        (self.directory / "links/entry.cpg").symlink_to(
            self.directory / "real/entry.cpg"
        )
        main = self.write("main.cpg", "@include links/entry.cpg;\n")
        result = self.invoke(main)
        self.assertEqual(result.returncode, 0, result.stderr)
        parsed = self.parse(self.compile_generated(), "real")
        self.assertEqual(parsed.returncode, 0, parsed.stdout + parsed.stderr)

    def test_symlink_aliases_share_identity_and_detect_cycles(self):
        main = self.write(
            "main.cpg",
            '@include token.cpg;\n@include alias.cpg;\nentry : TOKEN ;\n',
        )
        token = self.write("token.cpg", 'TOKEN = "ok"\n')
        (self.directory / "alias.cpg").symlink_to(token)
        result = self.invoke(main)
        self.assertEqual(result.returncode, 0, result.stderr)
        token.write_text("@include alias.cpg;\nTOKEN = [a-z]+\n")
        self.assert_failure(main, "include cycle")

    def test_hard_links_are_distinct_include_sources(self):
        main = self.write(
            "main.cpg", "@include token.cpg;\n@include alias.cpg;\nentry : TOKEN ;\n",
        )
        token = self.write("token.cpg", 'TOKEN = "ok"\n')
        os.link(token, self.directory / "alias.cpg")
        diagnostic = self.assert_failure(main, "duplicate lexer rule TOKEN")
        self.assertIn(f"{self.directory / 'alias.cpg'}:1:", diagnostic)
        self.assertIn(f"related: {token}:1:", diagnostic)

    def test_cli_validation_and_library_mode(self):
        main = self.write("main.cpg", '@include token.cpg;\nentry : TOKEN ;\n')
        self.write("token.cpg", 'TOKEN = "ok"\n')
        if self.backend == "cwhip":
            result = self.invoke(main, "--include-path", "", "--library")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("start {", self.generated.read_text())
        for options in [
            ["--unknown"], ["--include-path"], ["--target", "rust"],
            ["--library", "--target", "c"],
        ]:
            result = subprocess.run(
                [str(self.generator),
                 *(["--target", "c"] if self.backend == "c" else []),
                 str(main), str(self.generated), "--dot", str(self.graph), *options],
                capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("usage: cparsegen", result.stderr)

    def test_no_implicit_cwd_search(self):
        main = self.write("grammar/main.cpg", '@include token.cpg;\nentry : TOKEN ;\n')
        self.write("token.cpg", 'TOKEN = "ok"\n')
        result = self.invoke(main, cwd=self.directory)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("cannot find included grammar", result.stderr)

    def test_main_and_absolute_include_path_errors(self):
        self.assert_failure(self.directory / "missing.cpg", "readable regular grammar file")
        main = self.write("main.cpg", f'@include "{self.directory}/missing.cpg";\n')
        diagnostic = self.assert_failure(main, "readable regular grammar file")
        self.assertIn(f"{main}:1:", diagnostic)
        diagnostic = self.assert_failure(self.directory, "readable regular grammar file")
        self.assertIn(str(self.directory), diagnostic)

    def test_option_terminator_and_relative_main_diagnostic(self):
        self.write("-main.cpg", 'entry : TOKEN ;\nTOKEN = "ok"\n')
        result = self.invoke("-main.cpg", "--", cwd=self.directory)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.write("invalid.cpg", "entry TOKEN;\n")
        result = self.invoke("invalid.cpg", cwd=self.directory)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(
            result.stderr,
            "invalid.cpg:1:7: bytes 6-11: expected '=' or ':' after declaration name\n",
        )


class CIncludeTests(IncludeTests):
    backend = "c"


if __name__ == "__main__":
    unittest.main()

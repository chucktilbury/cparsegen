"""Real CLI generation, path derivation, and preflight output safety."""

import os
import subprocess

from generator_support import FIXTURE, GeneratorTestCase, c_compile_command


class CliTests(GeneratorTestCase):
    def write(self, name, text=None):
        path = self.directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(FIXTURE.read_text() if text is None else text)
        return path

    def invoke(self, *arguments):
        return subprocess.run(
            [str(self.generator), *map(str, arguments)],
            cwd=self.directory, capture_output=True, text=True, timeout=60,
        )

    def success(self, *arguments):
        result = self.invoke(*arguments)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def failure(self, status, message, *arguments):
        before = {
            path.relative_to(self.directory): path.read_bytes()
            for path in self.directory.rglob("*") if path.is_file()
        }
        result = self.invoke(*arguments)
        self.assertEqual(result.returncode, status, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertIn(message, result.stderr)
        after = {
            path.relative_to(self.directory): path.read_bytes()
            for path in self.directory.rglob("*") if path.is_file()
        }
        self.assertEqual(after, before, "failure created or changed a file")

    def compile_and_parse(self, output, mode):
        executable = self.directory / "parser"
        if mode == "c":
            command = c_compile_command(output, executable)
        else:
            if mode == "library":
                driver = self.write(
                    "driver.cw",
                    f'include "{output.name}"\n'
                    'start {\n'
                    '    InputScanner scanner("123+456")\n'
                    '    scanner.scan()\n'
                    '    GeneratedParser parser(scanner.tokens)\n'
                    '    print(format("{}\\n", parser.parseAll().render()))\n'
                    '}\n',
                )
                output = driver
            command = [str(self.compiler), str(output), "-o", str(executable)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = (
            subprocess.run([str(executable)], capture_output=True, text=True, timeout=60)
            if mode == "library" else self.parse(executable, "123+456")
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "sum(INTEGER(123), @literal0(+), INTEGER(456))\n")

    def test_default_outputs_generate_compile_and_parse_all_modes_without_dot(self):
        self.write("grammar.cpg")
        for mode, options, suffix in [
            ("cwhip", [], ".cw"), ("c", ["--target", "c"], ".c"),
            ("library", ["--library"], ".cw"),
        ]:
            with self.subTest(mode=mode):
                self.success(*options, "grammar.cpg")
                output = self.directory / ("grammar" + suffix)
                self.assertTrue(output.is_file())
                self.assertFalse(list(self.directory.glob("*.dot")))
                self.compile_and_parse(output, mode)
                output.unlink()

    def test_explicit_output_and_optional_dot_match_default_artifacts(self):
        self.write("grammar.cpg")
        graph = None
        for options, suffix in [([], ".cw"), (["--library"], ".cw"), (["--target", "c"], ".c")]:
            with self.subTest(options=options):
                self.success("grammar.cpg", *options)
                default = self.directory / ("grammar" + suffix)
                self.success("grammar.cpg", "custom.output", "--dot", "graph.txt", *options)
                self.assertEqual((self.directory / "custom.output").read_bytes(), default.read_bytes())
                emitted = (self.directory / "graph.txt").read_bytes()
                self.assertIn(b"digraph", emitted)
                if graph is not None:
                    self.assertEqual(graph, emitted)
                graph = emitted
                self.success("--dot", "default.dot", *options, "grammar.cpg")
                self.assertEqual((self.directory / "default.dot").read_bytes(), graph)
                self.assertEqual((self.directory / "custom.output").read_bytes(), default.read_bytes())

    def test_omitting_dot_does_not_touch_existing_graph(self):
        self.write("grammar.cpg")
        graph = self.write("grammar.dot", "keep existing graph")
        self.success("grammar.cpg")
        self.assertEqual(graph.read_text(), "keep existing graph")

    def test_filename_derivation_last_extension_and_directory_preservation(self):
        for options, suffix in [([], ".cw"), (["--target", "c"], ".c"), (["--library"], ".cw")]:
            for name, stem in [
                ("plain", "plain"), ("many.parts.cpg", "many.parts"),
                (".grammar", ".grammar"), (".grammar.cpg", ".grammar"),
                ("trailing.", "trailing"), ("dir.v1/plain", "dir.v1/plain"),
                ("dir.v1/name with spaces.part.cpg", "dir.v1/name with spaces.part"),
            ]:
                with self.subTest(options=options, name=name):
                    grammar = self.write(name)
                    self.success(*options, grammar)
                    output = self.directory / (stem + suffix)
                    self.assertTrue(output.is_file(), str(output))
                    self.assertEqual(grammar.read_text(), FIXTURE.read_text())
                    output.unlink()
                    grammar.unlink()
        self.assertFalse(list(self.directory.rglob("*.dot")))

    def test_default_uses_supplied_symlink_name_not_resolved_target(self):
        self.write("real/original.cpg")
        (self.directory / "alias.cpg").symlink_to("real/original.cpg")
        self.success("alias.cpg")
        self.assertTrue((self.directory / "alias.cw").is_file())
        self.assertFalse((self.directory / "real/original.cw").exists())

    def test_options_interleave_with_paths_includes_and_target(self):
        self.write("source/main.cpg", "@include token.cpg;\nentry : TOKEN ;\n")
        self.write("search path/token.cpg", 'TOKEN = "ok"\n')
        for options, suffix in [([], ".cw"), (["--target", "c"], ".c"), (["--library"], ".cw")]:
            with self.subTest(options=options):
                self.success(
                    "source/main.cpg", "--include-path", "missing", *options,
                    "--dot", "graph with spaces.dot", "--include-path", "search path",
                )
                self.assertTrue((self.directory / ("source/main" + suffix)).is_file())
                self.assertTrue((self.directory / "graph with spaces.dot").is_file())
                self.success(
                    "--include-path", "missing:search path", "source/main.cpg",
                    "explicit parser", *options,
                )
                self.assertEqual(
                    (self.directory / "explicit parser").read_bytes(),
                    (self.directory / ("source/main" + suffix)).read_bytes(),
                )

    def test_terminator_and_dash_prefixed_paths(self):
        self.write("-grammar.cpg")
        self.success("--", "-grammar.cpg")
        self.assertTrue((self.directory / "-grammar.cw").is_file())
        self.success("--dot", "-graph.dot", "--", "-grammar.cpg", "-parser.cw")
        self.assertTrue((self.directory / "-parser.cw").is_file())
        self.success("--dot", "./--graph.dot", "--", "-grammar.cpg")
        self.assertTrue((self.directory / "--graph.dot").is_file())
        self.failure(1, "readable regular grammar file", "--", "--target", "c")
        self.failure(2, "usage:", "--", "-grammar.cpg", "-parser.cw", "--dot", "new.dot")

    def test_usage_errors_never_create_or_truncate_files(self):
        self.write("grammar.cpg")
        self.write("parser.cw", "keep parser")
        self.write("graph.dot", "keep graph")
        for arguments in [
            [], ["--dot", "graph.dot"], ["grammar.cpg", "parser.cw", "graph.dot"],
            ["grammar.cpg", "parser.cw", "--unknown"],
            ["--unknown", "grammar.cpg"], ["--dot"],
            ["grammar.cpg", "--dot"], ["grammar.cpg", "--dot", ""],
            ["--dot", "--library", "grammar.cpg"],
            ["grammar.cpg", "--dot", "graph.dot", "--dot", "graph.dot"],
            ["--dot", "a.dot", "grammar.cpg", "--dot", "b.dot"],
            ["--target"], ["grammar.cpg", "--target"],
            ["--target", "rust", "grammar.cpg"],
            ["--target", "cwhip", "grammar.cpg"],
            ["--target", "c", "grammar.cpg", "--target", "c"],
            ["--library", "grammar.cpg", "--library"],
            ["--library", "grammar.cpg", "--target", "c"],
            ["--target", "c", "grammar.cpg", "--library"],
            ["grammar.cpg", "--include-path"],
            ["--include-path", "--dot", "graph.dot", "grammar.cpg"],
            [""], ["grammar.cpg", ""], ["--"],
        ]:
            with self.subTest(arguments=arguments):
                self.failure(2, "usage: cparsegen", *arguments)

    def test_input_and_validation_failures_preserve_default_and_explicit_outputs(self):
        for options, suffix in [([], ".cw"), (["--library"], ".cw"), (["--target", "c"], ".c")]:
            for existing in (False, True):
                for name, text, message in [
                    ("missing.cpg", None, "readable regular grammar file"),
                    ("syntax.cpg", "entry TOKEN;\n", "expected '=' or ':'"),
                    ("semantic.cpg", "entry : MISSING ;\nTOKEN = [a-z]+\n", "unknown lexer token"),
                    ("include.cpg", "@include missing-part.cpg;\n", "cannot find included grammar"),
                ]:
                    with self.subTest(options=options, name=name, existing=existing):
                        if text is not None:
                            self.write(name, text)
                        default = self.directory / (name.removesuffix(".cpg") + suffix)
                        explicit = self.directory / "explicit.output"
                        graph = self.directory / "failure.dot"
                        for path in (default, explicit, graph):
                            if existing:
                                path.write_text("keep me")
                            else:
                                path.unlink(missing_ok=True)
                        self.failure(1, message, *options, name)
                        self.failure(1, message, *options, "--dot", graph, name)
                        self.failure(1, message, *options, name, explicit, "--dot", graph)
        self.write("unsupported.cpg", "@unsupported opaque;\n" + FIXTURE.read_text())
        for existing in (False, True):
            for name in ("unsupported.c", "backend.dot"):
                path = self.directory / name
                if existing:
                    path.write_text("keep backend output")
                else:
                    path.unlink(missing_ok=True)
            self.failure(1, "does not support @unsupported",
                         "--target", "c", "--dot", "backend.dot", "unsupported.cpg")

    def test_input_output_collisions_include_implicit_defaults(self):
        for name, options in [
            ("grammar.cw", []), ("grammar.c", ["--target", "c"]),
            ("library.cw", ["--library"]),
        ]:
            self.write(name)
            self.failure(1, "path collision", *options, name)
            self.failure(1, "path collision", *options, name, "--dot", "new.dot")
        self.write("grammar.cpg")
        for arguments in [
            ["grammar.cpg", "grammar.cpg"],
            ["grammar.cpg", "--dot", "grammar.cpg"],
            ["grammar.cpg", "parser.cw", "--dot", "./parser.cw"],
            ["grammar.cpg", "--dot", "grammar.cw"],
            ["--target", "c", "grammar.cpg", "--dot", "grammar.c"],
            ["--library", "grammar.cpg", "--dot", "grammar.cw"],
        ]:
            self.failure(1, "path collision", *arguments)

    def test_normalized_absolute_symlink_and_hard_link_collisions(self):
        grammar = self.write("grammar.cpg")
        (self.directory / "subdir").mkdir()
        (self.directory / "dir-link").symlink_to(self.directory, target_is_directory=True)
        aliases = ["./grammar.cpg", "subdir/../grammar.cpg", "dir-link/grammar.cpg", str(grammar)]
        for name, link in [("symlink.cpg", os.symlink), ("hardlink.cpg", os.link)]:
            link(grammar, self.directory / name)
            aliases.append(name)
        for alias in aliases:
            with self.subTest(alias=alias):
                self.failure(1, "path collision", "grammar.cpg", alias)
                self.failure(1, "path collision", "grammar.cpg", "--dot", alias)
        for first, second in [
            ("parser.cw", "subdir/../parser.cw"),
            ("parser.cw", "dir-link/parser.cw"),
            ("parser.cw", str(self.directory / "parser.cw")),
        ]:
            self.failure(1, "path collision", "grammar.cpg", first, "--dot", second)
        parser = self.write("existing.cw", "keep parser")
        for name, link in [("parser-link", os.symlink), ("parser-hardlink", os.link)]:
            link(parser, self.directory / name)
            self.failure(1, "path collision", "grammar.cpg", parser, "--dot", name)

    def test_implicit_defaults_cannot_alias_input_through_links(self):
        for mode, options, suffix in [
            ("cwhip", [], ".cw"), ("library", ["--library"], ".cw"),
            ("c", ["--target", "c"], ".c"),
        ]:
            grammar = self.write(mode + ".cpg")
            output = self.directory / (mode + suffix)
            for link in (os.symlink, os.link):
                with self.subTest(mode=mode, link=link.__name__):
                    link(grammar, output)
                    self.failure(1, "path collision", *options, grammar)
                    self.failure(1, "path collision", *options, "--dot", "new.dot", grammar)
                    output.unlink()

    def test_outputs_cannot_overwrite_included_grammars(self):
        self.write("main.cpg", "@include token.cpg;\nentry : TOKEN ;\n")
        token = self.write("token.cpg", 'TOKEN = "ok"\n')
        (self.directory / "alias.cpg").symlink_to(token)
        os.link(token, self.directory / "hardlink.cpg")
        for output in ["token.cpg", "alias.cpg", "hardlink.cpg"]:
            self.failure(1, "path collision", "main.cpg", output)
            self.failure(1, "path collision", "main.cpg", "--dot", output)
        for options, suffix in [([], ".cw"), (["--target", "c"], ".c")]:
            self.write("default" + suffix, 'TOKEN = "ok"\n')
            self.write("default.cpg", f"@include default{suffix};\nentry : TOKEN ;\n")
            self.failure(1, "path collision", *options, "default.cpg")

    def test_unresolvable_output_paths_are_rejected_before_writing(self):
        self.write("grammar.cpg")
        (self.directory / "dangling").symlink_to("not-created")
        for path in ["missing-parent/parser.cw", "dangling"]:
            self.failure(1, "cannot resolve output paths", "grammar.cpg", path)
            self.failure(1, "cannot resolve output paths", "grammar.cpg", "--dot", path)

    def test_distinct_existing_output_files_may_be_replaced(self):
        self.write("grammar.cpg")
        parser = self.write("parser.cw", "old parser")
        graph = self.write("graph.dot", "old graph")
        self.success("grammar.cpg", parser, "--dot", graph)
        self.assertIn("GeneratedParser", parser.read_text())
        self.assertIn("digraph", graph.read_text())

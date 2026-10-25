"""Local Markdown links and selected runnable documentation, using unittest."""

import json
import os
import re
import subprocess
import unittest
from urllib.parse import unquote

from generator_support import GeneratorTestCase, ROOT


def tracked_markdown():
    return subprocess.run(
        ["git", "ls-files", "*.md"], cwd=ROOT, check=True,
        capture_output=True, text=True,
    ).stdout.splitlines()


def without_fences(text):
    return re.sub(r"^```[^\n]*\n.*?^```\s*$", "", text, flags=re.M | re.S)


def anchors(text):
    counts = {}
    result = set()
    for heading in re.findall(r"^#{1,6} (.+)$", without_fences(text), flags=re.M):
        slug = re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
        count = counts.get(slug, 0)
        counts[slug] = count + 1
        result.add(f"{slug}-{count}" if count else slug)
    return result


class DocumentationLinks(unittest.TestCase):
    def test_tracked_markdown_local_links_and_anchors(self):
        documents = [ROOT / path for path in tracked_markdown()]
        documents.extend(path for path in (ROOT / "doc").glob("*.md")
                         if path not in documents)
        for document in documents:
            text = without_fences(document.read_text())
            for target in re.findall(r"!?\[[^\]]*\]\(([^)\s]+)\)", text):
                if re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", target):
                    continue
                name, _, fragment = unquote(target).partition("#")
                path = (document.parent / name).resolve() if name else document
                with self.subTest(document=document.relative_to(ROOT), target=target):
                    self.assertTrue(path.exists(), f"missing local link: {target}")
                    if fragment and path.suffix == ".md":
                        self.assertIn(fragment, anchors(path.read_text()))


class DocumentationWorkflows(GeneratorTestCase):
    def setUp(self):
        super().setUp()
        (self.directory / "bin").mkdir()
        (self.directory / "bin/cparsegen").symlink_to(self.generator)
        for name in ("examples", "tests"):
            (self.directory / name).symlink_to(ROOT / name, target_is_directory=True)
        self.env = os.environ.copy()
        self.env["PATH"] = str(self.compiler.parent) + os.pathsep + self.env.get("PATH", "")

    def blocks(self, document, heading, language="sh"):
        text = (ROOT / document).read_text()
        section = text.split(heading + "\n", 1)[1]
        level = len(heading) - len(heading.lstrip("#"))
        section = re.split(r"^#{1," + str(level) + r"} ", section, maxsplit=1, flags=re.M)[0]
        return re.findall(r"^```" + language + r"\n(.*?)^```", section, re.M | re.S)

    def commands(self, text):
        result = subprocess.run(
            ["sh", "-eu", "-c", text], cwd=self.directory, env=self.env,
            capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")
        # Compiler progress is not the documented program output.
        return re.sub(r"^cwhip: built .*\n", "", result.stdout, flags=re.M)

    def test_reference_prefix_complete_json_and_words_commands(self):
        doc = "doc/INPUT-OUTPUT.md"
        self.commands("mkdir -p build/reference")
        output = self.commands(self.blocks(
            doc, "### End-to-end Cwhip example: prefix versus complete input",
        )[0])
        self.assertEqual(output, "sum(INTEGER(123))\n"
                         "sum(INTEGER(123), @literal0(+), INTEGER(456))\n")
        output = self.commands(self.blocks(
            doc, "### End-to-end C example: the same grammar, JSON output",
        )[0])
        expected = self.blocks(
            doc, "### End-to-end C example: the same grammar, JSON output", "json",
        )[0]
        self.assertEqual(json.loads(output), json.loads(expected))
        section = "### Whitespace, repetition, and a graph"
        output = self.commands(self.blocks(doc, section)[0])
        self.assertEqual(output, self.blocks(doc, section, "text")[1])
        self.assertEqual(
            (self.directory / "build/reference/shortest.dot").read_bytes(),
            (self.directory / "build/reference/shortest-c.dot").read_bytes(),
        )

    def test_reference_complete_c_and_cwhip_library_snippets(self):
        doc = "doc/INPUT-OUTPUT.md"
        section = "## Embedding a C parser"
        blocks = self.blocks(doc, section)
        self.commands(blocks[0])
        (self.directory / "build/reference-c/consumer.c").write_text(
            self.blocks(doc, section, "c")[0],
        )
        self.assertEqual(self.commands(blocks[1]), "words: 3 children\n")
        section = "## Embedding a Cwhip parser"
        self.assertEqual(self.commands(self.blocks(doc, section)[0]), "names=3\n")
        snippet = self.blocks(doc, section, "cwhip")[0]
        (self.directory / "build/reference-cwhip/snippet.cw").write_text(
            'include "parser.cw"\nstart {\n' + snippet + "\n}\n",
        )
        output = self.commands(
            "cwhip build/reference-cwhip/snippet.cw -o build/reference-cwhip/snippet\n"
            "build/reference-cwhip/snippet",
        )
        self.assertEqual(output, "words(IDENT(alpha), @literal0(,), IDENT(beta))\n")

    def test_documented_insertion_and_lexer_expression_commands(self):
        # The prerequisite generator is already built by CMake's test target.
        for section, expected in [
            ("## Code insertion", "words=3\n" * 2),
            ("## Composable lexer expressions",
             "assignment(@literal0(let), IDENT(total), @literal1(=), "
             "NUMBER(-12.5e+2), @literal2(;))\n" * 2),
        ]:
            with self.subTest(section=section):
                commands = self.blocks("doc/EXAMPLES.md", section)[0]
                commands = commands.removeprefix("cmake --build build\n")
                self.assertEqual(self.commands(commands), expected)

    def test_documented_manual_visitor_commands(self):
        doc = "doc/VISITORS.md"
        self.assertEqual(self.commands(self.blocks(
            doc, "## Build and run the standalone C consumer",
        )[1]), "names=3\n")
        self.assertEqual(self.commands(self.blocks(
            doc, "## Build and use the Cwhip consumer",
        )[0]), "names=3\nnames=2\nnames=1 (stopped)\n")

    def test_documented_include_default_output_workflow(self):
        commands = self.blocks("doc/INPUT-OUTPUT.md", "### Grammar includes")[0]
        self.assertEqual(self.commands(commands), "entry(WORD(alpha))\n" * 2)
        self.assertFalse(list((self.directory / "build/include-example").glob("*.dot")))

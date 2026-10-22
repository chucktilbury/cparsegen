"""Grammar-source provenance and diagnostic coordinate conventions."""

from generator_support import GeneratorTestCase


class SourceProvenanceTests(GeneratorTestCase):
    def write_bytes(self, name, content):
        path = self.directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def invoke(self, grammar):
        return self.generate(grammar)

    def test_tabs_crlf_and_utf8_keep_byte_based_columns_and_offsets(self):
        grammar = self.write_bytes(
            "tabbed.cpg",
            b"\tentry : MISSING ;\r\nTOKEN = [a-z]+\r\n",
        )
        result = self.invoke(grammar)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(
            result.stderr,
            f"{grammar}:1:10: bytes 9-16: unknown lexer token MISSING\n",
        )

        grammar = self.write_bytes(
            "utf8.cpg",
            "@note café;\nentry : MISSING ;\nTOKEN = [a-z]+\n".encode(),
        )
        result = self.invoke(grammar)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(
            result.stderr,
            f"{grammar}:2:9: bytes 21-28: unknown lexer token MISSING\n",
        )

        grammar = self.write_bytes(
            "utf8-column.cpg",
            "@note café; entry : MISSING ;\nTOKEN = [a-z]+\n".encode(),
        )
        result = self.invoke(grammar)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(
            result.stderr,
            f"{grammar}:1:22: bytes 21-28: unknown lexer token MISSING\n",
        )

    def test_eof_location_is_zero_width_after_final_byte(self):
        grammar = self.write_bytes("eof.cpg", b"entry : TOKEN")
        result = self.invoke(grammar)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(
            result.stderr,
            f"{grammar}:1:14: bytes 13-13: parser rule must end with ';'\n",
        )

    def test_parser_reference_and_directive_sites_are_source_located(self):
        grammar = self.write_bytes(
            "parser.cpg",
            b"entry : missing ;\nTOKEN = [a-z]+\n",
        )
        result = self.invoke(grammar)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(
            result.stderr,
            f"{grammar}:1:9: bytes 8-15: unknown parser rule missing\n",
        )

        grammar = self.write_bytes(
            "directive.cpg",
            b"entry : TOKEN ;\n@skip MISSING;\nTOKEN = [a-z]+\n",
        )
        result = self.invoke(grammar)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(
            result.stderr,
            f"{grammar}:2:1: bytes 16-30: @skip requires a declared lexer token name\n",
        )

    def test_nested_origin_duplicate_related_location_and_include_chain(self):
        main = self.write_bytes("main.cpg", b"@include parts/child.cpg;\n")
        child = self.write_bytes("parts/child.cpg", b"@include leaf.cpg;\n")
        leaf = self.write_bytes(
            "parts/leaf.cpg",
            b"entry : TOKEN ;\nTOKEN = [a-z]+\nTOKEN = [0-9]+\n",
        )
        result = self.invoke(main)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(
            result.stderr,
            f"{leaf}:3:1: bytes 31-36: duplicate lexer rule TOKEN\n"
            f"  related: {leaf}:2:1: bytes 16-21\n"
            f"  included from {child}:1:1: byte 0\n"
            f"  included from {main}:1:1: byte 0\n",
        )

    def test_lexer_expression_and_insertion_failures_point_to_the_origin(self):
        lexer = self.write_bytes(
            "lexer.cpg",
            b"entry : TOKEN ;\nTOKEN = \"unterminated\n",
        )
        result = self.invoke(lexer)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(
            result.stderr,
            f"{lexer}:2:9: bytes 24-37: unterminated quoted literal\n",
        )

        insertion = self.write_bytes(
            "insert.cpg",
            b"entry : TOKEN ;\nTOKEN = [a-z]+\n"
            b"@insert c file_post { \"unfinished",
        )
        result = self.invoke(insertion)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn(f"{insertion}:3:23: bytes 53-64:", result.stderr)
        self.assertIn("unterminated @insert quoted literal", result.stderr)
        self.assertFalse(self.generated.exists())
        self.assertFalse(self.graph.exists())

    def test_deep_include_diagnostic_chain_is_explicitly_truncated(self):
        for index in range(11):
            self.write_bytes(f"{index}.cpg", f"@include {index + 1}.cpg;\n".encode())
        leaf = self.write_bytes("11.cpg", b"entry : MISSING ;\nTOKEN = [a-z]+\n")
        result = self.invoke(self.directory / "0.cpg")
        self.assertEqual(result.returncode, 1)
        lines = result.stderr.splitlines()
        self.assertEqual(lines[0], f"{leaf}:1:9: bytes 8-15: unknown lexer token MISSING")
        self.assertEqual(len(lines), 10)
        for index, line in zip(range(10, 2, -1), lines[1:9]):
            self.assertEqual(line, f"  included from {self.directory / str(index)}.cpg:1:1: byte 0")
        self.assertEqual(lines[-1], "  included from ...")
        self.assertFalse(self.generated.exists())
        self.assertFalse(self.graph.exists())


class CSourceProvenanceTests(SourceProvenanceTests):
    backend = "c"


if __name__ == "__main__":
    import unittest

    unittest.main()

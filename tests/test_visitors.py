"""Exercise the generated public APIs through real handwritten consumers."""

import os
import subprocess

from generator_support import GeneratorTestCase, ROOT, c_compile_command


FIXTURES = ROOT / "tests/fixtures/visitor"


class VisitorTests(GeneratorTestCase):
    def setUp(self):
        super().setUp()
        self.env = os.environ.copy()
        for name in ("CWHIP_PACKAGE_PATH", "CWHIP_MODULE_DIR", "CWHIP_MODULE_REGISTRY",
                     "DESTDIR", "XDG_RUNTIME_DIR"):
            self.env.pop(name, None)
        for name in ("HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME",
                     "XDG_STATE_HOME"):
            path = self.directory / name.lower()
            path.mkdir()
            self.env[name] = str(path)
        self.env["CWHIP_REGISTER_SDK"] = "OFF"

    def consumer(self, backend, grammar, source):
        suffix = ".c" if backend == "c" else ".cw"
        parser = self.directory / ("parser" + suffix)
        result = subprocess.run(
            [str(self.generator), *(["--target", "c"] if backend == "c" else ["--library"]),
             str(grammar), str(parser), "--dot", str(self.graph)],
            env=self.env, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        app = self.directory / ("consumer" + suffix)
        app.write_text(source)
        executable = self.directory / ("consumer-" + backend)
        command = (c_compile_command(app, executable) if backend == "c" else
                   [str(self.compiler), str(app), "-o", str(executable)])
        result = subprocess.run(
            command, env=self.env, capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return executable

    def run_consumer(self, executable, *args):
        return subprocess.run(
            [str(executable), *args], env=self.env,
            capture_output=True, text=True, timeout=30,
        )

    def assert_contract(self, backend):
        executable = self.consumer(
            backend, FIXTURES / "grammar.cpg",
            (FIXTURES / ("consumer.c" if backend == "c" else "consumer.cw")).read_text(),
        )
        prefix = "e:entry p:pair "
        contents = "n:NUMBER l:NUMBER t:@literal0 l:@literal0 n:NUMBER l:NUMBER q:pair "
        cases = {
            "walk": (0, 2, prefix + contents + "e:empty l:empty l:entry "),
            "skip": (0, 0, prefix + "q:pair e:empty l:empty l:entry "),
            "stop": (2, 1, prefix + "n:NUMBER "),
            "error": (-1, 1, prefix + "n:NUMBER "),
            "leave-stop": (2, 2, prefix + contents),
            "leave-error": (-1, 2, prefix + contents),
            "leave-skip": (-1, 2, prefix + contents),
            "invalid-leave": (-1, 2, prefix + contents),
            "invalid-enter": (-1, 0, prefix),
            "dispatch": (0, 0, "d:entry "),
            "dispatch-stop": (2, 0, "d:entry "),
            "dispatch-error": (-1, 0, "d:entry "),
            "dispatch-skip": (1, 0, "d:entry "),
            "dispatch-invalid": (-1, 0, "d:entry "),
            "unknown": (0, 0, "e:custom l:custom "),
            "null": (-1, 0, ""),
        }
        for mode, (status, count, events) in cases.items():
            with self.subTest(backend=backend, mode=mode):
                result = self.run_consumer(executable, mode)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(result.stderr, "")
                self.assertEqual(result.stdout, f"{status}|{count}|{events}\n")

    def test_c_contract(self):
        self.assert_contract("c")

    def test_cwhip_contract(self):
        self.assert_contract("cwhip")

    def assert_example(self, backend):
        source = ROOT / "examples/visitor" / ("words.c" if backend == "c" else "words.cw")
        executable = self.consumer(backend, ROOT / "examples/words.cpg", source.read_text())
        for arguments, status, output, problem in [
            (["alpha, beta, gamma"], 0, "names=3\n", ""),
            (["--dispatch", "alpha, beta"], 0, "names=2\n", ""),
            (["--first", "alpha, forbidden"], 0, "names=1 (stopped)\n", ""),
            (["alpha, forbidden"], 1, "", "identifier 'forbidden' is not allowed"),
            (["--dispatch", "alpha, forbidden"], 1, "", "identifier 'forbidden' is not allowed"),
            (["alpha,"], 1, "", "parse error"),
            (["alpha?"], 1, "", "lex error"),
            ([], 2, "", "usage:"),
        ]:
            with self.subTest(backend=backend, arguments=arguments):
                result = self.run_consumer(executable, *arguments)
                self.assertEqual(result.returncode, status, result.stdout + result.stderr)
                self.assertEqual(result.stdout, output)
                if problem:
                    self.assertIn(problem, result.stderr)
                else:
                    self.assertEqual(result.stderr, "")

    def test_c_example(self):
        self.assert_example("c")

    def test_cwhip_example(self):
        self.assert_example("cwhip")

    def test_left_recursive_library_tree_visitors_and_repeated_selection(self):
        grammar = self.directory / "left.cpg"
        grammar.write_text('entry : entry "+" NUMBER | NUMBER ;\nNUMBER = [0-9]\n')
        sources = {
            "c": r'''
#define CPARSEGEN_NO_MAIN
#include "parser.c"
#include <assert.h>
typedef struct { const Context *ctx; int rules, number; } Seen;
static CpgVisit rule(const Node *node, void *user) {
    Seen *seen = user;
    assert(!strcmp(cpg_node_kind(node), "entry"));
    ++seen->rules;
    return CPG_CONTINUE;
}
static CpgVisit number(const Node *node, void *user) {
    Seen *seen = user;
    assert(cpg_node_text_length(node) == 1);
    seen->number = seen->number * 10 + *cpg_node_text(seen->ctx, node) - '0';
    return CPG_CONTINUE;
}
int main(void) {
    Context ctx;
    cpg_init(&ctx, (const unsigned char *)"1+2+3", 5, "left");
    const Node *prefix = cpg_parse(&ctx, 0);
    assert(prefix && cpg_child_count(prefix) == 1);
    assert(cpg_child_at(prefix, 0)->offset == 0);
    const Node *root = cpg_parse(&ctx, 1);
    assert(root && cpg_child_count(root) == 3);
    assert(cpg_child_count(cpg_child_at(root, 0)) == 3);
    assert(cpg_child_count(cpg_child_at(cpg_child_at(root, 0), 0)) == 1);
    CpgVisitor visitor = {0};
    visitor.enter_rule_entry = rule;
    Seen seen = {&ctx, 0, 0};
    assert(cpg_walk(root, &visitor, &seen) == CPG_CONTINUE);
    assert(seen.rules == 3);
    const Node *digit = cpg_child_at(cpg_child_at(cpg_child_at(root, 0), 0), 0);
    assert(cpg_node_text_length(digit) == 1 && *cpg_node_text(&ctx, digit) == '1');
    visitor.enter_token_NUMBER = number;
    seen.rules = 0;
    assert(cpg_walk(root, &visitor, &seen) == CPG_CONTINUE);
    assert(seen.rules == 3 && seen.number == 123);
    cpg_destroy(&ctx);
    cpg_init(&ctx, (const unsigned char *)"1+", 2, "left");
    assert(!cpg_parse(&ctx, 1) && ctx.problem);
    assert(cpg_parse(&ctx, 0) && !ctx.problem);
    cpg_destroy(&ctx);
    return 0;
}
''',
            "cwhip": '''
include "parser.cw"
class Seen : GeneratedVisitor {
    int64 rules
    String digits
    Seen() { super GeneratedVisitor()
rules = 0
digits = "" }
    int64 enter_rule_entry(AstNode node) { rules += 1
return VISIT_CONTINUE }
    int64 enter_token_NUMBER(AstNode node) { digits.append(node.lexeme())
return VISIT_CONTINUE }
}
start {
    InputScanner scanner("1+2+3")
    if (!scanner.scan()) { Sys.Process().exit(10) }
    GeneratedParser parser(scanner.tokens)
    AstNode prefix = parser.parse_entry()
    if (prefix == null || prefix.childCount() != 1 || parser.position != 1) {
        Sys.Process().exit(11)
    }
    parser.position = 0
    AstNode root = parser.parseAll()
    if (root == null || root.childCount() != 3 || parser.position != 5
            || root.childAt(0).childCount() != 3
            || root.childAt(0).childAt(0).childCount() != 1) {
        Sys.Process().exit(12)
    }
    Seen visitor()
    if (visitor.walk(root) != visitor.VISIT_CONTINUE || visitor.rules != 3
            || !visitor.digits.equals("123")) { Sys.Process().exit(13) }
    InputScanner bad("1+")
    if (!bad.scan()) { Sys.Process().exit(14) }
    GeneratedParser retry(bad.tokens)
    if (retry.parseAll() != null || retry.position != 0 || retry.problem.equals("")) {
        Sys.Process().exit(15)
    }
    if (retry.parse_entry() == null || retry.position != 1 || !retry.problem.equals("")) {
        Sys.Process().exit(16)
    }
}
''',
        }
        for backend, source in sources.items():
            with self.subTest(backend=backend):
                result = self.run_consumer(self.consumer(backend, grammar, source))
                self.assertEqual((result.returncode, result.stdout, result.stderr),
                                 (0, "", ""))

    def test_c_library_reports_failures_without_exiting_or_printing(self):
        grammar = self.directory / "recursive.cpg"
        grammar.write_text('entry : NUMBER | "(" entry ")" ;\nNUMBER = [0-9]+\n')
        executable = self.consumer("c", grammar, r'''
#define CPARSEGEN_NO_MAIN
#include "parser.c"
#include <assert.h>
static void rejected(const unsigned char *input, size_t length, const char *message,
                     size_t offset) {
    Context parser;
    cpg_init(&parser, input, length, "test");
    assert(!cpg_parse(&parser, 1));
    assert(parser.problem && !strcmp(parser.problem, message));
    assert(parser.error_offset == offset);
    cpg_destroy(&parser);
    cpg_destroy(&parser);
}
int main(void) {
    rejected((const unsigned char *)"?", 1, "lex error", 0);
    rejected((const unsigned char *)"(1", 2, "parse error", 2);
    rejected((const unsigned char *)"", 0, "parse error", 0);
    rejected(NULL, 0, "invalid input or C runtime input limit exceeded", 0);
    rejected((const unsigned char *)"", 1024u * 1024u + 1,
             "invalid input or C runtime input limit exceeded", 0);
    unsigned char deep[601];
    memset(deep, '(', 300);
    deep[300] = '1';
    memset(deep + 301, ')', 300);
    Context parser;
    cpg_init(&parser, deep, sizeof(deep), "deep");
    assert(!cpg_parse(&parser, 1));
    assert(!strcmp(parser.problem, "parser resource limit exceeded"));
    cpg_destroy(&parser);
    cpg_init(&parser, (const unsigned char *)"12", 2, "good");
    assert(cpg_parse(&parser, 1));
    cpg_destroy(&parser);
    return 0;
}
''')
        result = self.run_consumer(executable)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))

    def test_library_tokens_tree_shapes_and_retained_roots(self):
        grammar = self.directory / "lifetime.cpg"
        parts = self.directory / "parts"
        parts.mkdir()
        grammar.write_text(
            '@include parts/entry.cpg;\n@include parts/tokens.cpg;\n',
        )
        (parts / "entry.cpg").write_text(
            'entry : item ("," item)* empty ;\nitem : WORD ;\nempty : ;\n'
            '@include tokens.cpg;\n',
        )
        (parts / "tokens.cpg").write_text(
            'WORD = LETTER+\nLETTER = [a-z]\nSPACE = [ \\t\\r\\n]+\n@skip SPACE;\n'
            '@block_comment /* */;\n'
        )
        sources = {
            "c": r'''
#define CPARSEGEN_NO_MAIN
#include "parser.c"
#include <assert.h>
int main(void) {
    const unsigned char input[] = {' ', 'a', 'b', ',', '\r', '\n', 'c'};
    Context ctx, other;
    cpg_init(&ctx, input, sizeof(input), "borrowed");
    const Node *root = cpg_parse(&ctx, 1);
    assert(root && !ctx.problem && ctx.token_count == 3);
    assert(ctx.input == input && ctx.length == sizeof(input));
    assert(!strcmp(ctx.tokens[0].kind, "WORD") && ctx.tokens[0].offset == 1);
    assert(ctx.tokens[0].length == 2 && ctx.tokens[1].offset == 3);
    assert(ctx.tokens[2].offset == 6 && ctx.tokens[2].length == 1);
    assert(!strcmp(cpg_node_kind(root), "entry") && cpg_child_count(root) == 4);
    assert(root->offset == 0 && cpg_node_text_length(root) == 0);
    const Node *word = cpg_child_at(cpg_child_at(root, 0), 0);
    assert(cpg_node_text(&ctx, word) == input + 1);
    assert(cpg_node_text_length(word) == 2);
    assert(!memcmp(cpg_node_text(&ctx, word), "ab", 2));
    assert(!strcmp(cpg_node_kind(cpg_child_at(root, 1)), "@literal0"));
    const Node *empty = cpg_child_at(root, 3);
    assert(!strcmp(cpg_node_kind(empty), "empty") && cpg_child_count(empty) == 0);
    assert(!cpg_child_at(root, 4) && !cpg_child_at(root, (size_t)-1));
    cpg_init(&other, (const unsigned char *)"z", 1, "other");
    assert(cpg_parse(&other, 1));
    cpg_destroy(&other);
    assert(cpg_parse(&ctx, 0));
    assert(!memcmp(cpg_node_text(&ctx, word), "ab", 2));
    assert(cpg_child_count(root) == 4);
    cpg_destroy(&ctx);
    cpg_destroy(&ctx);
    return 0;
}
''',
            "cwhip": '''
include "parser.cw"
class Retained {
    AstNode tree() {
        InputScanner scanner(" ab,\\r\\nc")
        if (!scanner.scan() || scanner.tokens.length != 3) { Sys.Process().exit(10) }
        LexToken first = scanner.tokens[0] as LexToken
        LexToken last = scanner.tokens[2] as LexToken
        if (!first.kind.equals("WORD") || !first.text.equals("ab")
                || first.offset != 1 || last.offset != 6) { Sys.Process().exit(11) }
        GeneratedParser parser(scanner.tokens)
        AstNode root = parser.parseAll()
        if (root == null || parser.position != 3 || root.childCount() != 4
                || !root.lexeme().equals("") || !root.childAt(3).kind().equals("empty")
                || root.childAt(3).childCount() != 0) { Sys.Process().exit(12) }
        scanner.input = "?"
        if (scanner.scan() || scanner.errorOffset != 0
                || !scanner.problem.equals("lex error at byte 0")) { Sys.Process().exit(13) }
        scanner.input = "z"
        if (!scanner.scan() || scanner.tokens.length != 1 || scanner.errorOffset != -1
                || !scanner.problem.equals("")) { Sys.Process().exit(14) }
        parser.position = 0
        if (parser.parse_item() == null || parser.position != 1) { Sys.Process().exit(15) }
        if (parser.parse_item() != null || parser.position != 1
                || parser.problem.equals("")) { Sys.Process().exit(16) }
        parser.position = 2
        if (parser.parseAll() == null || parser.position != 3
                || !parser.problem.equals("")) { Sys.Process().exit(17) }
        return root
    }
}
start {
    AstNode root = Retained().tree()
    if (!root.render().equals(
            "entry(item(WORD(ab)), @literal0(,), item(WORD(c)), empty())")) {
        Sys.Process().exit(18)
    }
}
''',
        }
        for backend, source in sources.items():
            with self.subTest(backend=backend):
                result = self.run_consumer(self.consumer(backend, grammar, source))
                self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))

    def test_legacy_cwhip_visitor_remains_rule_only_and_ordered(self):
        executable = self.consumer("cwhip", FIXTURES / "grammar.cpg", '''
include "parser.cw"
class Legacy : GeneratedVisitor {
    String events
    Legacy() { super GeneratedVisitor()
events = "" }
    void pre_entry(AstNode node) { events.append("pre:entry ") }
    void post_entry(AstNode node) { events.append("post:entry ") }
    void pre_pair(AstNode node) { events.append("pre:pair ") }
    void post_pair(AstNode node) { events.append("post:pair ") }
    void pre_empty(AstNode node) { events.append("pre:empty ") }
    void post_empty(AstNode node) { events.append("post:empty ") }
    int64 enter(AstNode node) { Sys.Process().exit(20)
return VISIT_ERROR }
    int64 onNode(AstNode node) { Sys.Process().exit(21)
return VISIT_ERROR }
}
start {
    InputScanner scanner("12+34")
    if (!scanner.scan()) { Sys.Process().exit(10) }
    GeneratedParser parser(scanner.tokens)
    AstNode root = parser.parseAll()
    if (root == null) { Sys.Process().exit(11) }
    Legacy visitor()
    visitor.visit(root)
    print(visitor.events)
}
''')
        result = self.run_consumer(executable)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (
            0, "pre:entry pre:pair post:pair pre:empty post:empty post:entry ", "",
        ))

    def test_c_allocation_failures_and_arena_boundary_are_recoverable(self):
        grammar = self.directory / "allocation.cpg"
        grammar.write_text('entry : NUMBER "+" NUMBER ;\nNUMBER = [0-9]+\n')
        executable = self.consumer("c", grammar, r'''
#include <stdlib.h>
#include <assert.h>
static size_t calls, fail_at, live;
static void *fault_malloc(size_t size) {
    if (++calls == fail_at) return NULL;
    void *p = malloc(size);
    if (p) ++live;
    return p;
}
static void *fault_calloc(size_t count, size_t size) {
    if (++calls == fail_at) return NULL;
    void *p = calloc(count, size);
    if (p) ++live;
    return p;
}
static void fault_free(void *p) {
    if (p) { assert(live); --live; }
    free(p);
}
#define malloc fault_malloc
#define calloc fault_calloc
#define free fault_free
#define CPARSEGEN_NO_MAIN
#include "parser.c"
#undef malloc
#undef calloc
#undef free
int main(void) {
    size_t total = 0;
    for (size_t failure = 0; failure <= total; ++failure) {
        Context ctx;
        calls = 0;
        fail_at = failure;
        cpg_init(&ctx, (const unsigned char *)"12+34", 5, "allocation");
        const Node *root = cpg_parse(&ctx, 1);
        if (!failure) {
            assert(root && !ctx.problem);
            total = calls;
            assert(total > 10);
        } else {
            assert(!root && !strcmp(ctx.problem, "C runtime allocation failed"));
        }
        cpg_destroy(&ctx);
        cpg_destroy(&ctx);
        assert(live == 0);
    }
    static Context ctx;
    fail_at = 0;
    cpg_init(&ctx, (const unsigned char *)"", 0, "arena");
    if (!setjmp(ctx.failure)) {
        assert(allocate(&ctx, 64u * 1024u * 1024u, 1));
        assert(ctx.allocated == 64u * 1024u * 1024u);
        (void)allocate(&ctx, 1, 1);
        assert(!"allocation beyond budget succeeded");
    }
    assert(ctx.problem && !strcmp(ctx.problem, "C runtime memory limit exceeded"));
    cpg_destroy(&ctx);
    assert(!live && !ctx.allocated && !ctx.allocations);
    cpg_init(&ctx, (const unsigned char *)"12+34", 5, "retry");
    assert(cpg_parse(&ctx, 1));
    cpg_destroy(&ctx);
    assert(!live);
    return 0;
}
''')
        result = self.run_consumer(executable)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))

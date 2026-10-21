# Integrating a generated parser

cparsegen generates syntax infrastructure, not an application compiler. Keep
semantic state, symbol tables, diagnostics, evaluation, and code generation in
handwritten code. Both backends provide an optional, read-only visitor layer
over the existing AST. Parsing does not automatically run a visitor. Direct AST
access remains available; neither interface transfers ownership or supports
node mutation/replacement.

The runnable [C consumer](../examples/visitor/words.c) and
[Cwhip consumer](../examples/visitor/words.cw) use the existing
[words grammar](../examples/words.cpg). They count identifiers and reject the
application-defined name `forbidden`. This is a semantic policy, not a grammar
restriction. Neither example is an interpreter.

For an end-to-end compiler rather than a name-counting consumer, see the
[expression compiler](../examples/compiler/README.md): a generated parser builds
the AST, a handwritten validation walker and dispatch-based emitter produce C,
and tests compile and execute that C and assert the arithmetic result.
Its incremental [statement compiler](../examples/compiler/STATEMENTS.md)
demonstrates an application-owned symbol table surviving across declarations,
assignments, print statements, and nested `if`/`else`/`while` blocks, with
source-order semantic validation, control-flow-sensitive definite-assignment
checking, and C emission. Declarations may omit initializers; reads require
initialization on every incoming path. Both `if`/`else` arms must establish it;
an `if` without `else` or a possibly zero-iteration `while` cannot. This is
opt-in compiler behavior, not a parser restriction. Storage is program-wide;
visitor dispatch recursively emits conditions and bodies without introducing
block-local scopes. Functions and methods have isolated local tables. Its
object slice shares application-owned multi-class/member signatures,
tracks distinct `int`, `bool`, and class-specific reference identities, validates
nested member access, typed locals/fields/parameters/returns, and exact assignment/
call compatibility, and lowers construction, pointer aliases,
and static calls with explicit receiver pointers. A generated allocation list
owns objects until program exit and frees them through `atexit`; field
dereferences check for null. Conditions require `bool`, arithmetic requires `int`,
and comparisons produce `bool`; there are no implicit conversions. Expression
diagnostics locate the first source token, since rule nodes have no source span.
Generated parsers remain syntax-only.

## Build and run the standalone C consumer

Run from the repository root, after selecting an installed SDK as described in
[Building](BUILDING.md):

```sh
cmake -S . -B build
cmake --build build --target cparsegen visitor-c
./bin/visitor-c 'alpha, beta, gamma'
./bin/visitor-c --dispatch 'alpha, beta'
./bin/visitor-c --first 'alpha, forbidden'
```

These print `names=3`, `names=2`, and `names=1 (stopped)`, respectively.
The optional CMake target generates `build/visitor-c/parser.c` and
`grammar.dot`, then compiles handwritten `examples/visitor/words.c`. It honors
`CWHIP_BIN_DIR`. Only generation needs the SDK; the consumer needs a host C99
compiler and the standard library.

The equivalent explicit generation/compilation sequence is:

```sh
mkdir -p build/visitor-manual-c
./bin/cparsegen --target c examples/words.cpg \
  build/visitor-manual-c/parser.c build/visitor-manual-c/grammar.dot
cc -std=c99 -Wall -Wextra -Werror -pedantic \
  -I build/visitor-manual-c examples/visitor/words.c \
  -o build/visitor-manual-c/words
build/visitor-manual-c/words 'alpha, beta, gamma'
```

`words.c` defines `CPARSEGEN_NO_MAIN` before including `parser.c`. This disables
only the generated CLI and its output helpers, not the scanner, parser, or
visitor. Include the generated source in **one translation unit**; do not also
compile it separately into the same executable. There is no separate header,
namespacing for multiple generated parsers in one executable, or
`--library --target c` command in this version.

The real public parse/visit lifecycle used by the consumer is:

```c
Context parser;
cpg_init(&parser, (const unsigned char *)input, strlen(input), "<argument>");
const Node *root = cpg_parse(&parser, 1); /* 1 = complete input, 0 = prefix */
if (!root) {
    fprintf(stderr, "%s:byte %zu: %s\n",
            parser.path, parser.error_offset, parser.problem);
    cpg_destroy(&parser);
    return 1;
}
Names names = {&parser, 0, 0, NULL, 0};
CpgVisitor visitor = {0};
visitor.enter_token_IDENT = count_name;
CpgVisit result = cpg_walk(root, &visitor, &names);
/* Inspect result and application-owned names.problem before reporting success. */
cpg_destroy(&parser);
```

`Names` and `count_name` are handwritten application symbols from the example;
`Context`, `Node`, `CpgVisitor`, `CpgVisit`, and the `cpg_*` functions are
generated. `CpgHook` has signature
`CpgVisit (*)(const Node *node, void *user)`. Zero-initialize the callback table;
unset kind-specific callbacks fall back to generic callbacks. The caller-owned
`void *` is passed unchanged to every callback. Separate parser and application
contexts are independent; there is no global visitor state.

`cpg_init` borrows the input bytes and path; it does not copy or free them.
Keep both alive and the input unchanged through parsing and all AST use.
Input need not be NUL-terminated. A non-NULL pointer is required even for an
empty input. The generated parser owns its arena allocations.
`cpg_parse` returns a borrowed root or NULL with `parser.problem` and a
zero-based `parser.error_offset`. In library use it prints nothing and never
exits the host process on lexical, parse, allocation, or resource errors.
Its internal resource-failure boundary does not invoke application callbacks.
Destroy the context on **both** success and failure. `cpg_destroy` frees the
arena, not the input or user context, and invalidates all AST/token pointers;
calling it twice is safe. Do not copy a live `Context` or parse concurrently
using the same context. Destroy and reinitialize before starting a fresh
parse to reset the cumulative allocation budget.

Node accessors require a live, non-NULL node:

| C accessor | Result |
| --- | --- |
| `cpg_node_kind(node)` | NUL-terminated grammar rule/token name or `@literalN` |
| `cpg_child_count(node)` | Number of stored children |
| `cpg_child_at(node, index)` | Borrowed child; NULL for an out-of-range index |
| `cpg_node_text(&parser, node)` | Borrowed byte slice; **not** a C string |
| `cpg_node_text_length(node)` | Slice length; zero for rule nodes, including empty rules |

Use length-bounded operations such as `memcmp` or `fwrite` on node text.
The public `Node` fields remain accessible. Terminals have byte offsets and
lengths into the input; rule nodes currently store zero offset/length, not a
computed source span. Do not infer token/rule identity merely from having no
children: an empty rule also has no children. For a rule diagnostic, an
application can locate its first terminal, or retain its own location index.

## Build and use the Cwhip consumer

With the same selected SDK, and `cwhip` on PATH:

```sh
mkdir -p build/visitor-manual-cwhip
./bin/cparsegen --library examples/words.cpg \
  build/visitor-manual-cwhip/parser.cw build/visitor-manual-cwhip/grammar.dot
cp examples/visitor/words.cw build/visitor-manual-cwhip/words.cw
cwhip build/visitor-manual-cwhip/words.cw -o build/visitor-manual-cwhip/words
build/visitor-manual-cwhip/words 'alpha, beta, gamma'
build/visitor-manual-cwhip/words --dispatch 'alpha, beta'
build/visitor-manual-cwhip/words --first 'alpha, forbidden'
```

`parser.cw` is generated without a `start` block; `words.cw` is handwritten,
includes it, and subclasses `GeneratedVisitor`. For example, its corresponding
single-node and walker hooks are:

```cwhip
int on_token_IDENT(AstNode node) {
    if (node.lexeme().equals("forbidden")) {
        problem = "identifier 'forbidden' is not allowed"
        return VISIT_ERROR
    }
    count += 1
    if (first) { return VISIT_STOP }
    return VISIT_CONTINUE
}
int enter_token_IDENT(AstNode node) {
    return on_token_IDENT(node)
}
```

These methods belong to `Names : GeneratedVisitor`; its constructor calls
`super GeneratedVisitor()` and initializes its own fields. Unoverridden
kind-specific methods call the corresponding generic method (`onNode`,
`enter`, or `leave`), using normal runtime method dispatch.

The full example checks `InputScanner.scan()` before constructing
`GeneratedParser(scanner.tokens)`, then checks `parser.parseAll()` for null.
Scanner failure is described by `scanner.problem`/`scanner.errorOffset`;
parser failure by `parser.problem`/`parser.errorPosition` (a token index).
It checks the visitor result separately from parse success. AST accessors are
`node.kind()`, `node.lexeme()`, `node.childCount()`, and `node.childAt(index)`.
Child indices must be in range; normal Cwhip list bounds errors propagate.
Rule text is empty; terminal text is the original spelling.
Existing `name`, `text`, and `children` fields remain available.

Cwhip objects and strings are managed references; there is no arena destroy
call. Keep the references needed by your pass, and release application-owned
resources explicitly as usual. Treat returned ASTs, strings, and lists as
read-only during visitation, even though the language permits mutation.

## Dispatch versus walking

For every grammar, hooks are generated for parser rules (`rule_NAME`), named
non-skipped tokens (`token_NAME`), and literals (`literal_N`). A literal's AST
kind remains `@literalN`; the hook uses a valid target-language identifier.
The number follows the generator's collected literal order and can change
when the grammar changes. For words, the hooks include `rule_words`,
`token_IDENT`, and `literal_0` (comma). No SmallC-specific vocabulary is
hardcoded. Whitespace/comments that are skipped do not produce AST nodes.

| Purpose | C | Cwhip |
| --- | --- | --- |
| Single-node operation | `cpg_dispatch(node, &visitor, user)` | `visitor.dispatch(node)` |
| Generic dispatch hook | `on_node` | `onNode(node)` |
| Specific dispatch hook | `on_rule_words` | `on_rule_words(node)` |
| Depth-first traversal | `cpg_walk(node, &visitor, user)` | `visitor.walk(node)` |
| Generic traversal hooks | `enter`, `leave` | `enter(node)`, `leave(node)` |
| Specific traversal hooks | `enter_token_IDENT`, `leave_token_IDENT` | Same method names |

Single-node dispatch invokes **one** selected `on_*` hook, falling back to
the generic hook. It does not call enter/leave hooks or traverse any children.
The example's `dispatch_words`/`on_rule_words` explicitly dispatches its
children, demonstrating application-owned order and result propagation.
The walker invokes enter, then children in stored order, then leave; it does
not invoke `on_*` hooks. A specific hook replaces, rather than additionally
invoking, the generic hook. With neither set, C defaults to continue.
Unknown/custom kinds fall back to generic hooks.

Use manual dispatch for evaluation, short-circuit operators, selected branches,
or passes where syntax order is not execution order. A generic DFS over an
`if` node visits both syntactic branches; it must not be mistaken for executing
the selected branch. An application handler can inspect children, compute its
own result in user state, dispatch only the chosen subtree, and propagate any
non-continue status. Evaluation and target-code generation belong to the
application, as demonstrated by the expression compiler, not the generated API.

| Hook result | C / Cwhip value | Walker behavior |
| --- | --- | --- |
| Continue | `CPG_CONTINUE` / `VISIT_CONTINUE` (`0`) | Enter descends; leave completes the node |
| Skip | `CPG_SKIP` / `VISIT_SKIP` (`1`) | Enter skips children **but still calls leave**; a successful skip completes as continue |
| Stop | `CPG_STOP` / `VISIT_STOP` (`2`) | Return stop immediately; intentional early termination, not an error |
| Error | `CPG_ERROR` / `VISIT_ERROR` (`-1`) | Return error immediately; application supplies the diagnostic |

Stop/error from either phase prevents all subsequent callbacks: no remaining
siblings and **no leave-hook unwind**, including for already-entered ancestors.
A leave hook cannot request skip; that result, or any unrecognized integer,
is normalized to error. Dispatch returns any of the four valid statuses
unchanged (skip has no implicit traversal effect). Null nodes, and a NULL C
visitor table, return error without calling hooks. Cwhip exceptions propagate
normally; they do not trigger leave hooks either. The caller must distinguish
stop from error and must not use leave as guaranteed resource cleanup.
Restore scope stacks/free temporary state outside the walk, including on
abort. Visitors do not store a hidden stopped flag: a later call is independent.

## Diagnostics and compiler integration

Try failures with either words executable:

```sh
./bin/visitor-c 'alpha?'            # lexical failure, exit 1
./bin/visitor-c 'alpha,'            # incomplete syntax, exit 1
./bin/visitor-c 'alpha, forbidden'  # application diagnostic, exit 1
```

Failures have no success output; the handwritten consumers report diagnostics
to stderr. The C example includes the offending token's byte offset.
`--first 'alpha, forbidden'` intentionally stops the semantic pass early and
succeeds with one name; it is **not** full semantic validation. Parsing still
checks the complete input first.

The real compiler-facing incremental consumer is
[SmallC](../examples/smallc/smallc.cw):

```sh
cmake --build build --target smallc
./bin/smallc-ast --check examples/smallc/valid/functions.c
```

`SmallCSemanticChecker` subclasses `GeneratedVisitor`. `parameterTypes`
resets application-owned name/type lists, walks a function's parameter list,
and propagates failure. `enter_rule_parameter` reads the parameter AST through
accessors, rejects duplicate names with the existing `fail` diagnostic helper,
records the signature type, and returns skip because it has handled that
parameter's subtree. The skip's default leave still runs. On a duplicate,
it returns error and preserves the first diagnostic. SmallC's existing
token-to-node location index supplies the source location; the generated
visitor does not maintain a symbol table or diagnostic system.

Other SmallC checks retain their direct-AST, source-order logic. This is
deliberately incremental: function signatures, scope/type state, and
control-flow rules belong to the application. `--check` still produces the
same JSON on success, and default syntax-only output on both backends is
unchanged. The older Cwhip `visit` with `pre_NAME`/`post_NAME` remains for
compatibility with its original rule-only traversal; new passes should use
the explicit `dispatch`/`walk` contracts above.

`make -C build test` compiles/runs both consumers and checks hook selection,
fallback, empty rules, terminal access, ordering, skip/leave, stop/error and
invalid-result propagation, dispatch without recursion, independent contexts,
and library parse/resource failures, alongside both existing parser suites.

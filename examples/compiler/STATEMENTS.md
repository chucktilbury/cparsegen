# A tiny statement-to-C compiler

This incremental companion to the [expression compiler](README.md) keeps its
arithmetic grammar, precedence, numeric representation, and visitor-dispatch
pattern, adding named bindings, source-order statements, and structured control
flow. It is a compiler,
not an interpreter: its stdout is C source, not the program's output.
The original `expression-compiler` and generated parser APIs are unchanged.

## Build, compile, and run

From the repository root, with the SDK selected as in
[Building](../../doc/BUILDING.md):

```sh
cmake -S . -B build
cmake --build build --target statement-compiler
./bin/statement-compiler examples/compiler/statements/basic.stmt \
  > build/statement-compiler/program.c
cc -std=c99 -Wall -Wextra -Werror -pedantic \
  build/statement-compiler/program.c -o build/statement-compiler/program
./build/statement-compiler/program
```

Output:

```text
20
56
28
```

The [sample](statements/basic.stmt) declares `total`, prints it, assigns a new
value, declares `twice` using the updated value, then prints both. Each print
and store executes in source order; bindings persist within the program.
CMake's executable honors `CWHIP_BIN_DIR` (default `bin/`).

For branches, loops, and nested blocks, compile the
[control-flow sample](statements/control-flow.stmt) through the same pipeline:

```sh
./bin/statement-compiler examples/compiler/statements/control-flow.stmt \
  > build/statement-compiler/control-flow.c
cc -std=c99 -Wall -Wextra -Werror -pedantic \
  build/statement-compiler/control-flow.c -o build/statement-compiler/control-flow
./build/statement-compiler/control-flow
```

It prints `3`, `3`, `3`, and `4` on separate lines. The first loop accumulates
`0 + 1 + 2`, the two conditionals select a true arm and a false arm, and the
inclusive-boundary loop executes once before its next condition check fails.
Standalone nested blocks group statements without creating lexical scopes.

## Explicit generation, syntax parsing, and compilation

```sh
cmake --build build --target cparsegen
mkdir -p build/statements-manual
./bin/cparsegen --target c examples/compiler/statements.cpg \
  build/statements-manual/parser.c build/statements-manual/grammar.dot
cc -std=c99 -Wall -Wextra -Werror -pedantic \
  build/statements-manual/parser.c -o build/statements-manual/syntax-parser
build/statements-manual/syntax-parser --json \
  examples/compiler/statements/basic.stmt
cc -std=c99 -Wall -Wextra -Werror -pedantic -I build/statements-manual \
  examples/compiler/statements.c -o build/statements-manual/statement-compiler
build/statements-manual/statement-compiler examples/compiler/statements/basic.stmt \
  > build/statements-manual/program.c
cc -std=c99 -Wall -Wextra -Werror -pedantic \
  build/statements-manual/program.c -o build/statements-manual/program
build/statements-manual/program
```

`statements.cpg` is the handwritten grammar. `parser.c` and `grammar.dot` are
generated; the parser owns the scanner, syntax AST, accessors, and visitor API.
`statements.c` is the handwritten compiler. It includes `parser.c` with
`CPARSEGEN_NO_MAIN`; do not compile the generated source separately into that
executable. Only generating the parser needs Cwhip; the consumer and emitted
program need only a C99 compiler and standard library.

The standalone generated parser is **syntax-only**. It does not invoke the
compiler's semantic visitor or emit executable code. Definite-assignment
checking is opt-in application/compiler behavior: running `statement-compiler`
enables it; generated parser modes do not.

## Visitor state and generated C

The compiler first parses the entire source file, then uses `cpg_dispatch` and
per-rule/token hooks for a semantic pass. A caller-owned `Compiler` context
holds an ordered symbol table of borrowed `IDENT` nodes and definite-initialization
flags. Generic callbacks
dispatch children in stored AST order; no generated walker is reimplemented.
Declaration callbacks check for duplicates, dispatch any initializer with the
current symbols, and only then add the new binding. Assignment callbacks
require an existing binding, validate the right-hand side, and only then mark
the binding initialized. Identifier
callbacks reject names not yet declared, including self-reference in an
initializer, and reads of declared but not definitely initialized bindings.
Control-flow callbacks snapshot entry flags, validate each arm from that entry
state, and intersect the flags after `if`/`else`. Loops and conditionals without
`else` restore the entry flags. Snapshots never remove textual declarations.
The context survives all statement callbacks, rather than being
recreated for each node. It is freed before destroying the parser and input.

Only a successful semantic pass starts output. A second visitor reuses the
completed symbol table and dispatches statements in source order. Declarations
with initializers and assignments emit stores; declarations without initializers
emit no store. Print callbacks emit checked `printf` calls,
converting comparison results to `double` for the variadic format.
The block callback dispatches its statement children between C braces.
Conditional and loop callbacks dispatch the condition and body blocks, emitting
`if`/`else` and `while` rather than evaluating conditions in the compiler.
Validation visits every body, including unreachable branches.
Expression callbacks follow the arithmetic example: grouping preserves
precedence and left associativity, and integer tokens become decimal `double`
constants (`000008` becomes `8.0`, never C octal). Identifiers map to stable
`cpg_v0`, `cpg_v1`, ... slots, so C keywords and names such as `printf` or `main`
are safe source-language variables. All slots are declared and zero-initialized
at the start of `main`, with an explicit `(void)` read to keep unused bindings
warning-free under strict C99. This storage initialization is a C-emission
detail, **not** a source-language fallback: the semantic visitor rejects reads
that would depend on it. Initializer expressions remain at their source
positions, so loop-body declarations reassign their slots on every iteration.

For example, `let x = 2; print x; x = x + 3; print x;` emits this shape
(expression parentheses/spacing abbreviated):

```c
#include <stdio.h>

int main(void) {
    double cpg_v0 = 0.0;
    (void)cpg_v0;
    cpg_v0 = 2.0;
    if (printf("%.17g\n", (double)cpg_v0) < 0) return 1;
    cpg_v0 = cpg_v0 + 3.0;
    if (printf("%.17g\n", (double)cpg_v0) < 0) return 1;
    return fflush(stdout) ? 1 : 0;
}
```

The emitted program prints `2` then `5`. The host C compiler, not the visitor,
performs expression code generation; the generated program stores and computes
the runtime values. See the [visitor contract](../../doc/VISITORS.md) for
dispatch behavior, AST lifetimes, and terminal source positions.

## Language and diagnostics

Programs contain zero or more statements:

```text
let name;
let name = expression;
name = expression;
print expression;
{ statements }
if (expression) { statements }
if (expression) { statements } else { statements }
while (expression) { statements }
```

There is one program-wide scope. Names are case-sensitive ASCII identifiers
matching `[a-zA-Z_][a-zA-Z0-9_]*`; `let`, `print`, `if`, `else`, and `while`
are keywords.
Declarations may omit initializers and cannot redeclare a name. Assignment does
not declare names. Arithmetic supports one-to-nine-digit integer literals,
unary `+`/`-`, binary `+`/`-`/`*`, and parentheses, just like the expression
example. Comparisons add `<`, `<=`, `>`, `>=`, `==`, and `!=`; their results
are numeric `0` or `1`, usable in prints, stores, arithmetic, and conditions.
Precedence from highest to lowest is parentheses, unary signs, multiplication,
addition/subtraction, relational comparisons, then equality/inequality.
Binary operators at each level associate left, including comparison chains:
`3 > 2 > 1` means `(3 > 2) > 1`, not a mathematical range test.
Zero is false; any nonzero value is true. `while` checks before every iteration.
Whitespace includes spaces, tabs, CR, and LF.

Control-flow conditions require parentheses and bodies require braces, with no
trailing semicolon. An `else` is optional and belongs to its braced `if`;
use `else { if (...) { ... } }` for an else-if chain. Empty bodies and arbitrary
nested blocks are supported within the parser's existing resource limits.

Name visibility still follows **textual declaration order**, not execution
order. A binding declared inside a block remains visible after the block;
shadowing or redeclaring it in any other block is an error, even in mutually
exclusive branches. References textually before a declaration (or in its own
initializer) fail. A later `else` arm can assign a name declared in the first arm,
but cannot assume that arm's initializer executed.

Definite-assignment checking follows control flow, separately from visibility:

- `let x;` declares an uninitialized binding. An initializer initializes a
  binding only when its declaration executes. Assignment initializes only
  after its right-hand side has been checked, so `let x; x = x + 1;` fails.
- Every read, including expressions, initializers, assignment right-hand sides,
  prints, and conditions, requires definite initialization.
- An `if`/`else` guarantees initialization afterward only if both arms guarantee
  it. Each arm starts from the same incoming initialization state.
- An `if` without `else` cannot establish initialization after the conditional.
  Conditions are not constant-folded: even `if (1) { x = 1; }` is conservative.
- A `while` may execute zero times. Its condition and body are checked using
  the incoming state; earlier assignments within that iteration count for later
  statements, but body assignments do not establish initialization afterward
  or justify a read before an assignment on the first iteration.
- Nested blocks share the same scope and propagate initialization in source
  order; nested branches and loops apply these same rules recursively.

For example, `let x; if (1) { x = 2; } else { x = 3; } print x;` is valid.
`if (0) { let x = 9; } print x;` and
`while (0) { let x = 9; } print x;` are semantic errors, not zero-valued reads.
Unreachable bodies are still checked.

```sh
./bin/statement-compiler examples/compiler/statements/use-before.stmt
# examples/compiler/statements/use-before.stmt:1:7: byte 6: use before declaration (unknown name): 'total'
./bin/statement-compiler examples/compiler/statements/duplicate.stmt
# examples/compiler/statements/duplicate.stmt:2:5: byte 19: duplicate declaration: 'total'
./bin/statement-compiler examples/compiler/statements/invalid-condition.stmt
# examples/compiler/statements/invalid-condition.stmt:2:8: byte 18: parse error
```

An assignment to an undeclared name reports `assignment to unknown name`.
An unknown right-hand-side name also reports use before declaration.
Reading a known but not definitely initialized binding reports
`read before definite initialization`.
These diagnostics include the file, one-based line/byte-column, zero-based
byte offset, and offending name. Lexical and parse errors also report source
locations. Syntax/semantic errors return `1` and emit **no C**, even if earlier
statements were valid. Incorrect argument counts return `2`. File-read and
C-source write failures return `1` with diagnostics; an I/O failure during
emission can leave partial C. The emitted program checks print and final
flush failures too.

The following still succeeds, demonstrating that semantic checks belong to
the application, not to the generated parser:

```sh
build/statements-manual/syntax-parser --json \
  examples/compiler/statements/use-before.stmt
```

This is deliberately not SmallC or the calculator CLI. There are no functions,
classes, nested scopes, logical `&&`/`||`/`!`, `break`/`continue`, comments,
strings, division, or fractions. Numbers use host C `double`; arithmetic
rounding, overflow, and finite-range checks are not implemented. Keep values
small enough for the host's range. The generated parser's existing input,
allocation, nesting, work, and result-count limits apply unchanged; this is a
bounded integration example, not a production language compiler.

## Tests

```sh
PYTHONPATH=tests python3 -m unittest test_statement_compiler test_compiler -v
make -C build test
```

The focused tests generate the real parser, compile the handwritten consumer
and standalone syntax parser, compile emitted programs with strict C99
warnings-as-errors, and compare exact execution output. They cover persistent
symbols and table growth, source order, arithmetic, all comparisons and their
precedence, true/false and nested branches, zero/one/many-iteration loops,
nested loops/blocks, optional initializers, initializer/assignment ordering,
both-arm intersection, one-arm/no-else rejection, zero-iteration conservatism,
block declarations and skipped initializers, C-safe identifier mapping,
unused bindings, empty programs, exact semantic locations, malformed syntax,
malformed conditions with source locations, file/usage errors, and syntax-only
acceptance of semantic failures inside control flow in C default, `--complete`,
and `--json` modes and Cwhip default/`--complete` modes. Existing
arithmetic tests run unchanged. The full target discovers both suites.
Direct test runs use the same SDK discovery and `CPARSEGEN_C_COMPILER`,
`CC`, and optional `CPARSEGEN_C_FLAGS` conventions as the expression tests.

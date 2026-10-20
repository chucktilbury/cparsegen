# A tiny statement-to-C compiler

This incremental companion to the [expression compiler](README.md) keeps its
arithmetic grammar, precedence, numeric representation, and visitor-dispatch
pattern, adding named bindings and source-order statements. It is a compiler,
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
compiler's semantic visitor or emit executable code.

## Visitor state and generated C

The compiler first parses the entire source file, then uses `cpg_dispatch` and
per-rule/token hooks for a semantic pass. A caller-owned `Compiler` context
holds an ordered symbol table of borrowed `IDENT` nodes. Generic callbacks
dispatch children in stored AST order; no generated walker is reimplemented.
Declaration callbacks check for duplicates, dispatch the initializer with the
current symbols, and only then add the new binding. Assignment callbacks
require an existing binding and validate the right-hand side. Identifier
callbacks reject names not yet declared, including self-reference in an
initializer. The context survives all statement callbacks, rather than being
recreated for each node. It is freed before destroying the parser and input.

Only a successful semantic pass starts output. A second visitor reuses the
completed symbol table and dispatches statements in source order. Declarations
and assignments emit stores; print callbacks emit checked `printf` calls.
Expression callbacks follow the arithmetic example: grouping preserves
precedence and left associativity, and integer tokens become decimal `double`
constants (`000008` becomes `8.0`, never C octal). Identifiers map to stable
`cpg_v0`, `cpg_v1`, ... slots, so C keywords and names such as `printf` or `main`
are safe source-language variables. An explicit `(void)` read keeps unused
bindings warning-free under strict C99.

For example, `let x = 2; print x; x = x + 3; print x;` emits this shape
(expression parentheses/spacing abbreviated):

```c
#include <stdio.h>

int main(void) {
    double cpg_v0 = 2.0;
    (void)cpg_v0;
    if (printf("%.17g\n", cpg_v0) < 0) return 1;
    cpg_v0 = cpg_v0 + 3.0;
    if (printf("%.17g\n", cpg_v0) < 0) return 1;
    return fflush(stdout) ? 1 : 0;
}
```

The emitted program prints `2` then `5`. The host C compiler, not the visitor,
performs expression code generation; the generated program stores and computes
the runtime values. See the [visitor contract](../../doc/VISITORS.md) for
dispatch behavior, AST lifetimes, and terminal source positions.

## Language and diagnostics

Programs contain zero or more semicolon-terminated statements:

```text
let name = expression;
name = expression;
print expression;
```

There is one program-wide scope. Names are case-sensitive ASCII identifiers
matching `[a-zA-Z_][a-zA-Z0-9_]*`; only `let` and `print` are keywords.
Declarations require initializers and cannot redeclare a name. Assignment does
not declare names. Arithmetic supports one-to-nine-digit integer literals,
unary `+`/`-`, binary `+`/`-`/`*`, and parentheses, just like the expression
example. Whitespace includes spaces, tabs, CR, and LF.

```sh
./bin/statement-compiler examples/compiler/statements/use-before.stmt
# examples/compiler/statements/use-before.stmt:1:7: byte 6: use before declaration (unknown name): 'total'
./bin/statement-compiler examples/compiler/statements/duplicate.stmt
# examples/compiler/statements/duplicate.stmt:2:5: byte 19: duplicate declaration: 'total'
```

An assignment to an undeclared name reports `assignment to unknown name`.
An unknown right-hand-side name also reports use before declaration.
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

This is deliberately not SmallC or the calculator CLI. There are no branches,
loops, functions, classes, nested scopes, comments, strings, division, fractions,
or uninitialized declarations. Numbers use host C `double`; arithmetic
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
symbols and table growth, source order, arithmetic, C-safe identifier mapping,
unused bindings, empty programs, exact semantic locations, malformed syntax,
file/usage errors, and syntax-only acceptance of semantic failures. Existing
arithmetic tests run unchanged. The full target discovers both suites.
Direct test runs use the same SDK discovery and `CPARSEGEN_C_COMPILER`,
`CC`, and optional `CPARSEGEN_C_FLAGS` conventions as the expression tests.

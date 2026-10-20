# An expression-to-C compiler

For the incremental example with persistent symbols, declarations, assignments,
source-order output, and structured control flow, see the
[tiny statement compiler](STATEMENTS.md).
This original arithmetic-only example remains independently runnable.

This small example demonstrates the full application workflow:

```text
compiler.cpg -> cparsegen -> parser.c -> AST -> handwritten visitor -> program.c
                                                                       |
                                                              host C compiler
                                                                       |
                                                              runnable program
```

Run from the repository root with the SDK selected as described in
[Building](../../doc/BUILDING.md). CMake builds the optional compiler example:

```sh
cmake -S . -B build
cmake --build build --target expression-compiler
./bin/expression-compiler '(2 + 3) * 4' > build/expression-compiler/program.c
cc -std=c99 -Wall -Wextra -Werror -pedantic \
  build/expression-compiler/program.c -o build/expression-compiler/program
./build/expression-compiler/program
```

The final executable prints `20`, not an AST. The expression compiler emits C
source on stdout; it neither evaluates the expression nor invokes `cc`.
Executables built by CMake honor `CWHIP_BIN_DIR` (default `bin/`).

## Explicit generation through execution

The equivalent steps without the example target show which files are generated:

```sh
cmake --build build --target cparsegen
mkdir -p build/compiler-manual
./bin/cparsegen --target c examples/compiler/compiler.cpg \
  build/compiler-manual/parser.c build/compiler-manual/grammar.dot
cc -std=c99 -Wall -Wextra -Werror -pedantic -I build/compiler-manual \
  examples/compiler/compiler.c -o build/compiler-manual/expression-compiler
build/compiler-manual/expression-compiler '2 + 3 * 4' > build/compiler-manual/program.c
cc -std=c99 -Wall -Wextra -Werror -pedantic \
  build/compiler-manual/program.c -o build/compiler-manual/program
build/compiler-manual/program
```

This prints `14`. Only building/running cparsegen needs Cwhip; compiling and
running the consumer or emitted C needs only a C99 compiler and standard library.

## Generated versus handwritten

- **Handwritten grammar:** [compiler.cpg](compiler.cpg) defines precedence,
  left-associative binary operations, unary signs, parentheses, and whitespace.
  There are no embedded code-generation actions.
- **Generated infrastructure:** `parser.c` contains the scanner, complete-input
  parser, owned AST arena, accessors, and visitor API. `grammar.dot` is the
  dependency graph. Do not edit either generated file.
- **Handwritten application:** [compiler.c](compiler.c) includes `parser.c` with
  `CPARSEGEN_NO_MAIN`, parses the argument, then calls `cpg_walk` with an integer
  validation hook. Only after validation succeeds does it emit a C program,
  using `cpg_dispatch` and per-rule/per-token `on_*` hooks. Rule hooks dispatch
  their children and wrap each rule in parentheses; C preserves the grammar's
  precedence and left associativity. The token hook normalizes leading zeros
  and emits decimal floating constants (`000008` becomes `8.0`, not C octal).
  The generated program performs the arithmetic and prints its result.

The application owns visitor state and diagnostics, propagates visitor errors,
and destroys the parser on success or failure. It never reimplements the
generated walker or dispatcher. Include `parser.c` in one translation unit;
do not also compile it separately. See the [visitor contract](../../doc/VISITORS.md)
for ownership, hooks, and error semantics.

## Language and limits

Supported syntax is unsigned decimal integer literals of **one to nine digits**
(including leading zeros), unary `+`/`-`, binary `+`/`-`/`*`, parentheses, and
whitespace. Unary signs bind tightest, then multiplication, then addition and
subtraction. There are deliberately no variables, assignments, division,
decimal fractions, functions, or control flow. Emitted arithmetic uses host C
`double`, not arbitrary-precision integers; rounding, overflow, and finite-range
checks are not implemented. Use small expressions whose intermediate values
fit the host's double range. This is an integration example, not a production
language compiler.

Parsing requires the entire input. Lexical/syntax errors and the application
literal-length check return `1`, write a byte-oriented diagnostic to stderr,
and emit no C. Usage errors return `2`. C-source write failures also return `1`
(a partial output file can remain on I/O failure). For example:

```sh
./bin/expression-compiler '2 +'             # parse error
./bin/expression-compiler '2 / 3'            # lex error: unsupported operator
./bin/expression-compiler '2 + 1234567890'   # application validation error
```

The generated parser's existing resource limits apply unchanged.

## End-to-end tests

```sh
PYTHONPATH=tests python3 -m unittest discover -s tests -p test_compiler.py -v
make -C build test
```

The focused suite runs cparsegen, compiles the real handwritten consumer with
the generated parser, parses representative expressions, compiles the emitted
C, executes it, and checks exact stdout, stderr, and exit status. It covers
precedence, parentheses, associativity, unary signs, leading zeros, whitespace,
and rejected input with no C output. The full `test` target discovers it
automatically.

Like the other generator suites, direct unittest execution skips the class
when cparsegen or the Cwhip compiler is unavailable. A configured but missing
generator is an error. A missing/failing host C compiler is an error, not a
silent skip. Direct tests honor `CPARSEGEN_C_COMPILER` (then `CC`, then `cc`)
and optional `CPARSEGEN_C_FLAGS`; `make test` supplies CMake's host compiler.

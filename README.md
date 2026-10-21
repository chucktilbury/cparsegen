# cparsegen

A Cwhip parser-generator prototype using a target-neutral grammar model and
backend emitters. The current executable is intentionally a small, bounded
slice; its supported syntax and unimplemented areas are listed in the
[architecture proposal](doc/ARCHITECTURE.md).

## Get started

Install the Cwhip SDK and its host prerequisites; cparsegen does not vendor,
download, or build the SDK during CMake configuration. Follow the
[Cwhip SDK installation guide](https://github.com/chucktilbury/cwhip/blob/master/doc/GETTING_STARTED.md#build-and-install-the-sdk)
to install a compiler-only SDK. Then configure/build and generate both
outputs:

```sh
./scripts/setup
cmake --build .
mkdir -p generated
../bin/cparsegen ../tests/fixtures/shortest.cpg generated/shortest.cw generated/shortest.dot
cwhip generated/shortest.cw -o generated/shortest-parser
printf '123+456' > generated/input.txt
generated/shortest-parser generated/input.txt
```

The default build type is `debug`. Choose `release` or `profile` with
`./scripts/setup release` or `./scripts/setup profile`.

## Generated examples

The [expression compiler](examples/compiler/README.md) demonstrates the complete
compiler workflow: grammar -> generated parser and AST -> handwritten visitor
-> emitted C -> compiled, executed program. Build the optional
`expression-compiler` target; the guide walks through every step and explains
which pieces are generated versus handwritten.

The [tiny statement compiler](examples/compiler/STATEMENTS.md) extends that
pattern with declarations, assignments, printing, braced `if`/`else` and `while`,
comparisons, nested blocks, and integer-valued functions with parameters,
locals, returns, forward calls, recursion, and one class with value-copy objects,
zero-initialized integer fields, field access/stores, and static method calls.
Its handwritten visitor collects class/member and function signatures, keeps
isolated function/method-local symbol tables with explicit receivers,
checks source-located semantic errors (including control-flow-sensitive reads
before definite initialization), and emits C prototypes/definitions plus
source-order statements. Build the optional `statement-compiler` target;
the original arithmetic compiler and syntax-only parsers remain unchanged.

Build a calculator with variables and an interactive CLI:

```sh
cmake --build build --target calculator
./bin/calculator
```

Try `x = 2 + 3 * 4`, `(x - 2) / 4`, and `:vars`. The calculator uses a
generated scanner/parser and a separate Cwhip evaluator, with arithmetic
precedence, parentheses, assignments, and complete-input checks.
See [Examples](examples/README.md) for batch mode, a comma-separated identifier
parser, the grammar files, and current limits.

The SmallC example generates a syntax AST for a C subset with `int`/`char`,
arrays and initializers, functions/prototypes/calls, comments, and control
flow. Its Cwhip app also offers an opt-in AST-based semantic check:

```sh
cmake --build build --target smallc
./bin/smallc-ast examples/smallc/valid/functions.c > build/smallc/functions.ast.json
./bin/smallc-ast --check examples/smallc/valid/functions.c
```

See [SmallC](examples/smallc/README.md) for the supported syntax and JSON
format, checked/deferred semantic rules, and type-conversion policy. It is not
a bytecode compiler or VM; the default CLI remains syntax-only.

## Standalone C target

The C backend generates standalone ISO C99 parsers for the calculator and
SmallC grammars, without embedding or invoking Cwhip:

```sh
cmake --build build --target calculator-c
printf 'x = 2 + 3 * 4' > build/calculator-c/input.txt
./bin/calculator-c --complete build/calculator-c/input.txt
cmake --build build --target smallc-c
./bin/smallc-c --json examples/smallc/valid/functions.c
```

This prints the syntax tree, **not** the calculated value. The optional target
creates `build/calculator-c/parser.c`, `build/calculator-c/grammar.dot`, and
`bin/calculator-c` (the executable follows `CWHIP_BIN_DIR`).
To generate and compile directly:

```sh
mkdir -p build/generated-c
./bin/cparsegen --target c examples/calculator/calculator.cpg \
  build/generated-c/parser.c build/generated-c/grammar.dot
cc -std=c99 build/generated-c/parser.c -o build/generated-c/parser
build/generated-c/parser --complete build/calculator-c/input.txt
```

The generated file needs only a host C compiler and standard C library;
neither the SDK nor a runtime template is needed to compile or run it.
The generator itself still requires the Cwhip SDK. Default generation and
`--library` remain Cwhip-only and unchanged.

The C slice supports the shared character-class regex/EBNF subset, including
`@skip`, forward references, non-left recursion, empty rules, keyword/reserved
discrimination, ASCII quoted character/string tokens, and line/block comments.
`--json` requires complete input and prints the same syntax-node schema as
the Cwhip SmallC frontend, with source-located errors on stderr. The existing
rendered-tree CLI and shortest-prefix default are unchanged. Unknown C-target
directives fail with a source-line error before outputs are opened (`@note`
is explicitly inert); malformed lexical directives also fail before output.
Define `CPARSEGEN_NO_MAIN` and include the generated C source to use its
parser/AST and visitor APIs from a handwritten application. Both targets offer
single-node dispatch and a controlled depth-first walker with per-kind and
generic hooks. See [Application integration](doc/VISITORS.md) for runnable C
and Cwhip consumers, ownership, diagnostics, and stop/error semantics.
There is no generated evaluator or SmallC semantic checking in the C backend;
the opt-in SmallC checker exists only in the Cwhip app layer.
See the [C target contract](doc/ARCHITECTURE.md#standalone-c-target-contract)
for exact output, tie-breaking, diagnostics, and resource limits.

## Tests

From the repository root, configure and run the full Python unittest suite:

```sh
cmake -S . -B build
cmake --build build --target test
```

With Unix Makefiles, `make -C build test` (or `make test` inside `build/`)
does the same thing. The target builds the generator first, then runs the
generator, grammar-conformance, standalone-C differential, visitor/compiler,
calculator, SmallC acceptance/differential, and SDK-discovery
tests with the configured SDK and private HOME/XDG directories. It honors
`CWHIP_BIN_DIR`; test failures fail the build target.

`tests/test_grammar_conformance.py` covers interleaved declaration collection
and forward references, opaque directive payloads, parser-rule whitespace and
comments through the terminating `;`, scanner longest-match competition, and
shortest-prefix selection with a longer alternative listed first. It also
checks source-located rejection of mixed declarations, embedded actions,
unsupported regex forms, and malformed grammar without creating either output.
The generator suite separately covers longer rule matches required by a
caller's continuation. These tests exercise the supported provisional subset,
not the architecture proposal's unimplemented grammar features.

The C tests compile generated source with the configured host C compiler
(`-std=c99 -Wall -Wextra -Werror -pedantic`), rerun the shared conformance
suite against C, and compare status/stdout/stderr and DOT output with Cwhip.
They cover calculator syntax, scanner longest match and equal-length ties,
shortest viable prefixes and caller continuations, complete input, EBNF,
empty rules, source-order ambiguity, malformed grammars, and explicit limits.
Every existing SmallC valid/invalid sample runs through both backends: tests
compare full JSON ASTs (rule/terminal names, nesting, and source spellings),
acceptance, and lexical/parser diagnostics including byte-oriented locations.
No unsupported sample is silently skipped. Both frontends also run the existing
SmallC precedence, dangling-else, quote/comment, and larger-input checks.
For direct unittest runs, `CPARSEGEN_C_COMPILER` overrides the compiler
(otherwise `CC`, then `cc`); `make test` supplies CMake's host compiler.
`CPARSEGEN_C_FLAGS` adds host compiler/linker flags for optional sanitizer runs.

## SDK selection

The project selects an installed SDK in this order: non-empty `CWHIP_SDK`,
the registered top-level `sdk_prefix` in
`$XDG_CONFIG_HOME/cwhip/sdk.toml` (or `$HOME/.config/cwhip/sdk.toml` when
`XDG_CONFIG_HOME` is unset or empty), then normal CMake discovery such as
`CMAKE_PREFIX_PATH`. The legacy `settings.toml` is read only when `sdk.toml`
does not exist, keeping SDK selection separate from editor preferences. See
[Building](doc/BUILDING.md) for override and troubleshooting details.

See [Building](doc/BUILDING.md) for SDK installation, selection, and
output-directory customization, and [Project shell](doc/PROJECT-SHELL.md) for
the shell environment and available commands. The architecture proposal and
provisional grammar fixtures are in [Architecture](doc/ARCHITECTURE.md),
[examples/expression.cpg](examples/expression.cpg), and
[tests/fixtures/shortest.cpg](tests/fixtures/shortest.cpg); none is a
finalized compatibility contract. See the
[changelog](doc/CHANGELOG.md) for updates.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).

# Generated examples

These examples use the installed Cwhip SDK and cparsegen, not handwritten
scanners or parsers. Run the commands below from the repository root. Configure
with `./scripts/setup` first, or use `cmake -S . -B build` with your SDK selected
as described in [Building](../doc/BUILDING.md).
The older `expression.cpg` remains a provisional left-recursive grammar sketch,
not a runnable example.

## Visitor application integration

[Application integration](../doc/VISITORS.md) walks through the runnable
[C](visitor/words.c) and [Cwhip](visitor/words.cw) consumers of `words.cpg`.
They demonstrate parsing, callback registration/subclass methods, application
state and diagnostics, AST access, controlled walking, manual dispatch,
early stop, and cleanup. Build the standalone example with
`cmake --build build --target visitor-c`, then run
`./bin/visitor-c 'alpha, beta'`.

## Expression-to-C compiler

The [compiler example](compiler/README.md) takes the workflow end to end:
grammar -> generated parser/AST -> handwritten visitor -> emitted C -> compiled,
executed program. Build with `cmake --build build --target expression-compiler`;
`./bin/expression-compiler '(2 + 3) * 4'` emits a C program that prints `20`
when compiled and run. The guide gives explicit generation and compilation
commands and distinguishes generated infrastructure from application code.

The incremental [statement compiler](compiler/STATEMENTS.md) adds `let`
declarations, assignments, `print`, comparisons, braced `if`/`else` and `while`,
and nested blocks, then typed functions, objects, single inheritance, and
virtual method dispatch, with persistent single-scope visitor symbols and
source-order C emission. Build with
`cmake --build build --target statement-compiler`, then run
`./bin/statement-compiler examples/compiler/statements/basic.stmt` to emit C.
The guide includes runnable samples for the compiler's incremental milestones,
including inheritance, and covers syntax-only parsing, compile/run steps,
semantic failures, and language limits.

## Calculator with variables

Build the generator, generate the calculator parser and DOT graph, and compile
the CLI:

```sh
cmake --build build --target calculator
./bin/calculator
```

An interactive session:

```text
calc> x = 2 + 3 * 4
x = 14
calc> y = (x - 2) / 4
y = 3
calc> -y + 0.5
-2.5
calc> :vars
x = 14
y = 3
calc> :quit
```

The calculator supports decimal numbers with digits on both sides of `.`,
case-sensitive identifiers, assignments, unary `+`/`-`, `+`, `-`, `*`, `/`,
parentheses, and whitespace. Multiplication/division bind more tightly than
addition/subtraction; both binary levels associate left. Arithmetic uses
Cwhip `float`, including fractional division. Exponents, functions, chained
assignments, and implicit multiplication are not supported.

Variables persist for one CLI session, not across invocations. `:help`,
`:vars`, and `:quit` are CLI commands; evaluation and variable storage are in
[calculator/calculator.cw](calculator/calculator.cw). The scanner, parser, AST,
and visitor are generated solely from
[calculator/calculator.cpg](calculator/calculator.cpg). Grammar rules contain
no evaluation code.

For a single expression or a non-interactive session:

```sh
./bin/calculator -e '(2 + 3) * 4'
printf 'x = 14\ny = x / 2\nx + y\n' | ./bin/calculator --batch
```

Every line must parse completely. Undefined variables, division by zero,
unrecognized characters, and syntax errors produce diagnostics on stderr and
an exit status of `1`. Batch/interactive sessions continue after an error;
failed assignments do not change the variable table. Usage errors return `2`.
Blank lines are ignored and EOF exits. `--batch` suppresses prompts.

The `calculator` target is optional, not part of the default generator build.
Its output follows `CWHIP_BIN_DIR` (default `bin/`). Generated
`build/calculator/parser.cw` is an includeable library with no `start` block;
`build/calculator/grammar.dot` is the dependency graph:

```sh
dot -Tsvg build/calculator/grammar.dot -o build/calculator/grammar.svg
```

## Comma-separated identifiers

[words.cpg](words.cpg) is a smaller example of character classes, repetition,
and skipped whitespace:

```sh
cmake --build build
mkdir -p build/words
./bin/cparsegen examples/words.cpg build/words/parser.cw build/words/grammar.dot
cwhip build/words/parser.cw -o build/words/parse-words
printf 'alpha, beta_2, gamma' > build/words/input.txt
build/words/parse-words --complete build/words/input.txt
```

Output:

```text
words(IDENT(alpha), @literal0(,), IDENT(beta_2), @literal0(,), IDENT(gamma))
```

The standalone generated runner retains shortest-prefix matching by default.
Use `--complete` to require the whole input, as above. Library consumers use
`GeneratedParser.parseAll()` for the same behavior. The calculator always
uses this complete-input API.

## Standalone C calculator syntax parser

```sh
cmake --build build --target calculator-c
printf '1 + 2' > build/calculator-c/input.txt
./bin/calculator-c --complete build/calculator-c/input.txt
```

This uses the same calculator grammar but generates
`build/calculator-c/parser.c` and `grammar.dot`, compiled with CMake's host C
compiler. The executable follows `CWHIP_BIN_DIR` (default `bin/`) and runs
without Cwhip or the SDK. Output is the same rendered syntax tree as the
standalone Cwhip parser, not the interactive calculator's evaluated result:

```text
statement(expression(product(unary(primary(number(INTEGER(1))))), @literal1(+), product(unary(primary(number(INTEGER(2)))))))
```

Omitting `--complete` selects the shortest successful prefix; the entire file
is still scanned. `--target c` supports this grammar's character classes,
skipped whitespace, and EBNF, as well as SmallC's lexical directives.
It has no evaluator or variable store. Define `CPARSEGEN_NO_MAIN` when including
the generated source to use its parser/visitor API from your own C application;
see [Application integration](../doc/VISITORS.md) and the
[C target contract](../doc/ARCHITECTURE.md#standalone-c-target-contract).

## Current limits

The generator now supports named parser-rule references, groups,
alternation, sequences, `?`/`*`/`+`, and explicit empty alternatives. Lexer
patterns are sequences of non-negated ASCII character classes with optional
`?`/`*`/`+`; `@skip TOKEN;` marks a whitespace-like token as discarded.
Lexer-rule composition, general regex groups/alternation, and escaped quoted
terminals remain unsupported.

Left recursion is diagnosed, not transformed: write expression levels as in
the calculator grammar. Parser repetition of a nullable expression is
rejected. The generated parser preserves alternatives until their surrounding
sequence can match, chooses the shortest successful prefix, and keeps source
order on equal-length ties. Whole-input mode requires a complete candidate
instead of discarding trailing tokens.

## SmallC syntax frontend

[SmallC](smallc/README.md) expands the examples to a C subset: `int`/`char`,
arrays and initializers, functions, prototypes, calls, arithmetic/comparisons,
comments, and `if`, `for`, `while`, `switch`, and `goto`. Build/run it with:

```sh
cmake --build build --target smallc
./bin/smallc-ast examples/smallc/valid/functions.c > build/smallc/functions.ast.json
./bin/smallc-ast --check examples/smallc/valid/functions.c > build/smallc/functions.checked.ast.json
```

Output is a complete-input **JSON syntax AST**, not bytecode or an executed
program. `--check` runs the Cwhip app's source-order semantic checker on the
AST; the default command remains syntax-only. See the SmallC documentation
for checked rules and deferred control-flow, array-bound, and runtime checks.

For a standalone C99 version of the same syntax frontend:

```sh
cmake --build build --target smallc-c
./bin/smallc-c --json examples/smallc/valid/functions.c > build/smallc-c/functions.ast.json
```

The generated `build/smallc-c/parser.c` compiles and runs without the SDK.
`--json` requires complete input and uses the Cwhip frontend's JSON schema and
source-located diagnostics. Without it, the executable retains the generic
rendered-tree/shortest-prefix CLI; use `--complete` for a complete rendered tree.
The standalone C parser does not evaluate SmallC or perform semantic checks;
`smallc-ast --check` is an app-layer feature and does not change either parser.

## Additional lexical directives

SmallC needs lexical behavior beyond the calculator's character classes.
The following additional directives work in both Cwhip and standalone C.
These features are generic and opt-in; existing grammars keep their old
literal-versus-token tie behavior:

| Directive | Meaning |
| --- | --- |
| `@keywords IDENT;` | When this named token wins longest match, remap exact grammar-literal spellings to their literal kinds; `if` becomes a keyword, `iffy` stays an identifier |
| `@reserved struct typedef;` | Reserve additional word spellings as unmatchable identifiers; requires `@keywords` |
| `@quoted CHAR single;` | Declare a single-quoted token containing exactly one printable ASCII byte or supported escape |
| `@quoted STRING double;` | Declare a double-quoted ASCII token; empty strings are allowed |
| `@line_comment //;` | Skip a marker through line end or EOF |
| `@block_comment /* */;` | Skip opening through closing marker; no nesting; an absent closer is an error |

Quote directives declare tokens, so do not also declare their names with
`=`. The supported quoted escapes are `\\`, `\"`, `\'`, `\n`, `\r`, `\t`,
and `\0`, retained verbatim in the token text. Malformed/unterminated quoted
tokens are errors. Comment markers are whitespace-separated opaque
spellings, not quoted strings; comments are recognized at token boundaries
before other lexer rules. If comment markers overlap, line-comment
declaration order is tried first, followed by block-comment declaration
order. Quotes consume their contents as a single token, so comment markers
inside a quoted token are not skipped.

## Resource bounds

This is a bounded backtracking implementation, not yet a production compiler
frontend. It reports resource limits rather than silently truncating parse
results: 256 nested parser-rule calls, 100,000 matcher calls per
parse, and 4,096 results per intermediate set. The scanner also limits pattern
matching to 100,000 calls per token. Full source spans, include stacks,
left-recursion normalization, richer lexer syntax, C++/Python backends, and
wider C grammar coverage remain future work. The standalone-C slice also
enforces 1 MiB input and 64 MiB cumulative arena-data limits.

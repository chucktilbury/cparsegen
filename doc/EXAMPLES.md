# Generated examples

These examples use the installed Cwhip SDK and cparsegen, not handwritten
scanners or parsers. Configure and start the project shell with
`./scripts/setup`, then return to the repository root with `cd ..` before
running `build [TARGET...]` and the root-relative commands below. See
[Building](BUILDING.md) for SDK selection.
The small `expression.cpg` demonstrates consuming left recursion and runs
with either backend; its original nested expression nodes are preserved.

## Visitor application integration

[Application integration](VISITORS.md) walks through the runnable
[C](../examples/visitor/words.c) and [Cwhip](../examples/visitor/words.cw) consumers of `words.cpg`.
They demonstrate parsing, callback registration/subclass methods, application
state and diagnostics, AST access, controlled walking, manual dispatch,
early stop, and cleanup. Build the standalone example with
`build visitor-c`, then run
`./bin/visitor-c 'alpha, beta'`.

## Code insertion

[insertion/words.cpg](../examples/insertion/words.cpg) puts trusted target-language
declarations/helpers beside generated code using
`@insert TARGET BOUNDARY { BODY };`. It supplies a C public prototype at
`ast_post`, a private visitor callback at `visitor_post`, and a public
parse/count helper at `parser_post`; Cwhip supplies a visitor subclass and
helper class at `visitor_post`. Both use normal AST/visitor/parser APIs;
there are no inline rule actions or generator-time execution.

Generate library parsers, then compile the tiny consumers:

```sh
build
mkdir -p build/insertion
./bin/cparsegen --target c examples/insertion/words.cpg \
  build/insertion/parser.c --dot build/insertion/grammar.dot
cp examples/insertion/words.c build/insertion/words.c
cc -std=c99 -Wall -Wextra -Werror -pedantic \
  build/insertion/words.c -o build/insertion/words-c
build/insertion/words-c

./bin/cparsegen --library examples/insertion/words.cpg \
  build/insertion/parser.cw --dot build/insertion/grammar.dot
cp examples/insertion/words.cw build/insertion/words.cw
cwhip build/insertion/words.cw -o build/insertion/words-cw
build/insertion/words-cw
```

Each prints `words=3`. The C consumer defines `CPARSEGEN_NO_MAIN`; Cwhip uses
`--library` so the consumer owns `start`. The same grammar also works with
both ordinary generated CLIs: helper declarations remain available but
are not called automatically. Blocks for the other target are not emitted.
See the [exact seams, preservation, restrictions and trust contract](INPUT-OUTPUT.md#code-insertion)
before accepting grammars containing code.

## Expression-to-C compiler

The [compiler example](EXPRESSION-COMPILER.md) takes the workflow end to end:
grammar -> generated parser/AST -> handwritten visitor -> emitted C -> compiled,
executed program. Build with `build expression-compiler`;
`./bin/expression-compiler '(2 + 3) * 4'` emits a C program that prints `20`
when compiled and run. The guide gives explicit generation and compilation
commands and distinguishes generated infrastructure from application code.

The incremental [statement compiler](../examples/compiler/STATEMENTS.md) adds `let`
declarations, assignments, `print`, comparisons, braced `if`/`else` and `while`,
and nested blocks, then typed `int`/`bool` functions (a bounded, non-object-oriented
demonstration), with persistent single-scope visitor symbols and
source-order C emission. Build with
`build statement-compiler`, then run
`./bin/statement-compiler examples/compiler/statements/basic.stmt` to emit C.
The guide includes runnable samples for the compiler's incremental milestones
and covers syntax-only parsing, compile/run steps,
semantic failures, and language limits.

## Calculator with variables

Build the generator, generate the calculator parser and DOT graph, and compile
the CLI:

```sh
build calculator
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
Cwhip `fp64` (64-bit floating point), including fractional division.
Exponents, functions, chained assignments, and implicit multiplication are
not supported.

Variables persist for one CLI session, not across invocations. `:help`,
`:vars`, and `:quit` are CLI commands; evaluation and variable storage are in
[calculator/calculator.cw](../examples/calculator/calculator.cw). The scanner, parser, AST,
and visitor are generated solely from
[calculator/calculator.cpg](../examples/calculator/calculator.cpg). Grammar rules contain
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

[words.cpg](../examples/words.cpg) is a smaller example of character classes, repetition,
and skipped whitespace:

```sh
build
mkdir -p build/words
./bin/cparsegen examples/words.cpg build/words/parser.cw --dot build/words/grammar.dot
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

## Composable lexer expressions

[lexer-expressions.cpg](../examples/lexer-expressions.cpg) composes signed decimal/exponent
numbers and identifiers from named helpers, including forward references:

```text
NUMBER = ("+" | "-")? DIGIT+ ("." DIGIT+)? EXP?
IDENT = LETTER (LETTER | DIGIT)*
EXP = [eE] ("+" | "-")? DIGIT+
DIGIT = [0-9]
LETTER = [A-Za-z_]
```

The complete grammar also declares `assignment`, skipped whitespace, keyword
remapping, and comments. Run it with either backend:

```sh
mkdir -p build/lexer-expressions
./bin/cparsegen examples/lexer-expressions.cpg \
  build/lexer-expressions/parser.cw --dot build/lexer-expressions/grammar.dot
cwhip build/lexer-expressions/parser.cw -o build/lexer-expressions/parse-cw
./bin/cparsegen --target c examples/lexer-expressions.cpg \
  build/lexer-expressions/parser.c --dot build/lexer-expressions/grammar.dot
cc -std=c99 -Wall -Wextra -Werror -pedantic \
  build/lexer-expressions/parser.c -o build/lexer-expressions/parse-c
printf 'let total = -12.5e+2; // amount\n' > build/lexer-expressions/input.txt
build/lexer-expressions/parse-cw --complete build/lexer-expressions/input.txt
build/lexer-expressions/parse-c --complete build/lexer-expressions/input.txt
```

Both print:

```text
assignment(@literal0(let), IDENT(total), @literal1(=), NUMBER(-12.5e+2), @literal2(;))
```

Helpers remain scanner candidates; declaring larger tokens first keeps their
token kinds on equal-length ties. References compose patterns, not parser/AST
nodes. See the [exact syntax, escaping, and limits](INPUT-OUTPUT.md#lexer-declarations).

## Standalone C calculator syntax parser

```sh
build calculator-c
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
see [Application integration](VISITORS.md) and the
[C target contract](ARCHITECTURE.md#standalone-c-target-contract).

## Current limits

The generator now supports named parser-rule references, groups,
alternation, sequences, `?`/`*`/`+`, and explicit empty alternatives. Lexer
patterns support ASCII classes/ranges/negation, quoted literals, named-rule
composition, groups, alternation, concatenation, and `?`/`*`/`+`.
`@skip TOKEN;` discards the winning token. Lexer patterns must be single-line,
nonnullable, and acyclic; there are no wildcard/anchor operators, counted
repetition, backreferences, or Unicode classes. Grammar literals support
`\\`, `\"`, `\'`, `\n`, `\r`, and `\t`.

Consuming direct/indirect left recursion, including nullable prefixes, is
supported by span-bounded expansion in both backends. Cycles with nullable
context on both sides are rejected because they admit infinitely many
equal-span trees. See the [left-recursion contract](INPUT-OUTPUT.md#left-recursion)
for examples and the exact rejection boundary. Parser repetition of a nullable
expression is rejected. The generated parser preserves alternatives until their surrounding
sequence can match, chooses the shortest successful prefix, and keeps source
order on equal-length ties. Whole-input mode requires a complete candidate
instead of discarding trailing tokens.

## SmallC frontend and CVM compiler

[SmallC](SMALLC.md) expands the examples to a C subset: `int`/`char`,
arrays and initializers, functions, prototypes, calls, arithmetic/comparisons,
comments, and `if`, `for`, `while`, `switch`, and `goto`. Build/run it with:

```sh
build smallc
./bin/smallc-ast examples/smallc/valid/functions.c > build/smallc/functions.ast.json
./bin/smallc-ast --check examples/smallc/valid/functions.c > build/smallc/functions.checked.ast.json
```

Output is a complete-input **JSON syntax AST**, not bytecode or an executed
program. `--check` runs the Cwhip app's source-order semantic checker on the
AST; the default command remains syntax-only. See the SmallC documentation
for checked rules and deferred control-flow, array-bound, and runtime checks.

An optional `smallc-cvm` target compiles the same checked AST to textual CVM
v1 assembly (`smallc-cvm INPUT.c OUTPUT.asm`). The official `cvm-as` assembler
then encodes the binary and `cvm-run` executes it; the compiler itself needs
only the Cwhip SDK. It supports a checked scalar/array/function and structured
control-flow subset plus `print`/`open`/`read`/`write`/`close` built-ins;
`switch`, labels, and `goto` are diagnosed explicitly.
See [SmallC](SMALLC.md#compile-and-run-with-cvm) for setup, exact
coverage, and end-to-end tests.

For a standalone C99 version of the same syntax frontend:

```sh
build smallc-c
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

The parser uses bounded backtracking and is not yet a production compiler
frontend. It reports resource limits rather than silently truncating parse
results: 256 nested parser-rule calls, 100,000 matcher calls per
parse, and 4,096 results per intermediate set. The iterative NFA scanner limits
matching to 100,000 state visits per token, with 4,096 expanded states and
128 expression/reference edges per path at generation time. Left-recursive
expansion uses the same budgets and is not linear-time. Grammar-source spans,
include stacks, and shared NFA/parser analysis are implemented; generated-input
AST spans, more efficient recursion handling, richer lexer syntax, C++/Python
backends, and wider C grammar coverage remain future work. The standalone-C slice also
enforces 1 MiB input and 64 MiB cumulative arena-data limits.
See the [feature/target evidence matrix](TEST-COVERAGE.md) for the
executable coverage and explicit target/mode exceptions.

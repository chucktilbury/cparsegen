# Generated examples

These examples use the installed Cwhip SDK and cparsegen, not handwritten
scanners or parsers. Run the commands below from the repository root. Configure
with `./scripts/setup` first, or use `cmake -S . -B build` with your SDK selected
as described in [Building](../doc/BUILDING.md).
The older `expression.cpg` remains a provisional left-recursive grammar sketch,
not a runnable example.

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
```

Output is a complete-input **JSON syntax AST**, not bytecode or an executed
program. The example documents the single-pass semantic/VM work still needed.

## Additional lexical directives

SmallC needs lexical behavior beyond the calculator's character classes.
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
left-recursion normalization, richer lexer syntax, and other language
backends remain future work.

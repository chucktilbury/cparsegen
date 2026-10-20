# SmallC syntax frontend

This milestone provides a **generated parser, JSON AST, and opt-in semantic
checker**, not a C compiler or interpreter. There is no bytecode output yet.
The Cwhip scanner/parser and AST nodes are generated from
[smallc.cpg](smallc.cpg); [smallc.cw](smallc.cw) supplies the file CLI,
source-located diagnostics, JSON serialization, and an AST-based semantic
pass. The checker does not reparse source or alter the generated parser.

## Build and run

From the repository root, with an installed Cwhip SDK selected:

```sh
cmake -S . -B build
cmake --build build --target smallc
./bin/smallc-ast examples/smallc/valid/functions.c > build/smallc/functions.ast.json
./bin/smallc-ast --check examples/smallc/valid/functions.c > build/smallc/functions.checked.ast.json
python3 -m json.tool build/smallc/functions.ast.json
dot -Tsvg build/smallc/grammar.dot -o build/smallc/grammar.svg
```

The optional target first builds cparsegen, generates
`build/smallc/parser.cw` and `build/smallc/grammar.dot`, and then compiles
the frontend. Its executable follows `CWHIP_BIN_DIR`, defaulting to
`bin/smallc-ast`. It is not installed with the generator. Compilation uses
private HOME/XDG directories in the build tree.

The same grammar also generates an actual standalone ISO C99 frontend:

```sh
cmake --build build --target smallc-c
./bin/smallc-c --json examples/smallc/valid/functions.c > build/smallc-c/functions.ast.json
```

This optional target generates `build/smallc-c/parser.c` and `grammar.dot`,
then compiles `bin/smallc-c` with the host C compiler (`CWHIP_BIN_DIR` applies).
The generated file needs only the standard C library, not Cwhip or the SDK.
The generator itself still requires the SDK. `--json` selects complete-input
JSON and source-located syntax errors matching the Cwhip frontend below.
Without `--json`, the generic C CLI prints a rendered tree and selects the
shortest prefix; `--complete` requires all tokens but retains rendered output.
It has no C library/visitor API, evaluation, or semantic checker; semantic
checking is available only through the Cwhip `smallc-ast --check` app.

The Cwhip CLI accepts `smallc-ast INPUT.c` for syntax-only parsing or
`smallc-ast --check INPUT.c` to run semantic checks on the parsed AST. Both
modes require complete-input parsing: no unconsumed suffix is silently
accepted. Successful output in either mode is one JSON object:

```json
{"name": "translationUnit", "text": "", "children": []}
```

That shows the node shape only; actual successful translation units contain
one or more declarations. Every node has exactly `name`, `text`, and
`children`. Rule nodes retain the grammar's rule names and nesting; their
`text` is empty. Terminal leaves preserve original source spellings, including
quotes and escapes. Named tokens use `IDENT`, `INTEGER`, `CHAR`, or `STRING`;
grammar literals use generated `@literalN` names. Match the leaf's `text` for
punctuation/keywords; literal numbering is not a stable language API.
Comments and whitespace do not appear in the AST. Source spans are not yet
part of the node schema.

Syntax errors in either mode, and semantic errors in `--check` mode, go to
stderr as `file:line:column: diagnostic` (one-based, byte-oriented columns),
with exit status `1` and no partial AST. Usage errors return `2`; `--help`
describes the command. Syntax-only mode intentionally accepts programs with
semantic errors. No mode executes programs.

## Supported subset

| Area | Syntax |
| --- | --- |
| Translation units | One or more global declarations, function prototypes, or function definitions |
| Types | `int` and `char` only; no qualifiers, storage classes, or `void` |
| Declarations | Block/global variables, comma-separated declarators, optional initializers |
| Initializers | Assignment expressions, quoted strings, or a nonempty brace list with an optional trailing comma |
| Arrays | One dimension; a decimal integer size or `[]`; `name[expression]` indexing |
| Functions | `int`/`char` return type, named `int`/`char` parameters, zero parameters as `()`, calls by function name, recursion, prototypes, `return expression;` or `return;` |
| Statements | Blocks, empty/expression statements, `if`/`else`, `for`, `while`, `switch`, `case`, `default`, `goto`, labels, `break`, `continue`, `return` |
| `for` | Declaration or expression initializer; each expression clause may be omitted |
| `switch` | Braced case/default sections; case syntax is an optionally signed decimal integer or a character literal; fall-through and stacked labels are representable |
| Assignment | `=`, `+=`, `-=`, `*=`, `/=`, `%=`; syntactic destinations are named variables or indexed arrays |
| Arithmetic | Unary `+`/`-`, binary `+`, `-`, `*`, `/`, `%`; prefix/postfix `++`/`--` on named/indexed lvalues |
| Comparisons/logical | `<`, `<=`, `>`, `>=`, `==`, `!=`, `!`, `&&`, `||` |
| Literals | Decimal integers; single ASCII character/escape; double-quoted ASCII strings |
| Escapes | `\\`, `\"`, `\'`, `\n`, `\r`, `\t`, `\0`; no raw newlines inside quotes |
| Comments | `//` to end of line or EOF, and non-nested `/* ... */` |

Operator precedence follows C for this subset: calls/indexing/postfix,
prefix, multiplication/division/remainder, addition/subtraction, relational,
equality, `&&`, `||`, assignment. Assignment nests to the right; the other
binary levels retain left-to-right operands in flat sequences for a later
semantic/backend walk to fold left. The matched/open statement rules bind
`else` to the nearest unmatched `if`, including through loop bodies and
labels. Groups do not create artificial AST nodes.

No preprocessor, pointers, address/dereference operators, structs, unions,
enums, typedefs, casts, member access, array parameters, multidimensional
arrays, floating literals, bitwise/shift operators, ternary/comma operators,
`do`/`while`, or varargs are supported. Array parameters are deliberately
excluded because C-style array parameters imply pointers. Strings are
initializer syntax, not general pointer-valued expressions. String
concatenation, hex/octal constants, and hex/octal escapes are also deferred.
`main()` is a convention in the samples, not a parser-enforced entry point.

## Samples

- [valid/functions.c](valid/functions.c): a prototype, recursive factorial,
  nested calls, and a later definition.
- [valid/control.c](valid/control.c): loops, comparisons, switch fall-through,
  break/continue, forward gotos, and labels.
- [valid/arrays.c](valid/arrays.c): string and brace initializers, indexing,
  character escapes, and comments.
- [valid/dangling_else.c](valid/dangling_else.c): nearest-`if` association.
- [invalid/](invalid/): excluded features, malformed declarations, invalid
  character literals, and an unterminated comment.

Build the generator, then run the full black-box suite from the repository
root:

```sh
python3 -m unittest discover -s tests -v
```

The SmallC tests generate/compile their own isolated frontend, inspect its
JSON AST, and run table-driven semantic success/failure cases through the
Cwhip app. Every semantic-negative source is also verified to parse in
syntax-only mode. They compile standalone C with strict C99
warnings-as-errors and compare both parsers on every sample and all shared
syntax checks:
complete JSON trees (including terminal spellings), exit status, and exact
lexical/parser diagnostics with locations. No sample is silently skipped.
They cover all sample files, expression nesting and precedence,
nearest-`if` binding, comments and escapes, keyword boundaries, errors and
complete-input rejection, plus a 100-statement input.

## Semantic checking and explicit limits

`smallc-ast --check INPUT.c` performs a source-order walk over the exact AST
produced by Cwhip parsing. It reports the first semantic error with a
source-located diagnostic, exits `1`, and emits no partial AST; on success it
prints the same JSON AST as syntax-only mode. The default
`smallc-ast INPUT.c` remains syntax-only and intentionally accepts
syntactically valid programs with undeclared names or invalid types. The
standalone `smallc-c` executable remains syntax-only; the checker is in the
SmallC Cwhip application layer, not either parser backend.

The implemented semantic slice is:

| Area | Checked behavior |
| --- | --- |
| Scope and order | Global declarations and local declarations take effect in source order; parameters and the function body's outer block share one scope; nested blocks and `for` statements introduce scopes; inner variables may shadow outer variables |
| Names | Variable reads/writes require a declared variable; declarations before use are required; duplicate same-scope variables, duplicate parameters, duplicate global names, and global variable/function collisions are errors |
| Functions | Calls require a function declared earlier (a matching prototype permits later calls and recursion); a single compatible prototype and definition may coexist; duplicate prototypes/definitions and incompatible return/parameter signatures are errors; parameter names do not affect signature compatibility |
| Calls | Callees must be functions, argument count must match, and each argument must have exactly the declared scalar type |
| Arrays | Arrays cannot be read or assigned as scalar values; indexing requires a declared array and an `int` or `char` scalar index; indexed elements are modifiable scalar lvalues |
| Scalar types | Only `int` and `char` are modeled. `=` assignments, scalar initializers, function arguments, and return values require an exact type match; there is no implicit conversion between `int` and `char` |
| Operators | Arithmetic, unary arithmetic, comparisons, and logical operators require scalar operands. `char` operands are promoted to `int` for arithmetic and unary `+`/`-`; comparisons/logical operators produce `int`. Prefix/postfix increment/decrement mutate scalar `int` or `char` lvalues in place. Compound assignments produce `int` and are accepted only for an `int` target under the strict assignment rule |
| Initializers | Scalar initializer types must exactly match; array brace-list elements must exactly match the element type; string initializers require a `char` array |

The checker does not infer unsized-array extents and does not validate array
sizes, initializer element counts, or runtime bounds. It does not require
global initializers to be constant expressions. Control-flow semantics
remain unchecked: missing/definite returns, `goto` targets, `break`/`continue`
context, duplicate `case`/`default` labels, and reachability are not analyzed.
The language is not executed. Integer/character widths, signedness, overflow,
storage layout, and runtime behavior remain unspecified.

The generated matcher remains bounded: 256 nested **parser-rule** calls,
100,000 matcher calls per parse, 4,096 candidates per intermediate set, and
100,000 scanner pattern calls per token. Grammar-expression wrappers no
longer count as separate source-recursion levels. Exceeding a limit reports
an explicit error rather than returning a truncated AST. These examples do
not promise arbitrary-size C inputs or production compiler performance.
Standalone C additionally limits input to 1 MiB, scanner-part recursion to 256,
and cumulative arena data to 64 MiB. Exhaustion is explicit; these C-specific
bounds can reject larger inputs accepted by Cwhip. The tested sample corpus is
within both runtimes' budgets.

## Future bytecode backend

A stack-based VM remains a suitable next target after broadening semantic
checks. Keep its emitter separate from the grammar: AST -> source-order
binding/type checks -> instructions. A first instruction set would need integer/character
constants, local/global loads and stores, bounds-aware array operations,
arithmetic/comparisons, conditional/unconditional branches, calls, and
returns. Function frames, parameter/result conventions, memory layout, and
branch/call/label fixups must be specified before bytecode is emitted; this
milestone does not select an encoding or implement a VM.

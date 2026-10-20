# SmallC syntax frontend

This milestone is a **generated parser and JSON AST**, not a C compiler or
interpreter. There is no bytecode output yet. The Cwhip scanner/parser, AST
nodes, and visitor are generated from [smallc.cpg](smallc.cpg);
[smallc.cw](smallc.cw) only supplies the file CLI, source-located diagnostics,
and JSON serialization. It contains no SmallC parsing logic or semantic
actions.

## Build and run

From the repository root, with an installed Cwhip SDK selected:

```sh
cmake -S . -B build
cmake --build build --target smallc
./bin/smallc-ast examples/smallc/valid/functions.c > build/smallc/functions.ast.json
python3 -m json.tool build/smallc/functions.ast.json
dot -Tsvg build/smallc/grammar.dot -o build/smallc/grammar.svg
```

The optional target first builds cparsegen, generates
`build/smallc/parser.cw` and `build/smallc/grammar.dot`, and then compiles
the frontend. Its executable follows `CWHIP_BIN_DIR`, defaulting to
`bin/smallc-ast`. It is not installed with the generator. Compilation uses
private HOME/XDG directories in the build tree.

The CLI requires complete-input parsing: no unconsumed suffix is silently
accepted. Successful output is one JSON object:

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

Errors go to stderr as `file:line:column: diagnostic` (one-based, byte-oriented
columns), with exit status `1` and no partial AST. Usage errors return `2`;
`--help` describes the command. All examples below are syntax tests, not
executed programs.

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

The SmallC tests generate/compile their own isolated frontend and inspect its
JSON AST. They cover all sample files, expression nesting and precedence,
nearest-`if` binding, comments and escapes, keyword boundaries, errors and
complete-input rejection, plus a 100-statement input.

## Single-pass and semantic boundary

The future compiler is intended to be source-order and syntax-driven. A
function's signature should enter the symbol table before checking its body,
allowing recursion. Calls to functions defined later should require a
prototype; mutual recursion works through prototypes. Forward `goto`
targets and control-flow branches require fixups rather than a second source
pass.

**Those rules are not semantic checks implemented by this frontend.**
The current pipeline reads/tokenizes the source once into memory and uses
the generated bounded backtracking matcher to construct an AST; it is not a
streaming, single-pass compiler. A later source-order AST walk can perform
binding/type checks and emission without reparsing the source.

Syntax acceptance does not imply a valid SmallC program. The parser does
not yet check declaration-before-use, scopes, duplicate declarations,
prototype/definition/call agreement, return types, array sizes/bounds,
unsized-array inference, initializer types/counts, array-to-pointer decay
or array arithmetic, whether break/continue have an enclosing loop/switch,
duplicate case/default labels, or whether a goto target exists. For example,
`return unknown(array + 1);` can form a syntax AST even though a semantic
checker must reject it if `unknown` is undeclared or `array` is an array.
`int`/`char` widths, signedness, arithmetic overflow, and storage layout need
a semantic/VM contract before execution.

The generated matcher remains bounded: 256 nested **parser-rule** calls,
100,000 matcher calls per parse, 4,096 candidates per intermediate set, and
100,000 scanner pattern calls per token. Grammar-expression wrappers no
longer count as separate source-recursion levels. Exceeding a limit reports
an explicit error rather than returning a truncated AST. These examples do
not promise arbitrary-size C inputs or production compiler performance.

## Future bytecode backend

A stack-based VM remains a suitable next target after semantic checks. Keep
its emitter separate from the grammar: AST -> source-order binding/type
checks -> instructions. A first instruction set would need integer/character
constants, local/global loads and stores, bounds-aware array operations,
arithmetic/comparisons, conditional/unconditional branches, calls, and
returns. Function frames, parameter/result conventions, memory layout, and
branch/call/label fixups must be specified before bytecode is emitted; this
milestone does not select an encoding or implement a VM.

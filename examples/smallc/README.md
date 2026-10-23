# SmallC frontend and CVM compiler

SmallC provides a generated parser, JSON AST, opt-in semantic checker, and an
optional compiler to CVM v1 bytecode. The Cwhip scanner/parser and AST nodes
are generated from [smallc.cpg](smallc.cpg); the shared
[smallc_frontend.cw](smallc_frontend.cw) provides parser integration and the
semantic pass. [smallc.cw](smallc.cw) preserves the AST CLI, while
[smallc-cvm.cw](smallc-cvm.cw) and [smallc_backend.cw](smallc_backend.cw)
compile the same checked AST. Code generation does not reparse source.

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
The generated C parser can be included with `CPARSEGEN_NO_MAIN` to use its
parser/visitor API in a handwritten application. It supplies no evaluation or
semantic checker; semantic checking is available only through the Cwhip
`smallc-ast --check` app. See [Application integration](../../doc/VISITORS.md)
for the public APIs and runnable C/Cwhip consumers.

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
semantic errors. These AST modes do not execute programs; the optional
`smallc-cvm` backend is documented below.

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

## Compile and run with CVM

The optional backend consumes the installed public CVM CWhip packages; it
does not vendor CVM source or define a second bytecode encoder. Install
`cvm` 1.0.0 and `cvmfile` 1.0.0, plus the matching official `cvm-run` 1.0.0,
under one prefix. The selected CWhip SDK must support the public binary file
APIs used by `cvmfile`. Configure with that prefix:

```sh
cmake -S . -B build -DCVM_PREFIX=/path/to/cvm-install
cmake --build build --target smallc-cvm
./bin/smallc-cvm examples/smallc/valid/functions.c build/smallc/functions.cvm
/path/to/cvm-install/bin/cvm-run build/smallc/functions.cvm
cmake --build build --target test-smallc-cvm
```

`smallc-cvm INPUT.c OUTPUT.cvm` runs the existing semantic checker, lowers
its AST with the public CVM instruction/container builders, validates the
container, and writes it only after successful compilation. `CVM_PREFIX` must
contain `share/cwhip/modules/cvm/1.0.0`,
`share/cwhip/modules/cvmfile/1.0.0`, and `bin/cvm-run`; CMake fails
configuration if any is absent. These paths pin the compiler interface to
CVM/CVMFile 1.0.0. The output is a normal CVM container and can be run outside
the cparsegen checkout with the installed official runner.

The compiler supports checked signed i32 and unsigned u8 scalars, globals and
locals, defined functions/prototypes/calls/recursion, one-dimensional
fixed/inferred arrays with brace and string initializers, arithmetic,
comparisons, short-circuit logic, assignments, increments, `if`/`else`,
`for`, `while`, `break`, `continue`, and `return`. The entry must be
`int main()`; called prototypes need a definition. Character reads
zero-extend for integer operations, and narrowing is checked. Arithmetic
overflow, division by zero, invalid signed division, array bounds violations,
and checked narrowing trap at runtime.

`switch`, `case`, `default`, labels, and `goto` parse and may pass `--check`,
but code generation rejects them with source-located diagnostics. Other
constructs outside the listed subset are likewise rejected explicitly. Array
extents and brace initializer counts are checked during code generation;
global initializer expressions run before `main`, and local initializer
expressions run when their declarations execute. The C and AST frontends
remain unchanged and do not gain bytecode output.

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
complete-input rejection, plus a 100-statement input. Control-flow regressions
cover nested loop/switch contexts and restoration, function-local forward and
backward jumps, labels wrapping statements, stacked duplicate switch labels,
signed/zero-padded decimal and escaped-character case equality, and strict
per-statement return rules (without claiming all-path completion).

## Semantic checking and explicit limits

`smallc-ast --check INPUT.c` performs a source-order walk over the exact AST
produced by Cwhip parsing. It reports the first semantic error with a
source-located diagnostic, exits `1`, and emits no partial AST; on success it
prints the same JSON AST as syntax-only mode. The default
`smallc-ast INPUT.c` remains syntax-only and intentionally accepts
syntactically valid programs with undeclared names or invalid types. The
standalone `smallc-c` executable remains syntax-only; the checker is in the
SmallC Cwhip application layer, not either parser backend.

The checker incrementally adopts the generated visitor for its existing
duplicate-parameter check and signature collection: `parameterTypes` walks
the parameter list, while `enter_rule_parameter` accesses each name/type,
updates application-owned lists, and returns skip or error. Other semantic
checks retain direct AST access. See the
[integration walkthrough](../../doc/VISITORS.md#diagnostics-and-compiler-integration)
for failure propagation, source-location handling, and application ownership.

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
| Loop/switch context | `break` requires an enclosing `while`, `for`, or `switch`; `continue` requires an enclosing loop, including through nested switches |
| Labels and `goto` | Labels have function scope, independent of variables and block scopes; forward/backward jumps are allowed, unresolved targets and duplicate labels are errors; labels may wrap any statement |
| Switch labels | Each switch permits one `default` and distinct literal case values, including stacked labels; nested/separate switches have independent labels |
| Returns | Every `return` in an `int`/`char` function must supply an expression of exactly the function's return type; bare `return;` parses but fails checking. `void` functions are not in the grammar |

Case equality uses mathematical signed decimal values, ignoring leading zeros
and a leading `+`, and equating `-0` with `0`. Leading zeros are decimal, not
octal. ASCII character literals and the supported escapes compare by their
nonnegative ASCII code (`'a'` equals `97`, `'\n'` equals `10`, `'\0'` equals
`0`). Case comparison promotes characters to integer values independently of
the strict assignment rule. Decimal spellings are compared without a host
integer-width limit; this does not define runtime integer widths or overflow.
The grammar already restricts cases to optionally signed decimal integer
tokens or character literals. No expression folding is performed.

Labels are collected per function before its source-order statement walk so
forward jumps resolve without making variables visible before declaration.
Duplicate labels are reported at the repeated identifier; unresolved jumps at
the target identifier; duplicate cases at the repeated value; and invalid
`break`, `continue`, bare `return`, or duplicate `default` at the keyword.

The checker does not infer unsized-array extents and does not validate array
sizes, initializer element counts, or runtime bounds. It does not require
global initializers to be constant expressions. Return checking validates
individual statements only: proving every path returns, detecting a function
that can fall off its end (including an empty body), and reachability are
explicitly deferred. There is no CFG/guaranteed-return analysis or jump
restriction across declarations/initializations.
The syntax frontend and semantic checker do not execute programs or define
runtime widths, signedness, overflow, storage layout, or behavior. Those
runtime rules are specified only for the optional CVM backend below.

The generated matcher remains bounded: 256 nested **parser-rule** calls,
100,000 matcher calls per parse, 4,096 candidates per intermediate set, and
100,000 scanner NFA state visits per token boundary. Grammar-expression wrappers no
longer count as separate source-recursion levels. Exceeding a limit reports
an explicit error rather than returning a truncated AST. These examples do
not promise arbitrary-size C inputs or production compiler performance.
Both scanners use iterative state sets, not recursive pattern matching.
Standalone C additionally limits input to 1 MiB
and cumulative arena data to 64 MiB. Exhaustion is explicit; these C-specific
bounds can reject larger inputs accepted by Cwhip. The tested sample corpus is
within both runtimes' budgets.

The backend does not add pointers, array parameters, structs, or OOP features.
Its runtime widths and checked arithmetic apply only to generated CVM programs;
the syntax AST and standalone C parser retain their previous contracts.

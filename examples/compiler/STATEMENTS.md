# A tiny statement-to-C compiler

This incremental companion to the [expression compiler](README.md) keeps its
arithmetic grammar, precedence, numeric representation, and visitor-dispatch
pattern, adding named bindings, source-order statements, structured control
flow, integer-valued functions, and a single class with value-like objects. It is a compiler,
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

For parameters, locals, nested/forward calls, and recursion, run the
[function sample](statements/functions.stmt) through the same pipeline:

```sh
./bin/statement-compiler examples/compiler/statements/functions.stmt \
  > build/statement-compiler/functions.c
cc -std=c99 -Wall -Wextra -Werror -pedantic \
  build/statement-compiler/functions.c -o build/statement-compiler/functions
./build/statement-compiler/functions
```

It prints `12`, `120`, and `7`. Functions use the same integer-literal
arithmetic language and `double` representation as existing expressions:

```text
fn add(left, right) {
    let total = left + right;
    return total;
}
print add(2, add(3, 4));
```

For fields, construction, value copies, and statically dispatched methods,
compile the [object sample](statements/objects.stmt):

```sh
./bin/statement-compiler examples/compiler/statements/objects.stmt \
  > build/statement-compiler/objects.c
cc -std=c99 -Wall -Wextra -Werror -pedantic \
  build/statement-compiler/objects.c -o build/statement-compiler/objects
./build/statement-compiler/objects
```

It prints `0`, `10`, `15`, `4`, `2`, and `15` on separate lines.
The first read demonstrates zero-initialized fields; modifying `copy` does not
change `counter`. Both conditional arms initialize `selected` before its read.

```text
class Counter {
    field value: int;
    fn add(amount) {
        self.value = self.value + amount;
        return self.value;
    }
}
let counter = new Counter();
counter.value = 10;
let copy = counter;
copy.add(5);
print counter.value;
print copy.value;
```

### Object semantics and lowering

There may be **at most one class** per program, declared at top level. Class,
field, and method signatures are collected before validation, so construction
and calls may precede the class declaration and methods may call later methods.
Fields use `field name: int;`; `int` is the existing integer-valued arithmetic
type, represented by C `double`, not a new machine-integer type. Fields and
methods share a member namespace, independent of variables and free functions.
All members are public. Empty classes are allowed.

`new Counter()` is a zero-argument, zero-initializing **value construction**:
every field starts at zero and there is no heap allocation, null, ownership,
or destructor. `let counter = new Counter();` infers the object type.
`let counter: Counter;` declares an uninitialized object binding; use
`let counter: Counter = new Counter();` or a later whole-object assignment to
initialize it. Whole-object assignment and initialization copy all fields,
without aliasing. Binding types never change. An unannotated `let name;`
retains the existing arithmetic type; it cannot later receive an object.
The annotation syntax currently names only the single class, not `int`.
Constructing again resets all fields, including declarations executed inside
loops. Field writes do **not** initialize an uninitialized object: the receiver
must already be definitely initialized before any field access or method call.
Once an object is initialized, all of its fields are initialized.

`counter.value` reads a field and `counter.value = expression;` writes one.
`counter.add(5)` calls a method on that named binding, passing its address
as an implicit receiver. Inside a method, `self` denotes that caller's object,
so `self.value = ...` mutates the caller. `self = new Counter();` replaces the
whole receiver value; `let copy = self;` creates an independent copy.
`self` is reserved as a binding only within methods; it is not implicitly
available in free functions or top-level code. Field names are never implicit:
write `self.value`, not `value`. Methods have isolated local/parameter tables
like free functions and cannot capture top-level variables or other methods'
locals. Every method must return an arithmetic value on every continuing path.
Method parameters and free-function parameters/returns remain arithmetic-only.
To use an object in a free function, construct a local object and return a
field or method result. Objects cannot be printed, used as conditions, compared,
or passed to arithmetic operators.

Method calls may be expressions or standalone statements (`counter.add(5);`,
which discards the numeric result). Free-function calls remain expression-only.
Receivers are named bindings (`counter` or `self`), not temporaries, chained
member expressions, or arbitrary expressions. No implicit method calls or
constructor arguments are supported; an ordinary method such as `init` can
perform explicit setup after zero construction. Method lookup is static:
there are no virtual tables or runtime type tests.

The emitter first writes the class layout, then all function/method prototypes
and definitions, and finally `main`. For example, the class above lowers to
this shape (expression parentheses/spacing abbreviated):

```c
typedef struct {
    double cpg_field0;
} cpg_object;

double cpg_f0(cpg_object *, double);
double cpg_f0(cpg_object *cpg_self, double cpg_v1) {
    (*cpg_self).cpg_field0 = (*cpg_self).cpg_field0 + cpg_v1;
    return (*cpg_self).cpg_field0;
}
```

Construction emits `(cpg_object){0}`, copies use C struct assignment, and a
call emits `cpg_f0(&(cpg_v0), 5.0)`. Fields appear in declaration order and use
numeric names, as do function/variable slots, so source names cannot collide
with C identifiers. Empty classes receive a private dummy byte because C99
does not permit empty structs. All lowering uses standard C99, without runtime
object support or additional dependencies.

Unknown classes, fields, or methods, non-object receivers, non-`int` field
types, duplicate members/bindings, wrong method argument counts, and arithmetic/
object type mismatches produce source-located errors and no C output.
These checks, including definite assignment, run only in the handwritten
compiler visitor; generated syntax parsers still accept semantically invalid
object programs.

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

The compiler first parses the entire source file and collects all top-level
function names and parameter counts, the optional class name, ordered fields,
and method signatures. It then uses `cpg_dispatch` and
per-rule/token hooks for a semantic pass. A caller-owned `Compiler` context
holds an ordered symbol table of borrowed `IDENT` nodes and definite-initialization
flags and arithmetic/object types. Class/member metadata is shared across
isolated function/method contexts; methods add an initialized implicit
receiver slot. Expression visitors propagate types and require arithmetic
operands at operators, arguments, conditions, prints, and returns. Generic callbacks
dispatch children in stored AST order; no generated walker is reimplemented.
Declaration callbacks check for duplicates, dispatch any initializer with the
current symbols, and only then add the new binding. Assignment callbacks
require an existing binding, validate the right-hand side, and only then mark
the binding initialized. Identifier
callbacks reject names not yet declared, including self-reference in an
initializer, and reads of declared but not definitely initialized bindings.
Control-flow callbacks snapshot entry flags, validate each arm from that entry
state, and intersect the flags of continuing arms after `if`/`else`.
A returning arm does not constrain the continuing arm's initialization state;
two returning arms terminate that path. Loops and conditionals without
`else` restore the entry flags. Snapshots never remove textual declarations.
The context survives all statement callbacks, rather than being
recreated for each node. It is freed before destroying the parser and input.
Each function body is dispatched with a separate symbol table, initially
containing its initialized parameters. The completed local tables are retained
for emission; function validation never changes the top-level table.
Return callbacks check their value expression and mark the path as terminated.
Every function must terminate all paths with a value return. A loop is still
conservatively allowed to execute zero times, even with a constant condition.

Only a successful semantic pass starts output. A second visitor emits numeric
function prototypes, then definitions, then the top-level statements in C
`main`. Prototypes support forward calls, self-recursion, and mutual recursion.
Calls emit `cpg_f0(...)`, `cpg_f1(...)`, etc.; function names cannot collide
with C keywords or library symbols. All functions return `double` and their
parameters are passed by value. The visitor reuses each completed symbol table
and dispatches statements in source order within each body. Declarations
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
are safe source-language variables. All non-parameter slots are declared and
zero-initialized at the start of `main` or their function, with an explicit
`(void)` read to keep unused bindings warning-free under strict C99.
This storage initialization is a C-emission
detail, **not** a source-language fallback: the semantic visitor rejects reads
that would depend on it. Initializer expressions remain at their source
positions, so loop-body declarations reassign their slots on every iteration.

For example, `let x = 2; print x; x = x + 3; print x;` emits this shape
(expression parentheses/spacing abbreviated):

```c
#include <stdio.h>
#include <stdlib.h>

int main(void) {
    double cpg_v0 = 0.0;
    (void)cpg_v0;
    cpg_v0 = 2.0;
    if (printf("%.17g\n", (double)cpg_v0) < 0) exit(EXIT_FAILURE);
    cpg_v0 = cpg_v0 + 3.0;
    if (printf("%.17g\n", (double)cpg_v0) < 0) exit(EXIT_FAILURE);
    return fflush(stdout) ? 1 : 0;
}
```

The emitted program prints `2` then `5`. The host C compiler, not the visitor,
performs expression code generation; the generated program stores and computes
the runtime values. See the [visitor contract](../../doc/VISITORS.md) for
dispatch behavior, AST lifetimes, and terminal source positions.

## Language and diagnostics

Programs contain zero or more statements, top-level function definitions,
and optionally one class declaration:

```text
let name;
let name = expression;
name = expression;
print expression;
{ statements }
if (expression) { statements }
if (expression) { statements } else { statements }
while (expression) { statements }
fn name(parameter, ...) { statements }
return expression;
class Type { field member: int; fn method(parameter, ...) { statements } }
let object: Type;
let object = new Type();
object.member = expression;
object.method(expression);
```

There is one scope for top-level statements and a separate lexical scope for
each function. Functions cannot read or assign top-level variables or another
function's parameters/locals. Names are case-sensitive ASCII identifiers
matching `[a-zA-Z_][a-zA-Z0-9_]*`; `let`, `print`, `if`, `else`, `while`,
`fn`, `return`, `class`, `field`, and `new` are keywords and cannot be used
as binding names. `int` remains an identifier outside field type annotations.
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
shadowing or redeclaring it in any other block of the same function/top-level
scope is an error, even in mutually exclusive branches. References textually
before a declaration (or in its own
initializer) fail. A later `else` arm can assign a name declared in the first arm,
but cannot assume that arm's initializer executed.

Function names occupy a separate namespace from variables. Duplicate function
names are rejected (no overloading), as are duplicate parameter names and
locals that redeclare parameters. Parameters are initialized on entry.
Zero-parameter functions and zero-argument calls use `name()`. Every call
must name a collected function and pass exactly its declared number of
arguments; all argument and return expressions must use the arithmetic type,
not an object. There are no conversions or return-type annotations.
Functions are not first-class values, and calls are expressions, not standalone
statements. Definitions cannot be nested inside blocks/functions.
`return` is only valid inside a function and must have a value; a bare
`return;` is accepted by the grammar but rejected by the semantic visitor.

Definite-assignment checking follows control flow, separately from visibility:

- `let x;` declares an uninitialized binding. An initializer initializes a
  binding only when its declaration executes. Assignment initializes only
  after its right-hand side has been checked, so `let x; x = x + 1;` fails.
- Every read, including expressions, initializers, assignment right-hand sides,
  prints, and conditions, requires definite initialization.
- An `if`/`else` guarantees initialization afterward only if every continuing
  arm guarantees it. Each arm starts from the same incoming initialization
  state. Returning arms are excluded from the join.
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
The same checks apply to call arguments and returned expressions, independently
for each function. For example,
`fn f(n) { let x; if (n) { return 1; } else { x = 2; } return x; }`
is valid; omitting the `else` assignment makes the final read invalid.

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
statements were valid. Incorrect CLI argument counts return `2`; function-call
arity errors return `1`. Function diagnostics include `unknown function`,
`argument count mismatch`, `duplicate function`, `return outside function`,
`return requires a value`, and `function may finish without returning a value`.
File-read and C-source write failures return `1` with diagnostics; an I/O failure during
emission can leave partial C. The emitted program checks print and final
flush failures too. A failed print inside a function terminates the program
with failure via `exit`, rather than returning an ordinary arithmetic value.

The following still succeeds, demonstrating that semantic checks belong to
the application, not to the generated parser:

```sh
build/statements-manual/syntax-parser --json \
  examples/compiler/statements/use-before.stmt
```

This is deliberately not SmallC or the calculator CLI. There are no
inheritance, dynamic/polymorphic dispatch, multiple classes, object-valued
fields/parameters/returns, generics, external interfaces, non-integer numeric types, block-local
scopes, logical `&&`/`||`/`!`, `break`/`continue`, comments,
strings, division, or fractions. Numbers use host C `double`; arithmetic
rounding, overflow, and finite-range checks are not implemented. Keep values
small enough for the host's range. The generated parser's existing input,
allocation, nesting, work, and result-count limits apply unchanged; this is a
bounded integration example, not a production language compiler.
Runtime recursion uses the host C stack with no additional depth check.
Sibling operands and call arguments follow C's unspecified evaluation order;
do not rely on the ordering of prints or receiver mutations in sibling calls.
Use separate statements when combining reads and mutations of the same object.

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
Function regressions additionally cover parameters, unused functions/parameters,
independent locals, nested/forward/self-recursive/mutually recursive calls,
return-aware joins, early returns, function/symbol-table growth, duplicate
signatures/parameters/locals, unknown functions, arity mismatches, missing/bare/
top-level returns, uninitialized arguments/returns, and scope leakage.
Object regressions check generated struct field order and types, explicit
receiver signatures, zero construction, copies, field mutation/access, resets,
static/forward/recursive method calls, local objects in free functions, method
control flow, object definite assignment, empty classes, C-safe names, invalid
members/types/arity/duplicates, exact diagnostic locations, and syntax-only
acceptance in both parser backends.
Direct test runs use the same SDK discovery and `CPARSEGEN_C_COMPILER`,
`CC`, and optional `CPARSEGEN_C_FLAGS` conventions as the expression tests.

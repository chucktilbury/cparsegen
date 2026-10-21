# A tiny statement-to-C compiler

This incremental companion to the [expression compiler](README.md) keeps its
arithmetic grammar, precedence, and visitor-dispatch
pattern, adding named bindings, source-order statements, structured control
flow, statically typed functions, and multiple classes with object references. It is a compiler,
not an interpreter: its stdout is C source, not the program's output.
The original `expression-compiler` and generated parser APIs are unchanged.
Unlike the expression compiler's `double` backend, this example uses signed
32-bit integers with checked arithmetic.

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
arithmetic language, with checked `int32_t` values:

```text
fn add(left, right) {
    let total = left + right;
    return total;
}
print add(2, add(3, 4));
```

For fields, construction, aliases, and statically dispatched methods,
compile the [object sample](statements/objects.stmt):

```sh
./bin/statement-compiler examples/compiler/statements/objects.stmt \
  > build/statement-compiler/objects.c
cc -std=c99 -Wall -Wextra -Werror -pedantic \
  build/statement-compiler/objects.c -o build/statement-compiler/objects
./build/statement-compiler/objects
```

It prints `0`, `15`, `15`, `4`, `3`, and `4` on separate lines.
The first read demonstrates zero-initialized integer fields; `copy` aliases
`counter`, so either binding can mutate the same object. Both conditional arms
initialize `selected` before its read.

For constructor parameters, initialized fields, nested control flow, early
returns, and receiver mutation, compile the
[constructor sample](statements/constructors.stmt) through the same pipeline:

```sh
./bin/statement-compiler examples/compiler/statements/constructors.stmt \
  > build/statement-compiler/constructors.c
cc -std=c99 -Wall -Wextra -Werror -pedantic \
  build/statement-compiler/constructors.c -o build/statement-compiler/constructors
./build/statement-compiler/constructors
```

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

Programs may declare multiple top-level classes. All class names are collected
first, followed by field and function/method signatures, before body validation.
Construction, type annotations, and calls may precede declarations; fields may
refer to later classes, their own class, or mutually referential classes.
Fields use `field name: int;`, `field name: bool;`, or `field name: ClassName;`.
`int` is a signed 32-bit integer, represented by C `int32_t`.
`bool` lowers to C99 `_Bool`. Neither primitive can also name a class.
Fields and methods share a namespace **per class**;
different classes may reuse member names. Free functions and variables have
separate namespaces. All members are public. Empty classes are allowed.

`new Counter()` allocates a fresh, distinct object. Integer fields start at zero;
boolean fields start at `false`;
class-typed fields start as null references, not recursively constructed objects.
Initialize nested objects explicitly, for example `pair.left = new Counter();`.
An optional single `constructor(parameters) { statements }` per class runs after
zero-initialization. It can initialize fields and nested objects using `self`,
and supports local declarations, assignments, conditionals, loops, and method
calls. Constructors may not return a value and always produce the newly
allocated receiver. An omitted constructor preserves zero-argument construction;
an explicit constructor's argument count and types are checked exactly.
There is no source-level null literal or null comparison. Dereferencing a null
field, including as a method receiver, prints `uninitialized object reference`
to stderr and exits with failure instead of invoking C undefined behavior.
Copying or passing a null reference is allowed; only dereferencing it fails.

`let counter = new Counter();` infers the class type.
`let counter: Counter;` declares an uninitialized object binding; an initializer
or later assignment establishes definite initialization. Assignment and
initialization copy **references**, never fields. Aliases observe each other's
field writes. Rebinding an alias to `new Counter()` does not reset the original
object. Each execution of `new`, including in loops, allocates a fresh object.
Binding types never change and distinct class types are incompatible.
An unannotated `let name;` retains the `int` type; local type annotations
may name either primitive or a class. Field writes do not initialize an uninitialized binding:
its receiver must already be definitely initialized. Definite assignment tracks
bindings, not the non-nullness of fields; field dereferences are checked at runtime.

`counter.value` reads a field and `counter.value = expression;` writes one.
Paths may have multiple fields: `pair.left.value`, `self.next.next.value`,
or `pair.left.add(5)`. A path begins at a named binding (`self` included);
arbitrary expression/temporary receivers such as `new Counter().add(5)` are
not supported. `counter.add(5)` passes the object reference as the implicit
receiver. Inside a method, `self.value = ...` mutates the shared object.
`let copy = self;` creates an alias. `self = new Counter();` rebinds only the
method-local receiver, not the caller's binding.
`self` is reserved as a binding only within methods; it is not implicitly
available in free functions or top-level code. Field names are never implicit:
write `self.value`, not `value`. Methods have isolated local/parameter tables
like free functions and cannot capture top-level variables or other methods'
locals. Every method must return a value of its declared type on every continuing path.
Method, free-function, and constructor parameters may be unannotated (`int`), explicitly
`: int`, `: bool`, or class-typed: `fn update(box: Box, amount: int) { ... }`.
Arguments must match the exact declared type. Passing a class argument copies
its reference: field mutation is shared, but rebinding a parameter is local.
Function/method return annotations support the same types, defaulting to `int`.
Returning an object copies its reference and preserves its lifetime and aliases.
Objects cannot be printed, used as conditions, compared, or passed to arithmetic operators.

Method calls may be expressions or standalone statements (`counter.add(5);`,
which discards the result). Free-function calls remain expression-only.
Method lookup uses the
compile-time class of the receiver; there are no virtual tables or runtime
type tests.

The [reference sample](statements/references.stmt) combines two classes, typed
parameters, aliases, nested fields, and method calls. Compile/run it using the
same commands as the object sample, substituting `references` for `objects`.
It prints `0`, `15`, `15`, `20`, `0`, and `20`. An object constructed inside
`initialize` remains alive after that function returns because `pair` retains
its reference.

The emitter writes forward declarations for every class, then layouts,
constructors, all function/method prototypes and definitions, and finally
`main`. The class above lowers to this shape (parentheses/spacing abbreviated):

```c
typedef struct cpg_class1 cpg_class1;
struct cpg_class1 {
    int32_t cpg_field0;
};

int32_t cpg_f0(cpg_class1 *, int32_t);
int32_t cpg_f0(cpg_class1 *cpg_self, int32_t cpg_v1) {
    ((cpg_class1 *)cpg_require(cpg_self))->cpg_field0 =
        cpg_add(((cpg_class1 *)cpg_require(cpg_self))->cpg_field0, cpg_v1);
    return ((cpg_class1 *)cpg_require(cpg_self))->cpg_field0;
}
```

Class fields, bindings, and parameters lower to `cpg_classN *`. Construction
calls `cpg_newN()`, which allocates storage and assigns `(cpg_classN){0}` for
portable arithmetic-zero/null-pointer initialization. Aliases use pointer
assignment, and calls emit `cpg_f0(cpg_require(cpg_v0), INT32_C(5))`. Member access
checks each dereferenced reference. Numeric class/field/function/variable names
avoid C identifier collisions. Empty classes have a dummy byte for C99.

**Ownership/lifetime:** the generated program owns a linked allocation list,
with one object allocation and one tracking-node allocation per `new`.
An `atexit` handler frees every object and tracking node, independent of aliases
or cycles, on normal return and on `exit` after runtime/print/allocation failure.
Registration failure is diagnosed before any object allocation. Partial
allocation failure frees its successful allocation before exiting. Objects
outlive blocks, loop iterations, function calls, and receiver rebinding, so
references stored into fields cannot dangle. Unreachable objects are retained
until exit; memory use grows with the number of constructions. There is no
garbage collection, destructor, or user-controlled deletion. Abnormal
termination (for example a signal or stack exhaustion) cannot run C `atexit`
cleanup. All support is emitted as standard C99 using only the standard library.

Unknown classes, fields, or methods, non-object receivers, duplicate
classes/members/bindings, wrong method argument counts, incompatible classes,
and arithmetic/object type mismatches produce source-located errors and no C output.
These checks, including definite assignment, run only in the handwritten
compiler visitor; generated syntax parsers still accept semantically invalid
object programs.

## Primitive types and compatibility

The [typed sample](statements/types.stmt) exercises `int` and `bool` fields,
constructor/method/function parameters, locals, returns, aliases, early returns,
and nested branches/loops. Compile it with the build pipeline above, substituting
`types` for `basic`. It prints `0`, `1`, `3`, `1`, `0`, and `7`.

```text
fn selected(flag: bool, yes: int, no: int): int {
    let result: int;
    if (flag) { result = yes; } else { return no; }
    return result;
}
let active: bool = 2 < 3;
print selected(active, 7, 9);
```

Compatibility is **exact type identity**, not C convertibility. `int`, `bool`,
and each declared class have distinct identities. There are no implicit
int/bool conversions, subtype conversions, overloading, inheritance, or dynamic
dispatch. Matching applies to initializers, binding/field assignments, return
values, and all function/method/constructor arguments. Arity must also match.

| Expression/context | Rule |
|---|---|
| Decimal integer literal | `int`; signed 32-bit range (see below) |
| `true`, `false` | `bool`; reserved keywords |
| Unary `+`, `-`; binary `+`, `-`, `*` | `int` operands, `int` result |
| `<`, `<=`, `>`, `>=` | `int` operands, `bool` result |
| `==`, `!=` | Two `int` or two `bool` operands, `bool` result; no reference equality |
| Parentheses | Preserve the enclosed type |
| Binding/field read | Its fixed declared or inferred type |
| Function/method call | Its declared return type (default `int`) |
| `new Class(...)` | That class's reference type |
| `if`, `while` | Require `bool`; numeric truthiness is rejected |
| `print` | Either primitive; booleans print `0` or `1` |

`let x: int;` and `let flag: bool;` require definite initialization before reads.
`let x = expression;` infers the expression's type once, including `bool` and
class references; `let x;` defaults to `int`. Unannotated parameters and returns
default to `int` for compatibility with previous arithmetic programs; annotations
do not change name visibility, definite assignment, or return-path analysis.
Fields always require an annotation and receive typed zero/false/null defaults;
field initializer expressions are not part of the grammar. Constructors perform
explicit initialization through checked field assignments and have no return
annotation or source-level return statement.

### Integer range and overflow

`int` is exactly signed 32-bit, from **-2147483648 through 2147483647**.
Decimal tokens normally have magnitude at most 2147483647. A directly preceding
unary `-` permits magnitude 2147483648: `-2147483648` and `- 0002147483648`
are valid. Whitespace and leading zeros do not change the value, and there is no
digit-count limit beyond the parser's input limits. `2147483648`,
`-2147483649`, `+2147483648`, and `-(2147483648)` are semantic errors:
the compiler reports `integer literal outside int32 range` at the decimal
token's line, column, and byte offset and emits no C. Even unreachable literals
are checked. The standalone syntax parser still accepts these tokens.
Magnitude conversion checks each digit before accumulation, without host
integer overflow or floating-point conversion.

Every executed binary `+`, `-`, and `*` and unary negation checks its result
before narrowing to `int32_t`. Overflow writes `integer overflow in +`, `-`,
or `*` to stderr and terminates with `EXIT_FAILURE` (a nonzero C failure status).
There is no wrapping, saturation, rounding, or compile-time constant folding.
Unary negation uses checked subtraction from zero, so negating `INT32_MIN`
(including `--2147483648`) fails at runtime; unary `+` preserves the value.
Checks apply to each left-associated intermediate: `2147483647 + 1 - 1` fails,
even though its mathematical final result fits. Unexecuted arithmetic does not
fail. Existing object cleanup runs on overflow via `exit`.

Generated helpers widen operands **before** arithmetic to C99 `int_least64_t`.
All sums, differences, and products of two signed 32-bit operands fit that
type; bounds are checked against `INT32_MIN`/`INT32_MAX` before conversion.
This avoids C signed-overflow undefined behavior. Generated C requires a C99
implementation providing `int32_t`; `<stdint.h>` and `<inttypes.h>` supply
the types, limits, constants, and portable `PRId32` print format.
Wider source-language numeric types, division, and fractions remain deferred.

Exact primitive typing is unchanged: the compiler rejects `let flag: bool = 1;`
and `let n: int = true;` even though C could convert either. Booleans still
use C99 `_Bool`. Printing uses decimal `PRId32` output, casting booleans to
`int32_t` so they continue to print `0` or `1`.

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
function names and parameter types, all class names, ordered typed fields,
and class-specific method signatures. It then uses `cpg_dispatch` and
per-rule/token hooks for a semantic pass. A caller-owned `Compiler` context
holds an ordered symbol table of borrowed `IDENT` nodes and definite-initialization
flags and primitive/class identities. Class/member metadata is shared across
isolated function/method contexts; methods add an initialized implicit
receiver slot. Expression visitors propagate types, check operator compatibility,
and require boolean conditions; arguments and returns match their declared
types. Generic callbacks
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
with C keywords or library symbols. Function signatures lower their declared
return types (`int32_t`, `_Bool`, or a class pointer) and their
parameters are passed by value (object pointers preserve aliases). The visitor reuses each completed symbol table
and dispatches statements in source order within each body. Declarations
with initializers and assignments emit stores; declarations without initializers
emit no store. Print callbacks emit checked `printf` calls,
using `PRId32` and converting primitive values to `int32_t` for the variadic format.
The block callback dispatches its statement children between C braces.
Conditional and loop callbacks dispatch the condition and body blocks, emitting
`if`/`else` and `while` rather than evaluating conditions in the compiler.
Validation visits every body, including unreachable branches.
Expression callbacks preserve precedence and left associativity using nested
checked arithmetic helper calls. Integer tokens become decimal `INT32_C`
constants (`000008` becomes `INT32_C(8)`, never C octal); the minimum signed
literal becomes `INT32_MIN`. Identifiers map to stable
`cpg_v0`, `cpg_v1`, ... slots, so C keywords and names such as `printf` or `main`
are safe source-language variables. All non-parameter slots are declared and
zero-initialized at the start of `main` or their function, with an explicit
`(void)` read to keep unused bindings warning-free under strict C99.
This storage initialization is a C-emission
detail, **not** a source-language fallback: the semantic visitor rejects reads
that would depend on it. Initializer expressions remain at their source
positions, so loop-body declarations reassign their slots on every iteration.

For example, `let x = 2; print x; x = x + 3; print x;` emits this shape
(expression parentheses/spacing abbreviated; checked helpers omitted):

```c
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <inttypes.h>

int main(void) {
    int32_t cpg_v0 = 0;
    (void)cpg_v0;
    cpg_v0 = INT32_C(2);
    if (printf("%" PRId32 "\n", (int32_t)cpg_v0) < 0) exit(EXIT_FAILURE);
    cpg_v0 = cpg_add(cpg_v0, INT32_C(3));
    if (printf("%" PRId32 "\n", (int32_t)cpg_v0) < 0) exit(EXIT_FAILURE);
    return fflush(stdout) ? 1 : 0;
}
```

The emitted program prints `2` then `5`. The host C compiler, not the visitor,
performs expression code generation; the generated program stores and computes
the runtime values. See the [visitor contract](../../doc/VISITORS.md) for
dispatch behavior, AST lifetimes, and terminal source positions.

## Language and diagnostics

Programs contain zero or more statements, top-level function definitions,
and class declarations:

```text
let name;
let name = expression;
let name: int = expression;
let flag: bool;
name = expression;
print expression;
{ statements }
if (expression) { statements }
if (expression) { statements } else { statements }
while (expression) { statements }
fn name(parameter, ...) { statements }
fn name(parameter: Type, amount: int, flag: bool, ...): ReturnType { statements }
return expression;
class Type { field member: OtherType; fn method(parameter, ...) { statements } }
class Type { field member: int; constructor(parameter: int, ...) { statements } }
let object: Type;
let object = new Type();
let object = new Type(argument, ...);
object.member = expression;
object.method(expression);
```

There is one scope for top-level statements and a separate lexical scope for
each function. Functions cannot read or assign top-level variables or another
function's parameters/locals. Names are case-sensitive ASCII identifiers
matching `[a-zA-Z_][a-zA-Z0-9_]*`; `let`, `print`, `if`, `else`, `while`,
`fn`, `return`, `class`, `field`, `constructor`, `new`, `true`, and `false` are keywords
and cannot be used as binding names. `int` and `bool` remain identifiers outside
type annotations, but cannot name classes.
Declarations may omit initializers and cannot redeclare a name. Assignment does
not declare names. Arithmetic supports signed 32-bit decimal integer literals,
unary `+`/`-`, binary `+`/`-`/`*`, and parentheses.
Comparisons add `<`, `<=`, `>`, `>=`, `==`, and `!=`; their results
are `bool`, usable in prints, boolean stores, and conditions, but not arithmetic.
Precedence from highest to lowest is parentheses, unary signs, multiplication,
addition/subtraction, relational comparisons, then equality/inequality.
Binary operators at each level associate left, including comparison chains:
`3 > 2 > 1` means `(3 > 2) > 1`, not a mathematical range test, and is now
rejected because the second `>` receives a boolean operand. Likewise
`2 == 2 == 1` fails; `(2 == 2) == true` is valid.
Only booleans may be conditions. `while` checks before every iteration.
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
arguments; arguments must match parameter types, and return expressions must
match the annotated return type (or `int` when omitted). There are no conversions.
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
  Conditions are not constant-folded: even `if (true) { x = 1; }` is conservative.
- A `while` may execute zero times. Its condition and body are checked using
  the incoming state; earlier assignments within that iteration count for later
  statements, but body assignments do not establish initialization afterward
  or justify a read before an assignment on the first iteration.
- Nested blocks share the same scope and propagate initialization in source
  order; nested branches and loops apply these same rules recursively.

For example, `let x; if (true) { x = 2; } else { x = 3; } print x;` is valid.
`if (false) { let x = 9; } print x;` and
`while (false) { let x = 9; } print x;` are semantic errors, not zero-valued reads.
Unreachable bodies are still checked.
The same checks apply to call arguments and returned expressions, independently
for each function. For example,
`fn f(n: bool) { let x; if (n) { return 1; } else { x = 2; } return x; }`
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
inheritance, dynamic/polymorphic dispatch,
generics, external interfaces, non-integer numeric types, block-local
scopes, logical `&&`/`||`/`!`, `break`/`continue`, comments,
strings, division, or fractions. Integers use the fixed-width range and checked
overflow contract above; wider numeric types are deferred.
The generated parser's existing input,
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
receiver signatures, zero construction, reference aliases, field mutation/access, rebinding,
static/forward/recursive method calls, local objects in free functions, method
control flow, object definite assignment, empty classes, C-safe names, invalid
members/types/arity/duplicates, exact diagnostic locations, and syntax-only
acceptance in both parser backends. Reference regressions cover distinct classes
with identical member names, forward/self/mutually referential fields, nested
reads/stores/calls, typed free-function/method parameters, escaped local objects,
receiver/parameter rebinding, and multi-class metadata growth. Allocation
instrumentation checks cleanup of cycles and loop allocations, null-receiver
failure paths, and each partial/complete allocation-failure position.
Primitive regressions check explicit/inferred `int`/`bool`, exact operator and
call/return compatibility, bool fields and constructor writes, class-valued
returns, bool-aware definite assignment and conservative return analysis,
source-token locations for expression errors, rejected numeric truthiness,
and syntax-only acceptance of semantic-invalid typed programs in both backends.
Integer boundary regressions cover minimum/maximum literals and typed storage,
leading zeros, exact out-of-range token locations, very long literals,
positive/negative add/subtract/multiply overflow, minimum-value negation,
valid arithmetic near the bounds, left-associated intermediate overflow,
unexecuted overflow, and unchanged boolean results.
Direct test runs use the same SDK discovery and `CPARSEGEN_C_COMPILER`,
`CC`, and optional `CPARSEGEN_C_FLAGS` conventions as the expression tests.

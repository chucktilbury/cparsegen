# Proving the SmallC toolchain end to end

The four programs in [end_to_end/](end_to_end) collectively exercise the
**executable SmallC subset**, including console and binary file I/O. They are
not merely parsing examples: each is compiled, assembled and executed in the
automated tests. Commands below run from the **cparsegen repository root**
unless a `cd` is shown.

## 1. Prerequisites and build

You need CMake, a host C compiler, Python 3 for tests and fixture generation,
and a separately installed **Cwhip SDK 0.0.2** with the `numeric-v2` ABI and
configurable application output directories. See [Building](../../doc/BUILDING.md) for SDK installation
and discovery. Select the whole SDK prefix, not just its `bin` directory.

Install the official [CVM tools](https://github.com/chucktilbury/cvm) separately.
The file example requires `cvm-as` and `cvm-run` with the integer file-handle
services `file_open`, `file_read_handle`, `file_write_handle` and
`file_close_handle` (service IDs 9 through 12). A version number alone is not
enough to identify support: an older assembler reports `unknown service`.
Use matching assembler/runner builds containing those services.

Replace these two placeholder prefixes with your installations:

```sh
export CWHIP_SDK=/absolute/path/to/cwhip-sdk
export CVM_PREFIX=/absolute/path/to/cvm-install
export PATH="$CVM_PREFIX/bin:$PATH"
./scripts/setup
```

In the project shell, build the examples:

```sh
cd ..
build smallc smallc-cvm
mkdir -p build/smallc-demo
```

For nonstandard tool names/locations or to require CVM tools at configuration
time, use CMake directly with `-DCVM_AS=/absolute/path/to/cvm-as`,
`-DCVM_RUN=/absolute/path/to/cvm-run`, and/or
`-DCPARSEGEN_REQUIRE_CVM_TOOLS=ON`. Setup intentionally exposes no arbitrary
CMake cache arguments; the commands below assume the standard names are on
`PATH`.

CMake first builds cparsegen, uses it to generate the SmallC scanner/parser
and AST support, then compiles the handwritten SmallC checker/backend with
Cwhip. **cparsegen generates parsers, not a complete compiler from the grammar
alone.** The handwritten app supplies semantics and assembly emission.
The resulting compiler has no runtime dependency on cparsegen and does not
import CVM packages. Commands assume the default `bin/` output directory; if
you set `CWHIP_BIN_DIR`, use that directory instead.

## 2. Understand the three artifacts

```text
SmallC source (.c)
    | smallc-cvm: parse, check, walk AST and emit text
    v
CVM assembly (.asm)
    | official cvm-as: resolve symbols, calculate stack limits, encode
    v
CVM binary (.cvm)
    | official cvm-run
    v
guest output and return value
```

`smallc-cvm INPUT.c OUTPUT.asm` writes assembly only after successful
compilation. It never builds a binary container. Assembly is readable text
with `.version`, `.entry`, declarations, `.func`/`.end`, symbolic labels and
instructions; `cvm-as` alone produces the executable binary.

Optionally inspect the frontend independently:

```sh
./bin/smallc-ast --check examples/smallc/end_to_end/arrays_functions.c \
  > build/smallc-demo/arrays_functions.ast.json
python3 -m json.tool build/smallc-demo/arrays_functions.ast.json
```

Without `--check`, this CLI validates syntax only. Neither AST mode executes
the program. The standalone `smallc-c` target is also syntax-only; it is not
an alternative to `smallc-cvm`.

## 3. Arithmetic and structured control flow

[operators_control.c](end_to_end/operators_control.c) checks its own results.
Its return codes 1 through 16 identify a failed check; zero means success.

```sh
./bin/smallc-cvm examples/smallc/end_to_end/operators_control.c \
  build/smallc-demo/operators_control.asm
head -n 25 build/smallc-demo/operators_control.asm
cvm-as build/smallc-demo/operators_control.asm \
  -o build/smallc-demo/operators_control.cvm
cvm-run build/smallc-demo/operators_control.cvm
```

Expected stdout:

```text
result: 0
```

The example covers precedence, grouping, unary signs, signed division and
remainder, comparisons, logical negation, short-circuit `&&`/`||` with
observable side effects, chained/compound assignments, prefix/postfix
increments/decrements, nested `if`/`else`, `while`, `for` with declaration or
expression initialization and omitted clauses, `break`, `continue`, an empty
statement, and block-local shadowing. The automated test also builds it with
strict ISO C99 and compares the host result with CVM.

## 4. Arrays, globals and functions

[arrays_functions.c](end_to_end/arrays_functions.c) combines a prototype and
later definition, nested calls, recursive factorial, `int` and `char`
parameters/returns, zero-initialized global state, and a global initialized
by a function call before `main`.

```sh
./bin/smallc-cvm examples/smallc/end_to_end/arrays_functions.c \
  build/smallc-demo/arrays_functions.asm
cvm-as build/smallc-demo/arrays_functions.asm \
  -o build/smallc-demo/arrays_functions.cvm
cvm-run build/smallc-demo/arrays_functions.cvm
```

Expected stdout:

```text
result: 48
```

It checks fixed/inferred local and global arrays, brace initializers with a
trailing comma, string/character escapes, runtime local initializers,
indexing, array mutation and increments. Returns 1 through 4 indicate a
failed internal check; success returns `twice(factorial(4))`, or 48.
Unlike ISO C99, this SmallC compiler permits a runtime global initializer
such as `int bias = seed();`, so this particular source is not a host-C
parity fixture.

## 5. Console output

[console.c](end_to_end/console.c) exercises all three forms of `print` input:
a NUL-terminated array, an array without a NUL, and a string literal.
It also proves that bytes after an embedded NUL are not printed.

```sh
./bin/smallc-cvm examples/smallc/end_to_end/console.c \
  build/smallc-demo/console.asm
cvm-as build/smallc-demo/console.asm -o build/smallc-demo/console.cvm
cvm-run build/smallc-demo/console.cvm
```

Expected stdout:

```text
SmallC -> CVM assembly -> binary
OK
yes
result: 0
```

`print(char[])` writes bytes up to the first NUL or the array's extent,
without adding a newline. The compiler retries short console writes.
It does not interpret arbitrary output bytes as UTF-8 strings.

## 6. Binary copy, EOF, truncate and append

[binary_copy.c](end_to_end/binary_copy.c) reads `input.bin`, writes `copy.bin`
and records `OK\n` in `copy.log`. These paths are relative to **the runner's
working directory**, not the source or binary location. Run it inside a
dedicated directory because `"w"` truncates existing output files:

```sh
./bin/smallc-cvm examples/smallc/end_to_end/binary_copy.c \
  build/smallc-demo/binary_copy.asm
cvm-as build/smallc-demo/binary_copy.asm \
  -o build/smallc-demo/binary_copy.cvm

(
  cd build/smallc-demo
  python3 -c 'from pathlib import Path; Path("input.bin").write_bytes(bytes(range(256)))'
  cvm-run binary_copy.cvm
  cmp input.bin copy.bin
  python3 -c 'from pathlib import Path; assert Path("copy.log").read_bytes() == b"OK\n"'
)
```

Expected runner stdout:

```text
OK
result: 256
```

`cmp` and the Python assertion are silent on success. The payload includes
every byte 0 through 255, including NUL and non-UTF-8 values. No text
conversion is involved in the copy.

The program closes every handle. It demonstrates `"r"` (binary read),
`"w"` (create/truncate) and `"a"` (create/append), short-transfer-safe copying
in 64-byte chunks, a positive read returning zero at EOF, and a validated
zero-length read returning zero. A successful return is the copied byte
count (which can exceed the host shell's exit-code range).

The source APIs are exactly:

| Built-in | Result and semantics |
| --- | --- |
| `open(path, mode)` | `int` handle; both arguments are `char[]`, mode exactly `"r"`, `"w"` or `"a"` |
| `read(handle, length, buffer)` | Actual byte count, zero at EOF for a positive request |
| `write(handle, length, buffer)` | Actual byte count, possibly less than requested |
| `close(handle)` | Void-like; use as a statement |

Read/write start at **buffer index zero** on every call. `length` must be
nonnegative and no greater than the array capacity. A short write is not
an error: the example copies the unwritten tail to the front before retrying.
Positive writes either make progress or report an I/O error. The small log
uses single-byte writes so that positive progress completes each request.
I/O failures are explicit VM errors, not negative return values or fake EOF.
Do not call `print` to copy binary data: it stops at NUL.

To repeat the EOF case with an empty file:

```sh
(
  cd build/smallc-demo
  python3 -c 'from pathlib import Path; Path("input.bin").write_bytes(b"")'
  cvm-run binary_copy.cvm
  cmp input.bin copy.bin
)
```

Expected stdout is `OK` followed by `result: 0`, each on its own line.

## 7. Automated evidence and limitations

```sh
build test-smallc-cvm
```

Tests compile these actual files to assembly, invoke the official assembler
and runner, and assert exact stdout and process status. The operator program
also has host-C parity. The copy test verifies byte-for-byte output for
empty, 256-byte and 1025-byte inputs (multiple chunks and a partial final
chunk), and verifies truncate/append behavior even with pre-existing output
files. An ordinary file-backed runner may satisfy each write in full;
the example contains a short-write retry loop, but this test does not
artificially force the host to return short writes.

No CVM tools means execution tests are skipped. An old assembler without
the handle services skips file tests even when the tools are required.
**A skipped file test is not proof of file support.** Use the updated
tools and check that all `test_documented_*` tests pass without skips.

The VM CLI prints `result: N`; successful execution has process exit status
zero even when the guest returns 48 or 256. Compiler, assembler and runtime
errors instead produce stderr diagnostics and a nonzero process status.
Thus checking `$?` alone does not check the guest's answer.

These examples cover the supported compiler, not full C:

- `switch`/`case`/`default`, labels and `goto` exist in the grammar/checker
  but are rejected by the assembly backend. See `valid/control.c` for a
  **frontend-only** example, not an executable backend demo.
- Types are signed checked 32-bit `int` and unsigned 8-bit `char`.
  There are no user-defined `void` functions, pointers, casts, array
  parameters, multidimensional arrays, structs, preprocessor, floating point,
  bitwise operators, or general library linking. Non-main functions must
  satisfy the compiler's conservative return-path check.
- Built-ins are recognized by the checker, not declarations you include
  from a header. Do not declare or redefine their names. Only built-ins
  accept a bare char-array name or string literal as a buffer argument.
  `print` and `close` have no value and cannot be assigned or returned.
- Arithmetic overflow, division by zero, invalid array indexing, invalid
  handles, bad modes, invalid lengths and host I/O failures do not silently
  succeed; the VM reports errors. There is no SmallC exception handler.

See the [SmallC reference](../../doc/SMALLC.md) for the full syntax/checker boundary
and [build documentation](../../doc/BUILDING.md) for SDK/tool discovery.

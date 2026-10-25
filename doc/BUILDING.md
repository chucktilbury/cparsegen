# Building

This project consumes the installed CWhip SDK; it does not vendor, download,
or build the compiler or SDK during CMake configuration. A fresh checkout
needs a separately installed compiler-only SDK and its host prerequisites.
The following explicit source-build sequence installs the current compiler
SDK into a user-owned prefix; Cwhip records that prefix in its
`sdk.toml`, which this project discovers automatically:

```sh
git clone --depth 1 https://github.com/chucktilbury/cwhip.git "$HOME/Src/cwhip"
cmake -S "$HOME/Src/cwhip" -B "$HOME/Src/cwhip-build" \
  -DCMAKE_BUILD_TYPE=Debug \
  -DCWHIP_STAGE_PREFIX="$HOME/Src/cwhip-build/stage" \
  -DCMAKE_INSTALL_PREFIX="$HOME/.local/cwhip" \
  -DCMAKE_INSTALL_LIBDIR=lib \
  -DBUILD_TESTING=OFF -DCWHIP_GTK=OFF -DCWHIP_GTK_SOURCEVIEW=OFF
cmake --build "$HOME/Src/cwhip-build" --target cwhip --parallel 4
cmake --install "$HOME/Src/cwhip-build"
```

Install the host prerequisites listed in the [Cwhip SDK installation
guide](https://github.com/chucktilbury/cwhip/blob/master/doc/GETTING_STARTED.md#host-prerequisites)
first. This project requires the exact Cwhip SDK version `0.0.2`, the
`numeric-v2` SDK ABI, and an installation that supports configurable
application output directories and the `cwhip_apply_application_defaults()`
CMake helper. Older SDK installations may not provide the required ABI or
capabilities.
Use an SDK built from current Cwhip `master`: version `0.0.2` and ABI
`numeric-v2` alone do not identify its source syntax revision. The generator,
examples, and emitted Cwhip use parenthesized keyword arguments such as
`return(value)`. Older compilers that require `return value` are unsupported.
The standalone C99 output and `.cpg` grammar syntax are unchanged.
Keep the complete SDK prefix; do not point the project at just its `bin/`
directory. The installer registers the prefix in the dedicated
`sdk.toml`; cparsegen only reads this configuration and never edits user
settings. For an existing SDK, use the selection options below instead of
rebuilding it.

## Select an SDK

SDK selection follows this order:

1. A non-empty `CWHIP_SDK` environment variable. It selects only that prefix;
   it bypasses configuration parsing, and an invalid explicit prefix fails
   instead of falling back.
2. The registered top-level `sdk_prefix` from
   `$XDG_CONFIG_HOME/cwhip/sdk.toml`, or
   `$HOME/.config/cwhip/sdk.toml` when `XDG_CONFIG_HOME` is unset or empty.
   A non-empty `XDG_CONFIG_HOME` is exclusive and must be absolute.
   `settings.toml` is consulted only when `sdk.toml` is absent. Invalid TOML
   or an invalid `sdk_prefix` in the selected file is an error.
3. Normal CMake package discovery, including `CMAKE_PREFIX_PATH`.

The dedicated `sdk.toml` keeps the SDK location separate from application
preferences that an editor may rewrite. If `sdk.toml` exists but has no
top-level `sdk_prefix`, cparsegen proceeds to normal CMake discovery and does
not consult `settings.toml`. Discovery is read-only; it does not create or
modify either configuration file.

After SDK discovery, cparsegen calls the SDK's
`cwhip_apply_application_defaults()` helper. The helper applies the registered
`[applications].install_prefix` and `[applications].build_type` as CMake
defaults only when the selected SDK's canonical install prefix matches the
registered `sdk_prefix`. Explicit `-D` values, existing CMake cache entries,
and the `CMAKE_INSTALL_PREFIX` and `CMAKE_BUILD_TYPE` environment variables
win. The setup script leaves the build type unspecified when no mode argument
is given, allowing the SDK default or an existing cache value to take effect;
`scripts/setup debug|release|profile` explicitly overrides it.
`cmake --install build` uses the inherited install prefix; pass `--prefix` or
set `DESTDIR` when installing elsewhere or staging a package. Staging does not
change the registered SDK settings.

To select an SDK explicitly, point `CWHIP_SDK` at its whole installed prefix:

```sh
export CWHIP_SDK=/path/to/cwhip-sdk
./scripts/setup
```

For either explicit or registered selection, CMake clears a stale cached
`Cwhip_DIR` and searches only the selected prefix. The project shell also adds
the selected SDK's `bin/` directory to `PATH`. To use normal CMake discovery,
unset `CWHIP_SDK`, remove `sdk_prefix` from `sdk.toml` (and, if that file is
absent, from legacy `settings.toml`), and configure the project.

## Troubleshoot missing package configuration

If CMake reports that it cannot find `CwhipConfig.cmake` or
`cwhip-config.cmake`, those are alternative package filenames, not files
cparsegen generates. The SDK normally installs
`lib/cmake/Cwhip/CwhipConfig.cmake` beneath its prefix. A compiler on `PATH`
alone is not enough for CMake discovery.

If configuration reports a missing application-defaults capability, the
selected SDK is too old even if it reports version `0.0.2`. Rebuild and
reinstall the updated Cwhip SDK into the prefix named in the error, following the
installation sequence above, or select an updated installed SDK with
`CWHIP_SDK`. Its `CwhipConfig.cmake` must include the installed
`CwhipApplicationDefaults.cmake` and provide
`cwhip_apply_application_defaults()`. Updating source alone does not update an
installed SDK. cparsegen fails rather than silently skipping defaults or
selecting a different SDK.

Configuration also requires `Cwhip_SDK_ABI` to be `numeric-v2`. This rejects
older or mismatched SDKs before building against incompatible numeric types.
Applications and native packages must be rebuilt against this ABI; package
manifests identify it with `[package] sdk-abi = "numeric-v2"`.
When changing SDK installations, use a fresh build directory so cached package
locks do not retain dependencies from the previous SDK (`CWHIP9001`).

For an SDK already installed at a known prefix, select it explicitly:

```sh
export CWHIP_SDK="/absolute/path/to/cwhip-sdk"
test -f "$CWHIP_SDK/lib/cmake/Cwhip/CwhipConfig.cmake"
./scripts/setup
```

The same override works without the project shell:

```sh
CWHIP_SDK="/absolute/path/to/cwhip-sdk" cmake -S . -B build
cmake --build build
```

A selected file without a **top-level** `sdk_prefix` does not register an
SDK, even if it contains other settings. A present `sdk.toml` is authoritative:
if it is malformed or its prefix is invalid, discovery fails rather than
falling back to `settings.toml` or a cached SDK. If no SDK is installed,
follow the installation steps above first. Do not rename package files or
select arbitrary sibling compiler build directories. Invalid explicit or
registered selections fail rather than reuse a cached SDK.

## Configure and build

The generator links a small C99/POSIX path-identity helper (`src/paths.c`)
with CMake's host C compiler. It detects existing hard-link aliases, which
the SDK's path API does not expose; parser/scanner/AST generation remains
in Cwhip. This helper is not needed by generated parsers.

The optional `calculator-c` and `smallc-c` targets generate and compile standalone
ISO C99 syntax parsers with CMake's host C compiler (strict warnings-as-errors
on GCC/Clang). The Cwhip SDK is needed to
build/run cparsegen, but not to compile or execute its generated C source.
`ctest --test-dir build` (or `make -C build test`, after building) also compiles C
fixtures with this host compiler and compares them with Cwhip under private
HOME/XDG directories. See [Standalone C](USAGE.md#standalone-c-target)
for direct generator/compiler commands and the bounded backend scope.

The setup script configures the `build/` directory and launches an interactive
project shell there. Its build type argument is optional:

| Argument | CMake build type |
| --- | --- |
| Omitted | Existing cache value, environment override, SDK application default, or empty |
| `debug` | `Debug` |
| `release` | `Release` |
| `profile` | `RelWithDebInfo` |

Build the generator and compile/run its generated parser from the project
shell:

```sh
cmake --build .
mkdir -p generated
../bin/cparsegen --dot generated/shortest.dot ../tests/fixtures/shortest.cpg generated/shortest.cw
cwhip generated/shortest.cw -o generated/shortest-parser
printf '123+456' > generated/input.txt
generated/shortest-parser generated/input.txt
```

The Cwhip application helper writes generated sources and package metadata
inside the build tree. The compiled generator is written directly to `bin/`.
Neither `bin/` nor `lib/` is created during configuration; the build creates
an output directory only when a target needs it.

## Customize output directories

The cache variables `CWHIP_BIN_DIR` and `CWHIP_LIB_DIR` choose output
locations. They default to the project-root `bin/` and `lib/`; native runtime
targets use the former, and native library/archive targets use the latter.
For example:

```sh
cmake -S . -B build \
  -DCWHIP_BIN_DIR="$PWD/out/bin" \
  -DCWHIP_LIB_DIR="$PWD/out/lib"
cmake --build build
```

The generator executable follows `CWHIP_BIN_DIR`. Generated output
directories are ignored by Git.

## Run tests

From the repository root, configure and run all black-box and SDK-selection
tests:

```sh
cmake -S . -B build
cmake --build build --parallel 4
ctest --test-dir build --output-on-failure -j4
```

For Unix Makefiles, the equivalent clean-build workflow is:

```sh
cmake -S . -B build -G "Unix Makefiles"
cd build
make -j4
make test
```

CTest registers one named suite per `tests/test_*.py` module: 18 suites,
named `cparsegen_analysis`, `cparsegen_cli`, etc. Each runs Python unittest
discovery for only that module, including the generated calculator and SmallC
acceptance tests. The normal build includes cparsegen and `smallc-cvm` when
`BUILD_TESTING=ON` (the default); other fixtures and example consumers are
compiled in the tests' temporary directories. The SmallC assembly tests use
installed `cvm-as` and `cvm-run` when found (see below).
CTest and CMake's built-in `test` target do not build prerequisites: always
build first. A failing suite fails CTest and the `test` target.
CTest passes the configured generator executable (including a custom
`CWHIP_BIN_DIR`) and the SDK selected during configuration, even when selected
via `CMAKE_PREFIX_PATH` or `Cwhip_DIR`. Each suite has a separate working
directory, HOME/XDG directories, and temporary root under
`build/tests/cparsegen_<module>/`, so suites can run concurrently with `-j`.
Tests do not register or install into the selected SDK; install smoke checks
use private prefixes. Configure with `-DBUILD_TESTING=OFF` to omit test
registration and the normal build's SmallC CVM test prerequisite.

List suites or select a module/label without running everything:

```sh
ctest --test-dir build -N
ctest --test-dir build --output-on-failure -R '^cparsegen_cli$'
ctest --test-dir build --output-on-failure -L '^smallc-cvm$'
```

The `test-smallc-cvm` convenience build target is retained; it builds
`smallc-cvm` and runs the same labeled CTest suite with the full isolated
environment.

For direct unittest execution after building the generator, from the
repository root:

```sh
python3 -m unittest discover -s tests -v
```

Direct execution needs the SDK's `cwhip` executable on `PATH`, in `CWHIP_SDK`,
or under `CMAKE_PREFIX_PATH`. Set `CWHIP_SDK` to include the installed-SDK
integration test. If you customized `CWHIP_BIN_DIR`, also set
`CPARSEGEN_EXECUTABLE` to the absolute path of the built generator.

The [feature/target matrix](TEST-COVERAGE.md) maps named tests to the
implemented contracts, with sampled-versus-exhaustive scope, API differences,
and validation outcomes. The installed-SDK opt-in also installs cparsegen to
a private prefix and generates, compiles, and runs both C and Cwhip from that
installed binary.
Optional artifact/diagnostic parity needs a separately built baseline:

```sh
CPARSEGEN_BASELINE_EXECUTABLE=/absolute/path/to/baseline/cparsegen \
  ctest --test-dir build --output-on-failure
```

Use a CLI-compatible current-main build; see the matrix's
[reproduction commands](TEST-COVERAGE.md#audit-reproduction-and-recorded-outcomes).
For a historical binary predating `--dot`, also set
`CPARSEGEN_BASELINE_POSITIONAL_DOT=1`. Without a baseline, the two parity
tests explicitly skip; without `CWHIP_SDK`, direct unittest runs skip the
real installed-SDK test. Include permission checks skip when run as root.
The documentation suite checks tracked local Markdown links/anchors and
executes representative generation/compilation/CLI/library/insertion snippets
in temporary directories using unittest under CTest. Individual unittest
skips remain visible with `ctest -V`; they do not mark a whole module skipped
when its other checks pass.

## Build the calculator example

From the repository root:

```sh
cmake --build build --target calculator
./bin/calculator -e '(2 + 3) * 4'
./bin/calculator
```

The optional target generates an includeable parser and DOT graph in
`build/calculator/`, then compiles the separate evaluator/CLI with the selected
SDK. Compilation uses private HOME/XDG directories in that build tree.
The executable follows `CWHIP_BIN_DIR`, just like cparsegen. See
[Examples](EXAMPLES.md) for the grammar, variables, batch input, error
handling, and a smaller identifier-list example.

## Build the SmallC AST frontend

```sh
cmake --build build --target smallc
./bin/smallc-ast examples/smallc/valid/functions.c > build/smallc/functions.ast.json
```

Like the calculator, this optional target generates its parser and DOT graph
in `build/smallc/` and builds with the selected SDK using private HOME/XDG
directories. Its executable follows `CWHIP_BIN_DIR`. The JSON output is a
syntax AST, not a compiled/executed program. `smallc-ast --check INPUT.c`
validates the AST's supported source-order semantic rules while preserving
the JSON output; the default command remains syntax-only. See
[SmallC](SMALLC.md) for the language subset, valid/invalid
samples, checked/deferred semantic rules, and the bytecode boundary.

For the standalone C99 frontend with the same JSON AST and source diagnostics:

```sh
cmake --build build --target smallc-c
./bin/smallc-c --json examples/smallc/valid/functions.c
```

The target generates `build/smallc-c/parser.c` and `grammar.dot`, then compiles
`bin/smallc-c` (`CWHIP_BIN_DIR` applies). Compilation/execution of the generated
source needs no SDK/runtime library. `--json` always requires complete input.
The CTest suite includes all SmallC samples and shared syntax checks against both
parser backends, comparing full JSON ASTs and lexical/parser diagnostic
locations, as well as table-driven semantic checks through the Cwhip app.
Neither parser backend executes SmallC; standalone C remains syntax-only.

## Build the SmallC CVM assembly compiler

`smallc-cvm` is a Cwhip application that needs only the Cwhip SDK. It emits
**textual CVM assembly**; it does not import CVM packages, build containers or
encode bytecode. The official CVM tools are a separate, independently
installed toolchain: `cvm-as` (assembler, the only producer of the binary) and
`cvm-run` (runner).

```sh
cmake --build build --target smallc-cvm
./bin/smallc-cvm examples/smallc/valid/functions.c build/example.asm
cvm-as build/example.asm -o build/example.cvm
cvm-run build/example.cvm
cmake --build build --target test-smallc-cvm
# Or, after building:
ctest --test-dir build --output-on-failure -L '^smallc-cvm$'
```

The executable follows `CWHIP_BIN_DIR`. The tests locate the CVM tools at
configure time: `-DCVM_PREFIX=/path/to/cvm-install` (searches `bin/`),
`-DCVM_AS=/path/to/cvm-as -DCVM_RUN=/path/to/cvm-run`, or `PATH`. The tests
read `CPARSEGEN_CVM_COMPILER`, `CPARSEGEN_CVM_ASSEMBLER` and
`CPARSEGEN_CVM_RUNNER`, which CMake sets. Emitted-text and checker tests always
run; assembler/runner tests are skipped with a message when the tools are
missing, or when the installed `cvm-as` lacks the file-handle services. Pass
`-DCPARSEGEN_REQUIRE_CVM_TOOLS=ON` to make missing tools a configuration
error.

`smallc-cvm INPUT.c OUTPUT.asm` preserves the syntax-only and `--check` AST
frontends and applies the existing semantic checker before lowering. See
[SmallC](SMALLC.md#compile-and-run-with-cvm) for supported
constructs, built-in I/O functions, runtime behavior and unsupported
diagnostics.

Optional host-C sanitizer validation, using the same test runner:

```sh
CPARSEGEN_C_FLAGS='-fsanitize=address,undefined -fno-omit-frame-pointer -g' \
  ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 \
  UBSAN_OPTIONS=halt_on_error=1 \
  ctest --test-dir build --output-on-failure
```

Use the configured SDK and private HOME/XDG environment as for `make test`;
the flag affects generated C fixtures, not SDK binaries.

## Build the visitor integration example

```sh
cmake --build build --target visitor-c
./bin/visitor-c 'alpha, beta, gamma'
```

This optional target generates `build/visitor-c/parser.c` from `examples/words.cpg`
and compiles the handwritten `examples/visitor/words.c` with strict C99 settings.
The executable follows `CWHIP_BIN_DIR`. See [Application integration](VISITORS.md)
for equivalent direct generation/build commands, a runnable Cwhip subclass
example, and the public API's traversal, error, and lifetime contracts.

## Build the compiler examples

```sh
cmake --build build --target expression-compiler statement-compiler
./bin/statement-compiler examples/compiler/statements/basic.stmt \
  > build/statement-compiler/program.c
cc -std=c99 -Wall -Wextra -Werror -pedantic \
  build/statement-compiler/program.c -o build/statement-compiler/program
./build/statement-compiler/program
```

These optional host-C targets honor `CWHIP_BIN_DIR` and generate parsers under
`build/expression-compiler/` and `build/statement-compiler/`. They use strict C99
settings and need no new dependencies. See the
[expression guide](EXPRESSION-COMPILER.md) and
[statement guide](../examples/compiler/STATEMENTS.md) for explicit generation,
syntax-only parsing, visitor state, generated C, and diagnostics.
Both end-to-end suites are registered with CTest and run by `make test` after
building.

## Clean

Use CMake's normal clean target to remove generated build artifacts:

```sh
cmake --build build --target clean
```

Rebuilding recreates the required output directories.

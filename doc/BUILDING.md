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
first. This project requires the exact Cwhip SDK version `0.0.1` and an
installation that supports configurable application output directories.
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

The optional `calculator-c` and `smallc-c` targets generate and compile standalone
ISO C99 syntax parsers with CMake's host C compiler (strict warnings-as-errors
on GCC/Clang). The Cwhip SDK is needed to
build/run cparsegen, but not to compile or execute its generated C source.
`cmake --build build --target test` (or `make -C build test`) also compiles C
fixtures with this host compiler and compares them with Cwhip under private
HOME/XDG directories. See [Standalone C](../README.md#standalone-c-target)
for direct generator/compiler commands and the bounded backend scope.

The setup script configures the `build/` directory and launches an interactive
project shell there. Its build type argument is optional:

| Argument | CMake build type |
| --- | --- |
| `debug` (default) | `Debug` |
| `release` | `Release` |
| `profile` | `RelWithDebInfo` |

Build the generator and compile/run its generated parser from the project
shell:

```sh
cmake --build .
mkdir -p generated
../bin/cparsegen ../tests/fixtures/shortest.cpg generated/shortest.cw generated/shortest.dot
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
cmake --build build --target test
```

For Unix Makefiles, the equivalent clean-build workflow is:

```sh
cmake -S . -B build -G "Unix Makefiles"
cd build
make test
```

The custom `test` target builds cparsegen before running Python unittest
discovery, including the generated calculator and SmallC acceptance tests.
Unlike CTest's built-in target, it has a build dependency on the generator;
no separate build step is required. A failing test fails the target.
The target passes the configured generator executable (including a custom
`CWHIP_BIN_DIR`) and the SDK selected during configuration, even when selected
via `CMAKE_PREFIX_PATH` or `Cwhip_DIR`. Tests run with private HOME/XDG
directories under `build/tests/` and do not register or install an SDK.

For direct unittest execution after building the generator, from the
repository root:

```sh
python3 -m unittest discover -s tests -v
```

Direct execution needs the SDK's `cwhip` executable on `PATH`, in `CWHIP_SDK`,
or under `CMAKE_PREFIX_PATH`. Set `CWHIP_SDK` to include the installed-SDK
integration test. If you customized `CWHIP_BIN_DIR`, also set
`CPARSEGEN_EXECUTABLE` to the absolute path of the built generator.

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
[Examples](../examples/README.md) for the grammar, variables, batch input, error
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
[SmallC](../examples/smallc/README.md) for the language subset, valid/invalid
samples, checked/deferred semantic rules, and the bytecode boundary.

For the standalone C99 frontend with the same JSON AST and source diagnostics:

```sh
cmake --build build --target smallc-c
./bin/smallc-c --json examples/smallc/valid/functions.c
```

The target generates `build/smallc-c/parser.c` and `grammar.dot`, then compiles
`bin/smallc-c` (`CWHIP_BIN_DIR` applies). Compilation/execution of the generated
source needs no SDK/runtime library. `--json` always requires complete input.
`make test` includes all SmallC samples and shared syntax checks against both
parser backends, comparing full JSON ASTs and lexical/parser diagnostic
locations, as well as table-driven semantic checks through the Cwhip app.
Neither parser backend executes SmallC; standalone C remains syntax-only.

Optional host-C sanitizer validation, using the same test runner:

```sh
CPARSEGEN_C_FLAGS='-fsanitize=address,undefined -fno-omit-frame-pointer -g' \
  cmake --build build --target test
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
[expression guide](../examples/compiler/README.md) and
[statement guide](../examples/compiler/STATEMENTS.md) for explicit generation,
syntax-only parsing, visitor state, generated C, and diagnostics.
Both end-to-end suites are discovered by `make test`.

## Clean

Use CMake's normal clean target to remove generated build artifacts:

```sh
cmake --build build --target clean
```

Rebuilding recreates the required output directories.

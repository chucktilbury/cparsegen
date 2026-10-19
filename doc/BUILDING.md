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

After building the generator, run the black-box and SDK-selection tests with:

```sh
python3 -m unittest discover -s ../tests -v
```

The black-box tests also compile generated Cwhip and therefore need the SDK's
`cwhip` executable on `PATH`, in `CWHIP_SDK`, or under `CMAKE_PREFIX_PATH`.

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

## Clean

Use CMake's normal clean target to remove generated build artifacts:

```sh
cmake --build build --target clean
```

Rebuilding recreates the required output directories.

# Building

This starter consumes the installed CWhip SDK; it does not build or download
the compiler or SDK for you. Use the complete SDK installation prefix, not
just its `bin/` directory. CMake requires SDK version `0.0.1` and an
installation that supports configurable application output directories.

## Select an SDK

If the SDK is already discoverable via `CMAKE_PREFIX_PATH`, no extra setting
is needed. Otherwise, point `CWHIP_SDK` at its whole installed prefix before
configuring:

```sh
export CWHIP_SDK=/path/to/cwhip-sdk
./scripts/setup
```

When `CWHIP_SDK` is set, CMake searches only that prefix. Switching the
environment variable also clears the previously cached `Cwhip_DIR`; an
invalid explicit prefix fails configuration rather than silently selecting a
different SDK. To use normal CMake discovery again, unset `CWHIP_SDK` and
configure the project.

## Configure and build

The setup script configures the `build/` directory and launches an interactive
project shell there. Its build type argument is optional:

| Argument | CMake build type |
| --- | --- |
| `debug` (default) | `Debug` |
| `release` | `Release` |
| `profile` | `RelWithDebInfo` |

Build and run the starter executable from the project shell:

```sh
cmake --build .
../bin/cparsegen
```

The Cwhip application helper writes generated sources and package metadata
inside the build tree. The compiled application is written directly to
`bin/`. Neither `bin/` nor `lib/` is created during configuration; the build
creates an output directory only when a target needs it.

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

The starter executable follows `CWHIP_BIN_DIR`. Generated output
directories are ignored by Git.

## Clean

Use CMake's normal clean target to remove generated build artifacts:

```sh
cmake --build build --target clean
```

Rebuilding recreates the required output directories.

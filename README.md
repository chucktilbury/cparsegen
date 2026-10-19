# cparsegen

A Cwhip parser-generator prototype using a target-neutral grammar model and
backend emitters. The current executable is intentionally a small, bounded
slice; its supported syntax and unimplemented areas are listed in the
[architecture proposal](doc/ARCHITECTURE.md).

## Get started

Install the Cwhip SDK and its host prerequisites; cparsegen does not vendor,
download, or build the SDK during CMake configuration. Follow the
[Cwhip SDK installation guide](https://github.com/chucktilbury/cwhip/blob/master/doc/GETTING_STARTED.md#build-and-install-the-sdk)
to install a compiler-only SDK. Then configure/build and generate both
outputs:

```sh
./scripts/setup
cmake --build .
mkdir -p generated
../bin/cparsegen ../tests/fixtures/shortest.cpg generated/shortest.cw generated/shortest.dot
cwhip generated/shortest.cw -o generated/shortest-parser
printf '123+456' > generated/input.txt
generated/shortest-parser generated/input.txt
```

The default build type is `debug`. Choose `release` or `profile` with
`./scripts/setup release` or `./scripts/setup profile`.

## Generated examples

Build a calculator with variables and an interactive CLI:

```sh
cmake --build build --target calculator
./bin/calculator
```

Try `x = 2 + 3 * 4`, `(x - 2) / 4`, and `:vars`. The calculator uses a
generated scanner/parser and a separate Cwhip evaluator, with arithmetic
precedence, parentheses, assignments, and complete-input checks.
See [Examples](examples/README.md) for batch mode, a comma-separated identifier
parser, the grammar files, and current limits.

## SDK selection

The project selects an installed SDK in this order: non-empty `CWHIP_SDK`,
the registered top-level `sdk_prefix` in
`$XDG_CONFIG_HOME/cwhip/sdk.toml` (or `$HOME/.config/cwhip/sdk.toml` when
`XDG_CONFIG_HOME` is unset or empty), then normal CMake discovery such as
`CMAKE_PREFIX_PATH`. The legacy `settings.toml` is read only when `sdk.toml`
does not exist, keeping SDK selection separate from editor preferences. See
[Building](doc/BUILDING.md) for override and troubleshooting details.

See [Building](doc/BUILDING.md) for SDK installation, selection, and
output-directory customization, and [Project shell](doc/PROJECT-SHELL.md) for
the shell environment and available commands. The architecture proposal and
provisional grammar fixtures are in [Architecture](doc/ARCHITECTURE.md),
[examples/expression.cpg](examples/expression.cpg), and
[tests/fixtures/shortest.cpg](tests/fixtures/shortest.cpg); none is a
finalized compatibility contract. See the
[changelog](doc/CHANGELOG.md) for updates.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).

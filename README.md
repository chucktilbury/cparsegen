# cparsegen

A Cwhip parser generator with a shared grammar model, Cwhip and standalone C99
backends, generated AST/visitor APIs, and runnable application examples.
`src/` contains the generator and embedded runtimes; `examples/` contains
grammars and consumers; `tests/` contains black-box and documentation tests;
`scripts/` contains setup, clean, and SDK-discovery helpers.

With an installed SDK, configure and enter the project shell with
`./scripts/setup`. In the project shell, `cd ..` to the repository root, then
`build` builds the project and `ctest --test-dir build --output-on-failure -j4`
runs the Python tests. CTest runs each module as a separately named, isolated
suite; see
[Run tests](doc/BUILDING.md#run-tests) for selection and optional tools.

See [Building](doc/BUILDING.md) for SDK requirements and setup,
[Usage](doc/USAGE.md) for workflows, [Input/output](doc/INPUT-OUTPUT.md) for
the implemented contract, [Examples](doc/EXAMPLES.md) for applications,
[Visitors](doc/VISITORS.md) for embedding, and
[Test coverage](doc/TEST-COVERAGE.md) for executable evidence.
[Architecture](doc/ARCHITECTURE.md), [Project shell](doc/PROJECT-SHELL.md),
and the [Changelog](doc/CHANGELOG.md) cover design, tooling, and history.

# cparsegen

`cparsegen` is a Cwhip parser generator with a shared grammar model, Cwhip and
standalone C99 backends, generated AST/visitor APIs, and runnable examples.
Source: [github.com/chucktilbury/cparsegen](https://github.com/chucktilbury/cparsegen).

This directory contains the generator and embedded runtimes in `src/`, grammars
and consumers in `examples/`, tests in `tests/`, and setup helpers in
`scripts/`.

With a current Cwhip SDK installed, run `scripts/setup [--clean] [debug|release|profile]`
from the checkout, then `build` in the project shell. Use `rebuild` for a
clean-first build, or `clean` to remove generated outputs; exit the shell before
running setup again. CTest runs each module as a named, isolated suite.

```sh
./scripts/setup
cd ..
build
ctest --test-dir build --output-on-failure -j4
```

- [Building](doc/BUILDING.md)
- [Usage](doc/USAGE.md)
- [Input and output](doc/INPUT-OUTPUT.md)
- [Examples](doc/EXAMPLES.md)
- [Visitors](doc/VISITORS.md)
- [Test coverage](doc/TEST-COVERAGE.md)
- [Architecture](doc/ARCHITECTURE.md)
- [Project shell](doc/PROJECT-SHELL.md)
- [Changelog](doc/CHANGELOG.md)

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).

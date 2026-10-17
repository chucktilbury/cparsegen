# cparsegen

A Cwhip parser-generator project bootstrapped with the Cwhip project template.
This initial template adoption provides the setup shell and SDK-backed build
conventions; the current `src/main.cw` is the template's hello-world example,
not the parser-generator implementation.

## Get started

Install the Cwhip SDK and its host prerequisites. If the SDK isn't
discoverable through `CMAKE_PREFIX_PATH`, set `CWHIP_SDK` to the SDK's whole
installation prefix. Then start the project shell and build:

```sh
./scripts/setup
cmake --build .
../bin/cparsegen
```

The default build type is `debug`. Choose `release` or `profile` with
`./scripts/setup release` or `./scripts/setup profile`.

See [Building](doc/BUILDING.md) for SDK selection and output-directory
customization, and [Project shell](doc/PROJECT-SHELL.md) for the shell
environment and available commands. See the [changelog](doc/CHANGELOG.md) for
updates.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).

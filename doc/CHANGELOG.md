# Changelog

## Unreleased

- Propose a target-neutral parser-generator architecture and add a provisional
  expression grammar fixture; syntax and implementation scope remain subject
  to review and sample-driven refinement.
- Clarify that grammar declarations may interleave, parser rules terminate
  with `;`, and parser shortest-match behavior differs from lexer longest
  match; leave unresolved syntax and include semantics open.
- Add a bounded Cwhip grammar reader, target-neutral declaration model and
  validation, plus Cwhip parser/AST/scanner and DOT emitters for a small
  fixture. Add generated-parser and SDK-discovery integration tests.
- Add explicit Cwhip SDK discovery through the registered `sdk_prefix`
  setting and document the standalone compiler SDK installation path.
- Read the SDK prefix from dedicated `sdk.toml`, using `settings.toml` only
  as a legacy fallback when the dedicated file is absent.
- Adopt the CWhip project template's setup shell, SDK-backed CMake configuration,
  configurable root output directories, and build documentation.
- Add the standard MIT license.

The parser generator remains an early prototype; consult the architecture
document for its current syntax boundary and deferred behavior.

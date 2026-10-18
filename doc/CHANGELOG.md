# Changelog

## Unreleased

- Propose a target-neutral parser-generator architecture and add a provisional
  expression grammar fixture; syntax and implementation scope remain subject
  to review and sample-driven refinement.
- Clarify that grammar declarations may interleave, parser rules terminate
  with `;`, and parser shortest-match behavior differs from lexer longest
  match; leave unresolved syntax and include semantics open.
- Adopt the CWhip project template's setup shell, SDK-backed CMake configuration,
  configurable root output directories, and build documentation.
- Add the standard MIT license.

The initial bootstrap includes the template hello-world executable. The
parser-generator implementation is not included in this change.

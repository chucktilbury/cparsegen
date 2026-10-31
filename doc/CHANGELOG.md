# Changelog

## Unreleased

- Parse argv through the SDK `cli` 0.1.0 package while preserving usage text,
  exit codes, duplicate-option rejection, and include-path empty-component rules.
- Read grammar bytes with `text[index]` and copy half-open spans through an
  inclusive range. Emitted Cwhip scanners use the same indexing. Empty spans
  stay empty. `String.byteAt` and `String.slice` are no longer SDK methods.
  C99 output and `.cpg` syntax are unchanged.
- Migrate generator sources, embedded Cwhip scanner/parser/AST/visitor
  templates, handwritten apps, insertion examples, test consumers, and
  documentation to current Cwhip syntax (`return(value)`). Rename local
  `range` variables to `interval` in sources and emitted scanners to avoid the
  current reserved type keyword. Keep bare void
  returns, C99 output, and `.cpg` semicolons unchanged. Pin representative
  generated return forms in the compile/run regression. Move detailed README
  guides into `doc/`, retain directory summaries, and update runnable links.

- Add the optional SmallC-to-CVM v1 compiler. Reuse the parsed, semantically
  checked AST and emit textual CVM assembly (`smallc-cvm INPUT.c OUTPUT.asm`);
  the official `cvm-as` produces the binary and `cvm-run` executes it. The
  compiler has no CVM package dependency. Add `print`, `open`, `read`, `write`
  and `close` built-ins lowered to CVM services. Cover
  scalar/array state, functions, arithmetic, and structured control flow;
  report unsupported switch/label/goto constructs at their source locations.
  Preserve the syntax-only AST CLI and standalone C frontend.

- Audit implemented features against named Cwhip/C CLI/library tests and add
  a maintained feature/target evidence matrix. Repair optional baseline parity
  to read real grammar paths and use the current CLI (legacy positional DOT
  is explicit opt-in). Add executable lifetime/legacy visitor, allocation-fault,
  NFA boundary, CLI, include-alias and documentation workflow regressions.
  Reconcile current architecture, resource limits and example documentation;
  preserve historical entries below. Fix statement-demo condition emission
  to compile parenthesized equality under strict Clang warnings without changing
  evaluation; generated parser bytes remain unchanged.

- Make the parser-output positional path optional: derive `.cw` (default or
  `--library`) or `.c` (`--target c`) beside the supplied grammar by replacing
  its filename's last extension. Generate DOT only with named `--dot FILE`;
  reject repeated `--dot` and the old third positional path. Allow options
  around positional paths, retain `--` and ordered include search paths,
  and reject input/output aliases (including includes, symlinks and hard links)
  and parser/DOT collisions before opening outputs. Migrate CMake examples,
  tests and documentation; add generation/compilation and path-safety CLI tests.

- Add a shared typed analysis phase (`src/analysis.cw`). `GrammarAnalyzer`
  runs once after include expansion and parsing and attaches `Analysis`
  (resolved references, lexer/parser nullability, left-corner edges and
  reachability, compiled lexer NFA plans, numbered parser expression table,
  provenance-preserving diagnostics) to the grammar model; Cwhip, C and DOT
  emitters consume it instead of recomputing. No language, diagnostic or
  generated-output change; the C directive allowlist stays backend validation.
  Add `tests/test_analysis.py` with optional baseline artifact parity.

- Implement `@insert c|cwhip BOUNDARY { BODY };` at twelve file-scope seams
  in both CLI/library workflows. Preserve opaque bodies and include encounter
  order in a source-located validated model; filter by target without changing
  parser/AST/visitor APIs. Collect nested braces, strings and C-style comments
  with explicit size/depth and translation-phase restrictions. Diagnose malformed
  blocks and unknown targets/seams before opening outputs. Add strict C99 and
  Cwhip runnable visitor/helper examples and preservation/placement regressions.

- Implement composable lexer expressions in both backends: grouping,
  alternation, concatenation, `?`/`*`/`+`, ASCII classes/ranges/negation,
  quoted literals and forward named-rule references. Define precedence and
  escaping; preserve simple class rules and allow optional lexer semicolons.
  Resolve/validate the shared AST and compile bounded Thompson NFAs before
  emitting either target. Reject empty tokens, nullable repetition, reference
  cycles, unknown/quoted-token references, and excessive nesting/expansion
  with source lines. Iterative deduplicated matching removes exponential
  scanner backtracking while preserving longest-byte selection, tie ordering,
  skips, keywords, comments, quoted input, and parser/AST APIs. Add cross-backend
  scanner/offset regressions, malformed-expression tests, and a runnable grammar.

- Support consuming direct, mutual/indirect, and nullable-prefix left recursion
  in both generated backends using span-bounded expansion. Preserve original
  rule nesting, source-order ties, precedence/associativity, caller
  continuations, and shortest-prefix/complete-input selection. Reject cycles
  with nullable context on both sides, which admit infinitely many equal-span
  derivations, with a source-line diagnostic and rewrite guidance. Existing
  parser budgets remain explicit failures; this is not a linear-time parser.
  Add cross-backend recognition/tree/order/budget regressions and library/
  visitor reuse coverage. No compiler-demo grammar or behavior changes.

- Scope cleanup: remove the object-oriented extensions (classes, objects,
  references, constructors, single inheritance, virtual dispatch) that were
  added to the optional statement compiler, along with their runtime, lowering,
  samples, tests, and documentation. cwhip is the separate full-featured OOP
  compiler. The bounded statement demo keeps variables, control flow, definite
  assignment, `int`/`bool` typed functions and calls, checked int32 arithmetic,
  and the small runtime helpers. The generator, scanner features, EBNF, AST
  accessors, visitors, C/Cwhip backends, SmallC, and the expression compiler
  are unchanged. The entries below are historical.

- Add single inheritance to the optional statement compiler, including
  `extends`, inherited field/method lookup, subtype-compatible reference
  upcasts, base-constructor initialization, and virtual dispatch through
  base-typed references and `self`. Lower classes to embedded C99 base
  subobjects with runtime class tags and typed dispatch functions. Add a
  runnable inheritance sample, strict C99 end-to-end regressions, and updated
  language/lowering documentation. Multiple and virtual inheritance remain
  deferred.

- Replace only the optional statement compiler's `double` integer lowering
  with signed 32-bit `int32_t`. Diagnose out-of-range decimal literals at their
  source tokens, accept directly negated `-2147483648`, and check executed
  addition, subtraction, multiplication, and unary negation via C99
  `int_least64_t` intermediates. Overflow reports the operation and exits with
  failure without signed-overflow UB. Keep `_Bool`, exact primitive typing,
  class/reference behavior, syntax-only parsing, and the expression compiler
  unchanged. Add strict C99 boundary/overflow execution regressions; wider
  numeric types remain deferred.

- Add explicit `int` and `bool` identities throughout the optional statement
  compiler: primitive/class annotations on locals, fields, parameters, and
  function/method returns; boolean literals; exact initialization, assignment,
  return, and call checking; integer-only arithmetic; boolean comparisons and
  conditions with no implicit conversions. Use C99 `_Bool` for booleans
  (integer lowering is superseded above). Class-valued returns copy references;
  static dispatch, ownership, definite assignment, and conservative return-path
  checks remain intact. Add a typed sample, source-token error locations,
  strict C99 execution tests, and semantic-invalid syntax-only regressions.
  Overloading, inheritance, and dynamic dispatch remain deferred.

- Extend the statement compiler to multiple classes with class-specific type
  metadata, class-typed fields and function/method parameters, nested member
  paths, and static dispatch. Object assignment/passing now preserves aliases
  instead of copying structs; receiver rebinding is local. Emit typed C99
  pointers, checked null dereferences, and program-lifetime allocations freed
  by an exit handler, including cycles and runtime failure paths. Add a
  reference sample, strict execution/diagnostic tests, and allocation-failure/
  cleanup instrumentation. Object returns, inheritance, virtual dispatch, and
  generics remain deferred; the parser-generator core is unchanged.

- Add a one-class object slice to the optional statement compiler: typed
  integer fields, zero construction, value-copy bindings, field reads/stores,
  and statically dispatched methods with explicit mutable receivers. Keep
  function/method scopes isolated and compose object initialization with
  definite-assignment/control-flow analysis. Add strict C99 execution,
  layout/lowering, semantic-diagnostic and syntax-only regressions, a runnable
  object sample, and pipeline/semantics documentation. Inheritance and dynamic
  dispatch remain deferred.

- Add integer-valued functions to the optional statement compiler: collected
  signatures, initialized parameters, isolated function-local symbols,
  value returns, nested/forward/recursive calls, arity validation, and
  return-aware definite-assignment joins. Emit C99 prototypes and definitions;
  keep parser-generator/visitor APIs and syntax-only semantics unchanged.
  Add strict C99 execution/error regressions and an end-to-end function sample.

- Add opt-in definite-assignment checking to the statement compiler visitor,
  with optional declaration initializers, both-arm `if`/`else` intersection,
  conservative no-else/zero-iteration loop handling, and source-located
  uninitialized-read errors. Preserve textual single-scope visibility and
  syntax-only parser acceptance. Add semantic tables and strict C99 execution
  regressions, including nested control flow and symbol-table growth.

- Extend the optional statement compiler with braced `if`/`else`, `while`,
  nested blocks, and all six relational/equality comparisons. Preserve textual
  single-scope name checking with hoisted zero-initialized storage and
  source-position initializer execution. Add strict C99 compile/run coverage
  for branches, loop boundaries, nested constructs, comparison precedence,
  skipped declarations, and source-located malformed-condition rejection.
  Update samples and the end-to-end walkthrough; parsers remain syntax-only.

- Extend the arithmetic compiler workflow with an optional `statement-compiler`
  example: declarations, assignments, printing, persistent visitor symbols,
  source-order C emission, and source-located semantic diagnostics. Add strict
  C99 compile/run tests, syntax-only boundary checks, samples, and a complete
  generation-to-execution guide; preserve the arithmetic example unchanged.

- Add an optional expression-to-C compiler example using generated AST visitor
  validation and dispatch, with explicit generation-to-execution documentation
  and end-to-end tests that compile emitted C and assert the program's result.
- Add read-only generated visitor interfaces on both backends: per-rule/token/
  literal dispatch, generic fallback, AST accessors, and a separate enter/leave
  walker with explicit skip/stop/error behavior. Retain the legacy Cwhip
  pre/post traversal. Expose include-based C parsing with caller-owned contexts,
  arena cleanup, and non-terminating library errors. Adopt the visitor for
  SmallC's existing duplicate-parameter check. Add runnable C/Cwhip consumers,
  the optional strict-C99 `visitor-c` target, public-contract regressions,
  and an end-to-end application integration guide.
- Extend standalone C generation to the existing SmallC grammar: keyword/
  reserved discrimination, quoted characters/strings, and skipped comments.
  Add optional `smallc-c`, complete-input `--json` AST/source diagnostics,
  and all-sample Cwhip differential coverage. Reject unsupported C directives
  before outputs (`@note` remains inert); retain the rendered CLI, default
  Cwhip generation, and syntax-only boundary.
- Add `--target c` with a standalone ISO C99 scanner/parser through the shared
  grammar IR. Add the optional `calculator-c` syntax-tree target and host-C
  conformance/differential tests under `make test`. Keep Cwhip as the default;
  the first C slice supports character-class regexes, EBNF, and `@skip`.
  The initial C slice did not yet expose a library interface.
- Add a generated SmallC JSON AST frontend, grammar, and valid/invalid source
  samples covering `int`/`char`, initializers, arrays, functions/prototypes/
  calls, and structured/unstructured control flow. Semantic checks, bytecode,
  and VM execution remain separate future milestones.
- Add opt-in keyword remapping/reserved words, quoted character/string
  tokens, and line/block comment directives for generated scanners. Preserve
  existing token/literal ties for grammars without keyword remapping.
- Measure parser nesting by rule calls rather than internal expression
  wrappers, permitting realistic expression nesting within the same bound.
- Add generated calculator and identifier-list examples. The calculator has
  variables, arithmetic precedence, decimals, parentheses, and interactive,
  batch, and single-expression CLI modes, with a separate AST evaluator.
- Extend grammar collection, validation, Cwhip generation, and DOT output for
  parser-rule references, groups, optional/repeated expressions, empty
  alternatives, ASCII lexer character-class sequences, and explicit skip
  tokens. Add library emission and complete-input parsing without changing
  the default shortest-prefix runner. Diagnose left recursion, nullable
  repetitions, and parser/scanner resource exhaustion.
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

The parser generator remains an early prototype; consult the
[input/output reference](INPUT-OUTPUT.md) for current behavior, the
[coverage matrix](TEST-COVERAGE.md) for executable evidence, and the
[architecture document](ARCHITECTURE.md) for deferred proposals.

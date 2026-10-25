# Feature and target verification

This is the maintained evidence map for the implemented
[input/output contract](INPUT-OUTPUT.md), not a claim that every possible
grammar, program, allocation schedule, or platform has been tested. When
changing a feature, update its named tests and this map together. A passing
test count is not a substitute for the feature evidence below.

## Scope and reading the matrix

The generator is cparsegen. SmallC is a C-subset demonstration; calculator,
expression/statement compiler semantics are handwritten consumers. cwhip is
the separate OOP compiler. No OOP demonstration expansion is part of this audit.

| Mode | Meaning |
| --- | --- |
| W | Default generated Cwhip file CLI: prefix or `--complete` |
| WL | `--library` Cwhip source included by a handwritten app |
| C | `--target c` standalone C99 file CLI: prefix, `--complete`, or `--json` |
| CL | The same C source included with `CPARSEGEN_NO_MAIN`, using `cpg_parse` |
| D | Optional `--dot FILE` graph; not a parser/backend |
| V | Generator validation shared by W/WL/C before any output is opened |

W/WL share one emitted scanner/parser implementation; C/CL share another.
The grammar/scanner/parser feature corpus executes both runtimes, predominantly
through W/C. Library tests separately exercise public APIs, inclusion, retained
trees, failures, and visitors; this is **not** a claim of the full Cartesian
product of every grammar with every public entry point. V assertions establish
generation/rejection, not execution. D assertions compare graph bytes, not
recognition. C is compiled with `-std=c99 -Wall -Wextra -Werror -pedantic`;
W/WL compile with the installed SDK. Positive runtime evidence below means
generate **and compile and run**, not merely inspect emitted strings.

The current-syntax migration was validated with a private SDK built from
Cwhip `master` plus its test fix (head `ca2bd106`): 353 tests ran successfully,
with only the two opt-in baseline-parity checks skipped. This includes
generated Cwhip/C compilation, installed-SDK and installed-generator smoke
checks for both targets, documentation workflows, and all SmallC/CVM tests
using the available assembler/runner. Earlier audit counts below describe
their historical runs, not this migration's result.

CTest registers **18 module suites** (`cparsegen_<module>`), one for each
`tests/test_*.py`, containing **355 unittest checks** (including two new CTest
registration/opt-out checks). These are different counts: CTest reports module
results, while `ctest -V` shows individual unittest results and optional skips.
Each module has private HOME/XDG, working, and temporary directories and can
run concurrently. The normal build supplies cparsegen and `smallc-cvm`;
generated parser/consumer fixtures are compiled privately by the tests.
See [Run tests](BUILDING.md#run-tests) for the build-before-test workflow.

CTest conversion validation on 2026-10-25 (UTC) used a fresh private build,
SDK `/tmp/cwhip-final-sdk`, `CWHIP_REGISTER_SDK=OFF`, private HOME/XDG
directories, and build-local binary/library outputs. All **18 suites passed**
serially (121.91 s), at `-j4` (32.52 s), and at `-j8` (25.27 s).
A verbose `-j8` repeat confirmed **355 checks, 2 baseline-parity skips,
0 failures**; installed-SDK, documentation, and available CVM-tool checks ran.
The built-in `test` target (CLI selection) and retained `test-smallc-cvm`
target also passed. A separate fresh build configured without CVM tools
passed the labeled SmallC suite, preserving optional tool skips while its
emission/checker checks still ran. No SDK or user configuration was modified.

## Evidence index

Method names below are exact unittest methods. Shared mixins run in each
listed concrete class:

| Label | File and concrete classes |
| --- | --- |
| G | [test_generator.py](../tests/test_generator.py): `GeneratorTests` (W/WL) |
| F | [test_grammar_conformance.py](../tests/test_grammar_conformance.py): `GrammarConformanceTests` (W); [test_c_backend.py](../tests/test_c_backend.py): `StandaloneCConformanceTests` (C) |
| B | [test_c_backend.py](../tests/test_c_backend.py): `CBackendTests` (W/C differential unless explicitly C-only) |
| L | [test_lexer_expressions.py](../tests/test_lexer_expressions.py): `CwhipLexerExpressionTests`, `CLexerExpressionTests`; validation/differential methods in `LexerExpressionValidationTests` |
| R | [test_left_recursion.py](../tests/test_left_recursion.py): `CwhipLeftRecursionTests`, `CLeftRecursionTests` |
| I | [test_includes.py](../tests/test_includes.py): `IncludeTests`, `CIncludeTests` |
| J | [test_insertions.py](../tests/test_insertions.py): `InsertionTests` (both targets) |
| A | [test_analysis.py](../tests/test_analysis.py): `SharedAnalysisDiagnostics`, opt-in `BaselineParity` |
| P | [test_source_provenance.py](../tests/test_source_provenance.py): `SourceProvenanceTests`, `CSourceProvenanceTests` |
| Q | [test_cli.py](../tests/test_cli.py): `CliTests` |
| U | [test_visitors.py](../tests/test_visitors.py): `VisitorTests` (WL/CL) |
| M | [test_documentation.py](../tests/test_documentation.py): `DocumentationLinks`, `DocumentationWorkflows` |
| SCV | [test_smallc_cvm.py](../tests/test_smallc_cvm.py): `SmallCCVMTests` (emitted-text/checker tests always run; assemble/run tests need installed `cvm-as`/`cvm-run`) |

## Grammar, analysis, scanner, and parser

Implementation: [grammar.cw](../src/grammar.cw) collects declarations and
source provenance; [analysis.cw](../src/analysis.cw) runs once after expansion,
compiles lexer NFAs and parser tables, and supplies all three emitters.
[emitter.cw](../src/emitter.cw) and [c_runtime.cw](../src/c_runtime.cw)
implement the generated runtimes; [c_emitter.cw](../src/c_emitter.cw) adds C's
directive allowlist. Black-box agreement and baseline bytes observe this
boundary; they do not independently prove the analyzer's internal call count.

| Feature / contract | Target/mode evidence | Concrete tests and scope |
| --- | --- | --- |
| Current Cwhip keyword syntax in generated AST, parser, visitor, and scanner | W/WL | G.`test_generate_compile_and_run_shortest_parser` pins representative `return(value)` output and compiles/runs it; U and J compile/run library visitors and inserted Cwhip bodies |
| Interleaved declarations, forward token/rule references, first parser rule as entry | W/C/D; WL/CL use the same tables | F.`test_interleaved_collection_resolves_forward_names_and_keeps_start_rule`; B.`test_shared_conformance_fixtures_are_differential` |
| Grammar comments, multiline parser rules, `;`, opaque payloads versus embedded actions/mixed declarations | W/C/V | F.`test_rule_trivia_does_not_terminate_or_enter_generated_input`, `test_unsupported_and_malformed_declarations_fail_without_outputs`; A.`test_c_directive_allowlist_is_backend_validation_after_analysis` |
| Groups, sequences, ordered choices, `?/*/+`, empty alternatives/rules, flattened children | W/C; WL/CL shapes | G.`test_optional_plus_and_explicit_empty_rule`; B.`test_ebnf_empty_rules_and_source_order`; U.`test_library_tokens_tree_shapes_and_retained_roots` |
| Shortest viable prefix, non-first alternative, caller-required longer results, complete input | W/C; WL/CL repeated selection | F.`test_shortest_prefix_is_not_first_successful_alternative`; B.`test_scanner_longest_match_and_shortest_viable_continuations`; U.`test_left_recursive_library_tree_visitors_and_repeated_selection` |
| Equal-extent source ordering, grammar-defined precedence and associativity | W/C | G.`test_equal_length_alternatives_keep_source_order`; B.`test_ebnf_empty_rules_and_source_order`; R.`test_precedence_and_left_associativity_are_grammar_defined`, `test_ambiguous_binary_recursion_keeps_source_order_not_growth_order` |
| Composable lexer precedence, grouping, quantifiers, forward references/helper metadata | W/C | L.`test_precedence_and_longest_alternative_not_first_success`, `test_forward_composition_nested_groups_and_quantifiers`, `test_composed_references_keep_named_token_order_and_skip_competition` |
| ASCII literals/classes/ranges/negation, grammar escapes, unsupported regexes | W/C/V | L.`test_literals_classes_ranges_negation_and_escaping`, `test_invalid_expressions_are_source_located_and_never_write_outputs`; B.`test_negated_class_byte_domain_and_text_input_boundary` tests all 256 single bytes for C and 128 ASCII bytes for W for one negated class, plus valid/invalid UTF-8 boundaries, not all expressions |
| Thompson NFA deduplication, no exponential regex backtracking | W/C | L.`test_ambiguous_paths_are_deduplicated_instead_of_backtracking`; `test_regular_subset_against_python_fullmatch` samples 40 words of length 0-3 before `!` for one pattern per backend |
| Lexer reference/nullable cycles and quoted-token composition rejection | V, W/C | L.`test_reference_cycles_and_quoted_references`; A.`test_lexer_cycles_and_nullability` |
| 4,096 expanded states; 128 expression/reference/group bounds | V, W/C execution at maximum state count | L.`test_expansion_and_nesting_limits_fail_during_generation` (both selections), `test_maximum_state_table_compiles_and_runs_both_targets`; flat C scanner sequences: B.`test_flat_scanner_sequences_do_not_use_recursive_stack` |
| Longest-byte token competition, named/literal ties, winning skip rule | W/C; WL/CL token offsets | F.`test_scanner_longest_match_beats_shorter_named_tokens_and_literals`; B.`test_scanner_longest_match_and_shortest_viable_continuations`; L.`test_raw_scanner_differential_including_offsets_and_skip` |
| Keyword remapping only after designated token wins, reserved override, exact boundaries | W/C; WL/CL raw scanner | B.`test_keywords_and_reserved_remap_only_the_winning_token`; L.`test_keywords_comments_quoted_and_parser_literals_still_compete`, `test_raw_scanner_differential_including_offsets_and_skip` |
| Quoted input escapes/spelling, malformed quotes, comments at token boundaries and marker order | W/C; SmallC JSON differential | B.`test_quoted_tokens_preserve_spelling_and_reject_malformed_input`, `test_comments_precede_token_competition_and_follow_marker_order`; SmallC.`test_comments_strings_characters_and_array_initializers` |
| Malformed lexical directives/arity/styles; skipped token references and declaration names | V, W/C | G.`test_invalid_lexical_directives_have_diagnostics`; B.`test_malformed_lexical_directives_fail_before_outputs`; A.`test_skip_and_duplicates`, `test_name_case_and_empty_terminal_validation` |
| Consuming direct/indirect/mutual/nullable-prefix left recursion, nullable bases, groups/repeated suffixes | W/C; WL/CL recursive trees | R.`test_direct_recursion_preserves_nested_tree_and_prefix`, `test_indirect_three_rule_cycle_and_caller_continuation`, `test_nullable_prefix_keeps_empty_nodes`, `test_nullable_base_and_nullable_suffix_component`, `test_mutual_recursion_with_nullable_base`, `test_grouped_recursion_and_repeated_suffix`; U.`test_left_recursive_library_tree_visitors_and_repeated_selection` |
| Mixed left/right recursion, ambiguous recursive alternative order, nonproductive termination | W/C | R.`test_mixed_left_and_right_recursion_and_optional_prefix`, `test_overlapping_recursive_alternatives_keep_outer_and_inner_order`, `test_nonproductive_consuming_cycle_terminates` |
| Zero-consumption cycles, including unreachable cycles, and nullable quantified operands rejected | V, W/C | R.`test_zero_context_cycles_rejected_before_outputs`, `test_nullable_quantifiers_and_malformed_recursive_rules_still_rejected`; A.`test_parser_nullability_and_left_recursion` |
| Shared normalized artifacts/diagnostic order; backend allowlist only after analysis | V/W/WL/C/D | A.`test_c_directive_allowlist_is_backend_validation_after_analysis`, `test_includes_are_analyzed_as_one_grammar`; `BaselineParity.test_valid_grammar_artifacts_match_baseline`, `test_diagnostics_match_baseline` |
| Grammar provenance: byte ranges, tabs/CRLF/UTF-8 byte columns, zero-width EOF, related locations, include ancestry bounded to eight sites | V, W/C | P.`test_tabs_crlf_and_utf8_keep_byte_based_columns_and_offsets`, `test_eof_location_is_zero_width_after_final_byte`, `test_nested_origin_duplicate_related_location_and_include_chain`, `test_deep_include_diagnostic_chain_is_explicitly_truncated`; A.`test_unknown_references_carry_locations` |

## Includes, insertions, CLI, and output safety

| Feature / contract | Target/mode evidence | Concrete tests and scope |
| --- | --- | --- |
| Nested depth-first includes, cross-file references, diamonds/include-once, flat artifact equivalence | W/C/D; WL/CL composite execution | I.`test_nested_relative_interleaved_forward_references_and_duplicate_diamond`, `test_cli_validation_and_library_mode`; A.`test_includes_are_analyzed_as_one_grammar`; U.`test_library_tokens_tree_shapes_and_retained_roots` compiles an include diamond with forward lexer composition and EBNF in both libraries |
| Relative/absolute/quoted paths, repeated colon search paths, empty components, local priority; no implicit cwd fallback | W/C compiled execution | I.`test_search_order_repeated_options_empty_components_and_local_priority`, `test_quoted_absolute_spaces_semicolons_and_parent_traversal`, `test_no_implicit_cwd_search`; M.`test_documented_include_default_output_workflow` |
| Resolved symlink-directory/alias identity, hard links distinct for inclusion, active cycles | W/C/V | I.`test_nested_include_uses_resolved_symlink_directory`, `test_symlink_aliases_share_identity_and_detect_cycles`, `test_hard_links_are_distinct_include_sources` |
| Include errors, malformed/split declarations, bad first candidate, unreadable files | W/C/V | I.`test_cycle_missing_directory_and_malformed_includes`, `test_included_syntax_semantic_and_backend_diagnostics`, `test_existing_bad_candidate_is_not_silently_skipped`, `test_unreadable_file_reports_include_site`, `test_includes_cannot_split_declarations_or_expressions` |
| 128 active / 1,024 distinct file limits; duplicate at limit | W/C/V | I.`test_include_depth_is_bounded`, `test_distinct_file_limit_and_duplicates_at_limit` accept exact boundaries and reject the next file |
| Insertion target filtering, opaque byte preservation, balanced lexical collection | W/WL/C/CL; D unchanged | J.`test_byte_preservation_and_target_filtering`, `test_malformed_blocks_and_invalid_contracts_before_output_open`, `test_nested_source_diagnostics` |
| All twelve insertion seams, CLI/library placement, source/include order; native includes not grammar includes | W/WL/C/CL compiled execution; D unchanged | J.`test_exact_placement_all_seams_cli_and_library`, `test_nested_includes_order_and_non_insertion_contracts`, `test_native_includes_are_target_code_not_grammar_includes`, `test_runnable_example_and_injected_public_apis` |
| Insertion body 1 MiB / nesting 256 incl. outer brace; forbidden NUL/splicing/trigraphs | V, W/C | J.`test_collection_limits` accepts exact boundaries and rejects excess; `test_malformed_blocks_and_invalid_contracts_before_output_open` checks absent/existing outputs |
| CLI defaults/no DOT, explicit parser override, `--dot`, `--library`, option interleaving/terminator, filename suffix rules | W/WL/C/D | Q.`test_default_outputs_generate_compile_and_parse_all_modes_without_dot`, `test_explicit_output_and_optional_dot_match_default_artifacts`, `test_filename_derivation_last_extension_and_directory_preservation`, `test_options_interleave_with_paths_includes_and_target`, `test_terminator_and_dash_prefixed_paths` |
| Unsupported targets/options/forms: C++/Python, explicit `cwhip`, C+`--library`, old positional DOT | Usage rejection, no generated backend claimed | Q.`test_usage_errors_never_create_or_truncate_files` explicitly tests `cpp`, `c++`, `python`; B.`test_generation_is_deterministic_and_cli_rejects_invalid_options` |
| Preflight aliases, normalized/absolute/symlink/hard-link input/output collision, included inputs, unresolved parents | W/WL/C generation; filesystem tests sampled across options | Q.`test_input_output_collisions_include_implicit_defaults`, `test_normalized_absolute_symlink_and_hard_link_collisions`, `test_implicit_defaults_cannot_alias_input_through_links`, `test_outputs_cannot_overwrite_included_grammars`, `test_unresolvable_output_paths_are_rejected_before_writing` |
| Validation/usage failure does not create/truncate outputs; existing distinct outputs may be replaced; omitted DOT untouched | W/WL/C/D | Q.`test_input_and_validation_failures_preserve_default_and_explicit_outputs`, `test_usage_errors_never_create_or_truncate_files`, `test_distinct_existing_output_files_may_be_replaced`, `test_omitting_dot_does_not_touch_existing_graph`; I/J sentinel checks |
| Optional deterministic DOT dependency graph, repeated edges/literal numbering, parity across target/library and inlining | W/WL/C/D | Q.`test_explicit_output_and_optional_dot_match_default_artifacts`; B.`assert_differential` compares graph bytes; I/J flattening comparisons; G.`test_library_emission_and_dot_are_deterministic` also invokes Graphviz when installed |

## Runtime APIs, modes, visitors, and applications

| Feature / contract | Target/mode evidence | Concrete tests and scope |
| --- | --- | --- |
| Tokens: kind, original text/slices, offsets, skip/comment omission | WL/CL | L.`test_raw_scanner_differential_including_offsets_and_skip`; U.`test_library_tokens_tree_shapes_and_retained_roots` includes non-NUL-terminated C input and CRLF offsets |
| AST: rule/token/literal names, nesting/order, empty rules, accessors, repeated selection, lifetime | W/C/WL/CL | U.`test_library_tokens_tree_shapes_and_retained_roots`, `test_left_recursive_library_tree_visitors_and_repeated_selection`; G.`test_rendering_does_not_mutate_ast_or_reused_token_kinds`; C roots survive another parse until destroy, Cwhip root survives local scanner/parser scope |
| JSON exact key shape/text/escapes and complete parsing | C; SmallC handwritten WL frontend differential | B.`test_json_mode_is_complete_escapes_bytes_and_keeps_errors_off_stdout`; [test_smallc.py](../tests/test_smallc.py) `SmallCTests` / `SmallCStandaloneTests`: `test_all_valid_samples`, `test_all_invalid_samples`, `test_eof_crlf_and_quoted_error_locations` |
| Parse/lex errors, EOF/farthest positions, recovery/reset of scanner/parser state | W/C/WL/CL | U.`test_c_library_reports_failures_without_exiting_or_printing`, `test_library_tokens_tree_shapes_and_retained_roots`; P grammar EOF is a distinct coordinate contract; SmallC.`test_lexical_error_locations_and_eof_comment` |
| File CLI usage/mode differences, C help, output flush failure | W/C, C-only help/write check | B.`test_generated_cli_usage_help_and_output_failure`, `test_explicit_resource_limits_and_io_errors`; Cwhip delegates file exceptions to SDK |
| Visitor specific/generic rule/token/literal dispatch, DFS enter/leave, skip/stop/error, invalid returns, null/custom nodes, independent passes | WL/CL | U.`test_c_contract`, `test_cwhip_contract`, `test_c_example`, `test_cwhip_example`; real fixtures assert exact events/statuses and retry after stop/error |
| Legacy rule-only pre/post traversal, independent of controlled hooks | WL only; C N/A (no legacy API) | U.`test_legacy_cwhip_visitor_remains_rule_only_and_ordered` |
| Scanner visits 100,000; parser calls 100,000, rule depth 256, result sets 4,096 | W/C, CL failure returns, C JSON diagnostics | G.`test_scanner_resource_limit_is_an_explicit_error`; B.`test_explicit_resource_limits_and_io_errors`; R.`test_long_chain_and_depth_and_ambiguity_budgets`, `test_call_budget_exhaustion_below_rule_depth_limit`; exhaustion tests, not exact thresholds for every budget |
| C input 1 MiB and arena data 64 MiB inclusive; allocation failure cleanup, quiet non-exiting library, destroy twice | C/CL; W/WL N/A (SDK managed allocation, no corresponding explicit caps) | B.`test_input_limit_accepts_exact_boundary_and_rejects_one_more_byte`; U.`test_c_allocation_failures_and_arena_boundary_are_recoverable` injects each malloc/calloc failure in one successful parse, checks zero live allocations and exact arena boundary; U.`test_c_library_reports_failures_without_exiting_or_printing` |
| Calculator evaluation/variables/batch/interactive/errors | WL consumer only; C syntax is differential, evaluator N/A | [test_calculator.py](../tests/test_calculator.py) `CalculatorTests`; B.`test_calculator_acceptance_rejection_and_rendering` |
| SmallC samples, precedence/nearest-if/comments/quotes, larger syntax and opt-in semantic boundary | WL app/C syntax; C semantic checker N/A | SmallC classes above: every **4 valid + 8 invalid** committed sample, plus named/table-driven structural and semantic cases; inherited C semantic methods deliberately call the Cwhip checker, not a C checker |
| SmallC-to-CVM functions/recursion, scalar and array state, strings, global initialization, arithmetic, comparisons, short-circuit logic, loops, branches, checked traps, explicit unsupported statements | CWhip frontend -> textual `.asm` -> installed `cvm-as` -> installed `cvm-run`; host-C parity where defined | SCV.`test_existing_function_and_array_samples_execute`, `test_globals_arrays_strings_functions_and_control_flow_match_c`, `test_continue_break_and_short_circuit_match_c`, `test_signed_division_and_remainder_follow_c`, `test_branches_ending_in_returns_have_valid_targets`, `test_dynamic_global_initializer_runs_before_main`, `test_char_scalar_increment_and_array_bounds`, `test_checked_overflow_traps_at_runtime`, `test_switch_goto_and_labels_are_explicitly_rejected`, `test_non_main_fallthrough_is_rejected_conservatively` |
| Cwhip `numeric-v2` migration in handwritten apps and generated parser APIs, plus exact SDK ABI gate | W/WL and installed SDK applications | G.`test_generate_compile_and_run_shortest_parser` checks `int64` generated interfaces and compiles/runs; `CalculatorTests`; [test_sdk_discovery.py](../tests/test_sdk_discovery.py) `test_sdk_numeric_abi_is_required`, `InstalledSdkTests.test_sdk_toml_builds_generator_and_examples_with_installed_sdk` |
| Expression/statement demos: generation -> AST visitor -> emitted C -> compiled result; typed/runtime/definite-assignment policies are app-owned | CL consumers; syntax-only W/C cases | [test_compiler.py](../tests/test_compiler.py) `CompilerTests`; [test_statement_compiler.py](../tests/test_statement_compiler.py) `StatementCompilerTests` (no generated evaluator or new backend) |
| SDK discovery/selection/errors, output paths and real installed SDK build | Generator build plus WL apps | [test_sdk_discovery.py](../tests/test_sdk_discovery.py) `SdkDiscoveryTests`, `InstalledSdkTests.test_sdk_toml_builds_generator_and_examples_with_installed_sdk`; actual audit builds every optional target and installs to a private prefix |
| Documentation local links/anchors and runnable commands/snippets | All tracked Markdown; representative W/WL/C/CL/D workflows | M.`test_tracked_markdown_local_links_and_anchors`, `test_reference_prefix_complete_json_and_words_commands`, `test_reference_complete_c_and_cwhip_library_snippets`, `test_documented_insertion_and_lexer_expression_commands`, `test_documented_manual_visitor_commands`, `test_documented_include_default_output_workflow` |

## Intentional exceptions and residual limitations

- C++/Python are planned, not output targets. Only explicit CLI rejection is
  tested. `--library --target c` is rejected; CL uses a preprocessor guard.
- Cwhip's generated CLI has no JSON/help API. Its SmallC app supplies JSON.
  C has no per-rule prefix method/cursor or legacy visitor. These are N/A,
  not missing implementations to infer from the other target.
- Grammar input has full provenance; generated rule nodes do **not** have
  spans. Cwhip AST nodes have no token offsets; C terminal nodes borrow input
  slices. Tests use the documented different layouts, not invented parity.
- SDK allocation/exception internals are outside this repository and are not
  fault-injected or sanitizer-instrumented. Allocation-fault enumeration
  covers generated C on a representative parse, not all host failures.
- Cwhip's SDK text-file API rejects malformed UTF-8 before scanning; its
  generated CLI leaves this as an uncaught SDK exception. C reads arbitrary
  bytes. Differential token results cover ASCII and valid UTF-8 input, not
  identical diagnostics for malformed text encodings.
- Budget tests cover exhaustion, plus exact C input/arena, NFA-state,
  include-file/depth and insertion boundaries. They do not establish a
  performance guarantee or exercise every grammar at every budget threshold.
- Filesystem checks are POSIX-oriented preflight, not atomic/transactional
  writes or protection against concurrent changes. Unreadable-file tests
  skip under root because mode 000 is readable there. Graphviz is optional.
- Markdown checks validate local inline links/anchors and selected runnable
  blocks, not arbitrary shell fragments, illustrative incomplete snippets,
  external network availability, every SDK installation method, or all host
  platforms. SDK source-build instructions are upstream prerequisites, not
  commands that modify another checkout during this audit.

## Audit reproduction and recorded outcomes

Current numeric-v2 comparison baseline:
`e3c30f7a64d75acc423bf0ee1adb2eb90a57ff1c` (main after SDK 0.0.2 migration).
Build the baseline from a separate archived source copy, not the edited
sources, using the same SDK 0.0.2/numeric-v2 installation as the current tree.
Both baseline trees can live in ignored `build/`; use fresh directories
rather than reusing a baseline from another SDK generation:

```sh
./scripts/setup
cd ..
build
mkdir -p build/audit-baseline-source
git archive e3c30f7a64d75acc423bf0ee1adb2eb90a57ff1c | tar -x -C build/audit-baseline-source
cmake -S build/audit-baseline-source -B build/audit-baseline \
  -DCWHIP_BIN_DIR="$PWD/build/audit-baseline/bin" \
  -DCWHIP_LIB_DIR="$PWD/build/audit-baseline/lib"
cmake --build build/audit-baseline
CPARSEGEN_BASELINE_EXECUTABLE="$PWD/build/audit-baseline/bin/cparsegen" \
  ctest --test-dir build --output-on-failure
```

CMake passes the selected installed SDK to tests, enabling the real installed-SDK
test even when discovery originally used registration. Direct unittest runs
need `CWHIP_SDK` explicitly for that opt-in. Baseline parity now uses current
`--dot`; only for an older, CLI-incompatible pre-`--dot` baseline, set
`CPARSEGEN_BASELINE_POSITIONAL_DOT=1`. The artifact corpus is all 12 tracked
`.cpg` files in W/WL/C, comparing real source and DOT bytes, plus diagnostic cases.

The initial opt-in run exposed 48 failing baseline subcases: the harness forced
the obsolete CLI and constructed nonexistent temporary paths for tracked
grammars. Repairing both and asserting successful generation prevents
equal-failure false positives. Strict Clang execution exposed a separate
statement-demo C-emission bug: parenthesized equality conditions triggered
`-Wparentheses-equality` under `-Werror`. Explicit `0 != (condition)` fixes
that compilation failure without changing evaluation. Only that handwritten
consumer's emitted C changes; generated parser source and DOT bytes stay unchanged.

Historical full audit recorded on 2026-10-22 used baseline
`952777921b60e21f80c2bdcc8d9d35686bbadf3a` (main after optional DOT/default
CLI), before the numeric-v2 migration, using Linux, CMake 3.31.6, Python 3.13.5,
GCC 14.2.0, Clang 22.1.8, and Cwhip SDK 0.0.1. Reproducing that historical
baseline requires SDK 0.0.1: its exact-version CMake check rejects SDK 0.0.2.
Generated Cwhip interfaces intentionally changed with numeric-v2; cross-SDK
byte equality is not a compatibility guarantee.

| Validation | Outcome |
| --- | --- |
| Full CMake `test`, GCC strict C99, baseline and installed SDK enabled | **319 tests passed, 0 skips** |
| Full CMake `test`, Clang strict C99 + ASan/UBSan, leak detection and halt-on-error enabled | **319 tests passed, 0 skips**, no sanitizer/leak diagnostics |
| Separately compiled current-main baseline | 12 grammars x 3 modes = 36 successful parser/DOT artifact pairs (72 byte comparisons), plus 12 diagnostic cases; no silent missing-input comparisons |
| All seven optional CMake example targets | Built successfully with **both GCC and Clang**; no warning suppressions |
| Local Markdown links/anchors and extracted runnable snippets | All 12 Markdown documents checked; all 6 documentation unittest methods passed in both full runs |
| Private-prefix install | Installed executable bytes match build output; installed generator generates C, which compiles/runs; covered by installed-SDK opt-in |
| Demonstrations and Graphviz | Calculator `20`; visitors `names=3`; SmallC checked/standalone JSON bytes equal; expression program `20`; statement basic `20/56/28`, control flow `3/3/3/4`, runtime `7true/false/-7/7/7/1`; DOT renders to SVG |
| External documentation | GETTING_STARTED.md, CMAKE-SDK.md, STDLIB.md retrieved read-only from cwhip/master; SDK installation/prerequisite anchors and build flags checked against upstream |

Numeric-v2 migration validation on 2026-10-23 used the supplied Cwhip SDK
0.0.2 `numeric-v2` fixture, including a fresh configure/build of cparsegen,
calculator, SmallC, and `smallc-cvm`. The complete CMake test target passed
**353 tests with 2 baseline-parity skips** (`CPARSEGEN_BASELINE_EXECUTABLE`
was not set).

The sanitizer run uses the same unittest runner, with Clang selected by
CMake and extra flags passed through the existing C harness:

```sh
cmake -S . -B build/audit-sanitize -DCMAKE_C_COMPILER=clang \
  -DCWHIP_BIN_DIR="$PWD/build/audit-sanitize/bin" \
  -DCWHIP_LIB_DIR="$PWD/build/audit-sanitize/lib"
cmake --build build/audit-sanitize --parallel 4
CPARSEGEN_BASELINE_EXECUTABLE="$PWD/build/audit-baseline/bin/cparsegen" \
  CPARSEGEN_C_FLAGS='-fsanitize=address,undefined -fno-omit-frame-pointer -g' \
  ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 \
  ctest --test-dir build/audit-sanitize --output-on-failure
```

This instruments harness-compiled generated C and compiler-demo programs
(backend/conformance, lexer, recursion, include, insertion, visitor, SmallC,
expression/statement and installed-generator C consumers). SDK binaries and
the generator are not sanitizer builds; literal documentation `cc` snippets
are checked as written with strict C99 rather than rewritten with instrumentation.

Build/install and representative application commands used in addition to
the extracted documentation workflows:

```sh
build calculator smallc calculator-c smallc-c visitor-c \
  expression-compiler statement-compiler
cmake --build build/audit-sanitize --target calculator smallc calculator-c smallc-c \
  visitor-c expression-compiler statement-compiler --parallel 2
cmake --install build --prefix "$PWD/build/audit-install"
./bin/calculator -e '(2 + 3) * 4'
./bin/visitor-c 'alpha, beta, gamma'
./bin/smallc-ast --check examples/smallc/valid/functions.c > build/smallc/functions.checked.ast.json
./bin/smallc-c --json examples/smallc/valid/functions.c > build/smallc-c/functions.ast.json
cmp build/smallc/functions.checked.ast.json build/smallc-c/functions.ast.json
./bin/expression-compiler '(2 + 3) * 4' > build/expression-compiler/program.c
cc -std=c99 -Wall -Wextra -Werror -pedantic \
  build/expression-compiler/program.c -o build/expression-compiler/program
./build/expression-compiler/program
./bin/statement-compiler examples/compiler/statements/basic.stmt > build/statement-compiler/program.c
cc -std=c99 -Wall -Wextra -Werror -pedantic \
  build/statement-compiler/program.c -o build/statement-compiler/program
./build/statement-compiler/program
./bin/statement-compiler examples/compiler/statements/control-flow.stmt > build/statement-compiler/control-flow.c
clang -std=c99 -Wall -Wextra -Werror -pedantic \
  build/statement-compiler/control-flow.c -o build/statement-compiler/control-flow
./build/statement-compiler/control-flow
./bin/statement-compiler examples/compiler/statements/runtime.stmt > build/statement-compiler/runtime.c
cc -std=c99 -Wall -Wextra -Werror -pedantic \
  build/statement-compiler/runtime.c -o build/statement-compiler/runtime
printf '%s\n' -7 | ./build/statement-compiler/runtime
./build/audit-install/bin/cparsegen --target c tests/fixtures/shortest.cpg \
  build/audit-install/parser.c --dot build/audit-install/grammar.dot
cc -std=c99 -Wall -Wextra -Werror -pedantic \
  build/audit-install/parser.c -o build/audit-install/parser
printf '123+456' > build/audit-install/input.txt
./build/audit-install/parser --json build/audit-install/input.txt
```

The SmallC CVM compiler emits assembly; its end-to-end evidence uses the
independently installed `cvm-as` and `cvm-run` when available:

```sh
cmake -S . -B build -DCVM_PREFIX=/path/to/cvm-install
cmake --build build --target smallc-cvm test-smallc-cvm
./bin/smallc-cvm examples/smallc/valid/functions.c build/example.asm
cvm-as build/example.asm -o build/example.cvm
cvm-run build/example.cvm
```

```sh
dot -Tsvg build/audit-install/grammar.dot -o build/audit-install/grammar.svg
```

The audit found and filled specific evidence holes, not new language scope:
baseline success/byte assertions, compiled maximum lexer tables, ASCII/raw-byte
and UTF-8 boundaries, library retention/reset/legacy visitors, deterministic
C allocation failures and exact arena bounds, hard-link include identity,
truncated provenance chains, all insertion seams in compiled library consumers,
unsupported targets/CLI errors, private install use, and executable documentation.
Remaining limitations are the explicit exceptions above; there were no
unexplained skips in the recorded environment.

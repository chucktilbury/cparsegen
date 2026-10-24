# Parser-generator architecture and provisional grammar format

This document records the implementation boundaries and longer-term design
for cparsegen. Implemented syntax, including insertion directives, is defined
in the input/output reference; proposal-only features remain provisional.

For current implemented behavior and practical usage, see the
[input/output reference](INPUT-OUTPUT.md). Proposal-only interfaces below
should not be treated as generated APIs.

## Pipeline

Implemented (`src/grammar.cw` → `src/analysis.cw` → `src/emitter.cw` /
`src/c_emitter.cw`):

```text
grammar source stack (include expansion, source order, provenance)
  -> declaration collector / parser            GrammarModel (declarations only)
  -> GrammarAnalyzer                           GrammarModel.analysis : Analysis
  -> backend-only validation                   C directive allowlist
  -> Cwhip / C / DOT emitters                  read Analysis, never recompute
```

`GrammarAnalyzer` runs exactly once, inside `GrammarSources.read`, after
includes are expanded and the whole grammar is parsed. It computes, in order:
insertion target/boundary validation; `@quoted`/`@keywords`/`@reserved`/comment
directives; lexer name checks; lexer reference resolution, nullability, cycle
and nullable-repetition checks, and Thompson NFA compilation (state and depth
bounds); `@skip`; parser name checks; a children-first numbered parser
expression table with literal interning and reference resolution; parser
nullability (fixpoint); left-corner edges, reachability and zero-consumption
cycle validation; and the `required` token lower bounds used by consuming left
recursion. Diagnostics are produced in the same order and with the same text and
source spans as before. The typed result is `Analysis`:

| Structure | Contents | Kind |
| --- | --- | --- |
| `LexerPlan` | Name, quote style, skip flag, nullability, NFA entry/accept/state range, resolved references | emitted normalization (NFA plan) |
| `Analysis.lexerStates` | Shared Thompson NFA state table | emitted normalization |
| `ParserExprRecord` | Numbered expression (kind, children indices, bounds, literal/rule/token target, nullable, `required` bound) | emitted normalization |
| `ParserRuleFacts` | Root expression, nullability, left-corner edges, reachability row, left-recursive flag | analysis-only except root |
| `LexicalConfig` | Keyword token, reserved words, line/block comments | emitted |
| `ResolvedReference` | Domain (lexer→lexer, parser→token, parser→rule), owner, target, source spans | analysis-only |
| `LeftCornerEdge` | Rule→rule edge with zero-consumption context flag | analysis-only |
| `AnalysisDiagnostic` | Phase plus the located `GrammarDiagnostic` | analysis-only |

"Normalization" in the implementation means compiled plans the emitters render
(NFAs, the numbered expression table, literal table, `required` bounds). No
grammar rewrite occurs: alternative order, associativity, precedence and AST
shape are untouched. Target-specific constraints (the C directive allowlist)
remain backend validation after shared analysis. Sections below explicitly
distinguish implemented contracts from future proposals; C++/Python emitters
and generated-input source stacks/spans are not implemented.

The proposed full pipeline, for reference:

```text
grammar source stack
  -> declaration collector
  -> reference resolution and validation
  -> validated target-neutral grammar model
  -> analysis and normalization
  -> Cwhip / C / C++ / Python / DOT emitters
```

The collector preserves source provenance and declaration order, but does
not require declarations to appear in separate sections. It gathers lexer
rules, parser rules, and named directives before resolving references and
validating the complete grammar. This permits forward references without
silently changing declaration order. The validated model is the shared
contract between parsing, analysis, and every emitter; target backends must
not re-parse grammar text or infer syntax from generated code. Emitters
consume only a model that has passed validation.

The executable proves this boundary with generated calculator, identifier-list,
and SmallC syntax examples, a Cwhip parser/AST/scanner emitter, a bounded
standalone-C scanner/parser emitter, and a DOT emitter. C++ and Python
emitters remain future backends and should follow the model rather than
define separate grammar semantics.

## Standalone C target contract

`cparsegen --target c GRAMMAR [OUTPUT.c] [--dot OUTPUT.dot]` consumes the same validated
`GrammarModel`, `LexerExpr`/`ByteRange`/`LexerState`, and `RuleExpr` objects as the default
Cwhip backend. It uses the shared emitter's postorder expression indices and
literal collection order; it does not translate generated Cwhip, re-read
grammar text, invoke another compiler, or load templates at runtime.
`src/c_emitter.cw` emits immutable C tables, and `src/c_runtime.cw` embeds the
bounded scanner/parser implementation in each generated translation unit.
The DOT output is identical for both targets.

This slice targets `examples/calculator/calculator.cpg` and
`examples/smallc/smallc.cpg` as syntax parsers, not evaluators or semantic
checkers. The SmallC Cwhip app adds an opt-in AST semantic pass; neither
generated parser backend performs those checks. It supports all currently validated parser
expressions (references, literals, sequences, choices, groups, `?`/`*`/`+`,
empty alternatives, consuming left recursion), composable lexer expressions,
and `@skip`. Declaration interleaving and forward references are resolved
by the shared reader. Shared invalid-grammar diagnostics still apply.
`@keywords`, `@reserved`, `@quoted`, `@line_comment`, and `@block_comment`
use the same validated lexical model and semantics as Cwhip. Quote spellings
and escapes are preserved, not decoded. Comments are recognized at token
boundaries before token competition, in line-comment then block-comment
declaration order; quotes consume embedded comment markers as ordinary text.
Keyword remapping applies only when the designated identifier token wins;
reserved spellings override literal remapping.

Grammar `@include` and target-code `@insert` are also implemented.
For C, directives outside this list and `@note` are rejected with source-located
diagnostics before either output is opened, rather than silently ignoring an
unsupported lexical extension. `@note` remains explicitly inert. Malformed
supported lexical directives are rejected by the shared reader. This stricter
C-target allowlist does not change default Cwhip generation or its handling
of opaque directives.
There is no `--library --target c`, semantic action,
arithmetic evaluation, SmallC semantic checking in the generated backend,
optimization, or new DOT behavior.
The generated C file can instead be included with `CPARSEGEN_NO_MAIN` for
the public parser, AST accessors, and read-only visitor API documented in
[Application integration](VISITORS.md).

The generated artifact is one ISO C99 source file with `main` and only
standard-library dependencies. Compile it with `cc -std=c99 OUTPUT.c -o parser`.
Its CLI is `parser [--complete | --json] INPUT`, where `INPUT` is a binary-read file:

| Contract | Behavior |
| --- | --- |
| Scanner selection | Longest byte match; named lexer rules win equal-length ties in declaration order, then literals in shared collection order; skipped tokens still compete |
| Parser selection | Shortest successful token prefix of the first declared rule, preserving longer candidates needed by caller continuations; equal-length ties keep source order |
| Complete input | `--complete` selects a candidate consuming all scanned non-skipped tokens; scanning always checks the entire input even in prefix mode |
| Success | Exit `0`, one rendered syntax tree plus newline on stdout, identical to Cwhip `AstNode.render()` |
| Tree format | `rule(child, child)` and `TOKEN(raw text)`; empty rules render `rule()`; literals use shared `@literalN` names; text is not escaped or normalized, so this is a human-readable format, not JSON |
| Lex/parse error | Exit `1`, `lex error at byte N` or `parse error at token N` plus newline on stdout, with zero-based indices matching Cwhip |
| JSON mode | `--json` always requires complete input; exit `0` prints one JSON object with exactly `name`, `text`, `children` per node, matching the Cwhip SmallC frontend's rule names/nesting and original terminal spellings |
| JSON diagnostics | Lexical/parser errors exit `1`, with empty stdout and `file:line:column: diagnostic` on stderr; one-based byte-oriented locations count LF as a line break, matching SmallC, including EOF and CRLF behavior |
| Usage / I/O | Usage errors exit `2` on stderr; file and output-write errors exit `1` on stderr |

Like the Cwhip prototype, the C runtime enumerates alternatives rather than
using PEG first-success semantics. It limits matching to 100,000 scanner NFA
state visits per token, 100,000 parser calls per parse, depth 256 for nested rule
matches, and 4,096 results per intermediate set. C additionally bounds
input to 1 MiB and cumulative arena data to
64 MiB. All limits produce explicit errors (exit `1`, stdout in rendered mode,
stderr with a source location in JSON mode); they do not
silently truncate input/results. These C-specific budgets can reject inputs
that Cwhip accepts; differential equivalence is asserted within both
runtimes' budgets. Arena memory is reclaimed on both success and failure.
In include-based library use, allocation/resource errors return NULL from
`cpg_parse` with a diagnostic in the caller's context, rather than terminating
the host process; the standalone CLI still exits `1`. Resource
error locations are the farthest parser position (or EOF before parsing);
they are not promised to identify the cause of exhaustion.

SmallC differential tests run every existing valid/invalid sample, compare
entire JSON objects and DOT output on success, and compare exit status and
exact source diagnostics on lexical/parser failure. They also exercise the
existing SmallC structural, precedence, nearest-`if`, and quote/comment cases.
This is a bounded syntax-only milestone, not a complete C compiler.

## Intermediate representation boundary

The model separates source syntax, validated grammar meaning, and target
rendering:

| Model component | Contents |
| --- | --- |
| `GrammarModel` | Source-ordered lexer rules, parser rules, named directives, insertions, and shared analysis |
| `SourceSpan` | Source identity, half-open byte range, and one-based start/end line and column |
| `LexerExpr` | Structured lexer syntax and named references compiled to bounded Thompson NFAs |
| `RuleExpr` | Tagged token reference, rule reference, literal terminal, sequence, alternation, optional, and repetition nodes |
| `CodeInsertion` | Target name, named boundary, opaque source text, and source span; present only when supplied by a directive |
| `Analysis` | Implemented as typed `Analysis` (see Pipeline): resolved references, nullability, left-corner graph, compiled lexer NFAs and numbered parser expressions. Proposal-only: rewrite records for alternatives, since no grammar rewriting exists |

Grammar declarations, expression nodes and directives retain their source
spans; emitted runtime tables do not expose those grammar spans. Regex text
and parser syntax are parsed into nodes rather than passed through as opaque strings. The
original spelling may be retained for diagnostics, but the emitters consume
the structured form. The model preserves declaration, alternative, and child
order; maps are lookup aids only and never define output order.

Parsing may create incomplete nodes, but validation must resolve all names,
check all supported constructs, and attach analysis before any backend runs.
The normalized representation numbers expressions and resolves references;
it does not rewrite ordered alternatives. Target renderers may choose different implementation
strategies, but cannot change grammar meaning or add parser actions.

## Cwhip implementation constraints

The repository's application build targets the installed Cwhip SDK `0.0.2`
with the `numeric-v2` ABI and uses its CMake `cwhip_add_program` integration;
it is not a native C/C++ build of the generator. The published Cwhip standard `system` package
provides file and path APIs, so the initial source stack can use that API
rather than embed native file-I/O code. Cwhip collections are dynamically
tagged, ordered lists; typed model objects and explicit checked extraction
should carry semantic structure, while dictionaries remain lookup aids.

The Cwhip language also supports `inline` native-C blocks. Those blocks are
not a substitute for grammar actions and should not be introduced into parser
rules. If a native bridge proves necessary, keep it behind the generator's
input/output boundary so the grammar model and generated parser semantics
remain Cwhip-level and target-neutral.

The SDK version and file/collection APIs are documented in the public
[Cwhip SDK contract](https://github.com/chucktilbury/cwhip/blob/master/doc/CMAKE-SDK.md)
and [standard library reference](https://github.com/chucktilbury/cwhip/blob/master/doc/STDLIB.md).

## Executable prototype boundary

The current executable is a bounded example-oriented implementation, not the
complete proposal. The original fixture uses interleaved declarations and a
forward token reference:

```text
sum : INTEGER | INTEGER "+" INTEGER ;
@note opaque directive payload;
INTEGER = [0-9]+
```

The reader recognizes named directives as `@name payload;`. `@skip TOKEN;`
marks a declared lexer token as discarded by the generated scanner.
`@keywords TOKEN;` opts into exact keyword remapping when that token wins;
`@reserved WORD...;` reserves additional unsupported keywords.
`@quoted TOKEN single|double;` declares character/string tokens with a bounded
ASCII escape vocabulary. `@line_comment MARKER;` and
`@block_comment OPEN CLOSE;` skip comments and diagnose unterminated blocks.
`@include` expands grammar files and `@insert TARGET BOUNDARY { BODY };`
collects target code as described below. Other directive payloads remain
opaque and have no generation effect. Lexer
patterns are single-line expressions supporting ASCII classes/ranges/negation,
quoted literals, named lexer references, groups, alternation, concatenation,
and `?`/`*`/`+`. Forward lexer references resolve before emission; reference
cycles, unknown/quoted-token references, empty-matching rules, nullable
quantified operands, and excessive nesting/expansion are rejected with source
lines. Quoted grammar literals decode a small escape vocabulary. See the
[precise syntax and escaping contract](INPUT-OUTPUT.md#lexer-declarations).

The shared model compiles each validated expression into Thompson NFA states
(`LexerState`: byte transition, epsilon split, accept). Both emitters serialize
those states rather than independently expanding regex semantics. Each
inlined helper occurrence consumes the same bytes as its expression; helper
token kind, skip, and keyword metadata do not propagate. Helpers remain
independent scanner candidates. Epsilon closure and byte advancement are
iterative, deduplicated state-set operations, with no scanner recursion or
backtracking explosion. Generation caps the expanded automata at 4,096 states
and expression/reference paths at 128 edges.

Parser expressions now support token and parser-rule references, quoted
terminals, sequences, ordered alternatives, groups, `?`/`*`/`+`, and explicit
empty alternatives. Forward references and consuming left recursion work.
Validation computes rule nullability, rejects repetitions with nullable
operands, and rejects direct/indirect cycles whose surrounding context can
be empty on both sides. Consuming cycles, including those through nullable
prefixes, use span-bounded expansion in both runtimes. A sequence reserves
one token per nonnullable remaining child before matching its current
child; each recursion cycle therefore advances the start or decreases the
ending-token ceiling. This preserves original source ordering and rule-node
nesting without helper rules or greedy suffix folding. Non-left-recursive
grammars keep the previous matcher behavior. See the
[exact boundary and examples](INPUT-OUTPUT.md#left-recursion).

The generated parser retains candidate matches until surrounding sequences
have matched; a locally shorter rule match cannot incorrectly hide a longer
one required by its caller. Prefix APIs select the shortest successful match;
equal-length alternatives keep source order. `parseAll()` instead selects a
candidate that consumes every non-skipped token. The standalone runner keeps
prefix mode by default, with `--complete` to request whole-input parsing.
The calculator and SmallC frontend always use the complete-input API.

The generated scanner uses longest byte match across lexer expressions
and quoted terminals. Ties favor lexer declaration order, then literal
appearance order. Without `@keywords`, a literal that also matches a named
token therefore loses an equal-length tie. With that directive, a winning
identifier token is remapped on exact equality to a grammar literal, keeping
longer identifiers intact. Skip rules participate in longest-match selection.
Comment directives apply at token boundaries before those rules; a quoted
token consumes comment-like text without interpreting it. See
[Examples](../examples/README.md) for the exact directive contracts.

Backtracking is bounded and intended for small examples: the parser allows
256 nested parser-rule calls, 100,000 matcher calls per parse, and 4,096 results per
intermediate set. The scanner allows 100,000 NFA state visits per token
boundary across all competing rules.
Exhaustion is an explicit failure, never a partial success.

`cparsegen --library GRAMMAR [OUTPUT.cw] [--dot OUTPUT.dot]` emits the same generated
scanner, AST, parser, and visitor without a `start` block. The calculator's
handwritten evaluator includes that library; its grammar has no semantic
actions. Rule nodes retain nested rule structure, terminals are leaves, and
groups/repetitions flatten their children in source order. See
[Examples](../examples/README.md) for runnable commands.

The SmallC CLI prints JSON ASTs and byte-based file/line/column diagnostics.
Its default mode is syntax-only; the handwritten Cwhip app's opt-in `--check`
adds source-order binding/type/control-context checks, not code generation or execution.
Its grammar preserves conventional nearest-`if` association through
matched/open statement rules rather than changing generic choice semantics.

The grammar reader records filename, byte ranges, one-based line/column spans,
and include ancestry for declarations/expressions/directives. Grammar includes
expand depth-first before shared analysis. These are implemented source
provenance, not generated-input AST spans: generated Cwhip tokens carry a
starting byte offset, C tokens carry offset/length, and neither backend
computes rule-node spans or supports stacked generated input sources.

## Implemented declaration format

Lexer declarations, parser rules, and directives may be interleaved at the
top level; there are no mandatory `DIRECTIVES`, `LEXER`, or `PARSER` sections.
The collector classifies declarations, retaining their encounter order
within each kind. It then resolves names and validates the assembled grammar
in a later pass. A parser rule may refer to a lexer rule or parser rule that
appears later in the source.

Lexer rules use uppercase names assigned to regex expressions. Larger lexer
rules may be built from smaller lexer rules. Every named rule remains a
scanner candidate; declaration order breaks equal-length ties. The first
lexer rule is not a start expression. The implemented operators, reference
composition, escaping and bounds are defined in the
[lexer reference](INPUT-OUTPUT.md#lexer-declarations).

Parser rules use lowercase names, a colon, and a rule definition terminated
by `;`. Whitespace and comments are permitted within a parser-rule
definition. The first parser rule encountered is the start rule. Alternatives,
grouping, repetition, empty alternatives and quoted terminals are implemented;
see the [parser syntax](INPUT-OUTPUT.md#parser-rules-and-ebnf).

Named directives are collected separately from grammar rules. Ordinary
payloads are opaque to the declaration collector, then recognized lexical
directives are validated by shared analysis; includes and insertions have
dedicated collectors. Payloads are not parsed as lexer or parser syntax.
The implemented insertion syntax and target selection are specified in
[Code insertion](INPUT-OUTPUT.md#code-insertion); future directive names
remain open.

Whitespace and comments inside grammar declarations are separate from
whitespace and comments in text scanned by a generated parser. The latter's
handling must be stated by the grammar or another confirmed rule; it must not
be inferred from formatting accepted by the grammar reader.

Grammar includes have explicit source-order, visibility, provenance,
duplicate, path-resolution and cycle semantics; see
[grammar includes](INPUT-OUTPUT.md#grammar-includes). This does not add an
include mechanism to text read by generated scanners.

## Scanner and source locations

The implemented scanner selects the longest matching token, with named
lexer rules winning equal-length ties in declaration order, then literals
in collection order. Parser matching instead selects the shortest viable
token prefix, or a complete candidate when requested, retaining longer
matches needed by callers and source order on equal extents. See the
[scanner/parser contract](INPUT-OUTPUT.md#scanner-and-parser-behavior).

**Proposal: generated-input source spans and source stacks.** A future token
could carry its kind, lexeme, and start/end source span. Such a span records
source identity, byte offsets, and one-based line and column positions. The
source identity retains filename and provenance, including whether input came
from a file, an include, or another pushed source.

In that proposal the scanner owns a stack of input sources. EOF in a nested source pops that
source and resumes its parent; EOF at the root is a stable terminal result,
not a fabricated token. Empty nested inputs follow the same pop-and-resume
rule. Generated-input includes and source-push syntax are not specified; that scanner
contract should not depend on the eventual spelling.

## AST and visitor contract

**Proposed spans, not current API:** each parser rule would produce a node
with its rule name, a source span, and
children in grammar/source order. Matched terminals are explicit leaf nodes
with token kind, lexeme, and span; grouping syntax does not add artificial
nodes. Repeated and optional constructs preserve the matched child order.
A proposed root span would run from the first consumed token through the last
consumed token. Current trailing-input behavior is already defined by the
prefix and complete-input APIs above.

The implemented read-only visitor layer exposes per-rule, named-token, and
literal hooks on both targets. Single-node dispatch invokes one selected
handler without implicit traversal. A separate depth-first walker uses
enter/leave hooks and stored child order; enter can descend, skip children
(still calling leave), stop, or report an error. Stop/error propagates
immediately without leave-hook unwinding. Specific hooks fall back to generic
hooks. C uses a callback table and caller-owned context; Cwhip uses a visitor
object. The original Cwhip rule-only pre/post visitor remains available.
See [Application integration](VISITORS.md) for exact APIs, error/lifetime
contracts, executable examples, and incremental SmallC adoption. Hooks are
application customization points, not parser actions, and do not change parse
semantics. AST mutation/replacement and ownership transfer are not supported.

The spans described above remain an architectural goal: current Cwhip nodes
store name/text/children, and C nodes store source offsets/lengths only for
terminals (rule offsets/lengths are zero). Neither visitor synthesizes spans.

## Directives and target code

`@insert TARGET BOUNDARY { BODY };` collects opaque code for `c` or `cwhip`.
The bounded iterative collector balances braces while protecting quoted
literals and C-style comments; it does not interpret target semantics.
`CodeInsertion` records target, boundary, byte-preserved body, source path
and provenance span (byte offsets, one-based line/column, and include parent),
plus the unique source-line ID used while retaining source order. Records
retain depth-first encounter order in `GrammarModel`.
Shared validation rejects unknown targets/boundaries before emission, even
for blocks not selected by this invocation. Emitters filter those records by
target and boundary without reparsing them. No insertion is run by the
generator or affects the grammar's rule/literal/visitor indexing or DOT.

Implemented seams are `file_pre`, `imports`, `declarations`, `ast_pre`,
`ast_post`, `scanner_pre`, `scanner_post`, `parser_pre`, `parser_post`,
`visitor_pre`, `visitor_post`, and `file_post`. All are file-scope
declaration seams, including in library mode, not member bodies or execution
hooks. The two runtimes have different physical component ordering; the
[input/output contract](INPUT-OUTPUT.md#code-insertion) specifies exact
placement, lexical restrictions, limits and security responsibilities.
There is no separate generated header/public/private partition; authors use
normal target linkage and visibility in their complete declarations.

Parser rules accept grammar expressions only. They cannot contain arbitrary
code, semantic actions, or embedded target-language fragments. AST visitors
are the supported extension point for user behavior.

## Left recursion and diagnostics

Validation builds the rule-reference/left-corner graph, resolves undefined
references, computes reachability (without rejecting unreachable rules),
and detects nullable repetitions and zero-consumption cycles
before emission. Diagnostics point to the grammar source span and include
the relevant rule path.

Left recursion must be detected and handled where supported, with the
generated parse preserving the grammar's shortest-match behavior, alternative
and child order, and AST associativity. A conventional greedy suffix loop
must not be assumed correct merely because it removes recursion. For
example, an expression grammar intended to produce `((a+b)+c)` must retain
that AST shape without changing which input extent the grammar matches.
The current implementation uses span-bounded expansion for consuming direct,
indirect, and nullable-prefix cycles, preserving all finite derivations within
the runtime budgets. It rejects zero-context cycles because they admit
infinitely many equal-span rule wrappers. It does not substitute productions
or flatten the resulting AST. A left-recursive form it cannot preserve fails with a
source-located diagnostic rather than generate a looping or
semantics-changing parser.

Other validation failures should likewise be actionable and located: duplicate
rules/tokens/directives, malformed expressions, unknown token/rule references,
unsupported regex constructs, and malformed declarations. Generation must
not silently omit invalid grammar fragments.

## DOT view

DOT is an optional emitter over shared analysis, selected only with `--dot`.
It emits parser-rule boxes, named-token ellipses (including skipped tokens),
literal diamonds, and dependency edges labeled with expression child paths.
Repeated references remain repeated edges; recursive edges have no special
styling. Both source targets and Cwhip library mode produce identical DOT.
It does not show the lexer NFA or encode quantifiers as operator nodes.
An expanded/operator view or special recursive-edge styling would be future
work, not another implemented mode.

## Milestone and open decisions

This document combines implemented boundaries with labeled proposals. The
executable now establishes declaration collection, a typed expression model,
reference/nullability/zero-context-cycle validation, consuming left recursion,
and Cwhip/C plus DOT emission for working small examples. Later work adds
C++ and Python emitters, richer regexes and generated-input source tracking, and more
efficient parser analysis. The calculator and SmallC grammar are concrete
fixtures. SmallC already has an opt-in source-order semantic checker;
its optional `smallc-cvm` compiler is separate from cparsegen's grammar
emitters, consumes the shared checked AST and emits textual CVM assembly;
the independent `cvm-as` assembler produces the binary and `cvm-run` executes
it. This does not add SmallC bytecode support to the standalone C target or expand
the language into OOP. See its
[semantic boundary](../examples/smallc/README.md#semantic-checking-and-explicit-limits)
and [CVM compiler](../examples/smallc/README.md#compile-and-run-with-cvm).
Future work must preserve the implemented include, insertion, regex-composition
and parser-selection contracts. The [feature/target evidence matrix](TEST-COVERAGE.md)
records named tests and residual limitations without claiming exhaustive grammar coverage.

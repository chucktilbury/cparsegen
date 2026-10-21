# Parser-generator architecture and provisional grammar format

This document proposes the first implementation boundary for cparsegen. The
syntax and insertion-directive spelling are provisional until they are
checked against a real user grammar. `examples/expression.cpg` is a fixture for
discussion, not a compatibility promise.

For current implemented behavior and practical usage, see the
[input/output reference](INPUT-OUTPUT.md). Proposal-only interfaces below
should not be treated as generated APIs.

## Pipeline

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

`cparsegen --target c GRAMMAR OUTPUT.c OUTPUT.dot` consumes the same validated
`GrammarModel`, `RegexPart`/`ByteRange`, and `RuleExpr` objects as the default
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
empty alternatives, non-left recursion), character-class regex sequences,
and `@skip`. Declaration interleaving and forward references are resolved
by the shared reader. Shared invalid-grammar diagnostics still apply.
`@keywords`, `@reserved`, `@quoted`, `@line_comment`, and `@block_comment`
use the same validated lexical model and semantics as Cwhip. Quote spellings
and escapes are preserved, not decoded. Comments are recognized at token
boundaries before token competition, in line-comment then block-comment
declaration order; quotes consume embedded comment markers as ordinary text.
Keyword remapping applies only when the designated identifier token wins;
reserved spellings override literal remapping.

For C, directives outside this list and `@note` are rejected with source-line
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
using PEG first-success semantics. It limits matching to 100,000 scanner
calls per token, 100,000 parser calls per parse, depth 256 for nested rule
matches, and 4,096 results per intermediate set. C additionally bounds
scanner-part recursion to 256, input to 1 MiB, and cumulative arena data to
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
| `Grammar` | Source-ordered lexer rules, parser rules, named directives, and source identity |
| `SourceSpan` | Source identity, half-open byte range, and one-based start/end line and column |
| `RegexExpr` | Structured regex syntax and references to smaller lexer rules; exact node kinds follow the confirmed regex notation |
| `RuleExpr` | Tagged token reference, rule reference, literal terminal, sequence, alternation, optional, and repetition nodes |
| `CodeInsertion` | Target name, named boundary, opaque source text, and source span; present only when supplied by a directive |
| `Analysis` | Resolved references, nullability, left-corner graph, and validated normalization records |

Every syntax/model node retains its source span. Regex text and parser syntax
are parsed into nodes rather than passed through as opaque strings. The
original spelling may be retained for diagnostics, but the emitters consume
the structured form. The model preserves declaration, alternative, and child
order; maps are lookup aids only and never define output order.

Parsing may create incomplete nodes, but validation must resolve all names,
check all supported constructs, and attach analysis before any backend runs.
The normalized representation records how original ordered alternatives
were rewritten, so code generation cannot accidentally change associativity
or precedence. Target renderers may choose different implementation
strategies, but cannot change grammar meaning or add parser actions.

## Cwhip implementation constraints

The repository's application build targets the installed Cwhip SDK `0.0.1`
exactly and uses its CMake `cwhip_add_program` integration; it is not a native
C/C++ build of the generator. The published Cwhip standard `system` package
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
Other directive payloads remain opaque and have no generation effect. Lexer
patterns are single-line sequences of ASCII character classes, each optionally
followed by `?`, `*`, or `+`. Classes support ranges and `\t`, `\r`, `\n`,
`\\`, `\]`, and `\-` escapes. Negated classes, regex groups/alternation,
lexer-rule composition, and escapes in quoted terminals remain unsupported.
Lexer rules that can match empty input are rejected.

Parser expressions now support token and parser-rule references, quoted
terminals, sequences, ordered alternatives, groups, `?`/`*`/`+`, and explicit
empty alternatives. Forward references and non-left recursion work.
Validation computes rule nullability, rejects repetitions with nullable
operands, and diagnoses direct/indirect left recursion including cycles
through nullable prefixes. Left recursion is not transformed.

The generated parser retains candidate matches until surrounding sequences
have matched; a locally shorter rule match cannot incorrectly hide a longer
one required by its caller. Prefix APIs select the shortest successful match;
equal-length alternatives keep source order. `parseAll()` instead selects a
candidate that consumes every non-skipped token. The standalone runner keeps
prefix mode by default, with `--complete` to request whole-input parsing.
The calculator and SmallC frontend always use the complete-input API.

The generated scanner uses longest byte match across character-class patterns
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
intermediate set. The scanner allows 100,000 pattern calls per token.
Exhaustion is an explicit failure, never a partial success.

`cparsegen --library GRAMMAR OUTPUT.cw OUTPUT.dot` emits the same generated
scanner, AST, parser, and visitor without a `start` block. The calculator's
handwritten evaluator includes that library; its grammar has no semantic
actions. Rule nodes retain nested rule structure, terminals are leaves, and
groups/repetitions flatten their children in source order. See
[Examples](../examples/README.md) for runnable commands.

The SmallC CLI prints JSON ASTs and byte-based file/line/column diagnostics.
It does not implement binding, types, code generation, or execution.
Its grammar preserves conventional nearest-`if` association through
matched/open statement rules rather than changing generic choice semantics.

The current reader records declaration/expression line numbers, not full
filename/line/column spans. Generated tokens record their starting byte
offset, but AST spans and source stacks are not implemented. The fuller
`SourceSpan`, source-stack, and include contracts above remain design targets,
not completed features.

## Provisional declaration format

Lexer declarations, parser rules, and directives may be interleaved at the
top level; there are no mandatory `DIRECTIVES`, `LEXER`, or `PARSER` sections.
The collector classifies declarations, retaining their encounter order
within each kind. It then resolves names and validates the assembled grammar
in a later pass. A parser rule may refer to a lexer rule or parser rule that
appears later in the source.

Lexer rules use uppercase names assigned to regex expressions. Larger lexer
rules may be built from smaller lexer rules. The first lexer rule encountered
defines the whole expression. These ordering and composition rules must be
preserved by collection and expansion; the exact regex operators and
remaining composition semantics are not fixed here.

Parser rules use lowercase names, a colon, and a rule definition terminated
by `;`. Whitespace and comments are permitted within a parser-rule
definition. The first parser rule encountered is the start rule. Alternatives,
grouping, repetition, and quoted terminals are part of the intended
ANTLR-like form, but this proposal does not settle every detail of their
spelling or precedence.

Named directives are collected separately from grammar rules. Their content
is opaque to the grammar reader and is not parsed as lexer or parser syntax.
The directive names, source spelling, and how a directive selects a target
remain open; no particular block delimiter or insertion syntax is implied by
this document.

Whitespace and comments inside grammar declarations are separate from
whitespace and comments in text scanned by a generated parser. The latter's
handling must be stated by the grammar or another confirmed rule; it must not
be inferred from formatting accepted by the grammar reader.

Inputs/includes must have explicit source semantics before include behavior
is implemented. Those semantics need to define source order and declaration
visibility, provenance in diagnostics, duplicate declarations, relative
path resolution, and cycle handling. The source stack must not imply an
undocumented include mechanism.

## Scanner and source locations

The scanner selects the longest matching lexer token. The equal-length tie
policy is not specified yet. Parser-expression matching is distinct: a
parser rule expression chooses the shortest possible match, rather than
applying the scanner's longest-token policy. The precise interaction of
alternatives, repetition, recursion, and equal-length parser matches remains
to be validated and specified; implementations must not substitute greedy
or maximal-munch parser behavior.

Each token carries its kind, lexeme, and start/end source span. A span records
source identity, byte offsets, and one-based line and column positions. The
source identity retains filename and provenance, including whether input came
from a file, an include, or another pushed source.

The scanner owns a stack of input sources. EOF in a nested source pops that
source and resumes its parent; EOF at the root is a stable terminal result,
not a fabricated token. Empty nested inputs follow the same pop-and-resume
rule. Includes and source-push syntax are not specified yet; the scanner
contract should not depend on the eventual spelling.

## AST and visitor contract

Each parser rule produces a rule node with its rule name, a source span, and
children in grammar/source order. Matched terminals are explicit leaf nodes
with token kind, lexeme, and span; grouping syntax does not add artificial
nodes. Repeated and optional constructs preserve the matched child order.
The root span runs from the first consumed token through the last consumed
token. Handling unconsumed trailing input is parser API behavior and is not
specified here.

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

Directives are named, and their content is opaque to grammar parsing. They
may eventually select output options or target-language insertion
boundaries, but the names, boundaries, payload rules, and syntax are not
specified here. If code-insertion directives are supported, their contents
must remain opaque until passed to the selected backend; parser rules cannot
contain those payloads or arbitrary actions.

Parser rules accept grammar expressions only. They cannot contain arbitrary
code, semantic actions, or embedded target-language fragments. AST visitors
are the supported extension point for user behavior.

## Left recursion and diagnostics

Validation builds the rule-reference graph, checks undefined references and
unreachable rules, and detects nullable repetitions and left-recursive cycles
before emission. Diagnostics point to the grammar source span and include
the relevant rule path.

Left recursion must be detected and transformed where supported, with the
generated parse preserving the grammar's shortest-match behavior, alternative
and child order, and AST associativity. A conventional greedy suffix loop
must not be assumed correct merely because it removes recursion. For
example, an expression grammar intended to produce `((a+b)+c)` must retain
that AST shape without changing which input extent the grammar matches.
Transformation details and the supported direct/indirect cases remain open
until their behavior is validated against representative grammars. A
left-recursive form the implementation cannot preserve must fail with a
source-located diagnostic rather than generate a looping or
semantics-changing parser.

Other validation failures should likewise be actionable and located: duplicate
rules/tokens/directives, malformed expressions, unknown token/rule references,
unsupported regex constructs, and malformed declarations. Generation must
not silently omit invalid grammar fragments.

## DOT view

DOT is another emitter over the validated model. Its primary graph shows
parser-rule dependencies with one node per rule and edges labeled with the
referencing alternative/order. Direct and indirect left-recursive edges are
visually distinguished. An optional expanded view may show expression
operators, token references, and literal leaves; it must still derive from the
same model and be deterministic for the same grammar.

## Milestone and open decisions

This document remains a design proposal with provisional fixtures. The
executable now establishes declaration collection, a typed expression model,
reference/nullability/left-cycle validation, and Cwhip plus DOT emission for
working small examples. Later work adds C, C++, and Python emitters, richer
regexes and source tracking, efficient parser analysis, and supported
left-recursion transformations. The calculator and SmallC grammar are concrete
fixtures. SmallC's next milestone is source-order semantic validation and,
eventually, a separate bytecode backend; see its
[boundary notes](../examples/smallc/README.md#single-pass-and-semantic-boundary).
Larger grammars must refine directive boundaries, includes, regex composition,
and backtracking/normalization semantics without silently changing the
existing prefix or whole-input APIs.

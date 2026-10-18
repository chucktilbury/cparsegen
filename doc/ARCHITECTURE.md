# Parser-generator architecture and provisional grammar format

This document proposes the first implementation boundary for cparsegen. The
syntax and insertion-directive spelling are provisional until they are
checked against a real user grammar. `examples/expression.cpg` is a fixture for
discussion, not a compatibility promise.

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

The first executable milestone should prove this boundary with one small
grammar, a Cwhip parser/AST/scanner emitter, and a DOT emitter. C, C++, and
Python emitters follow the model rather than defining separate grammar
semantics.

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

Generated visitors expose normal target-language APIs with a pre-hook and a
post-hook for every parser rule. A pre-hook runs before child traversal and a
post-hook after it; the default visitor walks children in order. Hooks are
visitor customization points, not parser actions, and do not change parse
semantics.

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

This is a design proposal and fixture, not an implemented parser generator.
The first code milestone should establish declaration collection, a typed
target-neutral model, later reference resolution/validation, and Cwhip plus
DOT emission. Later work adds C, C++, and Python emitters. A real example
grammar is needed to settle directive spelling and content boundaries,
comment syntax, include semantics, regex composition and operators,
equal-length match behavior, parser-expression choice/backtracking details,
and the supported left-recursion transformations without baking guesses into
the format.

# Parser-generator architecture and provisional grammar format

This document proposes the first implementation boundary for cparsegen. The
syntax and insertion-directive spelling are provisional until they are
checked against a real user grammar. `examples/expression.cpg` is a fixture for
discussion, not a compatibility promise.

## Pipeline

```text
grammar source stack
  -> section-aware grammar reader
  -> validated target-neutral grammar model
  -> analysis and normalization
  -> Cwhip / C / C++ / Python / DOT emitters
```

The grammar reader should preserve source provenance in diagnostics. The
validated model is the shared contract between parsing, analysis, and every
emitter; target backends must not re-parse grammar text or infer syntax from
generated code. Emitters consume only a model that has passed validation.

The first executable milestone should prove this boundary with one small
grammar, a Cwhip parser/AST/scanner emitter, and a DOT emitter. C, C++, and
Python emitters follow the model rather than defining separate grammar
semantics.

## Intermediate representation boundary

The model separates source syntax, validated grammar meaning, and target
rendering:

| Model component | Contents |
| --- | --- |
| `Grammar` | Ordered lexer rules, ordered parser rules, directives, and source identity |
| `SourceSpan` | Source identity, half-open byte range, and one-based start/end line and column |
| `RegexExpr` | Tagged literal, character class, any-character, sequence, alternation, and repetition nodes |
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

## Provisional file structure

Each grammar has three distinct top-level sections, in this order:

```text
DIRECTIVES { ... }
LEXER     { ... }
PARSER    { ... }
```

The section names are illustrative. A file must contain exactly one of each;
directives and grammar rules never share a section. Duplicate, missing,
unknown, or out-of-order sections are errors rather than silently ignored
input.

`LEXER` contains uppercase token names assigned flex-like regular expressions.
`PARSER` contains lowercase rule names, `:`, and alternatives separated by
`|`. Parentheses group expressions; `*`, `+`, and `?` mean zero-or-more,
one-or-more, and optional. Literal terminals are quoted. Named lexer tokens
are referenced by their uppercase names.

The initial regex subset should be explicit and portable: concatenation,
alternation, grouping, character classes and ranges, escapes, `.`, and the
`*`, `+`, `?` quantifiers. Anchors, counted repetition, trailing context,
start conditions, backreferences, and engine-specific extensions are not in
the initial subset. Unsupported constructs must have source-located errors.

## Scanner and source locations

The scanner selects the longest matching token. Equal-length matches resolve
by lexer declaration order; literal terminals are added in first-appearance
order after named lexer rules. Whitespace and comments are not implicitly
discarded: grammars must declare them and the format must provide a distinct
skip directive before implementation.

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
token, excluding trailing skipped input.

Generated visitors expose normal target-language APIs with a pre-hook and a
post-hook for every parser rule. A pre-hook runs before child traversal and a
post-hook after it; the default visitor walks children in order. Hooks are
visitor customization points, not parser actions, and do not change parse
semantics.

## Directives and target code

Directives select output options and named target-language insertion
boundaries. Proposed boundaries are a file preamble, generated declarations,
and file footer, with target-language source kept only in `DIRECTIVES`.
Insertion order within a boundary is source order. The generator should reject
a code block whose declared target does not match the selected backend.
Directive names, quoting/escaping, and exact block delimiters remain open
until a real sample grammar is available.

Parser rules accept grammar expressions only. They cannot contain arbitrary
code, semantic actions, or embedded target-language fragments. AST visitors
are the supported extension point for user behavior.

## Left recursion and diagnostics

Validation builds the rule-reference graph, checks undefined references and
unreachable rules, and detects nullable repetitions and left-recursive cycles
before emission. Diagnostics point to the grammar source span and include
the relevant rule path.

Direct left recursion of the form `A : A suffix | base` can be normalized
into a seed parse followed by an ordered suffix loop. AST construction must
fold each suffix onto the prior result so the resulting tree remains
left-associative; for example, `a+b+c` becomes `((a+b)+c)`, not
`(a+(b+c))`. Alternative order and child order remain observable. A recursive
alternative without a base, a nullable suffix, or a cycle that the selected
normalizer cannot preserve must fail with a diagnostic instead of generating
a looping or semantics-changing parser. Indirect-left-recursion handling and
its precise supported subset require validation against representative
grammars before being promised.

Other validation failures should likewise be actionable and located: duplicate
rules/tokens, malformed expressions, unknown token/rule references, invalid
regex constructs, and malformed section boundaries. Generation must not
silently omit invalid grammar fragments.

## DOT view

DOT is another emitter over the validated model. Its primary graph shows
parser-rule dependencies with one node per rule and edges labeled with the
referencing alternative/order. Direct and indirect left-recursive edges are
visually distinguished. An optional expanded view may show expression
operators, token references, and literal leaves; it must still derive from the
same model and be deterministic for the same grammar.

## Milestone and open decisions

This is a design proposal and fixture, not an implemented parser generator.
The first code milestone should establish section-aware parsing, a typed
target-neutral model, validation, and Cwhip plus DOT emission. Later work adds
C, C++, and Python emitters. A real example grammar is needed to settle
directive/block syntax, whitespace and comment conventions, source-stack
include spelling, regex compatibility details, and indirect-left-recursion
behavior without baking guesses into the format.

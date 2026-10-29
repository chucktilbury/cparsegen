// Typed, target-neutral analysis of a parsed (and include-expanded) grammar.
//
// Pipeline: GrammarSources.read() collects declarations into a GrammarModel,
// then GrammarAnalyzer.run() resolves references, validates them, and attaches
// one immutable-after-construction Analysis to the model. Backends only read
// it. Analysis-only facts: references, nullability, left-corner graph,
// reachability. Emitted normalization records: lexer NFA plans, the numbered
// parser expression table and its literal table.

class AnalysisDiagnostic {
    String phase
    GrammarDiagnostic info
    bool located

    AnalysisDiagnostic(String analysisPhase, GrammarDiagnostic diagnostic, bool hasLocation) {
        phase = analysisPhase
        info = diagnostic
        located = hasLocation
    }
}

// Domains: 0 lexer expression to lexer token, 1 parser to lexer token,
// 2 parser expression to parser rule.
class ResolvedReference {
    int64 domain
    String name
    int64 owner
    int64 target
    int64 line
    SourceSpan span
    SourceSpan targetSpan

    ResolvedReference(int64 referenceDomain, String targetName, int64 ownerIndex, int64 targetIndex,
                      int64 sourceLine, SourceSpan location, SourceSpan declaration) {
        domain = referenceDomain
        name = targetName
        owner = ownerIndex
        target = targetIndex
        line = sourceLine
        span = location
        targetSpan = declaration
    }
}

// One lexer token, including synthetic @quoted tokens, with its compiled
// Thompson NFA entry in Analysis.lexerStates and its resolved dependencies.
class LexerPlan {
    int64 index
    String name
    LexerRule rule
    int64 quote
    bool skip
    bool nullable
    int64 entry
    int64 accept
    int64 firstState
    int64 stateCount
    int64 color
    list references
    int64 line
    SourceSpan span

    LexerPlan(int64 position, LexerRule declaration) {
        index = position
        name = declaration.name
        rule = declaration
        quote = declaration.quote
        skip = false
        nullable = false
        entry = -1
        accept = -1
        firstState = 0
        stateCount = 0
        color = 0
        references = []
        line = declaration.line
        span = declaration.span
    }
}

// An edge A -> B means B can start a match of A once only nullable material
// precedes it. zeroContext is true when nothing non-nullable can follow it
// inside A, so a cycle of such edges consumes nothing and nothing follows it.
class LeftCornerEdge {
    int64 origin
    int64 destination
    bool zeroContext
    int64 line
    SourceSpan span

    LeftCornerEdge(int64 source, int64 target, bool zero, int64 sourceLine, SourceSpan location) {
        origin = source
        destination = target
        zeroContext = zero
        line = sourceLine
        span = location
    }
}

class ParserRuleFacts {
    int64 index
    String name
    ParserRule rule
    int64 root
    bool nullable
    bool leftRecursive
    list corners
    list reachable
    int64 line
    SourceSpan span

    ParserRuleFacts(int64 position, ParserRule declaration) {
        index = position
        name = declaration.name
        rule = declaration
        root = -1
        nullable = false
        leftRecursive = false
        corners = []
        reachable = []
        line = declaration.line
        span = declaration.span
    }
}

// Numbered parser expression. Children precede parents, so the table order is
// the emitted expression order. kind: 0 reference, 1 literal, 2 sequence,
// 3 choice, 4 repetition. target is a parser-rule index and token a lexer
// index for references (-1 otherwise); literal indexes Analysis.literals.
class ParserExprRecord {
    int64 index
    int64 kind
    String value
    list children
    int64 minimum
    int64 maximum
    int64 required
    int64 literal
    int64 target
    int64 token
    bool nullable
    int64 line
    SourceSpan span

    ParserExprRecord(RuleExpr expression, int64 position) {
        index = position
        kind = expression.kind
        value = expression.value
        children = []
        minimum = expression.minimum
        maximum = expression.maximum
        required = 0
        literal = -1
        target = -1
        token = -1
        nullable = false
        line = expression.line
        span = expression.span
    }
}

class LexicalConfig {
    String keywordToken
    SourceSpan keywordSpan
    SourceSpan reservedSpan
    list reserved
    list lineComments
    list blockComments

    LexicalConfig() {
        keywordToken = ""
        keywordSpan = null
        reservedSpan = null
        reserved = []
        lineComments = []
        blockComments = []
    }
}

class Analysis {
    bool complete
    LexicalConfig lexical
    list lexers
    list lexerStates
    list lexerReferences
    list parserRules
    list expressions
    list literals
    list parserReferences
    bool leftRecursive
    list diagnostics

    Analysis() {
        complete = false
        lexical = LexicalConfig()
        lexers = []
        lexerStates = []
        lexerReferences = []
        parserRules = []
        expressions = []
        literals = []
        parserReferences = []
        leftRecursive = false
        diagnostics = []
    }

    int64 lexerIndex(String name) {
        int64 i = 0
        while (i < lexers.length) {
            if ((lexers[i] as LexerPlan).name.equals(name)) { return(i) }
            i += 1
        }
        return(-1)
    }

    int64 parserIndex(String name) {
        int64 i = 0
        while (i < parserRules.length) {
            if ((parserRules[i] as ParserRuleFacts).name.equals(name)) { return(i) }
            i += 1
        }
        return(-1)
    }

    int64 literalIndex(String value) {
        int64 i = 0
        while (i < literals.length) {
            if ((literals[i] as String).equals(value)) { return(i) }
            i += 1
        }
        return(-1)
    }

    int64 nameCount(list names, String name) {
        int64 count = 0
        int64 i = 0
        while (i < names.length) {
            if ((names[i] as String).equals(name)) { count += 1 }
            i += 1
        }
        return(count)
    }
}

class GrammarAnalyzer {
    GrammarModel grammar
    Analysis analysis
    String lexerProblem
    SourceSpan lexerProblemSpan
    bool lastNullable

    GrammarAnalyzer(GrammarModel model) {
        grammar = model
        analysis = Analysis()
        lexerProblem = ""
        lexerProblemSpan = null
        lastNullable = false
    }

    // Runs every shared check in the established order and attaches the result.
    String run() {
        grammar.diagnosticSpan = null
        grammar.relatedSpan = null
        grammar.diagnosticInfo = null
        String problem = analyze()
        analysis.complete = problem.equals("")
        grammar.analysis = analysis
        if (analysis.diagnostics.length > 0) {
            AnalysisDiagnostic last = analysis.diagnostics[analysis.diagnostics.length - 1] as AnalysisDiagnostic
            if (last.located) {
                grammar.diagnosticInfo = last.info
                grammar.diagnosticSpan = last.info.span
                grammar.relatedSpan = last.info.related
            }
        }
        return(problem)
    }

    String fail(String phase, String error, SourceSpan span, SourceSpan related) {
        analysis.diagnostics.append(AnalysisDiagnostic(phase, GrammarDiagnostic(error, span, related), true))
        return(error)
    }

    String failPlain(String phase, String error) {
        analysis.diagnostics.append(AnalysisDiagnostic(phase, GrammarDiagnostic(error, null, null), false))
        return(error)
    }

    bool identifier(String name) {
        int64 i = 0
        while (i < name.length) {
            int64 byte = int64(name[i])
            bool letter = (byte >= 65 && byte <= 90) || (byte >= 97 && byte <= 122) || byte == 95
            if (!letter && (i == 0 || byte < 48 || byte > 57)) { return(false) }
            i += 1
        }
        return(name.length > 0)
    }

    list directiveWords(String content) {
        list pieces = content.replace("\t", " ").replace("\n", " ").replace("\r", " ").split(" ")
        list words = []
        int64 i = 0
        while (i < pieces.length) {
            String word = pieces[i] as String
            if (word.length > 0) { words.append(word) }
            i += 1
        }
        return(words)
    }

    String analyze() {
        String error = validateInsertions()
        if (!error.equals("")) { return(error) }
        int64 d = 0
        while (d < grammar.lexerRules.length) {
            addLexer(grammar.lexerRules[d] as LexerRule)
            d += 1
        }
        error = lexicalDirectives()
        if (!error.equals("")) { return(error) }
        if (analysis.lexers.length == 0) { return(failPlain("declarations", "grammar must declare a lexer rule")) }
        if (grammar.parserRules.length == 0) { return(failPlain("declarations", "grammar must declare a parser rule")) }
        error = checkLexerNames()
        if (!error.equals("")) { return(error) }
        error = compileLexers()
        if (!error.equals("")) { return(error) }
        error = applySkips()
        if (!error.equals("")) { return(error) }
        error = checkParserNames()
        if (!error.equals("")) { return(error) }
        buildParserTable()
        computeNullability()
        buildLeftCorners()
        error = validateParser()
        if (!error.equals("")) { return(error) }
        finishLeftRecursion()
        return("")
    }

    void addLexer(LexerRule rule) {
        analysis.lexers.append(LexerPlan(analysis.lexers.length, rule))
    }

    String validateInsertions() {
        int64 i = 0
        while (i < grammar.insertions.length) {
            CodeInsertion block = grammar.insertions[i] as CodeInsertion
            if (!block.target.equals("c") && !block.target.equals("cwhip")) {
                return(fail("insertions", format("line {}: unknown @insert target {}", block.location,
                    block.target), block.targetSpan, null))
            }
            if (!block.boundary.equals("file_pre") && !block.boundary.equals("file_post") &&
                !block.boundary.equals("imports") && !block.boundary.equals("declarations") &&
                !block.boundary.equals("ast_pre") && !block.boundary.equals("ast_post") &&
                !block.boundary.equals("scanner_pre") && !block.boundary.equals("scanner_post") &&
                !block.boundary.equals("parser_pre") && !block.boundary.equals("parser_post") &&
                !block.boundary.equals("visitor_pre") && !block.boundary.equals("visitor_post")) {
                return(fail("insertions", format("line {}: unknown @insert boundary {}",
                    block.location, block.boundary), block.boundarySpan, null))
            }
            i += 1
        }
        return("")
    }

    String lexicalDirectives() {
        LexicalConfig lexical = analysis.lexical
        int64 i = 0
        while (i < grammar.directives.length) {
            GrammarDirective directive = grammar.directives[i] as GrammarDirective
            list words = directiveWords(directive.content)
            if (directive.name.equals("quoted")) {
                if (words.length != 2) {
                    return(fail("directives", format("line {}: @quoted requires TOKEN single|double",
                        directive.line), directive.span, null))
                }
                String style = words[1] as String
                if (!style.equals("single") && !style.equals("double")) {
                    return(fail("directives", format("line {}: @quoted requires single or double",
                        directive.line), directive.span, null))
                }
                LexerRule rule = LexerRule(words[0] as String, directive.line)
                rule.quote = 34
                if (style.equals("single")) { rule.quote = 39 }
                rule.span = directive.span
                addLexer(rule)
            }
            if (directive.name.equals("keywords")) {
                if (words.length != 1 || !lexical.keywordToken.equals("")) {
                    return(fail("directives", format("line {}: @keywords requires one identifier token and may occur only once",
                        directive.line), directive.span, null))
                }
                lexical.keywordToken = words[0] as String
                lexical.keywordSpan = directive.span
            }
            if (directive.name.equals("reserved")) {
                lexical.reservedSpan = directive.span
                if (words.length == 0) {
                    return(fail("directives", format("line {}: @reserved requires word names",
                        directive.line), directive.span, null))
                }
                int64 w = 0
                while (w < words.length) {
                    if (!identifier(words[w] as String)) {
                        return(fail("directives", format("line {}: @reserved requires identifier spellings",
                            directive.line), directive.span, null))
                    }
                    lexical.reserved.append(words[w])
                    w += 1
                }
            }
            if (directive.name.equals("line_comment")) {
                if (words.length != 1 || (words[0] as String).length == 0) {
                    return(fail("directives", format("line {}: @line_comment requires one nonempty marker",
                        directive.line), directive.span, null))
                }
                lexical.lineComments.append(words[0])
            }
            if (directive.name.equals("block_comment")) {
                if (words.length != 2) {
                    return(fail("directives", format("line {}: @block_comment requires opening and closing markers",
                        directive.line), directive.span, null))
                }
                lexical.blockComments.append(words)
            }
            i += 1
        }
        if (!lexical.keywordToken.equals("")) {
            int64 token = analysis.lexerIndex(lexical.keywordToken)
            if (token < 0 || (analysis.lexers[token] as LexerPlan).quote != 0) {
                return(fail("directives", "@keywords must name a declared expression lexer token",
                            lexical.keywordSpan, null))
            }
        }
        if (lexical.reserved.length > 0 && lexical.keywordToken.equals("")) {
            return(fail("directives", "@reserved requires @keywords to identify the identifier token",
                        lexical.reservedSpan, null))
        }
        return("")
    }

    String checkLexerNames() {
        list names = []
        int64 i = 0
        while (i < analysis.lexers.length) {
            names.append((analysis.lexers[i] as LexerPlan).name)
            i += 1
        }
        i = 0
        while (i < analysis.lexers.length) {
            LexerPlan plan = analysis.lexers[i] as LexerPlan
            int64 first = int64(plan.name[0])
            if (first < 65 || first > 90 || !identifier(plan.name)) {
                return(fail("lexer", format("line {}: lexer names must begin with an uppercase letter",
                    plan.line), plan.span, null))
            }
            if (analysis.nameCount(names, plan.name) > 1) {
                SourceSpan previous = null
                int64 p = 0
                while (p < i && previous == null) {
                    LexerPlan candidate = analysis.lexers[p] as LexerPlan
                    if (candidate.name.equals(plan.name)) { previous = candidate.span }
                    p += 1
                }
                if (previous != null) {
                    return(fail("lexer", format("line {}: duplicate lexer rule {}", plan.line,
                        plan.name), plan.span, previous))
                }
            }
            i += 1
        }
        return("")
    }

    String resolveLexer(LexerPlan owner, LexerExpr expression, int64 depth) {
        if (depth > 128) {
            return(fail("lexer", format("line {}: lexer expression nesting/reference limit exceeded (128)",
                expression.line), expression.span, null))
        }
        if (expression.kind == 1) {
            int64 index = analysis.lexerIndex(expression.value)
            if (index < 0) {
                return(fail("lexer", format("line {}: unknown lexer reference {}", expression.line,
                    expression.value), expression.span, null))
            }
            LexerPlan target = analysis.lexers[index] as LexerPlan
            if (target.quote != 0) {
                return(fail("lexer", format("line {}: cannot compose @quoted token {}",
                    expression.line, target.name), expression.span, target.span))
            }
            if (target.color == 1) {
                return(fail("lexer", format("line {}: cyclic lexer reference {}",
                    expression.line, target.name), expression.span, target.span))
            }
            if (target.color == 0) {
                target.color = 1
                String error = resolveLexer(target, target.rule.expression, depth + 1)
                if (!error.equals("")) { return(error) }
                target.nullable = lastNullable
                target.color = 2
            }
            owner.references.append(ResolvedReference(0, target.name, owner.index, index,
                expression.line, expression.span, target.span))
            lastNullable = target.nullable
            return("")
        }
        bool nullable = expression.kind == 2 || (expression.kind == 4 && expression.minimum == 0)
        int64 c = 0
        while (c < expression.children.length) {
            LexerExpr child = expression.children[c] as LexerExpr
            String error = resolveLexer(owner, child, depth + 1)
            if (!error.equals("")) { return(error) }
            bool childNullable = lastNullable
            if (expression.kind == 2 && !childNullable) { nullable = false }
            if (expression.kind == 3 && childNullable) { nullable = true }
            if (expression.kind == 4 && childNullable) {
                return(fail("lexer", format("line {}: nullable lexer repetition is not supported",
                    expression.line), expression.span, null))
            }
            c += 1
        }
        lastNullable = nullable
        return("")
    }

    int64 lexerState(int64 kind, list ranges, int64 next, int64 alternate, int64 line, SourceSpan span) {
        if (analysis.lexerStates.length >= 4096) {
            lexerProblem = format("line {}: expanded lexer state limit exceeded (4096)", line)
            lexerProblemSpan = span
            return(-1)
        }
        int64 index = analysis.lexerStates.length
        analysis.lexerStates.append(LexerState(kind, ranges, next, alternate))
        return(index)
    }

    int64 compileLexer(LexerExpr expression, int64 next, int64 depth) {
        if (!lexerProblem.equals("")) { return(-1) }
        if (depth > 128) {
            lexerProblem = format("line {}: expanded lexer nesting/reference limit exceeded (128)", expression.line)
            lexerProblemSpan = expression.span
            return(-1)
        }
        if (expression.kind == 0) {
            return(lexerState(0, expression.ranges, next, -1, expression.line, expression.span))
        }
        if (expression.kind == 1) {
            LexerPlan target = analysis.lexers[analysis.lexerIndex(expression.value)] as LexerPlan
            return(compileLexer(target.rule.expression, next, depth + 1))
        }
        if (expression.kind == 2) {
            int64 c = expression.children.length - 1
            while (c >= 0 && lexerProblem.equals("")) {
                next = compileLexer(expression.children[c] as LexerExpr, next, depth + 1)
                c -= 1
            }
            return(next)
        }
        if (expression.kind == 3) {
            int64 result = compileLexer(expression.children[0] as LexerExpr, next, depth + 1)
            int64 c = 1
            while (c < expression.children.length && lexerProblem.equals("")) {
                int64 branch = compileLexer(expression.children[c] as LexerExpr, next, depth + 1)
                result = lexerState(1, [], result, branch, expression.line, expression.span)
                c += 1
            }
            return(result)
        }
        int64 split = lexerState(1, [], -1, next, expression.line, expression.span)
        if (split < 0) { return(-1) }
        int64 continuation = next
        if (expression.maximum < 0) { continuation = split }
        int64 child = compileLexer(expression.children[0] as LexerExpr, continuation, depth + 1)
        (analysis.lexerStates[split] as LexerState).next = child
        if (expression.minimum == 0) { return(split) }
        return(child)
    }

    String compileLexers() {
        int64 i = 0
        while (i < analysis.lexers.length) {
            LexerPlan plan = analysis.lexers[i] as LexerPlan
            if (plan.quote == 0) {
                if (plan.color == 0) {
                    plan.color = 1
                    String error = resolveLexer(plan, plan.rule.expression, 0)
                    if (!error.equals("")) { return(error) }
                    plan.nullable = lastNullable
                    plan.color = 2
                }
                if (plan.nullable) {
                    return(fail("lexer", format("line {}: lexer rule {} can match empty input",
                        plan.line, plan.name), plan.span, null))
                }
                plan.firstState = analysis.lexerStates.length
                plan.accept = lexerState(2, [], -1, -1, plan.line, plan.span)
                plan.entry = compileLexer(plan.rule.expression, plan.accept, 0)
                if (!lexerProblem.equals("")) {
                    return(fail("lexer", lexerProblem, lexerProblemSpan, null))
                }
                plan.stateCount = analysis.lexerStates.length - plan.firstState
            }
            i += 1
        }
        i = 0
        while (i < analysis.lexers.length) {
            list references = (analysis.lexers[i] as LexerPlan).references
            int64 r = 0
            while (r < references.length) {
                analysis.lexerReferences.append(references[r])
                r += 1
            }
            i += 1
        }
        return("")
    }

    String applySkips() {
        int64 i = 0
        while (i < grammar.directives.length) {
            GrammarDirective directive = grammar.directives[i] as GrammarDirective
            if (directive.name.equals("skip")) {
                int64 token = analysis.lexerIndex(directive.content)
                if (token < 0) {
                    return(fail("directives", format("line {}: @skip requires a declared lexer token name",
                        directive.line), directive.span, null))
                }
                (analysis.lexers[token] as LexerPlan).skip = true
            }
            i += 1
        }
        String keyword = analysis.lexical.keywordToken
        if (!keyword.equals("")) {
            LexerPlan token = analysis.lexers[analysis.lexerIndex(keyword)] as LexerPlan
            if (token.skip) {
                return(fail("directives", "@keywords cannot use a skipped lexer token",
                            analysis.lexical.keywordSpan, token.span))
            }
        }
        return("")
    }

    String checkParserNames() {
        list names = []
        int64 i = 0
        while (i < grammar.parserRules.length) {
            names.append((grammar.parserRules[i] as ParserRule).name)
            i += 1
        }
        i = 0
        while (i < grammar.parserRules.length) {
            ParserRule rule = grammar.parserRules[i] as ParserRule
            int64 first = int64(rule.name[0])
            if (first < 97 || first > 122) {
                return(fail("parser", format("line {}: parser-rule names must begin with a lowercase letter",
                    rule.line), rule.span, null))
            }
            if (analysis.nameCount(names, rule.name) > 1) {
                SourceSpan previous = null
                int64 p = 0
                while (p < i && previous == null) {
                    ParserRule candidate = grammar.parserRules[p] as ParserRule
                    if (candidate.name.equals(rule.name)) { previous = candidate.span }
                    p += 1
                }
                if (previous != null) {
                    return(fail("parser", format("line {}: duplicate parser rule {}", rule.line,
                        rule.name), rule.span, previous))
                }
            }
            i += 1
        }
        return("")
    }

    // Numbers expressions children-first, resolves references, and interns literals.
    int64 record(RuleExpr expression) {
        ParserExprRecord entry = ParserExprRecord(expression, 0)
        int64 c = 0
        while (c < expression.children.length) {
            entry.children.append(record(expression.children[c] as RuleExpr))
            c += 1
        }
        if (expression.kind == 0) {
            entry.token = analysis.lexerIndex(expression.value)
            if (entry.token < 0) { entry.target = analysis.parserIndex(expression.value) }
        }
        if (expression.kind == 1) {
            entry.literal = analysis.literalIndex(expression.value)
            if (entry.literal < 0) {
                entry.literal = analysis.literals.length
                analysis.literals.append(expression.value)
            }
        }
        entry.index = analysis.expressions.length
        analysis.expressions.append(entry)
        return(entry.index)
    }

    ParserExprRecord expressionAt(int64 index) {
        return(analysis.expressions[index] as ParserExprRecord)
    }

    ParserRuleFacts ruleAt(int64 index) {
        return(analysis.parserRules[index] as ParserRuleFacts)
    }

    void buildParserTable() {
        int64 i = 0
        while (i < grammar.parserRules.length) {
            analysis.parserRules.append(ParserRuleFacts(i, grammar.parserRules[i] as ParserRule))
            i += 1
        }
        i = 0
        while (i < analysis.parserRules.length) {
            ParserRuleFacts facts = ruleAt(i)
            facts.root = record(facts.rule.expression)
            i += 1
        }
    }

    // Least fixed point over rule nullability; expression records follow it.
    void computeNullability() {
        bool changed = true
        while (changed) {
            changed = false
            int64 e = 0
            while (e < analysis.expressions.length) {
                ParserExprRecord entry = expressionAt(e)
                bool nullable = false
                if (entry.kind == 0) {
                    nullable = entry.target >= 0 && ruleAt(entry.target).nullable
                }
                if (entry.kind == 4) {
                    nullable = entry.minimum == 0 || expressionAt(entry.children[0] as int64).nullable
                }
                if (entry.kind == 2) {
                    nullable = true
                    int64 c = 0
                    while (c < entry.children.length) {
                        if (!expressionAt(entry.children[c] as int64).nullable) { nullable = false }
                        c += 1
                    }
                }
                if (entry.kind == 3) {
                    int64 c = 0
                    while (c < entry.children.length) {
                        if (expressionAt(entry.children[c] as int64).nullable) { nullable = true }
                        c += 1
                    }
                }
                entry.nullable = nullable
                e += 1
            }
            int64 r = 0
            while (r < analysis.parserRules.length) {
                ParserRuleFacts facts = ruleAt(r)
                if (!facts.nullable && expressionAt(facts.root).nullable) {
                    facts.nullable = true
                    changed = true
                }
                r += 1
            }
        }
    }

    void collectCorners(ParserRuleFacts owner, int64 index, bool zero) {
        ParserExprRecord entry = expressionAt(index)
        if (entry.kind == 0) {
            if (entry.target >= 0) {
                owner.corners.append(LeftCornerEdge(owner.index, entry.target, zero, entry.line, entry.span))
            }
            return
        }
        int64 c = 0
        while (c < entry.children.length) {
            bool childZero = zero
            if (entry.kind == 2) {
                int64 s = c + 1
                while (s < entry.children.length) {
                    if (!expressionAt(entry.children[s] as int64).nullable) { childZero = false }
                    s += 1
                }
            }
            collectCorners(owner, entry.children[c] as int64, childZero)
            if (entry.kind == 2 && !expressionAt(entry.children[c] as int64).nullable) { return }
            c += 1
        }
    }

    void buildLeftCorners() {
        int64 r = 0
        while (r < analysis.parserRules.length) {
            ParserRuleFacts facts = ruleAt(r)
            collectCorners(facts, facts.root, true)
            r += 1
        }
        r = 0
        while (r < analysis.parserRules.length) {
            ParserRuleFacts facts = ruleAt(r)
            int64 n = 0
            while (n < analysis.parserRules.length) {
                facts.reachable.append(false)
                n += 1
            }
            list pending = []
            int64 e = 0
            while (e < facts.corners.length) {
                pending.append((facts.corners[e] as LeftCornerEdge).destination)
                e += 1
            }
            int64 p = 0
            while (p < pending.length) {
                int64 node = pending[p] as int64
                if (!(facts.reachable[node] as bool)) {
                    facts.reachable[node] = true
                    list next = ruleAt(node).corners
                    int64 k = 0
                    while (k < next.length) {
                        pending.append((next[k] as LeftCornerEdge).destination)
                        k += 1
                    }
                }
                p += 1
            }
            facts.leftRecursive = facts.reachable[r] as bool
            r += 1
        }
    }

    String validateExpression(int64 index) {
        ParserExprRecord entry = expressionAt(index)
        if (entry.kind == 0) {
            if (entry.token < 0 && entry.target < 0) {
                int64 first = int64(entry.value[0])
                if (first >= 65 && first <= 90) {
                    return(fail("references", format("line {}: unknown lexer token {}", entry.line,
                        entry.value), entry.span, null))
                }
                return(fail("references", format("line {}: unknown parser rule {}", entry.line,
                    entry.value), entry.span, null))
            }
            if (entry.token >= 0) {
                LexerPlan token = analysis.lexers[entry.token] as LexerPlan
                if (token.skip) {
                    return(fail("references", format("line {}: skipped lexer token {} cannot be matched by a parser",
                        entry.line, token.name), entry.span, token.span))
                }
                analysis.parserReferences.append(ResolvedReference(1, token.name, -1, entry.token,
                    entry.line, entry.span, token.span))
            }
            else {
                analysis.parserReferences.append(ResolvedReference(2, ruleAt(entry.target).name, -1,
                    entry.target, entry.line, entry.span, ruleAt(entry.target).span))
            }
        }
        if (entry.kind == 1 && entry.value.length == 0) {
            return(fail("references", format("line {}: empty quoted terminals are not supported",
                entry.line), entry.span, null))
        }
        if (entry.kind == 4 && expressionAt(entry.children[0] as int64).nullable) {
            return(fail("references", format("line {}: nullable repetition is not supported",
                entry.line), entry.span, null))
        }
        int64 i = 0
        while (i < entry.children.length) {
            String error = validateExpression(entry.children[i] as int64)
            if (!error.equals("")) { return(error) }
            i += 1
        }
        return("")
    }

    // Only zero-context cycles admit infinitely many equal-span trees.
    String zeroCycle(int64 rule, list onPath, list done) {
        onPath[rule] = true
        list corners = ruleAt(rule).corners
        int64 e = 0
        while (e < corners.length) {
            LeftCornerEdge edge = corners[e] as LeftCornerEdge
            if (edge.zeroContext) {
                if (onPath[edge.destination] as bool) {
                    ParserRuleFacts target = ruleAt(edge.destination)
                    return(fail("left-recursion", format("line {}: left recursion through parser rule {} can repeat without consuming tokens; require a nonnullable prefix or suffix on every cycle",
                        edge.line, target.name), edge.span, target.span))
                }
                if (!(done[edge.destination] as bool)) {
                    String error = zeroCycle(edge.destination, onPath, done)
                    if (!error.equals("")) { return(error) }
                }
            }
            e += 1
        }
        onPath[rule] = false
        done[rule] = true
        return("")
    }

    String validateParser() {
        list onPath = []
        list done = []
        int64 n = 0
        while (n < analysis.parserRules.length) {
            onPath.append(false)
            done.append(false)
            n += 1
        }
        int64 r = 0
        while (r < analysis.parserRules.length) {
            ParserRuleFacts facts = ruleAt(r)
            String error = validateExpression(facts.root)
            if (!error.equals("")) { return(error) }
            error = zeroCycle(r, onPath, done)
            if (!error.equals("")) { return(error) }
            r += 1
        }
        return("")
    }

    // Consuming left recursion needs a conservative token lower bound per expression.
    void finishLeftRecursion() {
        int64 r = 0
        while (r < analysis.parserRules.length) {
            if (ruleAt(r).leftRecursive) { analysis.leftRecursive = true }
            r += 1
        }
        if (!analysis.leftRecursive) { return }
        int64 e = 0
        while (e < analysis.expressions.length) {
            ParserExprRecord entry = expressionAt(e)
            if (!entry.nullable) { entry.required = 1 }
            e += 1
        }
    }
}

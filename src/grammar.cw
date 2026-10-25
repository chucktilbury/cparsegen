class SourceLocation {
    String path
    String displayPath
    int64 offset
    int64 line
    int64 column
    int64 logicalLine
    SourceLocation includedFrom

    SourceLocation(String sourcePath, String shownPath, int64 byteOffset, int64 sourceLine,
                   int64 sourceColumn, int64 grammarLine, SourceLocation parent) {
        path = sourcePath
        displayPath = shownPath
        offset = byteOffset
        line = sourceLine
        column = sourceColumn
        logicalLine = grammarLine
        includedFrom = parent
    }

}

class SourceSpan {
    SourceLocation first
    SourceLocation last

    SourceSpan(SourceLocation startPoint, SourceLocation endPoint) {
        first = startPoint
        last = endPoint
    }
}

class GrammarDiagnostic {
    String message
    SourceSpan span
    SourceSpan related

    GrammarDiagnostic(String text, SourceSpan location, SourceSpan relatedLocation) {
        message = text
        if (text.startsWith("line ")) {
            int64 end = 5
            while (end < text.length && int64(text.byteAt(end)) >= 48 &&
                   int64(text.byteAt(end)) <= 57) { end += 1 }
            if (end + 1 < text.length) { message = text.slice(end + 2, text.length) }
        }
        span = location
        related = relatedLocation
    }
}

class GrammarToken {
    int64 kind
    String text
    String name
    int64 line
    String target
    String boundary
    SourceSpan span
    SourceSpan targetSpan
    SourceSpan boundarySpan

    GrammarToken(int64 tokenKind, String tokenText, String tokenName, int64 tokenLine) {
        kind = tokenKind
        text = tokenText
        name = tokenName
        line = tokenLine
        target = ""
        boundary = ""
        span = null
        targetSpan = null
        boundarySpan = null
    }
}

class GrammarScanner {
    String source
    String sourcePath
    String displayPath
    int64 offset
    int64 line
    int64 sourceLine
    int64 column
    bool previousCR
    SourceLocation includedFrom
    SourceSpan lastWordSpan
    String problem
    SourceSpan problemSpan

    GrammarScanner(String text, String path, String shownPath, int64 firstLine,
                   SourceLocation parent) {
        source = text
        sourcePath = path
        displayPath = shownPath
        offset = 0
        line = firstLine
        sourceLine = 1
        column = 1
        previousCR = false
        includedFrom = parent
        lastWordSpan = null
        problem = ""
        problemSpan = null
    }

    int64 current() {
        if (offset >= source.length) { return(-1) }
        return(int64(source.byteAt(offset)))
    }

    int64 following() {
        if (offset + 1 >= source.length) { return(-1) }
        return(int64(source.byteAt(offset + 1)))
    }

    void advance() {
        int64 value = current()
        if (value == 13) {
            line += 1
            sourceLine += 1
            column = 1
            previousCR = true
        }
        else {
            if (value == 10) {
                if (!previousCR) {
                    line += 1
                    sourceLine += 1
                }
                column = 1
                previousCR = false
            }
            else {
                column += 1
                previousCR = false
            }
        }
        offset += 1
    }

    SourceLocation location() {
        return(SourceLocation(sourcePath, displayPath, offset, sourceLine, column,
                              line, includedFrom))
    }

    SourceSpan span(int64 startOffset, int64 startLine, int64 startColumn) {
        int64 startLogicalLine = line - (sourceLine - startLine)
        SourceLocation first(sourcePath, displayPath, startOffset, startLine,
                             startColumn, startLogicalLine, includedFrom)
        return(SourceSpan(first, location()))
    }

    GrammarToken makeToken(int64 kind, String text, String name, int64 startOffset,
                           int64 startSourceLine, int64 startColumn, int64 startLogicalLine) {
        GrammarToken token(kind, text, name, startLogicalLine)
        token.span = span(startOffset, startSourceLine, startColumn)
        return(token)
    }

    bool letter(int64 value) {
        return((value >= 65 && value <= 90) || (value >= 97 && value <= 122) || value == 95)
    }

    bool digit(int64 value) {
        return(value >= 48 && value <= 57)
    }

    void skipTrivia() {
        while (current() >= 0) {
            if (current() <= 32) {
                advance()
            }
            else {
                if (current() == 35 || (current() == 47 && following() == 47)) {
                    while (current() >= 0 && current() != 10 && current() != 13) { advance() }
                }
                else {
                    if (current() == 47 && following() == 42) {
                        int64 startLine = line
                        int64 startSourceLine = sourceLine
                        int64 startColumn = column
                        int64 startOffset = offset
                        advance()
                        advance()
                        while (current() >= 0 && !(current() == 42 && following() == 47)) { advance() }
                        if (current() < 0) {
                            problem = format("line {}: unterminated block comment", startLine)
                            problemSpan = span(startOffset, startSourceLine, startColumn)
                            return
                        }
                        advance()
                        advance()
                    }
                    else {
                        return
                    }
                }
            }
        }
    }

    String insertionWord() {
        while (current() == 32 || current() == 9 || current() == 10 || current() == 13) { advance() }
        int64 startIndex = offset
        int64 startSourceLine = sourceLine
        int64 startColumn = column
        int64 startLogicalLine = line
        if (letter(current())) {
            while (letter(current()) || digit(current())) { advance() }
        }
        lastWordSpan = span(startIndex, startSourceLine, startColumn)
        lastWordSpan.first.logicalLine = startLogicalLine
        return(source.slice(startIndex, offset))
    }

    GrammarToken insertion(int64 startLine) {
        int64 startOffset = offset - 1
        int64 startSourceLine = sourceLine
        int64 startColumn = column - 1
        int64 startLogicalLine = startLine
        GrammarToken token(260, "", "insert", startLine)
        token.target = insertionWord()
        token.targetSpan = lastWordSpan
        token.boundary = insertionWord()
        token.boundarySpan = lastWordSpan
        while (current() == 32 || current() == 9 || current() == 10 || current() == 13) { advance() }
        if (token.target.equals("") || token.boundary.equals("") || current() != 123) {
            problem = format("line {}: @insert requires TARGET BOUNDARY {{ code }};", startLine)
            return(token)
        }
        advance()
        int64 startIndex = offset
        int64 depth = 1
        // State: code, quote byte, line comment ('/'), or block comment ('*').
        int64 state = 0
        int64 stateLine = line
        int64 stateSourceLine = sourceLine
        int64 stateColumn = column
        int64 stateOffset = offset
        bool escaped = false
        while (current() >= 0) {
            int64 value = current()
            int64 size = offset - startIndex
            if (size > 1048576 || (size == 1048576 && !(value == 125 && state == 0 && depth == 1))) {
                problem = format("line {}: @insert block exceeds 1048576 bytes", startLine)
                problemSpan = span(offset, sourceLine, column)
                return(token)
            }
            // C translation-phase rewriting would change delimiter recognition.
            if (value == 0 || (value == 92 && (following() == 10 || following() == 13)) ||
                (value == 63 && following() == 63)) {
                problem = format("line {}: @insert forbids NUL, backslash-newline and trigraph prefixes", line)
                problemSpan = span(offset, sourceLine, column)
                return(token)
            }
            if (state == 34 || state == 39) {
                if (value == 10 || value == 13) {
                    problem = format("line {}: unterminated @insert quoted literal", stateLine)
                    problemSpan = span(stateOffset, stateSourceLine, stateColumn)
                    return(token)
                }
                if (escaped) { escaped = false }
                else {
                    if (value == state) { state = 0 }
                    else { if (value == 92) { escaped = true } }
                }
            }
            else {
                if (state == 47) {
                    if (value == 10 || value == 13) { state = 0 }
                }
                else {
                    if (state == 42) {
                        if (value == 42 && following() == 47) {
                            advance()
                            state = 0
                        }
                    }
                    else {
                        if (value == 34 || value == 39) {
                            state = value
                            stateLine = line
                            stateSourceLine = sourceLine
                            stateColumn = column
                            stateOffset = offset
                        }
                        else {
                            if (value == 47 && (following() == 47 || following() == 42)) {
                                state = following()
                                stateLine = line
                                stateSourceLine = sourceLine
                                stateColumn = column
                                stateOffset = offset
                                advance()
                            }
                            else {
                                if (value == 123) {
                                    depth += 1
                                    if (depth > 256) {
                                        problem = format("line {}: @insert brace nesting exceeds 256", line)
                                        problemSpan = span(offset, sourceLine, column)
                                        return(token)
                                    }
                                }
                                if (value == 125) {
                                    depth -= 1
                                    if (depth == 0) { break }
                                }
                            }
                        }
                    }
                }
            }
            advance()
        }
        if (current() < 0) {
            if (state == 34 || state == 39) {
                problem = format("line {}: unterminated @insert quoted literal", stateLine)
                problemSpan = span(stateOffset, stateSourceLine, stateColumn)
            }
            else {
                if (state == 42) {
                    problem = format("line {}: unterminated @insert block comment", stateLine)
                    problemSpan = span(stateOffset, stateSourceLine, stateColumn)
                }
                else {
                    problem = format("line {}: unterminated @insert block", startLine)
                    problemSpan = span(startOffset, startSourceLine, startColumn)
                }
            }
            return(token)
        }
        token.text = source.slice(startIndex, offset)
        advance()
        skipTrivia()
        if (problem.equals("") && current() != 59) {
            problem = format("line {}: @insert block must end with ';'", startLine)
            problemSpan = span(offset, sourceLine, column)
        }
        if (problem.equals("")) { advance() }
        token.span = span(startOffset, startSourceLine, startColumn)
        if (!problem.equals("") && problemSpan == null) { problemSpan = token.span }
        return(token)
    }

    GrammarToken next() {
        skipTrivia()
        if (!problem.equals("")) {
            GrammarToken failed(0, "", "", line)
            failed.span = problemSpan
            return(failed)
        }
        int64 startLine = line
        int64 startSourceLine = sourceLine
        int64 startColumn = column
        int64 startOffset = offset
        int64 value = current()
        if (value < 0) {
            return(makeToken(0, "", "", startOffset, startSourceLine, startColumn, startLine))
        }

        if (letter(value)) {
            int64 startIndex = offset
            while (letter(current()) || digit(current())) { advance() }
            return(makeToken(256, source.slice(startIndex, offset), "", startOffset,
                             startSourceLine, startColumn, startLine))
        }

        if (value == 34 || value == 39) {
            int64 quote = value
            advance()
            String literal = ""
            int64 literalStart = offset
            while (current() >= 0 && current() != quote && current() != 10) {
                if (current() == 92) {
                    int64 escapeOffset = offset
                    int64 escapeSourceLine = sourceLine
                    int64 escapeColumn = column
                    literal.append(source.slice(literalStart, offset))
                    advance()
                    int64 escaped = current()
                    if (escaped == 110) { literal.append("\n") }
                    else {
                        if (escaped == 114) { literal.append("\r") }
                        else {
                            if (escaped == 116) { literal.append("\t") }
                            else {
                                if (escaped != 92 && escaped != 34 && escaped != 39) {
                                    problem = format("line {}: unsupported quoted escape", startLine)
                                    if (current() >= 0) { advance() }
                                    GrammarToken failed = makeToken(0, "", "", startOffset,
                                        startSourceLine, startColumn, startLine)
                                    problemSpan = span(escapeOffset, escapeSourceLine,
                                                       escapeColumn)
                                    failed.span = problemSpan
                                    return(failed)
                                }
                                literal.append(source.slice(offset, offset + 1))
                            }
                        }
                    }
                    literalStart = offset + 1
                }
                advance()
            }
            if (current() != quote) {
                problem = format("line {}: unterminated quoted literal", startLine)
                GrammarToken failed = makeToken(0, "", "", startOffset,
                    startSourceLine, startColumn, startLine)
                problemSpan = failed.span
                return(failed)
            }
            literal.append(source.slice(literalStart, offset))
            advance()
            return(makeToken(257, literal, "", startOffset, startSourceLine,
                             startColumn, startLine))
        }

        if (value == 91) {
            int64 startIndex = offset
            advance()
            while (current() >= 0 && current() != 93 && current() != 10) {
                if (current() == 92) {
                    advance()
                    if (current() < 0 || current() == 10) { break }
                }
                advance()
            }
            if (current() != 93) {
                problem = format("line {}: unterminated character class", startLine)
                GrammarToken failed = makeToken(0, "", "", startOffset,
                    startSourceLine, startColumn, startLine)
                problemSpan = failed.span
                return(failed)
            }
            advance()
            return(makeToken(258, source.slice(startIndex, offset), "", startOffset,
                             startSourceLine, startColumn, startLine))
        }

        if (value == 64) {
            advance()
            if (!letter(current())) {
                problem = format("line {}: expected directive name after @", startLine)
                GrammarToken failed = makeToken(0, "", "", startOffset,
                    startSourceLine, startColumn, startLine)
                problemSpan = failed.span
                return(failed)
            }
            int64 nameStart = offset
            while (letter(current()) || digit(current())) { advance() }
            String directiveName = source.slice(nameStart, offset)
            if (directiveName.equals("insert")) {
                GrammarToken token = insertion(startLine)
                if (token.span == null) {
                    token.span = span(startOffset, startSourceLine, startColumn)
                }
                if (!problem.equals("") && problemSpan == null) { problemSpan = token.span }
                return(token)
            }
            while (current() == 32 || current() == 9) { advance() }
            int64 contentStart = offset
            // Only @include interprets quotes; other directive payloads stay opaque.
            int64 includeQuote = 0
            while (current() >= 0 && (current() != 59 || includeQuote != 0)) {
                if (directiveName.equals("include")) {
                    if ((current() == 10 || current() == 13) && includeQuote != 0) { break }
                    if (current() == includeQuote) { includeQuote = 0 }
                    else {
                        if (includeQuote == 0 && (current() == 34 || current() == 39)) {
                            includeQuote = current()
                        }
                    }
                }
                advance()
            }
            if (current() != 59) {
                problem = format("line {}: directive @{} must end with ';'", startLine, directiveName)
                GrammarToken failed = makeToken(0, "", "", startOffset,
                    startSourceLine, startColumn, startLine)
                problemSpan = failed.span
                return(failed)
            }
            String content = source.slice(contentStart, offset).trim()
            advance()
            return(makeToken(259, content, directiveName, startOffset,
                             startSourceLine, startColumn, startLine))
        }

        if (value > 127) {
            problem = format("line {}: unsupported non-ASCII grammar syntax", startLine)
            GrammarToken failed = makeToken(0, "", "", startOffset,
                startSourceLine, startColumn, startLine)
            problemSpan = failed.span
            return(failed)
        }
        advance()
        return(makeToken(value, source.slice(offset - 1, offset), "", startOffset,
                         startSourceLine, startColumn, startLine))
    }
}

class LexerRule {
    String name
    LexerExpr expression
    int64 quote
    int64 line
    SourceSpan span

    LexerRule(String tokenName, int64 sourceLine) {
        name = tokenName
        expression = null
        quote = 0
        line = sourceLine
        span = null
    }
}

// Kinds: character class, reference, sequence, choice, repetition.
class LexerExpr {
    int64 kind
    String value
    list children
    list ranges
    int64 minimum
    int64 maximum
    int64 line
    SourceSpan span

    LexerExpr(int64 expressionKind, int64 sourceLine) {
        kind = expressionKind
        value = ""
        children = []
        ranges = []
        minimum = 1
        maximum = 1
        line = sourceLine
        span = null
    }
}

// Thompson states: byte transition, epsilon split, accepting state.
class LexerState {
    int64 kind
    list ranges
    int64 next
    int64 alternate

    LexerState(int64 stateKind, list characters, int64 target, int64 other) {
        kind = stateKind
        ranges = characters
        next = target
        alternate = other
    }
}

class ByteRange {
    int64 first
    int64 last

    ByteRange(int64 lower, int64 upper) {
        first = lower
        last = upper
    }
}

// Kinds: reference, literal, sequence, choice, repetition.
class RuleExpr {
    int64 kind
    String value
    list children
    int64 minimum
    int64 maximum
    int64 line
    SourceSpan span

    RuleExpr(int64 expressionKind, String text, int64 sourceLine) {
        kind = expressionKind
        value = text
        children = []
        minimum = 1
        maximum = 1
        line = sourceLine
        span = null
    }
}

class ParserRule {
    String name
    RuleExpr expression
    int64 line
    SourceSpan span

    ParserRule(String ruleName, int64 sourceLine) {
        name = ruleName
        line = sourceLine
        expression = null
        span = null
    }
}

class GrammarDirective {
    String name
    String content
    int64 line
    SourceSpan span

    GrammarDirective(String directiveName, String payload, int64 sourceLine) {
        name = directiveName
        content = payload
        line = sourceLine
        span = null
    }
}

class CodeInsertion {
    String target
    String boundary
    String content
    String source
    int64 line
    int64 location
    SourceSpan span
    SourceSpan targetSpan
    SourceSpan boundarySpan

    CodeInsertion(GrammarToken token, String path, int64 firstLine) {
        target = token.target
        boundary = token.boundary
        content = token.text
        source = path
        line = token.line - firstLine + 1
        location = token.line
        span = token.span
        targetSpan = token.targetSpan
        boundarySpan = token.boundarySpan
    }
}

class GrammarModel {
    list lexerRules
    list parserRules
    list directives
    list insertions
    SourceSpan diagnosticSpan
    SourceSpan relatedSpan
    GrammarDiagnostic diagnosticInfo
    Analysis analysis

    // Declarations only; GrammarAnalyzer attaches the shared analysis once.
    GrammarModel() {
        lexerRules = []
        parserRules = []
        directives = []
        insertions = []
        diagnosticSpan = null
        relatedSpan = null
        diagnosticInfo = null
        analysis = null
    }
}

class GrammarReader {
    list tokens
    int64 position
    int64 classPosition
    String problem
    GrammarToken inclusion
    String sourcePath
    int64 sourceFirstLine
    SourceSpan problemSpan
    GrammarDiagnostic diagnosticInfo

    GrammarReader(String source, int64 firstLine, String path, String shownPath,
                  SourceLocation parent) {
        tokens = []
        position = 0
        classPosition = 0
        problem = ""
        inclusion = null
        sourcePath = path
        sourceFirstLine = firstLine
        problemSpan = null
        diagnosticInfo = null
        GrammarScanner scanner(source, path, shownPath, firstLine, parent)
        while (true) {
            GrammarToken token = scanner.next()
            if (!scanner.problem.equals("")) {
                problem = scanner.problem
                problemSpan = scanner.problemSpan
                diagnosticInfo = GrammarDiagnostic(problem, problemSpan, null)
                return
            }
            tokens.append(token)
            if (token.kind == 0) { return }
        }
    }

    GrammarToken peek() {
        return(tokens[position] as GrammarToken)
    }

    GrammarToken take() {
        GrammarToken token = peek()
        if (position < tokens.length - 1) { position += 1 }
        return(token)
    }

    void fail(String message, SourceSpan span) {
        problem = message
        problemSpan = span
        diagnosticInfo = GrammarDiagnostic(message, span, null)
    }

    int64 classByte(GrammarToken token) {
        int64 byte = int64(token.text.byteAt(classPosition))
        classPosition += 1
        if (byte == 92) {
            byte = int64(token.text.byteAt(classPosition))
            classPosition += 1
            if (byte == 110) { return(10) }
            if (byte == 114) { return(13) }
            if (byte == 116) { return(9) }
            if (byte != 92 && byte != 93 && byte != 91 && byte != 45 && byte != 94) {
                fail(format("line {}: unsupported character-class escape", token.line), token.span)
            }
        }
        return(byte)
    }

    list classRanges(GrammarToken token) {
        String pattern = token.text
        list ranges = []
        classPosition = 1
        bool negated = int64(pattern.byteAt(1)) == 94
        if (negated) { classPosition += 1 }
        while (classPosition < pattern.length - 1 && problem.equals("")) {
            int64 first = classByte(token)
            int64 last = first
            if (classPosition + 1 < pattern.length - 1 && int64(pattern.byteAt(classPosition)) == 45) {
                classPosition += 1
                last = classByte(token)
                if (last < first) {
                    fail(format("line {}: descending character-class range", token.line), token.span)
                    return(ranges)
                }
            }
            if (first == 0 || last > 127) {
                fail(format("line {}: character classes must contain non-NUL ASCII bytes", token.line), token.span)
                return(ranges)
            }
            ranges.append(ByteRange(first, last))
        }
        if (ranges.length == 0) {
            fail(format("line {}: empty character class", token.line), token.span)
        }
        if (negated && problem.equals("")) {
            list complement = []
            int64 byte = 1
            int64 lower = -1
            while (byte <= 127) {
                bool included = false
                int64 r = 0
                while (r < ranges.length) {
                    ByteRange interval = ranges[r] as ByteRange
                    if (byte >= interval.first && byte <= interval.last) { included = true }
                    r += 1
                }
                if (!included && lower < 0) { lower = byte }
                if (included && lower >= 0) {
                    complement.append(ByteRange(lower, byte - 1))
                    lower = -1
                }
                byte += 1
            }
            if (lower >= 0) { complement.append(ByteRange(lower, 127)) }
            if (complement.length == 0) {
                fail(format("line {}: character class matches no ASCII bytes", token.line), token.span)
            }
            return(complement)
        }
        return(ranges)
    }

    LexerExpr lexerChoice(int64 line, int64 depth) {
        LexerExpr expression = LexerExpr(3, line)
        if (depth > 128) {
            fail(format("line {}: lexer group nesting limit exceeded (128)", line), peek().span)
            return(expression)
        }
        expression.children.append(lexerSequence(line, depth))
        while (peek().line == line && peek().kind == 124 && problem.equals("")) {
            take()
            expression.children.append(lexerSequence(line, depth))
        }
        if (expression.children.length > 0 &&
            (expression.children[0] as LexerExpr).span != null) {
            expression.span = (expression.children[0] as LexerExpr).span
            int64 child = expression.children.length - 1
            if (child >= 0 && (expression.children[child] as LexerExpr).span != null) {
                expression.span = SourceSpan(expression.span.first,
                    (expression.children[child] as LexerExpr).span.last)
            }
        }
        return(expression)
    }

    LexerExpr lexerSequence(int64 line, int64 depth) {
        LexerExpr expression = LexerExpr(2, line)
        while (peek().line == line && peek().kind != 0 && peek().kind != 124 &&
               peek().kind != 41 && peek().kind != 59 && problem.equals("")) {
            GrammarToken token = take()
            LexerExpr atom = null
            if (token.kind == 258) {
                atom = LexerExpr(0, token.line)
                atom.ranges = classRanges(token)
                atom.span = token.span
            }
            else {
                if (token.kind == 256) {
                    atom = LexerExpr(1, token.line)
                    atom.value = token.text
                    atom.span = token.span
                }
                else {
                    if (token.kind == 257) {
                        atom = LexerExpr(2, token.line)
                        atom.span = token.span
                        if (token.text.length == 0) {
                            fail(format("line {}: empty lexer literal is not supported", token.line), token.span)
                        }
                        int64 b = 0
                        while (b < token.text.length) {
                            int64 byte = int64(token.text.byteAt(b))
                            if (byte == 0 || byte > 127) {
                                fail(format("line {}: lexer literals must contain non-NUL ASCII bytes", token.line), token.span)
                            }
                            LexerExpr character = LexerExpr(0, token.line)
                            character.ranges.append(ByteRange(byte, byte))
                            character.span = token.span
                            atom.children.append(character)
                            b += 1
                        }
                    }
                    else {
                        if (token.kind == 40) {
                            atom = lexerChoice(line, depth + 1)
                            if (atom.span != null) {
                                atom.span = SourceSpan(token.span.first, atom.span.last)
                            }
                            if (problem.equals("") && (peek().line != line || peek().kind != 41)) {
                                fail(format("line {}: expected ')' after lexer group", token.line), peek().span)
                            }
                            if (peek().line == line && peek().kind == 41) {
                                GrammarToken closing = take()
                                atom.span = SourceSpan(token.span.first, closing.span.last)
                            }
                        }
                        else {
                            fail(format("line {}: unsupported lexer expression syntax (expected class, literal, reference, or group)",
                                token.line), token.span)
                            return(expression)
                        }
                    }
                }
            }
            if (peek().line == line && (peek().kind == 42 || peek().kind == 43 || peek().kind == 63)) {
                GrammarToken quantifier = take()
                LexerExpr repeated = LexerExpr(4, quantifier.line)
                repeated.children.append(atom)
                if (atom.span == null) { repeated.span = quantifier.span }
                else { repeated.span = SourceSpan(atom.span.first, quantifier.span.last) }
                if (quantifier.kind != 43) { repeated.minimum = 0 }
                if (quantifier.kind != 63) { repeated.maximum = -1 }
                atom = repeated
            }
            expression.children.append(atom)
        }
        if (expression.children.length == 0 && problem.equals("")) {
            fail(format("line {}: expected nonempty lexer expression", line), peek().span)
        }
        if (expression.children.length > 0 &&
            (expression.children[0] as LexerExpr).span != null &&
            (expression.children[expression.children.length - 1] as LexerExpr).span != null) {
            expression.span = SourceSpan(
                (expression.children[0] as LexerExpr).span.first,
                (expression.children[expression.children.length - 1] as LexerExpr).span.last)
        }
        return(expression)
    }

    RuleExpr choice() {
        RuleExpr expression = RuleExpr(3, "", peek().line)
        expression.children.append(sequence())
        while (peek().kind == 124 && problem.equals("")) {
            take()
            expression.children.append(sequence())
        }
        if (expression.children.length > 0 &&
            (expression.children[0] as RuleExpr).span != null &&
            (expression.children[expression.children.length - 1] as RuleExpr).span != null) {
            expression.span = SourceSpan(
                (expression.children[0] as RuleExpr).span.first,
                (expression.children[expression.children.length - 1] as RuleExpr).span.last)
        }
        return(expression)
    }

    RuleExpr sequence() {
        RuleExpr expression = RuleExpr(2, "", peek().line)
        while (peek().kind != 0 && peek().kind != 124 && peek().kind != 41 &&
               peek().kind != 59 && problem.equals("")) {
            GrammarToken token = take()
            RuleExpr atom = null
            if (token.kind == 256) {
                atom = RuleExpr(0, token.text, token.line)
                atom.span = token.span
            }
            else {
                if (token.kind == 257) {
                    atom = RuleExpr(1, token.text, token.line)
                    atom.span = token.span
                }
                else {
                    if (token.kind == 40) {
                        atom = choice()
                        GrammarToken closing = take()
                        if (closing.kind != 41) {
                            fail(format("line {}: expected ')' after parser group",
                                closing.line), closing.span)
                        }
                        atom.span = SourceSpan(token.span.first, closing.span.last)
                    }
                    else {
                        fail(format("line {}: unsupported parser-expression syntax", token.line), token.span)
                        return(expression)
                    }
                }
            }
            if (peek().kind == 42 || peek().kind == 43 || peek().kind == 63) {
                GrammarToken quantifier = take()
                RuleExpr repeated = RuleExpr(4, "", quantifier.line)
                repeated.children.append(atom)
                if (atom.span == null) { repeated.span = quantifier.span }
                else { repeated.span = SourceSpan(atom.span.first, quantifier.span.last) }
                if (quantifier.kind != 43) { repeated.minimum = 0 }
                if (quantifier.kind != 63) { repeated.maximum = -1 }
                atom = repeated
            }
            expression.children.append(atom)
        }
        if (expression.children.length > 0) {
            expression.span = SourceSpan(
                (expression.children[0] as RuleExpr).span.first,
                (expression.children[expression.children.length - 1] as RuleExpr).span.last)
        }
        return(expression)
    }

    void readInto(GrammarModel grammar) {
        inclusion = null
        if (!problem.equals("")) { return }
        while (peek().kind != 0 && problem.equals("")) {
            GrammarToken first = take()
            if (first.kind == 260) {
                grammar.insertions.append(CodeInsertion(first, sourcePath, sourceFirstLine))
                continue
            }
            if (first.kind == 259) {
                if (first.name.equals("include")) {
                    inclusion = first
                    return
                }
                else {
                    GrammarDirective directive(first.name, first.text, first.line)
                    directive.span = first.span
                    grammar.directives.append(directive)
                }
            }
            else {
                if (first.kind == 256) {
                    GrammarToken separator = take()
                    if (separator.kind == 61) {
                        LexerRule rule = LexerRule(first.text, first.line)
                        rule.expression = lexerChoice(first.line, 0)
                        rule.span = first.span
                        if (peek().line == first.line && peek().kind == 59) { take() }
                        if (peek().kind != 0 && peek().line == first.line && problem.equals("")) {
                            fail(format("line {}: unexpected token after lexer expression",
                                first.line), peek().span)
                        }
                        grammar.lexerRules.append(rule)
                    }
                    else {
                        if (separator.kind == 58) {
                            ParserRule rule(first.text, first.line)
                            rule.span = first.span
                            rule.expression = choice()
                            if (problem.equals("") && peek().kind != 59) {
                                fail(format("line {}: parser rule must end with ';'",
                                    first.line), peek().span)
                            }
                            if (problem.equals("")) { take() }
                            grammar.parserRules.append(rule)
                        }
                        else {
                            fail(format("line {}: expected '=' or ':' after declaration name",
                                first.line), separator.span)
                        }
                    }
                }
                else {
                    fail(format("line {}: expected lexer rule, parser rule, or @directive",
                        first.line), first.span)
                }
            }
        }
    }
}

class GrammarSource {
    String path
    String displayPath
    int64 firstLine
    int64 lineCount
    int64 includedAt
    bool active
    SourceLocation includedFrom

    GrammarSource(String filename, int64 first, int64 count, SourceLocation parent) {
        path = filename
        displayPath = filename
        firstLine = first
        lineCount = count
        includedAt = 0
        if (parent != null) { includedAt = parent.logicalLine }
        includedFrom = parent
        active = true
    }
}

// Line IDs remain unique across files while preserving line-local lexer parsing.
class GrammarSources {
    list paths
    list files
    int64 nextLine
    int64 depth
    String problem
    SourceSpan diagnosticSpan
    SourceSpan relatedSpan
    GrammarDiagnostic diagnosticInfo

    GrammarSources(list searchPaths) {
        paths = searchPaths
        files = []
        nextLine = 1
        depth = 0
        problem = ""
        diagnosticSpan = null
        relatedSpan = null
        diagnosticInfo = null
    }

    String location(int64 line) {
        int64 i = 0
        while (i < files.length) {
            GrammarSource file = files[i] as GrammarSource
            if (line >= file.firstLine && line < file.firstLine + file.lineCount) {
                return(format("{}: line {}", file.displayPath, line - file.firstLine + 1))
            }
            i += 1
        }
        return("grammar")
    }

    String diagnostic(String error) {
        if (diagnosticInfo == null && diagnosticSpan != null) {
            diagnosticInfo = GrammarDiagnostic(error, diagnosticSpan, relatedSpan)
        }
        if (diagnosticInfo != null) { return(renderDiagnostic(diagnosticInfo)) }
        if (!error.startsWith("line ")) { return(error) }
        int64 end = 5
        int64 line = 0
        while (end < error.length && int64(error.byteAt(end)) >= 48 && int64(error.byteAt(end)) <= 57) {
            line = line * 10 + int64(error.byteAt(end)) - 48
            end += 1
        }
        String result = format("{}{}", location(line), error.slice(end, error.length))
        while (line != 0) {
            int64 parent = 0
            int64 i = 0
            while (i < files.length) {
                GrammarSource file = files[i] as GrammarSource
                if (line >= file.firstLine && line < file.firstLine + file.lineCount) {
                    parent = file.includedAt
                    break
                }
                i += 1
            }
            if (parent != 0) { result.append(format("\n  included from {}", location(parent))) }
            line = parent
        }
        return(result)
    }

    String renderLocation(SourceLocation location, int64 endOffset) {
        return(format("{}:{}:{}: bytes {}-{}", location.displayPath, location.line,
                      location.column, location.offset, endOffset))
    }

    String renderDiagnostic(GrammarDiagnostic diagnostic) {
        if (diagnostic.span == null) { return(diagnostic.message) }
        SourceSpan span = diagnostic.span
        String result = format("{}: {}", renderLocation(span.first, span.last.offset),
                               diagnostic.message)
        if (diagnostic.related != null) {
            result.append(format("\n  related: {}", renderLocation(
                diagnostic.related.first, diagnostic.related.last.offset)))
        }
        SourceLocation parent = span.first.includedFrom
        int64 count = 0
        while (parent != null && count < 8) {
            result.append(format("\n  included from {}:{}:{}: byte {}",
                parent.displayPath, parent.line, parent.column, parent.offset))
            parent = parent.includedFrom
            count += 1
        }
        if (parent != null) { result.append("\n  included from ...") }
        return(result)
    }

    void load(String path, SourceSpan includeSpan, GrammarModel grammar) {
        Sys.FileSystem fs()
        String absolute = fs.absolutePath(path)
        int64 includedAt = 0
        SourceLocation includedFrom = null
        if (includeSpan != null) {
            includedAt = includeSpan.first.logicalLine
            includedFrom = includeSpan.first
        }
        int64 i = 0
        while (i < files.length) {
            GrammarSource previous = files[i] as GrammarSource
            if (previous.path.equals(absolute)) {
                if (previous.active) {
                    problem = format("line {}: include cycle involving {}", includedAt, absolute)
                    diagnosticSpan = includeSpan
                }
                return
            }
            i += 1
        }
        if (depth >= 128 || files.length >= 1024) {
            problem = format("line {}: grammar include limit exceeded (128 levels, 1024 files)", includedAt)
            diagnosticSpan = includeSpan
            return
        }
        if (!fs.isFile(absolute)) {
            problem = format("{}: expected a readable regular grammar file", absolute)
            if (includedAt != 0) { problem = format("line {}: {}", includedAt, problem) }
            diagnosticSpan = includeSpan
            return
        }
        String source = ""
        try {
            Sys.File file(absolute, "r")
            source = file.readAll()
            file.close()
            if (source.length != fs.fileSize(absolute)) {
                problem = format("{}: incomplete grammar read", absolute)
            }
        }
        except() as error { problem = format("{}: {}", absolute, error) }
        if (!problem.equals("")) {
            if (includedAt != 0) { problem = format("line {}: {}", includedAt, problem) }
            diagnosticSpan = includeSpan
            return
        }
        int64 count = 1
        i = 0
        bool previousCR = false
        while (i < source.length) {
            int64 value = int64(source.byteAt(i))
            if (value == 13) {
                count += 1
                previousCR = true
            }
            else {
                if (value == 10) {
                    if (!previousCR) { count += 1 }
                    previousCR = false
                }
                else { previousCR = false }
            }
            i += 1
        }
        GrammarSource file(absolute, nextLine, count, includedFrom)
        if (includedAt == 0) { file.displayPath = path }
        else { file.displayPath = absolute }
        files.append(file)
        nextLine += count + 1
        depth += 1
        GrammarReader reader(source, file.firstLine, absolute, file.displayPath, includedFrom)
        while (problem.equals("")) {
            reader.readInto(grammar)
            problem = reader.problem
            if (!problem.equals("")) {
                diagnosticSpan = reader.problemSpan
                diagnosticInfo = reader.diagnosticInfo
            }
            if (!problem.equals("") || reader.inclusion == null) { break }
            includeFile(reader.inclusion.text, absolute, reader.inclusion.span, grammar)
        }
        depth -= 1
        file.active = false
    }

    void includeFile(String payload, String parent, SourceSpan includeSpan,
                     GrammarModel grammar) {
        int64 line = includeSpan.first.logicalLine
        String name = payload.trim()
        bool valid = name.length > 0
        if (valid) {
            int64 quote = int64(name.byteAt(0))
            if (quote == 34 || quote == 39) {
                valid = name.length > 2 && int64(name.byteAt(name.length - 1)) == quote
                if (valid) {
                    name = name.slice(1, name.length - 1)
                    int64 i = 0
                    while (i < name.length) {
                        if (int64(name.byteAt(i)) == quote || int64(name.byteAt(i)) < 32) { valid = false }
                        i += 1
                    }
                }
            }
            else {
                int64 i = 0
                while (i < name.length) {
                    int64 byte = int64(name.byteAt(i))
                    if (byte <= 32 || byte == 34 || byte == 39) { valid = false }
                    i += 1
                }
            }
        }
        if (!valid) {
            problem = format("line {}: @include requires exactly one nonempty path (quote paths containing spaces)", line)
            diagnosticSpan = includeSpan
            return
        }
        Sys.FileSystem fs()
        if (name.startsWith("/")) {
            load(name, includeSpan, grammar)
            return
        }
        String candidate = fs.join(fs.dirname(parent), name)
        if (fs.exists(candidate) || fs.isDir(candidate)) {
            load(candidate, includeSpan, grammar)
            return
        }
        int64 i = 0
        while (i < paths.length) {
            candidate = fs.join(paths[i] as String, name)
            if (fs.exists(candidate) || fs.isDir(candidate)) {
                load(candidate, includeSpan, grammar)
                return
            }
            i += 1
        }
        problem = format("line {}: cannot find included grammar {}", line, name)
        diagnosticSpan = includeSpan
    }

    GrammarModel read(String path) {
        GrammarModel grammar()
        load(path, null, grammar)
        if (problem.equals("")) {
            GrammarAnalyzer analyzer(grammar)
            problem = analyzer.run()
            diagnosticSpan = grammar.diagnosticSpan
            relatedSpan = grammar.relatedSpan
            diagnosticInfo = grammar.diagnosticInfo
            if (!problem.equals("") && !problem.startsWith("line ")) {
                problem = format("{}: {}", path, problem)
            }
        }
        return(grammar)
    }
}

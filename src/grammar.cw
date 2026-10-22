class GrammarToken {
    int kind
    String text
    String name
    int line

    GrammarToken(int tokenKind, String tokenText, String tokenName, int tokenLine) {
        kind = tokenKind
        text = tokenText
        name = tokenName
        line = tokenLine
    }
}

class GrammarScanner {
    String source
    int offset
    int line
    String problem

    GrammarScanner(String text) {
        source = text
        offset = 0
        line = 1
        problem = ""
    }

    int current() {
        if (offset >= source.length) { return -1 }
        return int(source.byteAt(offset))
    }

    int following() {
        if (offset + 1 >= source.length) { return -1 }
        return int(source.byteAt(offset + 1))
    }

    void advance() {
        if (current() == 10) { line += 1 }
        offset += 1
    }

    bool letter(int value) {
        return (value >= 65 && value <= 90) || (value >= 97 && value <= 122) || value == 95
    }

    bool digit(int value) {
        return value >= 48 && value <= 57
    }

    void skipTrivia() {
        while (current() >= 0) {
            if (current() <= 32) {
                advance()
            }
            else {
                if (current() == 35 || (current() == 47 && following() == 47)) {
                    while (current() >= 0 && current() != 10) { advance() }
                }
                else {
                    if (current() == 47 && following() == 42) {
                        int startLine = line
                        advance()
                        advance()
                        while (current() >= 0 && !(current() == 42 && following() == 47)) { advance() }
                        if (current() < 0) {
                            problem = format("line {}: unterminated block comment", startLine)
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

    GrammarToken next() {
        skipTrivia()
        if (!problem.equals("")) { return GrammarToken(0, "", "", line) }
        int startLine = line
        int value = current()
        if (value < 0) { return GrammarToken(0, "", "", line) }

        if (letter(value)) {
            int startIndex = offset
            while (letter(current()) || digit(current())) { advance() }
            return GrammarToken(256, source.slice(startIndex, offset), "", startLine)
        }

        if (value == 34 || value == 39) {
            int quote = value
            advance()
            String literal = ""
            int literalStart = offset
            while (current() >= 0 && current() != quote && current() != 10) {
                if (current() == 92) {
                    literal.append(source.slice(literalStart, offset))
                    advance()
                    int escaped = current()
                    if (escaped == 110) { literal.append("\n") }
                    else {
                        if (escaped == 114) { literal.append("\r") }
                        else {
                            if (escaped == 116) { literal.append("\t") }
                            else {
                                if (escaped != 92 && escaped != 34 && escaped != 39) {
                                    problem = format("line {}: unsupported quoted escape", startLine)
                                    return GrammarToken(0, "", "", startLine)
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
                return GrammarToken(0, "", "", startLine)
            }
            literal.append(source.slice(literalStart, offset))
            advance()
            return GrammarToken(257, literal, "", startLine)
        }

        if (value == 91) {
            int startIndex = offset
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
                return GrammarToken(0, "", "", startLine)
            }
            advance()
            return GrammarToken(258, source.slice(startIndex, offset), "", startLine)
        }

        if (value == 64) {
            advance()
            if (!letter(current())) {
                problem = format("line {}: expected directive name after @", startLine)
                return GrammarToken(0, "", "", startLine)
            }
            int nameStart = offset
            while (letter(current()) || digit(current())) { advance() }
            String directiveName = source.slice(nameStart, offset)
            while (current() == 32 || current() == 9) { advance() }
            int contentStart = offset
            while (current() >= 0 && current() != 59) { advance() }
            if (current() != 59) {
                problem = format("line {}: directive @{} must end with ';'", startLine, directiveName)
                return GrammarToken(0, "", "", startLine)
            }
            String content = source.slice(contentStart, offset).trim()
            advance()
            return GrammarToken(259, content, directiveName, startLine)
        }

        if (value > 127) {
            problem = format("line {}: unsupported non-ASCII grammar syntax", startLine)
            return GrammarToken(0, "", "", startLine)
        }
        advance()
        return GrammarToken(value, source.slice(offset - 1, offset), "", startLine)
    }
}

class LexerRule {
    String name
    LexerExpr expression
    int state
    int entry
    bool skip
    int quote
    int line

    LexerRule(String tokenName, int sourceLine) {
        name = tokenName
        expression = null
        state = 0
        entry = -1
        skip = false
        quote = 0
        line = sourceLine
    }
}

// Kinds: character class, reference, sequence, choice, repetition.
class LexerExpr {
    int kind
    String value
    list children
    list ranges
    int minimum
    int maximum
    int line
    bool nullable

    LexerExpr(int expressionKind, int sourceLine) {
        kind = expressionKind
        value = ""
        children = []
        ranges = []
        minimum = 1
        maximum = 1
        line = sourceLine
        nullable = false
    }
}

// Thompson states: byte transition, epsilon split, accepting state.
class LexerState {
    int kind
    list ranges
    int next
    int alternate

    LexerState(int stateKind, list characters, int target, int other) {
        kind = stateKind
        ranges = characters
        next = target
        alternate = other
    }
}

class ByteRange {
    int first
    int last

    ByteRange(int lower, int upper) {
        first = lower
        last = upper
    }
}

// Kinds: reference, literal, sequence, choice, repetition.
class RuleExpr {
    int kind
    String value
    list children
    int minimum
    int maximum
    int line
    int index
    int required

    RuleExpr(int expressionKind, String text, int sourceLine) {
        kind = expressionKind
        value = text
        children = []
        minimum = 1
        maximum = 1
        line = sourceLine
        index = -1
        required = 0
    }
}

class ParserRule {
    String name
    RuleExpr expression
    bool nullable
    int line

    ParserRule(String ruleName, int sourceLine) {
        name = ruleName
        line = sourceLine
        nullable = false
        expression = null
    }
}

class GrammarDirective {
    String name
    String content
    int line

    GrammarDirective(String directiveName, String payload, int sourceLine) {
        name = directiveName
        content = payload
        line = sourceLine
    }
}

class GrammarModel {
    list lexerRules
    list parserRules
    list directives
    String keywordToken
    list reserved
    list lineComments
    list blockComments
    bool leftRecursive
    list lexerStates
    String lexerProblem

    GrammarModel() {
        lexerRules = []
        parserRules = []
        directives = []
        keywordToken = ""
        reserved = []
        lineComments = []
        blockComments = []
        leftRecursive = false
        lexerStates = []
        lexerProblem = ""
    }

    LexerRule findLexer(String name) {
        int i = 0
        while (i < lexerRules.length) {
            LexerRule rule = lexerRules[i] as LexerRule
            if (rule.name.equals(name)) { return rule }
            i += 1
        }
        return null
    }

    ParserRule findParser(String name) {
        int i = 0
        while (i < parserRules.length) {
            ParserRule rule = parserRules[i] as ParserRule
            if (rule.name.equals(name)) { return rule }
            i += 1
        }
        return null
    }

    bool isNullable(RuleExpr expression) {
        if (expression.kind == 0) {
            ParserRule rule = findParser(expression.value)
            return rule != null && rule.nullable
        }
        if (expression.kind == 1) { return false }
        if (expression.kind == 4) {
            return expression.minimum == 0 || isNullable(expression.children[0] as RuleExpr)
        }
        int i = 0
        while (i < expression.children.length) {
            bool childNullable = isNullable(expression.children[i] as RuleExpr)
            if (expression.kind == 2 && !childNullable) { return false }
            if (expression.kind == 3 && childNullable) { return true }
            i += 1
        }
        return expression.kind == 2
    }

    String validateExpression(RuleExpr expression) {
        if (expression.kind == 0 && findLexer(expression.value) == null) {
            if (findParser(expression.value) == null) {
                int first = int(expression.value.byteAt(0))
                if (first >= 65 && first <= 90) {
                    return format("line {}: unknown lexer token {}", expression.line, expression.value)
                }
                return format("line {}: unknown parser rule {}", expression.line, expression.value)
            }
        }
        if (expression.kind == 0) {
            LexerRule token = findLexer(expression.value)
            if (token != null && token.skip) {
                return format("line {}: skipped lexer token {} cannot be matched by a parser", expression.line, token.name)
            }
        }
        if (expression.kind == 1 && expression.value.length == 0) {
            return format("line {}: empty quoted terminals are not supported", expression.line)
        }
        if (expression.kind == 4 && isNullable(expression.children[0] as RuleExpr)) {
            return format("line {}: nullable repetition is not supported", expression.line)
        }
        int i = 0
        while (i < expression.children.length) {
            String error = validateExpression(expression.children[i] as RuleExpr)
            if (!error.equals("")) { return error }
            i += 1
        }
        return ""
    }

    bool hasName(list names, String name) {
        int i = 0
        while (i < names.length) {
            if ((names[i] as String).equals(name)) { return true }
            i += 1
        }
        return false
    }

    list directiveWords(String content) {
        list pieces = content.replace("\t", " ").replace("\n", " ").replace("\r", " ").split(" ")
        list words = []
        int i = 0
        while (i < pieces.length) {
            String word = pieces[i] as String
            if (word.length > 0) { words.append(word) }
            i += 1
        }
        return words
    }

    bool identifier(String name) {
        int i = 0
        while (i < name.length) {
            int byte = int(name.byteAt(i))
            bool letter = (byte >= 65 && byte <= 90) || (byte >= 97 && byte <= 122) || byte == 95
            if (!letter && (i == 0 || byte < 48 || byte > 57)) { return false }
            i += 1
        }
        return name.length > 0
    }

    String lexicalDirectives() {
        int i = 0
        while (i < directives.length) {
            GrammarDirective directive = directives[i] as GrammarDirective
            list words = directiveWords(directive.content)
            if (directive.name.equals("quoted")) {
                if (words.length != 2) {
                    return format("line {}: @quoted requires TOKEN single|double", directive.line)
                }
                String style = words[1] as String
                if (!style.equals("single") && !style.equals("double")) {
                    return format("line {}: @quoted requires single or double", directive.line)
                }
                LexerRule rule = LexerRule(words[0] as String, directive.line)
                rule.quote = 34
                if (style.equals("single")) { rule.quote = 39 }
                lexerRules.append(rule)
            }
            if (directive.name.equals("keywords")) {
                if (words.length != 1 || !keywordToken.equals("")) {
                    return format("line {}: @keywords requires one identifier token and may occur only once", directive.line)
                }
                keywordToken = words[0] as String
            }
            if (directive.name.equals("reserved")) {
                if (words.length == 0) {
                    return format("line {}: @reserved requires word names", directive.line)
                }
                int w = 0
                while (w < words.length) {
                    if (!identifier(words[w] as String)) {
                        return format("line {}: @reserved requires identifier spellings", directive.line)
                    }
                    reserved.append(words[w])
                    w += 1
                }
            }
            if (directive.name.equals("line_comment")) {
                if (words.length != 1 || (words[0] as String).length == 0) {
                    return format("line {}: @line_comment requires one nonempty marker", directive.line)
                }
                lineComments.append(words[0])
            }
            if (directive.name.equals("block_comment")) {
                if (words.length != 2) {
                    return format("line {}: @block_comment requires opening and closing markers", directive.line)
                }
                blockComments.append(words)
            }
            i += 1
        }
        if (!keywordToken.equals("")) {
            LexerRule token = findLexer(keywordToken)
            if (token == null || token.quote != 0) {
                return "@keywords must name a declared expression lexer token"
            }
        }
        if (reserved.length > 0 && keywordToken.equals("")) {
            return "@reserved requires @keywords to identify the identifier token"
        }
        return ""
    }

    String leftCycle(RuleExpr expression, list path, bool zeroOnly) {
        if (expression.kind == 0) {
            ParserRule target = findParser(expression.value)
            if (target != null) {
                if (hasName(path, target.name)) {
                    return format("line {}: left recursion through parser rule {} can repeat without consuming tokens; require a nonnullable prefix or suffix on every cycle", expression.line, target.name)
                }
                list next = []
                int p = 0
                while (p < path.length) {
                    next.append(path[p])
                    p += 1
                }
                next.append(target.name)
                return leftCycle(target.expression, next, zeroOnly)
            }
        }
        int i = 0
        while (i < expression.children.length) {
            RuleExpr child = expression.children[i] as RuleExpr
            bool nullableSuffix = true
            if (zeroOnly && expression.kind == 2) {
                int s = i + 1
                while (s < expression.children.length) {
                    if (!isNullable(expression.children[s] as RuleExpr)) { nullableSuffix = false }
                    s += 1
                }
            }
            // Only zero-context cycles admit infinitely many equal-span trees.
            if (!zeroOnly || nullableSuffix) {
                String error = leftCycle(child, path, zeroOnly)
                if (!error.equals("")) { return error }
            }
            if (expression.kind == 2 && !isNullable(child)) { return "" }
            i += 1
        }
        return ""
    }

    String resolveLexer(LexerExpr expression, int depth) {
        if (depth > 128) {
            return format("line {}: lexer expression nesting/reference limit exceeded (128)", expression.line)
        }
        if (expression.kind == 1) {
            LexerRule target = findLexer(expression.value)
            if (target == null) {
                return format("line {}: unknown lexer reference {}", expression.line, expression.value)
            }
            if (target.quote != 0) {
                return format("line {}: cannot compose @quoted token {}", expression.line, target.name)
            }
            if (target.state == 1) {
                return format("line {}: cyclic lexer reference {}", expression.line, target.name)
            }
            if (target.state == 0) {
                target.state = 1
                String error = resolveLexer(target.expression, depth + 1)
                if (!error.equals("")) { return error }
                target.state = 2
            }
            expression.nullable = target.expression.nullable
            return ""
        }
        bool nullable = expression.kind == 2 || (expression.kind == 4 && expression.minimum == 0)
        int c = 0
        while (c < expression.children.length) {
            LexerExpr child = expression.children[c] as LexerExpr
            String error = resolveLexer(child, depth + 1)
            if (!error.equals("")) { return error }
            if (expression.kind == 2 && !child.nullable) { nullable = false }
            if (expression.kind == 3 && child.nullable) { nullable = true }
            if (expression.kind == 4 && child.nullable) {
                return format("line {}: nullable lexer repetition is not supported", expression.line)
            }
            c += 1
        }
        expression.nullable = nullable
        return ""
    }

    int lexerState(int kind, list ranges, int next, int alternate, int line) {
        if (lexerStates.length >= 4096) {
            lexerProblem = format("line {}: expanded lexer state limit exceeded (4096)", line)
            return -1
        }
        int index = lexerStates.length
        lexerStates.append(LexerState(kind, ranges, next, alternate))
        return index
    }

    int compileLexer(LexerExpr expression, int next, int depth) {
        if (!lexerProblem.equals("")) { return -1 }
        if (depth > 128) {
            lexerProblem = format("line {}: expanded lexer nesting/reference limit exceeded (128)", expression.line)
            return -1
        }
        if (expression.kind == 0) {
            return lexerState(0, expression.ranges, next, -1, expression.line)
        }
        if (expression.kind == 1) {
            return compileLexer(findLexer(expression.value).expression, next, depth + 1)
        }
        if (expression.kind == 2) {
            int c = expression.children.length - 1
            while (c >= 0 && lexerProblem.equals("")) {
                next = compileLexer(expression.children[c] as LexerExpr, next, depth + 1)
                c -= 1
            }
            return next
        }
        if (expression.kind == 3) {
            int result = compileLexer(expression.children[0] as LexerExpr, next, depth + 1)
            int c = 1
            while (c < expression.children.length && lexerProblem.equals("")) {
                int branch = compileLexer(expression.children[c] as LexerExpr, next, depth + 1)
                result = lexerState(1, [], result, branch, expression.line)
                c += 1
            }
            return result
        }
        int split = lexerState(1, [], -1, next, expression.line)
        if (split < 0) { return -1 }
        int continuation = next
        if (expression.maximum < 0) { continuation = split }
        int child = compileLexer(expression.children[0] as LexerExpr, continuation, depth + 1)
        (lexerStates[split] as LexerState).next = child
        if (expression.minimum == 0) { return split }
        return child
    }

    String validate() {
        String directiveError = lexicalDirectives()
        if (!directiveError.equals("")) { return directiveError }
        if (lexerRules.length == 0) { return "grammar must declare a lexer rule" }
        if (parserRules.length == 0) { return "grammar must declare a parser rule" }
        int i = 0
        while (i < lexerRules.length) {
            LexerRule rule = lexerRules[i] as LexerRule
            int first = int(rule.name.byteAt(0))
            if (first < 65 || first > 90 || !identifier(rule.name)) {
                return format("line {}: lexer names must begin with an uppercase letter", rule.line)
            }
            if (findLexerCount(rule.name) > 1) {
                return format("line {}: duplicate lexer rule {}", rule.line, rule.name)
            }
            i += 1
        }
        i = 0
        while (i < lexerRules.length) {
            LexerRule rule = lexerRules[i] as LexerRule
            if (rule.quote == 0) {
                rule.state = 1
                String error = resolveLexer(rule.expression, 0)
                if (!error.equals("")) { return error }
                rule.state = 2
                if (rule.expression.nullable) {
                    return format("line {}: lexer rule {} can match empty input", rule.line, rule.name)
                }
                int accept = lexerState(2, [], -1, -1, rule.line)
                rule.entry = compileLexer(rule.expression, accept, 0)
                if (!lexerProblem.equals("")) { return lexerProblem }
            }
            i += 1
        }
        i = 0
        while (i < directives.length) {
            GrammarDirective directive = directives[i] as GrammarDirective
            if (directive.name.equals("skip")) {
                LexerRule token = findLexer(directive.content)
                if (token == null) {
                    return format("line {}: @skip requires a declared lexer token name", directive.line)
                }
                token.skip = true
            }
            i += 1
        }
        if (!keywordToken.equals("") && findLexer(keywordToken).skip) {
            return "@keywords cannot use a skipped lexer token"
        }
        i = 0
        while (i < parserRules.length) {
            ParserRule rule = parserRules[i] as ParserRule
            int first = int(rule.name.byteAt(0))
            if (first < 97 || first > 122) {
                return format("line {}: parser-rule names must begin with a lowercase letter", rule.line)
            }
            if (findParserCount(rule.name) > 1) {
                return format("line {}: duplicate parser rule {}", rule.line, rule.name)
            }
            i += 1
        }
        bool changed = true
        while (changed) {
            changed = false
            i = 0
            while (i < parserRules.length) {
                ParserRule rule = parserRules[i] as ParserRule
                if (!rule.nullable && isNullable(rule.expression)) {
                    rule.nullable = true
                    changed = true
                }
                i += 1
            }
        }
        i = 0
        while (i < parserRules.length) {
            ParserRule rule = parserRules[i] as ParserRule
            String error = validateExpression(rule.expression)
            if (!error.equals("")) { return error }
            list path = [rule.name]
            error = leftCycle(rule.expression, path, true)
            if (!error.equals("")) { return error }
            if (!leftCycle(rule.expression, path, false).equals("")) { leftRecursive = true }
            i += 1
        }
        return ""
    }

    int findLexerCount(String name) {
        int count = 0
        int i = 0
        while (i < lexerRules.length) {
            if ((lexerRules[i] as LexerRule).name.equals(name)) { count += 1 }
            i += 1
        }
        return count
    }

    int findParserCount(String name) {
        int count = 0
        int i = 0
        while (i < parserRules.length) {
            if ((parserRules[i] as ParserRule).name.equals(name)) { count += 1 }
            i += 1
        }
        return count
    }
}

class GrammarReader {
    list tokens
    int position
    int classPosition
    String problem

    GrammarReader(String source) {
        tokens = []
        position = 0
        classPosition = 0
        problem = ""
        GrammarScanner scanner(source)
        while (true) {
            GrammarToken token = scanner.next()
            if (!scanner.problem.equals("")) {
                problem = scanner.problem
                return
            }
            tokens.append(token)
            if (token.kind == 0) { return }
        }
    }

    GrammarToken peek() {
        return tokens[position] as GrammarToken
    }

    GrammarToken take() {
        GrammarToken token = peek()
        if (position < tokens.length - 1) { position += 1 }
        return token
    }

    String expect(int kind, String description) {
        GrammarToken token = take()
        if (token.kind != kind) {
            problem = format("line {}: expected {}", token.line, description)
        }
        return token.text
    }

    int classByte(GrammarToken token) {
        int byte = int(token.text.byteAt(classPosition))
        classPosition += 1
        if (byte == 92) {
            byte = int(token.text.byteAt(classPosition))
            classPosition += 1
            if (byte == 110) { return 10 }
            if (byte == 114) { return 13 }
            if (byte == 116) { return 9 }
            if (byte != 92 && byte != 93 && byte != 91 && byte != 45 && byte != 94) {
                problem = format("line {}: unsupported character-class escape", token.line)
            }
        }
        return byte
    }

    list classRanges(GrammarToken token) {
        String pattern = token.text
        list ranges = []
        classPosition = 1
        bool negated = int(pattern.byteAt(1)) == 94
        if (negated) { classPosition += 1 }
        while (classPosition < pattern.length - 1 && problem.equals("")) {
            int first = classByte(token)
            int last = first
            if (classPosition + 1 < pattern.length - 1 && int(pattern.byteAt(classPosition)) == 45) {
                classPosition += 1
                last = classByte(token)
                if (last < first) {
                    problem = format("line {}: descending character-class range", token.line)
                    return ranges
                }
            }
            if (first == 0 || last > 127) {
                problem = format("line {}: character classes must contain non-NUL ASCII bytes", token.line)
                return ranges
            }
            ranges.append(ByteRange(first, last))
        }
        if (ranges.length == 0) {
            problem = format("line {}: empty character class", token.line)
        }
        if (negated && problem.equals("")) {
            list complement = []
            int byte = 1
            int lower = -1
            while (byte <= 127) {
                bool included = false
                int r = 0
                while (r < ranges.length) {
                    ByteRange range = ranges[r] as ByteRange
                    if (byte >= range.first && byte <= range.last) { included = true }
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
                problem = format("line {}: character class matches no ASCII bytes", token.line)
            }
            return complement
        }
        return ranges
    }

    LexerExpr lexerChoice(int line, int depth) {
        LexerExpr expression = LexerExpr(3, line)
        if (depth > 128) {
            problem = format("line {}: lexer group nesting limit exceeded (128)", line)
            return expression
        }
        expression.children.append(lexerSequence(line, depth))
        while (peek().line == line && peek().kind == 124 && problem.equals("")) {
            take()
            expression.children.append(lexerSequence(line, depth))
        }
        return expression
    }

    LexerExpr lexerSequence(int line, int depth) {
        LexerExpr expression = LexerExpr(2, line)
        while (peek().line == line && peek().kind != 0 && peek().kind != 124 &&
               peek().kind != 41 && peek().kind != 59 && problem.equals("")) {
            GrammarToken token = take()
            LexerExpr atom = null
            if (token.kind == 258) {
                atom = LexerExpr(0, token.line)
                atom.ranges = classRanges(token)
            }
            else {
                if (token.kind == 256) {
                    atom = LexerExpr(1, token.line)
                    atom.value = token.text
                }
                else {
                    if (token.kind == 257) {
                        atom = LexerExpr(2, token.line)
                        if (token.text.length == 0) {
                            problem = format("line {}: empty lexer literal is not supported", token.line)
                        }
                        int b = 0
                        while (b < token.text.length) {
                            int byte = int(token.text.byteAt(b))
                            if (byte == 0 || byte > 127) {
                                problem = format("line {}: lexer literals must contain non-NUL ASCII bytes", token.line)
                            }
                            LexerExpr character = LexerExpr(0, token.line)
                            character.ranges.append(ByteRange(byte, byte))
                            atom.children.append(character)
                            b += 1
                        }
                    }
                    else {
                        if (token.kind == 40) {
                            atom = lexerChoice(line, depth + 1)
                            if (problem.equals("") && (peek().line != line || peek().kind != 41)) {
                                problem = format("line {}: expected ')' after lexer group", token.line)
                            }
                            if (problem.equals("")) { take() }
                        }
                        else {
                            problem = format("line {}: unsupported lexer expression syntax (expected class, literal, reference, or group)", token.line)
                            return expression
                        }
                    }
                }
            }
            if (peek().line == line && (peek().kind == 42 || peek().kind == 43 || peek().kind == 63)) {
                GrammarToken quantifier = take()
                LexerExpr repeated = LexerExpr(4, quantifier.line)
                repeated.children.append(atom)
                if (quantifier.kind != 43) { repeated.minimum = 0 }
                if (quantifier.kind != 63) { repeated.maximum = -1 }
                atom = repeated
            }
            expression.children.append(atom)
        }
        if (expression.children.length == 0 && problem.equals("")) {
            problem = format("line {}: expected nonempty lexer expression", line)
        }
        return expression
    }

    RuleExpr choice() {
        RuleExpr expression = RuleExpr(3, "", peek().line)
        expression.children.append(sequence())
        while (peek().kind == 124 && problem.equals("")) {
            take()
            expression.children.append(sequence())
        }
        return expression
    }

    RuleExpr sequence() {
        RuleExpr expression = RuleExpr(2, "", peek().line)
        while (peek().kind != 0 && peek().kind != 124 && peek().kind != 41 &&
               peek().kind != 59 && problem.equals("")) {
            GrammarToken token = take()
            RuleExpr atom = null
            if (token.kind == 256) { atom = RuleExpr(0, token.text, token.line) }
            else {
                if (token.kind == 257) { atom = RuleExpr(1, token.text, token.line) }
                else {
                    if (token.kind == 40) {
                        atom = choice()
                        expect(41, "')' after parser group")
                    }
                    else {
                        problem = format("line {}: unsupported parser-expression syntax", token.line)
                        return expression
                    }
                }
            }
            if (peek().kind == 42 || peek().kind == 43 || peek().kind == 63) {
                GrammarToken quantifier = take()
                RuleExpr repeated = RuleExpr(4, "", quantifier.line)
                repeated.children.append(atom)
                if (quantifier.kind != 43) { repeated.minimum = 0 }
                if (quantifier.kind != 63) { repeated.maximum = -1 }
                atom = repeated
            }
            expression.children.append(atom)
        }
        return expression
    }

    GrammarModel read() {
        GrammarModel grammar()
        if (!problem.equals("")) { return grammar }
        while (peek().kind != 0 && problem.equals("")) {
            GrammarToken first = take()
            if (first.kind == 259) {
                grammar.directives.append(GrammarDirective(first.name, first.text, first.line))
            }
            else {
                if (first.kind == 256) {
                    GrammarToken separator = take()
                    if (separator.kind == 61) {
                        LexerRule rule = LexerRule(first.text, first.line)
                        rule.expression = lexerChoice(first.line, 0)
                        if (peek().line == first.line && peek().kind == 59) { take() }
                        if (peek().kind != 0 && peek().line == first.line && problem.equals("")) {
                            problem = format("line {}: unexpected token after lexer expression", first.line)
                        }
                        grammar.lexerRules.append(rule)
                    }
                    else {
                        if (separator.kind == 58) {
                            ParserRule rule(first.text, first.line)
                            rule.expression = choice()
                            if (problem.equals("") && peek().kind != 59) {
                                problem = format("line {}: parser rule must end with ';'", first.line)
                            }
                            if (problem.equals("")) { take() }
                            grammar.parserRules.append(rule)
                        }
                        else {
                            problem = format("line {}: expected '=' or ':' after declaration name", first.line)
                        }
                    }
                }
                else {
                    problem = format("line {}: expected lexer rule, parser rule, or @directive", first.line)
                }
            }
        }
        if (!problem.equals("")) { return grammar }
        problem = grammar.validate()
        return grammar
    }
}

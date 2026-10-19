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
            int startIndex = offset
            while (current() >= 0 && current() != quote && current() != 10) {
                if (current() == 92) {
                    problem = format("line {}: escapes are not supported in this prototype", startLine)
                    return GrammarToken(0, "", "", startLine)
                }
                advance()
            }
            if (current() != quote) {
                problem = format("line {}: unterminated quoted literal", startLine)
                return GrammarToken(0, "", "", startLine)
            }
            String literal = source.slice(startIndex, offset)
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

        advance()
        return GrammarToken(value, source.slice(offset - 1, offset), "", startLine)
    }
}

class LexerRule {
    String name
    list parts
    bool skip
    int line

    LexerRule(String tokenName, int sourceLine) {
        name = tokenName
        parts = []
        skip = false
        line = sourceLine
    }
}

class RegexPart {
    list ranges
    int minimum
    int maximum

    RegexPart(list characters, int lower, int upper) {
        ranges = characters
        minimum = lower
        maximum = upper
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

    RuleExpr(int expressionKind, String text, int sourceLine) {
        kind = expressionKind
        value = text
        children = []
        minimum = 1
        maximum = 1
        line = sourceLine
        index = -1
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

    GrammarModel() {
        lexerRules = []
        parserRules = []
        directives = []
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

    String leftCycle(RuleExpr expression, list path) {
        if (expression.kind == 0) {
            ParserRule target = findParser(expression.value)
            if (target != null) {
                if (hasName(path, target.name)) {
                    return format("line {}: left recursion through parser rule {}", expression.line, target.name)
                }
                list next = []
                int p = 0
                while (p < path.length) {
                    next.append(path[p])
                    p += 1
                }
                next.append(target.name)
                return leftCycle(target.expression, next)
            }
        }
        int i = 0
        while (i < expression.children.length) {
            RuleExpr child = expression.children[i] as RuleExpr
            String error = leftCycle(child, path)
            if (!error.equals("")) { return error }
            if (expression.kind == 2 && !isNullable(child)) { return "" }
            i += 1
        }
        return ""
    }

    String validate() {
        if (lexerRules.length == 0) { return "grammar must declare a lexer rule" }
        if (parserRules.length == 0) { return "grammar must declare a parser rule" }
        int i = 0
        while (i < lexerRules.length) {
            LexerRule rule = lexerRules[i] as LexerRule
            int first = int(rule.name.byteAt(0))
            if (first < 65 || first > 90) {
                return format("line {}: lexer names must begin with an uppercase letter", rule.line)
            }
            if (findLexerCount(rule.name) > 1) {
                return format("line {}: duplicate lexer rule {}", rule.line, rule.name)
            }
            bool nullable = true
            int p = 0
            while (p < rule.parts.length) {
                RegexPart part = rule.parts[p] as RegexPart
                if (part.minimum > 0) { nullable = false }
                p += 1
            }
            if (nullable) {
                return format("line {}: lexer rule {} can match empty input", rule.line, rule.name)
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
            error = leftCycle(rule.expression, path)
            if (!error.equals("")) { return error }
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
    String problem

    GrammarReader(String source) {
        tokens = []
        position = 0
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

    list classRanges(GrammarToken token) {
        String pattern = token.text
        list ranges = []
        int i = 1
        while (i < pattern.length - 1) {
            int first = int(pattern.byteAt(i))
            if (first == 94 && i == 1) {
                problem = format("line {}: negated character classes are not supported", token.line)
                return ranges
            }
            if (first == 92) {
                i += 1
                first = int(pattern.byteAt(i))
                if (first == 110) { first = 10 }
                else {
                    if (first == 114) { first = 13 }
                    else {
                        if (first == 116) { first = 9 }
                        else {
                            if (first != 92 && first != 93 && first != 45) {
                                problem = format("line {}: unsupported character-class escape", token.line)
                                return ranges
                            }
                        }
                    }
                }
            }
            i += 1
            int last = first
            if (i + 1 < pattern.length - 1 && int(pattern.byteAt(i)) == 45) {
                i += 1
                last = int(pattern.byteAt(i))
                if (last == 92) {
                    problem = format("line {}: escaped range endpoints are not supported", token.line)
                    return ranges
                }
                i += 1
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
        return ranges
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
                        while (peek().kind == 258 && peek().line == first.line && problem.equals("")) {
                            GrammarToken tokenClass = take()
                            list ranges = classRanges(tokenClass)
                            int minimum = 1
                            int maximum = 1
                            if (peek().line == first.line &&
                                (peek().kind == 43 || peek().kind == 42 || peek().kind == 63)) {
                                int quantifier = take().kind
                                if (quantifier != 43) { minimum = 0 }
                                if (quantifier != 63) { maximum = -1 }
                            }
                            rule.parts.append(RegexPart(ranges, minimum, maximum))
                        }
                        if (rule.parts.length == 0) {
                            problem = format("line {}: expected lexer character class", first.line)
                        }
                        if (peek().kind != 0 && peek().line == first.line) {
                            problem = format("line {}: unsupported lexer regex syntax", first.line)
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

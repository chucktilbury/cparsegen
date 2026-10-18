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
            while (current() >= 0 && current() != 93 && current() != 10) { advance() }
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
    String characterClass
    bool repeat
    int line

    LexerRule(String tokenName, String tokenClass, bool repeated, int sourceLine) {
        name = tokenName
        characterClass = tokenClass
        repeat = repeated
        line = sourceLine
    }
}

class ParseAtom {
    String name
    String literal
    bool isLiteral
    int line

    ParseAtom(String tokenName, String tokenLiteral, bool literalValue, int sourceLine) {
        name = tokenName
        literal = tokenLiteral
        isLiteral = literalValue
        line = sourceLine
    }
}

class ParseAlternative {
    list atoms

    ParseAlternative() {
        atoms = []
    }
}

class ParserRule {
    String name
    list alternatives
    int line

    ParserRule(String ruleName, int sourceLine) {
        name = ruleName
        line = sourceLine
        alternatives = []
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
            if (!rule.characterClass.equals("[0-9]")) {
                return format("line {}: prototype supports only [0-9] lexer classes ({})", rule.line, rule.name)
            }
            i += 1
        }
        if (lexerRules.length > 1) {
            return "prototype accepts one lexer rule; lexer-rule composition is deferred"
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
            int a = 0
            while (a < rule.alternatives.length) {
                ParseAlternative alternative = rule.alternatives[a] as ParseAlternative
                int b = 0
                if (alternative.atoms.length == 0) {
                    return format("line {}: empty alternatives are not supported", rule.line)
                }
                while (b < alternative.atoms.length) {
                    ParseAtom atom = alternative.atoms[b] as ParseAtom
                    if (!atom.isLiteral && findLexer(atom.name) == null) {
                        if (findParser(atom.name) != null) {
                            return format("line {}: parser-rule references are deferred in this prototype ({})",
                                atom.line, atom.name)
                        }
                        return format("line {}: unknown lexer token {}", atom.line, atom.name)
                    }
                    if (atom.isLiteral && atom.literal.length == 0) {
                        return format("line {}: empty quoted terminals are not supported", atom.line)
                    }
                    b += 1
                }
                a += 1
            }
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
                    String pattern = expect(258, "a [0-9] character class")
                    bool repeat = false
                    if (peek().kind == 43) {
                        take()
                        repeat = true
                    }
                    else {
                        if (peek().kind == 42 || peek().kind == 63) {
                            problem = format("line {}: only '+' repetition is supported in lexer regexes", first.line)
                        }
                    }
                    if (peek().kind != 0 && peek().line == first.line && peek().kind != 35) {
                        problem = format("line {}: unsupported lexer regex syntax", first.line)
                    }
                    grammar.lexerRules.append(LexerRule(first.text, pattern, repeat, first.line))
                    }
                    else {
                        if (separator.kind == 58) {
                    ParserRule rule(first.text, first.line)
                    ParseAlternative alternative()
                    bool sawAtom = false
                    bool ended = false
                    while (peek().kind != 0 && problem.equals("")) {
                        GrammarToken atomToken = take()
                        if (atomToken.kind == 59) {
                            if (sawAtom) { rule.alternatives.append(alternative) }
                            else { problem = format("line {}: empty parser alternative", first.line) }
                            ended = true
                            break
                        }
                        if (atomToken.kind == 124) {
                            if (!sawAtom) {
                                problem = format("line {}: empty parser alternative", atomToken.line)
                            }
                            else {
                                rule.alternatives.append(alternative)
                                alternative = ParseAlternative()
                                sawAtom = false
                            }
                        }
                        else {
                            if (atomToken.kind == 256) {
                                alternative.atoms.append(ParseAtom(atomToken.text, "", false, atomToken.line))
                                sawAtom = true
                            }
                            else {
                                if (atomToken.kind == 257) {
                                    alternative.atoms.append(ParseAtom("", atomToken.text, true, atomToken.line))
                                    sawAtom = true
                                }
                                else {
                                    problem = format("line {}: unsupported parser-expression syntax", atomToken.line)
                                }
                            }
                        }
                    }
                    if (problem.equals("") && !ended) {
                        problem = format("line {}: parser rule must end with ';'", first.line)
                    }
                    if (rule.alternatives.length > 0) { grammar.parserRules.append(rule) }
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

class GrammarEmitter {
    GrammarModel grammar
    list literals
    String problem

    GrammarEmitter(GrammarModel model) {
        grammar = model
        literals = []
        problem = ""
        collectLiterals()
    }

    void collectLiterals() {
        int r = 0
        while (r < grammar.parserRules.length) {
            ParserRule rule = grammar.parserRules[r] as ParserRule
            int a = 0
            while (a < rule.alternatives.length) {
                ParseAlternative alternative = rule.alternatives[a] as ParseAlternative
                int i = 0
                while (i < alternative.atoms.length) {
                    ParseAtom atom = alternative.atoms[i] as ParseAtom
                    if (atom.isLiteral && literalIndex(atom.literal) < 0) {
                        literals.append(atom.literal)
                    }
                    i += 1
                }
                a += 1
            }
            r += 1
        }
    }

    int literalIndex(String value) {
        int i = 0
        while (i < literals.length) {
            if ((literals[i] as String).equals(value)) { return i }
            i += 1
        }
        return -1
    }

    String quoted(String value) {
        String result = "\""
        int i = 0
        while (i < value.length) {
            int byte = int(value.byteAt(i))
            if (byte == 34 || byte == 92) { result.append("\\") }
            if (byte == 10) {
                result.append("\\n")
            }
            else {
                if (byte == 13) {
                    result.append("\\r")
                }
                else {
                    if (byte == 9) {
                        result.append("\\t")
                    }
                    else {
                        result.append(value.slice(i, i + 1))
                    }
                }
            }
            i += 1
        }
        result.append("\"")
        return result
    }

    String literalKind(int index) {
        return format("LIT_{}", index)
    }

    String emitScanner(String output) {
        output.append("import system as Sys\n\n")
        output.append("class LexToken {\n")
        output.append("    String kind\n    String text\n")
        output.append("    LexToken(String tokenKind, String tokenText) {\n        kind = tokenKind\n        text = tokenText\n    }\n")
        output.append("}\n\n")
        output.append("class AstNode {\n")
        output.append("    String name\n    String text\n    list children\n")
        output.append("    AstNode(String nodeName, String nodeText) {\n")
        output.append("        name = nodeName\n        text = nodeText\n        children = []\n    }\n")
        output.append("    void add(AstNode child) { children.append(child) }\n")
        output.append("    String render() {\n")
        output.append("        String result = name\n")
        output.append("        result.append(\"(\")\n")
        output.append("        if (children.length == 0) { result.append(text) }\n")
        output.append("        int i = 0\n")
        output.append("        while (i < children.length) {\n")
        output.append("            if (i > 0) { result.append(\", \") }\n")
        output.append("            result.append((children[i] as AstNode).render())\n")
        output.append("            i += 1\n")
        output.append("        }\n")
        output.append("        result.append(\")\")\n")
        output.append("        return result\n")
        output.append("    }\n}\n\n")
        output.append("class InputScanner {\n")
        output.append("    String input\n    list tokens\n    int errorOffset\n")
        output.append("    InputScanner(String text) {\n        input = text\n        tokens = []\n        errorOffset = -1\n    }\n")
        output.append("    bool scan() {\n")
        output.append("        int i = 0\n")
        output.append("        while (i < input.length) {\n")
        output.append("            int bestLength = 0\n            String bestKind = \"\"\n")
        int r = 0
        while (r < grammar.lexerRules.length) {
            LexerRule rule = grammar.lexerRules[r] as LexerRule
            output.append("            if (int(input.byteAt(i)) >= 48 && int(input.byteAt(i)) <= 57) {\n")
            output.append("                int end")
            output.append(format("{} = i + 1\n", r))
            if (rule.repeat) {
                output.append(format("                while (end{} < input.length && int(input.byteAt(end{})) >= 48 && int(input.byteAt(end{})) <= 57) {{ end{} += 1 }}\n",
                    r, r, r, r))
            }
            output.append(format("                if (end{} - i > bestLength) {{\n                    bestLength = end{} - i\n                    bestKind = {}\n                }}\n",
                r, r, quoted(rule.name)))
            output.append("            }\n")
            r += 1
        }
        int lit = 0
        while (lit < literals.length) {
            String value = literals[lit] as String
            output.append(format("            if (input.length - i >= {} && input.slice(i, i + {}).equals({}) && {} > bestLength) {{\n                bestLength = {}\n                bestKind = {}\n            }}\n",
                value.length, value.length, quoted(value), value.length, value.length, quoted(literalKind(lit))))
            lit += 1
        }
        output.append("            if (bestLength == 0) {\n                errorOffset = i\n                return false\n            }\n")
        output.append("            tokens.append(LexToken(bestKind, input.slice(i, i + bestLength)))\n")
        output.append("            i += bestLength\n")
        output.append("        }\n        return true\n    }\n}\n\n")
        return output
    }

    String emitParser(String output) {
        output.append("class GeneratedParser {\n")
        output.append("    list tokens\n    int position\n")
        output.append("    GeneratedParser(list inputTokens) {\n        tokens = inputTokens\n        position = 0\n    }\n")
        int r = 0
        while (r < grammar.parserRules.length) {
            ParserRule rule = grammar.parserRules[r] as ParserRule
            output.append(format("    AstNode parse_{}() {{\n", rule.name))
            output.append("        int startIndex = position\n        AstNode best = null\n        int bestLength = -1\n        int bestEnd = startIndex\n")
            int a = 0
            while (a < rule.alternatives.length) {
                ParseAlternative alternative = rule.alternatives[a] as ParseAlternative
                output.append("        {\n            position = startIndex\n")
                output.append(format("            AstNode candidate = AstNode({}, \"\")\n",
                    quoted(rule.name)))
                output.append("            bool matched = true\n")
                int i = 0
                while (i < alternative.atoms.length) {
                    ParseAtom atom = alternative.atoms[i] as ParseAtom
                    String expected = atom.name
                    if (atom.isLiteral) { expected = literalKind(literalIndex(atom.literal)) }
                    output.append("            if (matched) {\n")
                    output.append("                if (position >= tokens.length) { matched = false }\n")
                    output.append("                else {\n")
                    output.append("                    LexToken token = tokens[position] as LexToken\n")
                    output.append(format("                    if (!token.kind.equals({})) {{ matched = false }}\n",
                        quoted(expected)))
                    output.append("                    else {\n")
                    output.append("                        candidate.add(AstNode(token.kind, token.text))\n")
                    output.append("                        position += 1\n")
                    output.append("                    }\n                }\n            }\n")
                    i += 1
                }
                output.append("            if (matched) {\n")
                output.append("                int length = 0\n                int cursor = startIndex\n")
                output.append("                while (cursor < position) {\n")
                output.append("                    LexToken consumed = tokens[cursor] as LexToken\n")
                output.append("                    length += consumed.text.length\n                    cursor += 1\n                }\n")
                output.append("                if (best == null || length < bestLength) {\n")
                output.append("                    best = candidate\n                    bestLength = length\n                    bestEnd = position\n")
                output.append("                }\n")
                output.append("            }\n        }\n")
                a += 1
            }
            output.append("        position = startIndex\n")
            output.append("        if (best == null) { return null }\n")
            output.append("        position = bestEnd\n        return best\n")
            output.append("    }\n")
            r += 1
        }
        output.append("}\n\n")
        output.append("class GeneratedVisitor {\n")
        output.append("    void visit(AstNode node) {\n")
        int v = 0
        while (v < grammar.parserRules.length) {
            ParserRule rule = grammar.parserRules[v] as ParserRule
            output.append(format("        if (node.name.equals({})) {{\n", quoted(rule.name)))
            output.append(format("            pre_{}(node)\n", rule.name))
            output.append("            int i = 0\n            while (i < node.children.length) {\n")
            output.append("                visit(node.children[i] as AstNode)\n                i += 1\n            }\n")
            output.append(format("            post_{}(node)\n            return\n        }}\n", rule.name))
            v += 1
        }
        output.append("    }\n")
        v = 0
        while (v < grammar.parserRules.length) {
            ParserRule rule = grammar.parserRules[v] as ParserRule
            output.append(format("    void pre_{}(AstNode node) {{}}\n", rule.name))
            output.append(format("    void post_{}(AstNode node) {{}}\n", rule.name))
            v += 1
        }
        output.append("}\n\n")
        return output
    }

    String emitProgram() {
        String output = ""
        emitScanner(output)
        emitParser(output)
        output.append("start {\n")
        output.append("    Sys.Process process()\n")
        output.append("    if (process.argc() != 2) {\n        print(\"usage: generated-parser INPUT\\n\")\n        process.exit(2)\n    }\n")
        output.append("    String input = Sys.File(process.arg(1), \"r\").readAll()\n")
        output.append("    InputScanner scanner(input)\n")
        output.append("    if (!scanner.scan()) {\n        print(format(\"lex error at byte {}\\n\", scanner.errorOffset))\n        process.exit(1)\n    }\n")
        ParserRule startRule = grammar.parserRules[0] as ParserRule
        output.append("    GeneratedParser parser(scanner.tokens)\n")
        output.append(format("    AstNode root = parser.parse_{}()\n", startRule.name))
        output.append("    if (root == null) {\n        print(\"parse error\\n\")\n        process.exit(1)\n    }\n")
        output.append("    print(format(\"{}\\n\", root.render()))\n")
        output.append("}\n")
        return output
    }

    String emitDot() {
        String output = "digraph grammar {\n    rankdir=LR;\n"
        int i = 0
        while (i < grammar.parserRules.length) {
            ParserRule rule = grammar.parserRules[i] as ParserRule
            output.append(format("    {} [shape=box];\n", rule.name))
            i += 1
        }
        i = 0
        while (i < grammar.lexerRules.length) {
            LexerRule rule = grammar.lexerRules[i] as LexerRule
            output.append(format("    {} [shape=ellipse];\n", rule.name))
            i += 1
        }
        int r = 0
        while (r < grammar.parserRules.length) {
            ParserRule rule = grammar.parserRules[r] as ParserRule
            int a = 0
            while (a < rule.alternatives.length) {
                ParseAlternative alternative = rule.alternatives[a] as ParseAlternative
                int n = 0
                while (n < alternative.atoms.length) {
                    ParseAtom atom = alternative.atoms[n] as ParseAtom
                    if (atom.isLiteral) {
                        int index = literalIndex(atom.literal)
                        output.append(format("    literal{} [shape=diamond,label={}];\n",
                            index, quoted(atom.literal)))
                        output.append(format("    {} -> literal{} [label=\"alt {}\"];\n",
                            rule.name, index, a + 1))
                    }
                    else {
                        output.append(format("    {} -> {} [label=\"alt {}\"];\n",
                            rule.name, atom.name, a + 1))
                    }
                    n += 1
                }
                a += 1
            }
            r += 1
        }
        output.append("}\n")
        return output
    }
}

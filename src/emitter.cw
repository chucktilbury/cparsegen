class GrammarEmitter {
    GrammarModel grammar
    list literals
    list expressions

    GrammarEmitter(GrammarModel model) {
        grammar = model
        literals = []
        expressions = []
        int i = 0
        while (i < grammar.parserRules.length) {
            collect((grammar.parserRules[i] as ParserRule).expression)
            i += 1
        }
    }

    void collect(RuleExpr expression) {
        int i = 0
        while (i < expression.children.length) {
            collect(expression.children[i] as RuleExpr)
            i += 1
        }
        if (expression.kind == 1 && literalIndex(expression.value) < 0) {
            literals.append(expression.value)
        }
        expression.index = expressions.length
        expressions.append(expression)
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
            if (byte == 10) { result.append("\\n") }
            else {
                if (byte == 13) { result.append("\\r") }
                else {
                    if (byte == 9) { result.append("\\t") }
                    else { result.append(value.slice(i, i + 1)) }
                }
            }
            i += 1
        }
        result.append("\"")
        return result
    }

    String literalKind(int index) {
        return format("@literal{}", index)
    }

    void emitScanner(String output) {
        output.append("import system as Sys\n\n")
        output.append("class LexToken {\n    String kind\n    String text\n    int offset\n    LexToken(String k, String t, int at) { kind = k\ntext = t\noffset = at }\n}\n\n")
        output.append("class AstNode {\n    String name\n    String text\n    list children\n")
        output.append("    AstNode(String n, String t) { name = n\ntext = t\nchildren = [] }\n")
        output.append("    String render() {\n        String result = \"\"\n        result.append(name)\n        result.append(\"(\")\n        if (children.length == 0) { result.append(text) }\n        int i = 0\n        while (i < children.length) {\n            if (i > 0) { result.append(\", \") }\n            result.append((children[i] as AstNode).render())\n            i += 1\n        }\n        result.append(\")\")\n        return result\n    }\n}\n\n")
        output.append("class ScanRange {\n    int first\n    int last\n    ScanRange(int a, int b) { first = a\nlast = b }\n}\n\n")
        output.append("class ScanPart {\n    list ranges\n    int minimum\n    int maximum\n    ScanPart(list r, int a, int b) { ranges = r\nminimum = a\nmaximum = b }\n")
        output.append("    bool accepts(int byte) {\n        int i = 0\n        while (i < ranges.length) {\n            ScanRange range = ranges[i] as ScanRange\n            if (byte >= range.first && byte <= range.last) { return true }\n            i += 1\n        }\n        return false\n    }\n}\n\n")
        output.append("class ScanRule {\n    String name\n    list parts\n    bool skip\n    ScanRule(String n, list p, bool s) { name = n\nparts = p\nskip = s }\n}\n\n")
        output.append("class InputScanner {\n    String input\n    list tokens\n    list rules\n    int errorOffset\n    String problem\n    int steps\n")
        output.append("    InputScanner(String text) {\n        input = text\n        tokens = []\n        rules = []\n        errorOffset = -1\n        problem = \"\"\n        steps = 0\n")
        int r = 0
        while (r < grammar.lexerRules.length) {
            LexerRule rule = grammar.lexerRules[r] as LexerRule
            output.append(format("        list parts{} = []\n", r))
            int p = 0
            while (p < rule.parts.length) {
                RegexPart part = rule.parts[p] as RegexPart
                output.append(format("        list ranges{}_{} = []\n", r, p))
                int n = 0
                while (n < part.ranges.length) {
                    ByteRange range = part.ranges[n] as ByteRange
                    output.append(format("        ranges{}_{}.append(ScanRange({}, {}))\n", r, p, range.first, range.last))
                    n += 1
                }
                output.append(format("        parts{}.append(ScanPart(ranges{}_{}, {}, {}))\n", r, r, p, part.minimum, part.maximum))
                p += 1
            }
            String skipped = "false"
            if (rule.skip) { skipped = "true" }
            output.append(format("        rules.append(ScanRule({}, parts{}, {}))\n", quoted(rule.name), r, skipped))
            r += 1
        }
        output.append("    }\n")
        output.append("    int matchParts(list parts, int index, int offset) {\n        steps += 1\n        if (steps > 100000) { problem = \"scanner resource limit exceeded\"\nreturn -1 }\n        if (index == parts.length) { return offset }\n        ScanPart part = parts[index] as ScanPart\n        int end = offset\n        while (end < input.length && (part.maximum < 0 || end - offset < part.maximum) && part.accepts(int(input.byteAt(end)))) { end += 1 }\n        int best = -1\n        while (end - offset >= part.minimum) {\n            int candidate = matchParts(parts, index + 1, end)\n            if (candidate > best) { best = candidate }\n            if (!problem.equals(\"\")) { return -1 }\n            end -= 1\n        }\n        return best\n    }\n")
        output.append("    bool scan() {\n        tokens = []\n        errorOffset = -1\n        problem = \"\"\n        int i = 0\n        while (i < input.length) {\n            int bestEnd = i\n            String bestKind = \"\"\n            bool skip = false\n            int r = 0\n            steps = 0\n            while (r < rules.length) {\n                ScanRule rule = rules[r] as ScanRule\n                int end = matchParts(rule.parts, 0, i)\n                if (!problem.equals(\"\")) { errorOffset = i\nreturn false }\n                if (end > bestEnd) { bestEnd = end\nbestKind = rule.name\nskip = rule.skip }\n                r += 1\n            }\n")
        int lit = 0
        while (lit < literals.length) {
            String value = literals[lit] as String
            output.append(format("            if (input.length - i >= {} && input.slice(i, i + {}).equals({}) && i + {} > bestEnd) {{ bestEnd = i + {}\nbestKind = {}\nskip = false }}\n",
                value.length, value.length, quoted(value), value.length, value.length, quoted(literalKind(lit))))
            lit += 1
        }
        output.append("            if (bestEnd == i) { errorOffset = i\nproblem = format(\"lex error at byte {}\", i)\nreturn false }\n            if (!skip) { tokens.append(LexToken(bestKind, input.slice(i, bestEnd), i)) }\n            i = bestEnd\n        }\n        return true\n    }\n}\n\n")
    }

    void emitParser(String output) {
        output.append("class ParserExpr {\n    int kind\n    String value\n    list children\n    int minimum\n    int maximum\n    ParserExpr(int k, String v, list c, int a, int b) { kind = k\nvalue = v\nchildren = c\nminimum = a\nmaximum = b }\n}\n\n")
        output.append("class ParserRuleDef {\n    String name\n    ParserExpr expression\n    ParserRuleDef(String n, ParserExpr e) { name = n\nexpression = e }\n}\n\n")
        output.append("class ParseResult {\n    int end\n    list nodes\n    ParseResult(int at, list children) { end = at\nnodes = children }\n}\n\n")
        output.append("class GeneratedParser {\n    list tokens\n    list rules\n    int position\n    int errorPosition\n    int steps\n    String problem\n")
        output.append("    GeneratedParser(list inputTokens) {\n        tokens = inputTokens\n        rules = []\n        position = 0\n        errorPosition = 0\n        steps = 0\n        problem = \"\"\n")
        int i = 0
        while (i < expressions.length) {
            RuleExpr expression = expressions[i] as RuleExpr
            String children = "["
            int c = 0
            while (c < expression.children.length) {
                if (c > 0) { children.append(", ") }
                RuleExpr child = expression.children[c] as RuleExpr
                children.append(format("e{}", child.index))
                c += 1
            }
            children.append("]")
            String value = expression.value
            if (expression.kind == 1) { value = literalKind(literalIndex(value)) }
            output.append(format("        ParserExpr e{} = ParserExpr({}, {}, {}, {}, {})\n",
                i, expression.kind, quoted(value), children, expression.minimum, expression.maximum))
            i += 1
        }
        i = 0
        while (i < grammar.parserRules.length) {
            ParserRule rule = grammar.parserRules[i] as ParserRule
            output.append(format("        rules.append(ParserRuleDef({}, e{}))\n", quoted(rule.name), rule.expression.index))
            i += 1
        }
        output.append("    }\n")
        output.append("    list joined(list first, list second) {\n        list result = []\n        int i = 0\n        while (i < first.length) { result.append(first[i])\ni += 1 }\n        i = 0\n        while (i < second.length) { result.append(second[i])\ni += 1 }\n        return result\n    }\n")
        output.append("    void addResult(list results, ParseResult value) {\n        if (results.length >= 4096) { problem = \"parser result limit exceeded\"\nreturn }\n        results.append(value)\n    }\n")
        output.append("    list matchRule(String name, int at, int depth) {\n        list results = []\n        int i = 0\n        while (i < rules.length) {\n            ParserRuleDef rule = rules[i] as ParserRuleDef\n            if (rule.name.equals(name)) {\n                list matches = match(rule.expression, at, depth + 1)\n                int m = 0\n                while (m < matches.length && problem.equals(\"\")) {\n                    ParseResult found = matches[m] as ParseResult\n                    AstNode node = AstNode(name, \"\")\n                    node.children = found.nodes\n                    addResult(results, ParseResult(found.end, [node]))\n                    m += 1\n                }\n                return results\n            }\n            i += 1\n        }\n        return results\n    }\n")
        output.append("    list match(ParserExpr expression, int at, int depth) {\n        list results = []\n        if (!problem.equals(\"\")) { return results }\n        steps += 1\n        if (steps > 100000 || depth > 256) { problem = \"parser resource limit exceeded\"\nreturn results }\n        if (at > errorPosition) { errorPosition = at }\n")
        output.append("        if (expression.kind == 0 || expression.kind == 1) {\n            if (expression.kind == 0) {\n                list nested = matchRule(expression.value, at, depth + 1)\n                if (nested.length > 0 || !problem.equals(\"\")) { return nested }\n                int r = 0\n                while (r < rules.length) {\n                    if ((rules[r] as ParserRuleDef).name.equals(expression.value)) { return results }\n                    r += 1\n                }\n            }\n            if (at < tokens.length) {\n                LexToken token = tokens[at] as LexToken\n                if (token.kind.equals(expression.value)) { addResult(results, ParseResult(at + 1, [AstNode(token.kind, token.text)])) }\n            }\n            return results\n        }\n")
        output.append("        if (expression.kind == 3) {\n            int c = 0\n            while (c < expression.children.length && problem.equals(\"\")) {\n                list alternatives = match(expression.children[c] as ParserExpr, at, depth + 1)\n                int a = 0\n                while (a < alternatives.length && problem.equals(\"\")) { addResult(results, alternatives[a] as ParseResult)\na += 1 }\n                c += 1\n            }\n            return results\n        }\n")
        output.append("        list states = [ParseResult(at, [])]\n        if (expression.kind == 2) {\n            int c = 0\n            while (c < expression.children.length && states.length > 0 && problem.equals(\"\")) {\n                list next = []\n                int s = 0\n                while (s < states.length && problem.equals(\"\")) {\n                    ParseResult state = states[s] as ParseResult\n                    list matches = match(expression.children[c] as ParserExpr, state.end, depth + 1)\n                    int m = 0\n                    while (m < matches.length && problem.equals(\"\")) {\n                        ParseResult found = matches[m] as ParseResult\n                        addResult(next, ParseResult(found.end, joined(state.nodes, found.nodes)))\n                        m += 1\n                    }\n                    s += 1\n                }\n                states = next\n                c += 1\n            }\n            return states\n        }\n")
        output.append("        if (expression.minimum == 0) { addResult(results, states[0] as ParseResult) }\n        int count = 0\n        while (states.length > 0 && (expression.maximum < 0 || count < expression.maximum) && problem.equals(\"\")) {\n            list next = []\n            int s = 0\n            while (s < states.length && problem.equals(\"\")) {\n                ParseResult state = states[s] as ParseResult\n                list matches = match(expression.children[0] as ParserExpr, state.end, depth + 1)\n                int m = 0\n                while (m < matches.length && problem.equals(\"\")) {\n                    ParseResult found = matches[m] as ParseResult\n                    if (found.end <= state.end) { problem = \"nullable repetition reached parser\"\nreturn [] }\n                    addResult(next, ParseResult(found.end, joined(state.nodes, found.nodes)))\n                    m += 1\n                }\n                s += 1\n            }\n            count += 1\n            if (count >= expression.minimum) {\n                int n = 0\n                while (n < next.length && problem.equals(\"\")) { addResult(results, next[n] as ParseResult)\nn += 1 }\n            }\n            states = next\n        }\n        return results\n    }\n")
        output.append("    AstNode select(String name, bool complete) {\n        problem = \"\"\n        errorPosition = position\n        steps = 0\n        list matches = matchRule(name, position, 0)\n        if (!problem.equals(\"\")) { return null }\n        ParseResult best = null\n        int i = 0\n        while (i < matches.length) {\n            ParseResult found = matches[i] as ParseResult\n            if ((!complete || found.end == tokens.length) && (best == null || found.end < best.end)) { best = found }\n            i += 1\n        }\n        if (best == null) { problem = format(\"parse error at token {}\", errorPosition)\nreturn null }\n        position = best.end\n        return best.nodes[0] as AstNode\n    }\n")
        ParserRule startRule = grammar.parserRules[0] as ParserRule
        output.append(format("    AstNode parseAll() {{ return select({}, true) }}\n", quoted(startRule.name)))
        i = 0
        while (i < grammar.parserRules.length) {
            ParserRule rule = grammar.parserRules[i] as ParserRule
            output.append(format("    AstNode parse_{}() {{ return select({}, false) }}\n", rule.name, quoted(rule.name)))
            i += 1
        }
        output.append("}\n\nclass GeneratedVisitor {\n    void visit(AstNode node) {\n")
        i = 0
        while (i < grammar.parserRules.length) {
            ParserRule rule = grammar.parserRules[i] as ParserRule
            output.append(format("        if (node.name.equals({})) {{\n            pre_{}(node)\n            int i = 0\n            while (i < node.children.length) {{ visit(node.children[i] as AstNode)\ni += 1 }}\n            post_{}(node)\n            return\n        }}\n", quoted(rule.name), rule.name, rule.name))
            i += 1
        }
        output.append("    }\n")
        i = 0
        while (i < grammar.parserRules.length) {
            ParserRule rule = grammar.parserRules[i] as ParserRule
            output.append(format("    void pre_{}(AstNode node) {{}}\n    void post_{}(AstNode node) {{}}\n", rule.name, rule.name))
            i += 1
        }
        output.append("}\n")
    }

    String emitProgram(bool library) {
        String output = ""
        emitScanner(output)
        emitParser(output)
        if (library) { return output }
        output.append("\nstart {\n    Sys.Process process()\n    bool complete = process.argc() == 3 && process.arg(1).equals(\"--complete\")\n    if (process.argc() != 2 && !complete) { print(\"usage: generated-parser [--complete] INPUT\\n\")\nprocess.exit(2) }\n    int argument = 1\n    if (complete) { argument = 2 }\n    String input = Sys.File(process.arg(argument), \"r\").readAll()\n    InputScanner scanner(input)\n    if (!scanner.scan()) { print(format(\"{}\\n\", scanner.problem))\nprocess.exit(1) }\n    GeneratedParser parser(scanner.tokens)\n    AstNode root = null\n")
        ParserRule startRule = grammar.parserRules[0] as ParserRule
        output.append(format("    if (complete) {{ root = parser.parseAll() }} else {{ root = parser.parse_{}() }}\n", startRule.name))
        output.append("    if (root == null) { print(format(\"{}\\n\", parser.problem))\nprocess.exit(1) }\n    print(format(\"{}\\n\", root.render()))\n}\n")
        return output
    }

    void dotExpression(String output, String owner, RuleExpr expression, String order) {
        if (expression.kind == 0) {
            output.append(format("    {} -> {} [label={}];\n", owner, expression.value, quoted(order)))
        }
        if (expression.kind == 1) {
            output.append(format("    {} -> __cpg_literal{} [label={}];\n", owner, literalIndex(expression.value), quoted(order)))
        }
        int i = 0
        while (i < expression.children.length) {
            dotExpression(output, owner, expression.children[i] as RuleExpr, format("{}.{}", order, i + 1))
            i += 1
        }
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
        i = 0
        while (i < literals.length) {
            output.append(format("    __cpg_literal{} [shape=diamond,label={}];\n", i, quoted(literals[i] as String)))
            i += 1
        }
        i = 0
        while (i < grammar.parserRules.length) {
            ParserRule rule = grammar.parserRules[i] as ParserRule
            dotExpression(output, rule.name, rule.expression, "alt")
            i += 1
        }
        output.append("}\n")
        return output
    }
}

class GrammarEmitter {
    GrammarModel grammar
    Analysis analysis
    list literals
    list expressions
    list visitorNames
    list visitorSuffixes

    // Reads only the shared, already-validated Analysis; it recomputes nothing.
    GrammarEmitter(GrammarModel model) {
        grammar = model
        analysis = model.analysis
        literals = analysis.literals
        expressions = analysis.expressions
        visitorNames = []
        visitorSuffixes = []
        int64 i = 0
        while (i < analysis.parserRules.length) {
            String name = (analysis.parserRules[i] as ParserRuleFacts).name
            visitorNames.append(name)
            visitorSuffixes.append(format("rule_{}", name))
            i += 1
        }
        i = 0
        while (i < analysis.lexers.length) {
            LexerPlan plan = analysis.lexers[i] as LexerPlan
            if (!plan.skip) {
                visitorNames.append(plan.name)
                visitorSuffixes.append(format("token_{}", plan.name))
            }
            i += 1
        }
        i = 0
        while (i < literals.length) {
            visitorNames.append(literalKind(i))
            visitorSuffixes.append(format("literal_{}", i))
            i += 1
        }
    }

    String quoted(String value) {
        String result = "\""
        int64 i = 0
        while (i < value.length) {
            int64 byte = int64(value.byteAt(i))
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
        return(result)
    }

    String literalKind(int64 index) {
        return(format("@literal{}", index))
    }

    void emitInsertions(String output, String target, String boundary) {
        int64 i = 0
        while (i < grammar.insertions.length) {
            CodeInsertion block = grammar.insertions[i] as CodeInsertion
            if (block.target.equals(target) && block.boundary.equals(boundary)) {
                output.append("\n")
                output.append(block.content)
                output.append("\n")
            }
            i += 1
        }
    }

    void emitScanner(String output) {
        output.append("import system as Sys\n\n")
        emitInsertions(output, "cwhip", "imports")
        emitInsertions(output, "cwhip", "declarations")
        output.append("class LexToken {\n    String kind\n    String text\n    int64 offset\n    LexToken(String k, String t, int64 at) { kind = k\ntext = t\noffset = at }\n}\n\n")
        emitInsertions(output, "cwhip", "ast_pre")
        output.append("class AstNode {\n    String name\n    String text\n    list children\n")
        output.append("    AstNode(String n, String t) { name = n\ntext = t\nchildren = [] }\n")
        output.append("    String kind() { return(name) }\n    String lexeme() { return(text) }\n    int64 childCount() { return(children.length) }\n    AstNode childAt(int64 index) { return(children[index] as AstNode) }\n")
        output.append("    String render() {\n        String result = \"\"\n        result.append(name)\n        result.append(\"(\")\n        if (children.length == 0) { result.append(text) }\n        int64 i = 0\n        while (i < children.length) {\n            if (i > 0) { result.append(\", \") }\n            result.append((children[i] as AstNode).render())\n            i += 1\n        }\n        result.append(\")\")\n        return(result)\n    }\n}\n\n")
        emitInsertions(output, "cwhip", "ast_post")
        emitInsertions(output, "cwhip", "scanner_pre")
        output.append("class ScanRange {\n    int64 first\n    int64 last\n    ScanRange(int64 a, int64 b) { first = a\nlast = b }\n}\n\n")
        output.append("class ScanState {\n    int64 kind\n    list ranges\n    int64 next\n    int64 alternate\n    ScanState(int64 k, list r, int64 n, int64 a) { kind = k\nranges = r\nnext = n\nalternate = a }\n")
        output.append("    bool accepts(int64 byte) {\n        int64 i = 0\n        while (i < ranges.length) {\n            ScanRange interval = ranges[i] as ScanRange\n            if (byte >= interval.first && byte <= interval.last) { return(true) }\n            i += 1\n        }\n        return(false)\n    }\n}\n\n")
        output.append("class ScanRule {\n    String name\n    int64 entry\n    bool skip\n    int64 quote\n    ScanRule(String n, int64 e, bool s, int64 q) { name = n\nentry = e\nskip = s\nquote = q }\n}\n\n")
        output.append("class InputScanner {\n    String input\n    list tokens\n    list rules\n    list states\n    list lineComments\n    list blockComments\n    int64 errorOffset\n    String problem\n    int64 steps\n")
        output.append("    InputScanner(String text) {\n        input = text\n        tokens = []\n        rules = []\n        states = []\n        lineComments = []\n        blockComments = []\n        errorOffset = -1\n        problem = \"\"\n        steps = 0\n")
        int64 comment = 0
        while (comment < analysis.lexical.lineComments.length) {
            output.append(format("        lineComments.append({})\n", quoted(analysis.lexical.lineComments[comment] as String)))
            comment += 1
        }
        comment = 0
        while (comment < analysis.lexical.blockComments.length) {
            list markers = analysis.lexical.blockComments[comment] as list
            output.append(format("        blockComments.append([{}, {}])\n", quoted(markers[0] as String), quoted(markers[1] as String)))
            comment += 1
        }
        int64 s = 0
        while (s < analysis.lexerStates.length) {
            LexerState state = analysis.lexerStates[s] as LexerState
            output.append(format("        list ranges{} = []\n", s))
            int64 n = 0
            while (n < state.ranges.length) {
                ByteRange interval = state.ranges[n] as ByteRange
                output.append(format("        ranges{}.append(ScanRange({}, {}))\n", s, interval.first, interval.last))
                n += 1
            }
            output.append(format("        states.append(ScanState({}, ranges{}, {}, {}))\n", state.kind, s, state.next, state.alternate))
            s += 1
        }
        int64 r = 0
        while (r < analysis.lexers.length) {
            LexerPlan rule = analysis.lexers[r] as LexerPlan
            String skipped = "false"
            if (rule.skip) { skipped = "true" }
            output.append(format("        rules.append(ScanRule({}, {}, {}, {}))\n", quoted(rule.name), rule.entry, skipped, rule.quote))
            r += 1
        }
        output.append("    }\n")
        output.append("    bool startsAt(int64 at, String marker) {\n        return(input.length - at >= marker.length && input.slice(at, at + marker.length).equals(marker))\n    }\n")
        output.append("    int64 skipComment(int64 at) {\n        int64 c = 0\n        while (c < lineComments.length) {\n            String marker = lineComments[c] as String\n            if (startsAt(at, marker)) {\n                int64 end = at + marker.length\n                while (end < input.length && int64(input.byteAt(end)) != 10 && int64(input.byteAt(end)) != 13) { end += 1 }\n                return(end)\n            }\n            c += 1\n        }\n        c = 0\n        while (c < blockComments.length) {\n            list markers = blockComments[c] as list\n            String opening = markers[0] as String\n            String closing = markers[1] as String\n            if (startsAt(at, opening)) {\n                int64 end = at + opening.length\n                while (end < input.length && !startsAt(end, closing)) { end += 1 }\n                if (end == input.length) { errorOffset = at\nproblem = format(\"unterminated block comment at byte {}\", at)\nreturn(-1) }\n                return(end + closing.length)\n            }\n            c += 1\n        }\n        return(at)\n    }\n")
        output.append("    int64 matchQuote(int64 at, int64 quote) {\n        if (int64(input.byteAt(at)) != quote) { return(-1) }\n        int64 end = at + 1\n        int64 characters = 0\n        while (end < input.length && int64(input.byteAt(end)) != quote) {\n            int64 byte = int64(input.byteAt(end))\n            if (byte < 32 || byte > 126) { break }\n            if (byte == 92) {\n                end += 1\n                if (end == input.length) { break }\n                byte = int64(input.byteAt(end))\n                if (byte != 92 && byte != 34 && byte != 39 && byte != 110 && byte != 114 && byte != 116 && byte != 48) {\n                    errorOffset = end\n                    problem = format(\"invalid quoted escape at byte {}\", end)\n                    return(-1)\n                }\n            }\n            characters += 1\n            end += 1\n        }\n        if (end >= input.length || int64(input.byteAt(end)) != quote) {\n            errorOffset = at\n            problem = format(\"unterminated quoted token at byte {}\", at)\n            return(-1)\n        }\n        if (quote == 39 && characters != 1) {\n            errorOffset = at\n            problem = format(\"character literal must contain one byte or escape at byte {}\", at)\n            return(-1)\n        }\n        return(end + 1)\n    }\n")
        output.append("    void addState(list active, list seen, int64 index) {\n        if (index >= 0 && !(seen[index] as bool)) { seen[index] = true\nactive.append(index) }\n    }\n")
        output.append("    bool closure(list active, list seen) {\n        int64 i = 0\n        while (i < active.length) {\n            steps += 1\n            if (steps > 100000) { problem = \"scanner resource limit exceeded\"\nreturn(false) }\n            ScanState state = states[active[i] as int64] as ScanState\n            if (state.kind == 1) { addState(active, seen, state.next)\naddState(active, seen, state.alternate) }\n            i += 1\n        }\n        return(true)\n    }\n")
        output.append("    int64 matchStates(int64 entry, int64 offset) {\n        list active = []\n        list seen = []\n        int64 s = 0\n        while (s < states.length) { seen.append(false)\ns += 1 }\n        addState(active, seen, entry)\n        int64 best = -1\n        int64 at = offset\n        while (active.length > 0) {\n            if (!closure(active, seen)) { return(-1) }\n            list next = []\n            s = 0\n            while (s < seen.length) { seen[s] = false\ns += 1 }\n            s = 0\n            while (s < active.length) {\n                ScanState state = states[active[s] as int64] as ScanState\n                if (state.kind == 2) { best = at }\n                if (state.kind == 0 && at < input.length && state.accepts(int64(input.byteAt(at)))) { addState(next, seen, state.next) }\n                s += 1\n            }\n            if (at == input.length) { return(best) }\n            active = next\n            at += 1\n        }\n        return(best)\n    }\n")
        output.append("    bool scan() {\n        tokens = []\n        errorOffset = -1\n        problem = \"\"\n        int64 i = 0\n        while (i < input.length) {\n            int64 afterComment = skipComment(i)\n            if (afterComment < 0) { return(false) }\n            if (afterComment > i) { i = afterComment }\n            else {\n            int64 bestEnd = i\n            String bestKind = \"\"\n            bool skip = false\n            int64 r = 0\n            steps = 0\n            while (r < rules.length) {\n                ScanRule rule = rules[r] as ScanRule\n                int64 end = -1\n                if (rule.quote != 0) { end = matchQuote(i, rule.quote) }\n                else { end = matchStates(rule.entry, i) }\n                if (!problem.equals(\"\")) {\n                    if (errorOffset < 0) { errorOffset = i }\n                    return(false)\n                }\n                if (end > bestEnd) { bestEnd = end\nbestKind = rule.name\nskip = rule.skip }\n                r += 1\n            }\n")
        int64 lit = 0
        while (lit < literals.length) {
            String value = literals[lit] as String
            output.append(format("            if (input.length - i >= {} && input.slice(i, i + {}).equals({}) && i + {} > bestEnd) {{ bestEnd = i + {}\nbestKind = {}\nskip = false }}\n",
                value.length, value.length, quoted(value), value.length, value.length, quoted(literalKind(lit))))
            lit += 1
        }
        if (!analysis.lexical.keywordToken.equals("")) {
            output.append(format("            if (bestKind.equals({})) {{\n                String word = input.slice(i, bestEnd)\n", quoted(analysis.lexical.keywordToken)))
            lit = 0
            while (lit < literals.length) {
                output.append(format("                if (word.equals({})) {{ bestKind = {} }}\n", quoted(literals[lit] as String), quoted(literalKind(lit))))
                lit += 1
            }
            lit = 0
            while (lit < analysis.lexical.reserved.length) {
                output.append(format("                if (word.equals({})) {{ bestKind = \"@reserved\" }}\n", quoted(analysis.lexical.reserved[lit] as String)))
                lit += 1
            }
            output.append("            }\n")
        }
        output.append("            if (bestEnd == i) { errorOffset = i\nproblem = format(\"lex error at byte {}\", i)\nreturn(false) }\n            if (!skip) { tokens.append(LexToken(bestKind, input.slice(i, bestEnd), i)) }\n            i = bestEnd\n            }\n        }\n        return(true)\n    }\n}\n\n")
    }

    void emitParser(String output) {
        output.append("class ParserExpr {\n    int64 kind\n    String value\n    list children\n    int64 minimum\n    int64 maximum\n    int64 required\n    ParserExpr(int64 k, String v, list c, int64 a, int64 b, int64 r) { kind = k\nvalue = v\nchildren = c\nminimum = a\nmaximum = b\nrequired = r }\n}\n\n")
        output.append("class ParserRuleDef {\n    String name\n    ParserExpr expression\n    ParserRuleDef(String n, ParserExpr e) { name = n\nexpression = e }\n}\n\n")
        output.append("class ParseResult {\n    int64 end\n    list nodes\n    ParseResult(int64 at, list children) { end = at\nnodes = children }\n}\n\n")
        output.append("class GeneratedParser {\n    list tokens\n    list rules\n    int64 position\n    int64 errorPosition\n    int64 steps\n    int64 endLimit\n    String problem\n")
        output.append("    GeneratedParser(list inputTokens) {\n        tokens = inputTokens\n        rules = []\n        position = 0\n        errorPosition = 0\n        steps = 0\n        endLimit = tokens.length\n        problem = \"\"\n")
        int64 i = 0
        while (i < expressions.length) {
            ParserExprRecord expression = expressions[i] as ParserExprRecord
            String children = "["
            int64 c = 0
            while (c < expression.children.length) {
                if (c > 0) { children.append(", ") }
                children.append(format("e{}", expression.children[c] as int64))
                c += 1
            }
            children.append("]")
            String value = expression.value
            if (expression.kind == 1) { value = literalKind(expression.literal) }
            output.append(format("        ParserExpr e{} = ParserExpr({}, {}, {}, {}, {}, {})\n",
                i, expression.kind, quoted(value), children, expression.minimum, expression.maximum, expression.required))
            i += 1
        }
        i = 0
        while (i < analysis.parserRules.length) {
            ParserRuleFacts rule = analysis.parserRules[i] as ParserRuleFacts
            output.append(format("        rules.append(ParserRuleDef({}, e{}))\n", quoted(rule.name), rule.root))
            i += 1
        }
        output.append("    }\n")
        output.append("    list joined(list first, list second) {\n        list result = []\n        int64 i = 0\n        while (i < first.length) { result.append(first[i])\ni += 1 }\n        i = 0\n        while (i < second.length) { result.append(second[i])\ni += 1 }\n        return(result)\n    }\n")
        output.append("    void addResult(list results, ParseResult value) {\n        if (results.length >= 4096) { problem = \"parser result limit exceeded\"\nreturn }\n        results.append(value)\n    }\n")
        output.append("    list matchRule(String name, int64 at, int64 depth) {\n        list results = []\n        int64 i = 0\n        while (i < rules.length) {\n            ParserRuleDef rule = rules[i] as ParserRuleDef\n            if (rule.name.equals(name)) {\n                list matches = match(rule.expression, at, depth + 1)\n                int64 m = 0\n                while (m < matches.length && problem.equals(\"\")) {\n                    ParseResult found = matches[m] as ParseResult\n                    AstNode node = AstNode(name, \"\")\n                    node.children = found.nodes\n                    addResult(results, ParseResult(found.end, [node]))\n                    m += 1\n                }\n                return(results)\n            }\n            i += 1\n        }\n        return(results)\n    }\n")
        output.append("    list match(ParserExpr expression, int64 at, int64 depth) {\n        list results = []\n        if (!problem.equals(\"\")) { return(results) }\n        steps += 1\n        if (steps > 100000 || depth > 256) { problem = \"parser resource limit exceeded\"\nreturn(results) }\n        if (at > errorPosition) { errorPosition = at }\n        if (at > endLimit || expression.required > endLimit - at) { return(results) }\n")
        output.append("        if (expression.kind == 0 || expression.kind == 1) {\n            if (expression.kind == 0) {\n                list nested = matchRule(expression.value, at, depth)\n                if (nested.length > 0 || !problem.equals(\"\")) { return(nested) }\n                int64 r = 0\n                while (r < rules.length) {\n                    if ((rules[r] as ParserRuleDef).name.equals(expression.value)) { return(results) }\n                    r += 1\n                }\n            }\n            if (at < endLimit) {\n                LexToken token = tokens[at] as LexToken\n                if (token.kind.equals(expression.value)) { addResult(results, ParseResult(at + 1, [AstNode(token.kind, token.text)])) }\n            }\n            return(results)\n        }\n")
        output.append("        if (expression.kind == 3) {\n            int64 c = 0\n            while (c < expression.children.length && problem.equals(\"\")) {\n                list alternatives = match(expression.children[c] as ParserExpr, at, depth)\n                int64 a = 0\n                while (a < alternatives.length && problem.equals(\"\")) { addResult(results, alternatives[a] as ParseResult)\na += 1 }\n                c += 1\n            }\n            return(results)\n        }\n")
        output.append("        list states = [ParseResult(at, [])]\n        if (expression.kind == 2) {\n            int64 limit = endLimit\n            int64 remaining = 0\n            int64 c = 0\n            while (c < expression.children.length) { remaining += (expression.children[c] as ParserExpr).required\nc += 1 }\n            c = 0\n            while (c < expression.children.length && states.length > 0 && problem.equals(\"\")) {\n                ParserExpr child = expression.children[c] as ParserExpr\n                remaining -= child.required\n                list next = []\n                int64 s = 0\n                while (s < states.length && problem.equals(\"\")) {\n                    ParseResult state = states[s] as ParseResult\n                    if (remaining <= limit - state.end) {\n                        endLimit = limit - remaining\n                        list matches = match(child, state.end, depth)\n                        endLimit = limit\n                        int64 m = 0\n                        while (m < matches.length && problem.equals(\"\")) {\n                            ParseResult found = matches[m] as ParseResult\n                            addResult(next, ParseResult(found.end, joined(state.nodes, found.nodes)))\n                            m += 1\n                        }\n                    }\n                    s += 1\n                }\n                states = next\n                c += 1\n            }\n            return(states)\n        }\n")
        output.append("        if (expression.minimum == 0) { addResult(results, states[0] as ParseResult) }\n        int64 count = 0\n        while (states.length > 0 && (expression.maximum < 0 || count < expression.maximum) && problem.equals(\"\")) {\n            list next = []\n            int64 s = 0\n            while (s < states.length && problem.equals(\"\")) {\n                ParseResult state = states[s] as ParseResult\n                list matches = match(expression.children[0] as ParserExpr, state.end, depth)\n                int64 m = 0\n                while (m < matches.length && problem.equals(\"\")) {\n                    ParseResult found = matches[m] as ParseResult\n                    if (found.end <= state.end) { problem = \"nullable repetition reached parser\"\nreturn([]) }\n                    addResult(next, ParseResult(found.end, joined(state.nodes, found.nodes)))\n                    m += 1\n                }\n                s += 1\n            }\n            count += 1\n            if (count >= expression.minimum) {\n                int64 n = 0\n                while (n < next.length && problem.equals(\"\")) { addResult(results, next[n] as ParseResult)\nn += 1 }\n            }\n            states = next\n        }\n        return(results)\n    }\n")
        output.append("    AstNode select(String name, bool complete) {\n        problem = \"\"\n        errorPosition = position\n        steps = 0\n        endLimit = tokens.length\n        list matches = matchRule(name, position, 0)\n        if (!problem.equals(\"\")) { return(null) }\n        ParseResult best = null\n        int64 i = 0\n        while (i < matches.length) {\n            ParseResult found = matches[i] as ParseResult\n            if ((!complete || found.end == tokens.length) && (best == null || found.end < best.end)) { best = found }\n            i += 1\n        }\n        if (best == null) { problem = format(\"parse error at token {}\", errorPosition)\nreturn(null) }\n        position = best.end\n        return(best.nodes[0] as AstNode)\n    }\n")
        ParserRule startRule = grammar.parserRules[0] as ParserRule
        output.append(format("    AstNode parseAll() {{ return(select({}, true)) }}\n", quoted(startRule.name)))
        i = 0
        while (i < grammar.parserRules.length) {
            ParserRule rule = grammar.parserRules[i] as ParserRule
            output.append(format("    AstNode parse_{}() {{ return(select({}, false)) }}\n", rule.name, quoted(rule.name)))
            i += 1
        }
        output.append("}\n\n")
        emitInsertions(output, "cwhip", "parser_post")
        emitInsertions(output, "cwhip", "visitor_pre")
        output.append("class GeneratedVisitor {\n")
        output.append("    enum { VISIT_CONTINUE = 0, VISIT_SKIP = 1, VISIT_STOP = 2, VISIT_ERROR = -1 }\n")
        output.append("    int64 onNode(AstNode node) { return(VISIT_CONTINUE) }\n    int64 enter(AstNode node) { return(VISIT_CONTINUE) }\n    int64 leave(AstNode node) { return(VISIT_CONTINUE) }\n")
        output.append("    int64 checkedResult(int64 result, int64 phase) {\n        if (result != VISIT_CONTINUE && result != VISIT_SKIP && result != VISIT_STOP && result != VISIT_ERROR) { return(VISIT_ERROR) }\n        if (phase == 2 && result == VISIT_SKIP) { return(VISIT_ERROR) }\n        return(result)\n    }\n")
        list phases = ["on", "enter", "leave"]
        int64 phase = 0
        while (phase < phases.length) {
            String prefix = phases[phase] as String
            String fallback = prefix
            String dispatcher = format("dispatch_{}", prefix)
            if (phase == 0) { fallback = "onNode"
dispatcher = "dispatch" }
            output.append(format("    int64 {}(AstNode node) {{\n        if (node == null) {{ return(VISIT_ERROR) }}\n", dispatcher))
            i = 0
            while (i < visitorNames.length) {
                output.append(format("        if (node.kind().equals({})) {{ return(checkedResult({}_{}(node), {})) }}\n", quoted(visitorNames[i] as String), prefix, visitorSuffixes[i] as String, phase))
                i += 1
            }
            output.append(format("        return(checkedResult({}(node), {}))\n    }}\n", fallback, phase))
            i = 0
            while (i < visitorNames.length) {
                output.append(format("    int64 {}_{}(AstNode node) {{ return({}(node)) }}\n", prefix, visitorSuffixes[i] as String, fallback))
                i += 1
            }
            phase += 1
        }
        output.append("    int64 walk(AstNode node) {\n        int64 result = dispatch_enter(node)\n        if (result == VISIT_STOP || result == VISIT_ERROR) { return(result) }\n        if (result == VISIT_CONTINUE) {\n            int64 i = 0\n            while (i < node.childCount()) {\n                result = walk(node.childAt(i))\n                if (result != VISIT_CONTINUE) { return(result) }\n                i += 1\n            }\n        }\n        return(dispatch_leave(node))\n    }\n")
        output.append("    void visit(AstNode node) {\n")
        i = 0
        while (i < grammar.parserRules.length) {
            ParserRule rule = grammar.parserRules[i] as ParserRule
            output.append(format("        if (node.name.equals({})) {{\n            pre_{}(node)\n            int64 i = 0\n            while (i < node.children.length) {{ visit(node.children[i] as AstNode)\ni += 1 }}\n            post_{}(node)\n            return\n        }}\n", quoted(rule.name), rule.name, rule.name))
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
        emitInsertions(output, "cwhip", "file_pre")
        emitScanner(output)
        emitInsertions(output, "cwhip", "scanner_post")
        emitInsertions(output, "cwhip", "parser_pre")
        emitParser(output)
        emitInsertions(output, "cwhip", "visitor_post")
        if (library) {
            emitInsertions(output, "cwhip", "file_post")
            return(output)
        }
        output.append("\nstart {\n    Sys.Process process()\n    bool complete = process.argc() == 3 && process.arg(1).equals(\"--complete\")\n    if (process.argc() != 2 && !complete) { print(\"usage: generated-parser [--complete] INPUT\\n\")\nprocess.exit(2) }\n    int64 argument = 1\n    if (complete) { argument = 2 }\n    String input = Sys.File(process.arg(argument), \"r\").readAll()\n    InputScanner scanner(input)\n    if (!scanner.scan()) { print(format(\"{}\\n\", scanner.problem))\nprocess.exit(1) }\n    GeneratedParser parser(scanner.tokens)\n    AstNode root = null\n")
        ParserRule startRule = grammar.parserRules[0] as ParserRule
        output.append(format("    if (complete) {{ root = parser.parseAll() }} else {{ root = parser.parse_{}() }}\n", startRule.name))
        output.append("    if (root == null) { print(format(\"{}\\n\", parser.problem))\nprocess.exit(1) }\n    print(format(\"{}\\n\", root.render()))\n}\n")
        emitInsertions(output, "cwhip", "file_post")
        return(output)
    }

    void dotExpression(String output, String owner, int64 index, String order) {
        ParserExprRecord expression = expressions[index] as ParserExprRecord
        if (expression.kind == 0) {
            output.append(format("    {} -> {} [label={}];\n", owner, expression.value, quoted(order)))
        }
        if (expression.kind == 1) {
            output.append(format("    {} -> __cpg_literal{} [label={}];\n", owner, expression.literal, quoted(order)))
        }
        int64 i = 0
        while (i < expression.children.length) {
            dotExpression(output, owner, expression.children[i] as int64, format("{}.{}", order, i + 1))
            i += 1
        }
    }

    String emitDot() {
        String output = "digraph grammar {\n    rankdir=LR;\n"
        int64 i = 0
        while (i < grammar.parserRules.length) {
            ParserRule rule = grammar.parserRules[i] as ParserRule
            output.append(format("    {} [shape=box];\n", rule.name))
            i += 1
        }
        i = 0
        while (i < analysis.lexers.length) {
            LexerPlan rule = analysis.lexers[i] as LexerPlan
            output.append(format("    {} [shape=ellipse];\n", rule.name))
            i += 1
        }
        i = 0
        while (i < literals.length) {
            output.append(format("    __cpg_literal{} [shape=diamond,label={}];\n", i, quoted(literals[i] as String)))
            i += 1
        }
        i = 0
        while (i < analysis.parserRules.length) {
            ParserRuleFacts rule = analysis.parserRules[i] as ParserRuleFacts
            dotExpression(output, rule.name, rule.root, "alt")
            i += 1
        }
        output.append("}\n")
        return(output)
    }
}

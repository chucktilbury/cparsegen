include "c_runtime.cw"

// Uses the same collected expression/literal indices as the Cwhip emitter.
class CGrammarEmitter {
    GrammarModel grammar
    GrammarEmitter shared

    CGrammarEmitter(GrammarModel model, GrammarEmitter emitter) {
        grammar = model
        shared = emitter
    }

    String validate() {
        int i = 0
        while (i < grammar.directives.length) {
            GrammarDirective directive = grammar.directives[i] as GrammarDirective
            if (!directive.name.equals("skip") && !directive.name.equals("keywords") &&
                !directive.name.equals("reserved") && !directive.name.equals("quoted") &&
                !directive.name.equals("line_comment") && !directive.name.equals("block_comment") &&
                !directive.name.equals("note")) {
                return format("line {}: C target does not support @{}", directive.line, directive.name)
            }
            i += 1
        }
        return ""
    }

    String quoted(String value) {
        String result = "\""
        int i = 0
        while (i < value.length) {
            int byte = int(value.byteAt(i))
            // Fixed-width octal escapes also avoid C trigraphs and encoding assumptions.
            result.append(format("\\{}{}{}", byte / 64, (byte / 8) % 8, byte % 8))
            i += 1
        }
        result.append("\"")
        return result
    }

    String emitProgram() {
        String output = ""
        CParserRuntime().emitTypes(output)
        int r = 0
        while (r < grammar.lexerRules.length) {
            LexerRule rule = grammar.lexerRules[r] as LexerRule
            if (rule.quote != 0) { r += 1
continue }
            int p = 0
            while (p < rule.parts.length) {
                RegexPart part = rule.parts[p] as RegexPart
                output.append(format("static const Range ranges{}_{}[] = {{", r, p))
                int n = 0
                while (n < part.ranges.length) {
                    ByteRange range = part.ranges[n] as ByteRange
                    output.append(format("{{{}, {}}},", range.first, range.last))
                    n += 1
                }
                output.append("};\n")
                p += 1
            }
            output.append(format("static const Part parts{}[] = {{", r))
            p = 0
            while (p < rule.parts.length) {
                RegexPart part = rule.parts[p] as RegexPart
                output.append(format("{{ranges{}_{}, {}, {}, {}}},", r, p,
                    part.ranges.length, part.minimum, part.maximum))
                p += 1
            }
            output.append("};\n")
            r += 1
        }
        output.append("static const ScanRule scan_rules[] = {\n")
        r = 0
        while (r < grammar.lexerRules.length) {
            LexerRule rule = grammar.lexerRules[r] as LexerRule
            int skip = 0
            if (rule.skip) { skip = 1 }
            String parts = "NULL"
            if (rule.quote == 0) { parts = format("parts{}", r) }
            output.append(format("{{{}, {}, {}, {}, {}}},\n", quoted(rule.name), parts, rule.parts.length, skip, rule.quote))
            r += 1
        }
        output.append("{NULL, NULL, 0, 0, 0}};\n")
        output.append(format("static const char *const keyword_token = {};\n", quoted(grammar.keywordToken)))
        output.append("static const char *const reserved[] = {")
        int word = 0
        while (word < grammar.reserved.length) {
            output.append(format("{},", quoted(grammar.reserved[word] as String)))
            word += 1
        }
        output.append("NULL};\nstatic const Comment line_comments[] = {\n")
        int comment = 0
        while (comment < grammar.lineComments.length) {
            String marker = grammar.lineComments[comment] as String
            output.append(format("{{{}, {}, NULL, 0}},\n", quoted(marker), marker.length))
            comment += 1
        }
        output.append("{NULL, 0, NULL, 0}};\nstatic const Comment block_comments[] = {\n")
        comment = 0
        while (comment < grammar.blockComments.length) {
            list markers = grammar.blockComments[comment] as list
            String opening = markers[0] as String
            String closing = markers[1] as String
            output.append(format("{{{}, {}, {}, {}}},\n", quoted(opening), opening.length, quoted(closing), closing.length))
            comment += 1
        }
        output.append("{NULL, 0, NULL, 0}};\n")
        output.append("static const Literal literals[] = {\n")
        int i = 0
        while (i < shared.literals.length) {
            String value = shared.literals[i] as String
            output.append(format("{{{}, {}, {}}},\n", quoted(value), value.length, quoted(shared.literalKind(i))))
            i += 1
        }
        output.append("{NULL, 0, NULL}};\n")
        i = 0
        while (i < shared.expressions.length) {
            RuleExpr expression = shared.expressions[i] as RuleExpr
            output.append(format("static const size_t children{}[] = {{", i))
            int c = 0
            while (c < expression.children.length) {
                output.append(format("{},", (expression.children[c] as RuleExpr).index))
                c += 1
            }
            output.append("0};\n")
            i += 1
        }
        output.append("static const Expr expressions[] = {\n")
        i = 0
        while (i < shared.expressions.length) {
            RuleExpr expression = shared.expressions[i] as RuleExpr
            String value = expression.value
            if (expression.kind == 1) { value = shared.literalKind(shared.literalIndex(value)) }
            output.append(format("{{{}, {}, children{}, {}, {}, {}}},\n",
                expression.kind, quoted(value), i, expression.children.length, expression.minimum, expression.maximum))
            i += 1
        }
        output.append("};\nstatic const Rule rules[] = {\n")
        i = 0
        while (i < grammar.parserRules.length) {
            ParserRule rule = grammar.parserRules[i] as ParserRule
            output.append(format("{{{}, {}}},\n", quoted(rule.name), rule.expression.index))
            i += 1
        }
        output.append("{NULL, 0}};\n")
        CParserRuntime().emitProgram(output)
        return output
    }
}

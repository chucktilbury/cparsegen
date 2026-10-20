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
            if (directive.name.equals("keywords") || directive.name.equals("reserved") ||
                directive.name.equals("quoted") || directive.name.equals("line_comment") ||
                directive.name.equals("block_comment")) {
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
            output.append(format("{{{}, parts{}, {}, {}}},\n", quoted(rule.name), r, rule.parts.length, skip))
            r += 1
        }
        output.append("{NULL, NULL, 0, 0}};\n")
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

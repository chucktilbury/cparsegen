include "parser.cw"

class Names : GeneratedVisitor {
    int64 count
    bool first
    String problem

    Names(bool stopAfterFirst) {
        super GeneratedVisitor()
        count = 0
        first = stopAfterFirst
        problem = ""
    }

    int64 on_token_IDENT(AstNode node) {
        if (node.lexeme().equals("forbidden")) {
            problem = "identifier 'forbidden' is not allowed"
            return(VISIT_ERROR)
        }
        count += 1
        if (first) { return(VISIT_STOP) }
        return(VISIT_CONTINUE)
    }

    int64 enter_token_IDENT(AstNode node) {
        return(on_token_IDENT(node))
    }

    int64 on_rule_words(AstNode node) {
        int64 i = 0
        while (i < node.childCount()) {
            int64 result = dispatch(node.childAt(i))
            if (result != VISIT_CONTINUE) { return(result) }
            i += 1
        }
        return(VISIT_CONTINUE)
    }
}

start {
    Sys.Process process()
    Sys.StandardIO io()
    bool first = process.argc() == 3 && process.arg(1).equals("--first")
    bool manual = process.argc() == 3 && process.arg(1).equals("--dispatch")
    if (process.argc() != 2 && !first && !manual) {
        io.writeErrorLine("usage: words-visitor [--first | --dispatch] TEXT")
        process.exit(2)
    }
    int64 argument = 1
    if (first || manual) { argument = 2 }
    InputScanner scanner(process.arg(argument))
    if (!scanner.scan()) {
        io.writeErrorLine(scanner.problem)
        process.exit(1)
    }
    GeneratedParser parser(scanner.tokens)
    AstNode root = parser.parseAll()
    if (root == null) {
        io.writeErrorLine(parser.problem)
        process.exit(1)
    }
    Names names(first)
    int64 result = names.VISIT_CONTINUE
    if (manual) { result = names.dispatch(root) }
    else { result = names.walk(root) }
    if (result == names.VISIT_CONTINUE || (first && result == names.VISIT_STOP)) {
        String suffix = ""
        if (result == names.VISIT_STOP) { suffix = " (stopped)" }
        io.writeLine(format("names={}{}", names.count, suffix))
    }
    else {
        if (names.problem.equals("")) { names.problem = "visitor failed" }
        io.writeErrorLine(names.problem)
        process.exit(1)
    }
}

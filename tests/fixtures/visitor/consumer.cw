include "parser.cw"

class Trace : GeneratedVisitor {
    String events
    String mode
    int64 count

    Trace(String selected) {
        super GeneratedVisitor()
        events = ""
        mode = selected
        count = 0
    }
    void event(String phase, AstNode node) {
        events.append(format("{}:{} ", phase, node.kind()))
    }
    int64 enter(AstNode node) {
        event("e", node)
        return(VISIT_CONTINUE)
    }
    int64 leave(AstNode node) {
        event("l", node)
        return(VISIT_CONTINUE)
    }
    int64 enter_rule_pair(AstNode node) {
        event("p", node)
        if (mode.equals("skip")) { return(VISIT_SKIP) }
        if (mode.equals("invalid-enter")) { return(99) }
        return(VISIT_CONTINUE)
    }
    int64 leave_rule_pair(AstNode node) {
        event("q", node)
        if (mode.equals("leave-stop")) { return(VISIT_STOP) }
        if (mode.equals("leave-error")) { return(VISIT_ERROR) }
        if (mode.equals("leave-skip")) { return(VISIT_SKIP) }
        if (mode.equals("invalid-leave")) { return(99) }
        return(VISIT_CONTINUE)
    }
    int64 enter_token_NUMBER(AstNode node) {
        event("n", node)
        count += 1
        if (mode.equals("stop")) { return(VISIT_STOP) }
        if (mode.equals("error")) { return(VISIT_ERROR) }
        return(VISIT_CONTINUE)
    }
    int64 enter_literal_0(AstNode node) {
        event("t", node)
        return(VISIT_CONTINUE)
    }
    int64 onNode(AstNode node) {
        event("g", node)
        return(VISIT_CONTINUE)
    }
    int64 on_rule_entry(AstNode node) {
        event("d", node)
        if (mode.equals("dispatch-stop")) { return(VISIT_STOP) }
        if (mode.equals("dispatch-error")) { return(VISIT_ERROR) }
        if (mode.equals("dispatch-skip")) { return(VISIT_SKIP) }
        if (mode.equals("dispatch-invalid")) { return(99) }
        return(VISIT_CONTINUE)
    }
}

start {
    InputScanner scanner("12 + 34")
    if (!scanner.scan()) { Sys.Process().exit(10) }
    GeneratedParser parser(scanner.tokens)
    AstNode root = parser.parseAll()
    if (root == null) { Sys.Process().exit(11) }
    AstNode first = root.childAt(0).childAt(0)
    if (!first.lexeme().equals("12") || root.childCount() != 2
            || root.childAt(1).childCount() != 0) { Sys.Process().exit(12) }
    String mode = Sys.Process().arg(1)
    Trace visitor(mode)
    Trace independent("walk")
    int64 result = visitor.VISIT_CONTINUE
    if (mode.length >= 8 && mode.slice(0, 8).equals("dispatch")) {
        result = visitor.dispatch(root)
        if (independent.dispatch(first) != visitor.VISIT_CONTINUE
                || !independent.events.equals("g:NUMBER ")) { Sys.Process().exit(13) }
    }
    else {
        if (mode.equals("unknown")) { result = visitor.walk(AstNode("custom", "")) }
        else {
            if (mode.equals("null")) { result = visitor.walk(null) }
            else { result = visitor.walk(root) }
        }
    }
    if (independent.walk(root) != visitor.VISIT_CONTINUE || independent.count != 2) {
        Sys.Process().exit(14)
    }
    print(format("{}|{}|{}\n", result, visitor.count, visitor.events))
    visitor.mode = "walk"
    visitor.count = 0
    visitor.events = ""
    if (visitor.walk(root) != visitor.VISIT_CONTINUE || visitor.count != 2) {
        Sys.Process().exit(15)
    }
}

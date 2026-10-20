include "parser.cw"

class SmallCFrontend {
    Sys.StandardIO io

    SmallCFrontend() {
        io = Sys.StandardIO()
    }

    String jsonString(String value) {
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

    String jsonAst(AstNode node) {
        String result = "{\"name\":"
        result.append(jsonString(node.name))
        result.append(",\"text\":")
        result.append(jsonString(node.text))
        result.append(",\"children\":[")
        int i = 0
        while (i < node.children.length) {
            if (i > 0) { result.append(",") }
            result.append(jsonAst(node.children[i] as AstNode))
            i += 1
        }
        result.append("]}")
        return result
    }

    void report(String path, String input, int offset, String problem) {
        int line = 1
        int column = 1
        int i = 0
        while (i < offset && i < input.length) {
            if (int(input.byteAt(i)) == 10) {
                line += 1
                column = 1
            }
            else { column += 1 }
            i += 1
        }
        io.writeErrorLine(format("{}:{}:{}: {}", path, line, column, problem))
    }

    int run() {
        Sys.Process process()
        if (process.argc() == 2 && process.arg(1).equals("--help")) {
            io.writeLine("usage: smallc-ast INPUT.c")
            io.writeLine("Parse the SmallC subset and print its JSON syntax AST; no semantic checks or execution.")
            return 0
        }
        if (process.argc() != 2) {
            io.writeErrorLine("usage: smallc-ast INPUT.c")
            return 2
        }
        String path = process.arg(1)
        if (!Sys.FileSystem().isFile(path)) {
            io.writeErrorLine(format("{}: input must be an existing file", path))
            return 1
        }
        String input = Sys.File(path, "r").readAll()
        InputScanner scanner(input)
        if (!scanner.scan()) {
            report(path, input, scanner.errorOffset, scanner.problem)
            return 1
        }
        GeneratedParser parser(scanner.tokens)
        AstNode root = parser.parseAll()
        if (root == null) {
            int offset = input.length
            if (parser.errorPosition < scanner.tokens.length) {
                offset = (scanner.tokens[parser.errorPosition] as LexToken).offset
            }
            report(path, input, offset, parser.problem)
            return 1
        }
        io.writeLine(jsonAst(root))
        return 0
    }
}

start {
    SmallCFrontend frontend()
    Sys.Process().exit(frontend.run())
}

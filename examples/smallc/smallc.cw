include "smallc_frontend.cw"

class SmallCASTApplication {
    Sys.StandardIO io

    SmallCASTApplication() {
        io = Sys.StandardIO()
    }

    int run() {
        Sys.Process process()
        if (process.argc() == 2 && process.arg(1).equals("--help")) {
            io.writeLine("usage: smallc-ast [--check] INPUT.c")
            io.writeLine("Parse SmallC to a JSON syntax AST; --check also validates the supported semantics.")
            return 0
        }
        bool checking = process.argc() == 3 && process.arg(1).equals("--check")
        if (process.argc() != 2 && !checking) {
            io.writeErrorLine("usage: smallc-ast [--check] INPUT.c")
            return 2
        }
        String path = process.arg(1)
        if (checking) { path = process.arg(2) }
        if (!Sys.FileSystem().isFile(path)) {
            io.writeErrorLine(format("{}: input must be an existing file", path))
            return 1
        }
        String input = Sys.File(path, "r").readAll()
        SmallCFrontend frontend()
        AstNode root = frontend.parseInput(input)
        if (root == null) {
            frontend.report(path, input, frontend.errorOffset, frontend.problem)
            return 1
        }
        if (checking && !frontend.check(root)) {
            frontend.report(path, input, frontend.errorOffset, frontend.problem)
            return 1
        }
        io.writeLine(frontend.jsonAst(root))
        return 0
    }
}

start {
    SmallCASTApplication application()
    Sys.Process().exit(application.run())
}

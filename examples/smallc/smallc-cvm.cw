import cvm as CVM
import cvmfile as CVMFile

include "smallc_frontend.cw"
include "smallc_backend.cw"

class SmallCCVMApplication {
    Sys.StandardIO io

    SmallCCVMApplication() {
        io = Sys.StandardIO()
    }

    int run() {
        Sys.Process process()
        if (process.argc() == 2 && process.arg(1).equals("--help")) {
            io.writeLine("usage: smallc-cvm INPUT.c OUTPUT.cvm")
            io.writeLine("Check SmallC and emit a validated CVM v1 binary.")
            return 0
        }
        if (process.argc() != 3) {
            io.writeErrorLine("usage: smallc-cvm INPUT.c OUTPUT.cvm")
            return 2
        }
        String inputPath = process.arg(1)
        String outputPath = process.arg(2)
        if (!Sys.FileSystem().isFile(inputPath)) {
            io.writeErrorLine(format("{}: input must be an existing file", inputPath))
            return 1
        }
        String input = Sys.File(inputPath, "r").readAll()
        SmallCFrontend frontend()
        AstNode root = frontend.parseInput(input)
        if (root == null) {
            frontend.report(inputPath, input, frontend.errorOffset, frontend.problem)
            return 1
        }
        if (!frontend.check(root)) {
            frontend.report(inputPath, input, frontend.errorOffset, frontend.problem)
            return 1
        }
        SmallCVMCompiler compiler()
        buffer program = compiler.compile(root, frontend)
        if (program == null) {
            int offset = frontend.offsetOf(compiler.errorNode)
            frontend.report(inputPath, input, offset, compiler.problem)
            return 1
        }
        CVMFile.Result written = CVMFile.Files().write(outputPath, program)
        if (!written.ok()) {
            io.writeErrorLine(format("{}: {}", outputPath, written.error()))
            return 1
        }
        return 0
    }
}

start {
    SmallCCVMApplication application()
    Sys.Process().exit(application.run())
}

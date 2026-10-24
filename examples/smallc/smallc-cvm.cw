include "smallc_frontend.cw"
include "smallc_backend.cw"

class SmallCCVMApplication {
    Sys.StandardIO io

    SmallCCVMApplication() {
        io = Sys.StandardIO()
    }

    int64 run() {
        Sys.Process process()
        if (process.argc() == 2 && process.arg(1).equals("--help")) {
            io.writeLine("usage: smallc-cvm INPUT.c OUTPUT.asm")
            io.writeLine("Check SmallC and emit textual CVM v1 assembly; assemble it with cvm-as.")
            return 0
        }
        if (process.argc() != 3) {
            io.writeErrorLine("usage: smallc-cvm INPUT.c OUTPUT.asm")
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
        SmallCAssemblyCompiler compiler()
        String assembly = compiler.compile(root, frontend)
        if (assembly == null) {
            int64 offset = frontend.offsetOf(compiler.errorNode)
            frontend.report(inputPath, input, offset, compiler.problem)
            return 1
        }
        Sys.File output = null
        try {
            output = Sys.File(outputPath, "w")
        } except(Exception) as error {
            io.writeErrorLine(format("{}: {}", outputPath, error.message))
            return 1
        }
        String failure = ""
        try {
            int64 count = output.write(assembly)
            failure = Sys.System().lastError()
            if (failure.equals("") && count != assembly.length) {
                failure = "could not write the complete assembly file"
            }
        } finally {
            output.close()
            String closeError = Sys.System().lastError()
            if (failure.equals("") && !closeError.equals("")) { failure = closeError }
        }
        if (!failure.equals("")) {
            io.writeErrorLine(format("{}: {}", outputPath, failure))
            return 1
        }
        return 0
    }
}

start {
    SmallCCVMApplication application()
    Sys.Process().exit(application.run())
}

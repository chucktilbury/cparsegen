import system as Sys

include "grammar.cw"
include "emitter.cw"

class GeneratorCli {
    Sys.StandardIO io
    Sys.Process process

    GeneratorCli() {
        io = Sys.StandardIO()
        process = Sys.Process()
    }

    int run() {
        if (process.argc() != 4) {
            io.writeErrorLine("usage: cparsegen GRAMMAR OUTPUT.cw OUTPUT.dot")
            return 2
        }

        String grammarPath = process.arg(1)
        String source = Sys.File(grammarPath, "r").readAll()
        GrammarReader reader(source)
        GrammarModel grammar = reader.read()
        if (!reader.problem.equals("")) {
            io.writeErrorLine(format("{}: {}", grammarPath, reader.problem))
            return 1
        }

        GrammarEmitter emitter(grammar)
        String program = emitter.emitProgram()
        String graph = emitter.emitDot()
        String programPath = process.arg(2)
        String graphPath = process.arg(3)
        Sys.File programFile(programPath, "w")
        Sys.File graphFile(graphPath, "w")
        if (programFile.write(program) != program.length) {
            io.writeErrorLine(format("{}: incomplete write", programPath))
            return 1
        }
        if (graphFile.write(graph) != graph.length) {
            io.writeErrorLine(format("{}: incomplete write", graphPath))
            return 1
        }
        programFile.close()
        graphFile.close()
        return 0
    }
}

start {
    GeneratorCli app()
    int result = app.run()
    Sys.Process().exit(result)
}

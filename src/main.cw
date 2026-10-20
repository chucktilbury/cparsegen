import system as Sys

include "grammar.cw"
include "emitter.cw"
include "c_emitter.cw"

class GeneratorCli {
    Sys.StandardIO io
    Sys.Process process

    GeneratorCli() {
        io = Sys.StandardIO()
        process = Sys.Process()
    }

    int run() {
        bool library = process.argc() == 5 && process.arg(1).equals("--library")
        bool cTarget = process.argc() == 6 && process.arg(1).equals("--target") && process.arg(2).equals("c")
        if (process.argc() != 4 && !library && !cTarget) {
            io.writeErrorLine("usage: cparsegen [--library | --target c] GRAMMAR OUTPUT OUTPUT.dot")
            return 2
        }

        int argument = 1
        if (library) { argument = 2 }
        if (cTarget) { argument = 3 }
        String grammarPath = process.arg(argument)
        String source = Sys.File(grammarPath, "r").readAll()
        GrammarReader reader(source)
        GrammarModel grammar = reader.read()
        if (!reader.problem.equals("")) {
            io.writeErrorLine(format("{}: {}", grammarPath, reader.problem))
            return 1
        }

        GrammarEmitter emitter(grammar)
        String program = ""
        if (cTarget) {
            CGrammarEmitter cEmitter(grammar, emitter)
            String problem = cEmitter.validate()
            if (!problem.equals("")) {
                io.writeErrorLine(format("{}: {}", grammarPath, problem))
                return 1
            }
            program = cEmitter.emitProgram()
        }
        else { program = emitter.emitProgram(library) }
        String graph = emitter.emitDot()
        String programPath = process.arg(argument + 1)
        String graphPath = process.arg(argument + 2)
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

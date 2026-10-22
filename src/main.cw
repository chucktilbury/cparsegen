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
        bool library = false
        bool cTarget = false
        bool valid = true
        list paths = []
        int argument = 1
        while (argument < process.argc() && process.arg(argument).startsWith("-")) {
            String option = process.arg(argument)
            argument += 1
            if (option.equals("--")) { break }
            if (option.equals("--library") && !library && !cTarget) { library = true }
            else {
                if (option.equals("--target") && !library && !cTarget && argument < process.argc()) {
                    cTarget = process.arg(argument).equals("c")
                    valid = cTarget
                    argument += 1
                }
                else {
                    if (option.equals("--include-path") && argument < process.argc()) {
                        String value = process.arg(argument)
                        int startIndex = 0
                        int end = 0
                        while (end <= value.length) {
                            if (end == value.length || int(value.byteAt(end)) == 58) {
                                String path = value.slice(startIndex, end)
                                if (path.equals("")) { path = "." }
                                paths.append(path)
                                startIndex = end + 1
                            }
                            end += 1
                        }
                        argument += 1
                    }
                    else { valid = false }
                }
            }
            if (!valid) { break }
        }
        if (!valid || process.argc() - argument != 3) {
            io.writeErrorLine("usage: cparsegen [--library | --target c] [--include-path DIR:DIR...] [--] GRAMMAR OUTPUT OUTPUT.dot")
            return 2
        }

        String grammarPath = process.arg(argument)
        GrammarSources reader(paths)
        GrammarModel grammar = reader.read(grammarPath)
        if (!reader.problem.equals("")) {
            io.writeErrorLine(reader.diagnostic(reader.problem))
            return 1
        }

        GrammarEmitter emitter(grammar)
        String program = ""
        if (cTarget) {
            CGrammarEmitter cEmitter(grammar, emitter)
            String problem = cEmitter.validate()
            if (!problem.equals("")) {
                reader.diagnosticSpan = cEmitter.diagnosticSpan
                reader.relatedSpan = cEmitter.relatedSpan
                reader.diagnosticInfo = cEmitter.diagnosticInfo
                io.writeErrorLine(reader.diagnostic(problem))
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

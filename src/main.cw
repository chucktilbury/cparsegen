import system as Sys

include "grammar.cw"
include "analysis.cw"
include "emitter.cw"
include "c_emitter.cw"

class FileIdentity {
    int sameFile(String first, String second)
}

int FileIdentity.sameFile(String first, String second) from "cparsegen_same_file"

class GeneratorCli {
    Sys.StandardIO io
    Sys.Process process

    GeneratorCli() {
        io = Sys.StandardIO()
        process = Sys.Process()
    }

    String defaultOutput(String grammarPath, bool cTarget) {
        int extension = grammarPath.length
        int i = grammarPath.length - 1
        while (i >= 0 && int(grammarPath.byteAt(i)) != 47) {
            if (int(grammarPath.byteAt(i)) == 46 && extension == grammarPath.length) {
                extension = i
            }
            i -= 1
        }
        // A leading dot alone is a basename, not an extension.
        if (extension == i + 1) { extension = grammarPath.length }
        String suffix = ".cw"
        if (cTarget) { suffix = ".c" }
        return format("{}{}", grammarPath.slice(0, extension), suffix)
    }

    String pathKey(String path) {
        Sys.FileSystem fs()
        String resolved = fs.absolutePath(path)
        if (!resolved.equals("")) { return resolved }
        String parent = fs.absolutePath(fs.dirname(path))
        if (parent.equals("")) { return "" }
        return fs.join(parent, fs.basename(path))
    }

    bool distinctPaths(String first, String second) {
        int same = FileIdentity().sameFile(first, second)
        String firstKey = pathKey(first)
        String secondKey = pathKey(second)
        if (same < 0 || firstKey.equals("") || secondKey.equals("")) {
            io.writeErrorLine(format("cannot resolve output paths: {} and {}", first, second))
            return false
        }
        if (same == 1 || firstKey.equals(secondKey)) {
            io.writeErrorLine(format("path collision: {} and {}", first, second))
            return false
        }
        return true
    }

    int run() {
        bool library = false
        bool cTarget = false
        bool valid = true
        list paths = []
        list positional = []
        bool options = true
        bool dot = false
        String graphPath = ""
        int argument = 1
        while (argument < process.argc()) {
            String option = process.arg(argument)
            argument += 1
            if (options && option.equals("--")) {
                options = false
                continue
            }
            if (!options || !option.startsWith("-")) {
                positional.append(option)
                continue
            }
            if (option.equals("--library") && !library && !cTarget) {
                library = true
                continue
            }
            if (option.equals("--target") && !library && !cTarget && argument < process.argc()) {
                if (!process.arg(argument).equals("c")) {
                    valid = false
                    break
                }
                cTarget = true
                argument += 1
                continue
            }
            if (option.equals("--dot") && !dot && argument < process.argc()) {
                graphPath = process.arg(argument)
                if (graphPath.equals("") || graphPath.startsWith("--")) {
                    valid = false
                    break
                }
                dot = true
                argument += 1
                continue
            }
            if (option.equals("--include-path") && argument < process.argc()) {
                String value = process.arg(argument)
                if (value.startsWith("--")) {
                    valid = false
                    break
                }
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
                continue
            }
            valid = false
            break
        }
        if (positional.length < 1 || positional.length > 2) { valid = false }
        int index = 0
        while (index < positional.length) {
            if ((positional[index] as String).equals("")) { valid = false }
            index += 1
        }
        if (!valid) {
            io.writeErrorLine("usage: cparsegen [--library | --target c] [--include-path DIR:DIR...] [--dot FILE] [--] GRAMMAR [OUTPUT]")
            return 2
        }

        String grammarPath = positional[0] as String
        String programPath = defaultOutput(grammarPath, cTarget)
        if (positional.length == 2) { programPath = positional[1] as String }
        GrammarSources reader(paths)
        GrammarModel grammar = reader.read(grammarPath)
        if (!reader.problem.equals("")) {
            io.writeErrorLine(reader.diagnostic(reader.problem))
            return 1
        }

        if (dot && !distinctPaths(programPath, graphPath)) { return 1 }
        index = 0
        while (index < reader.files.length) {
            GrammarSource source = reader.files[index] as GrammarSource
            if (!distinctPaths(source.path, programPath)) { return 1 }
            if (dot && !distinctPaths(source.path, graphPath)) { return 1 }
            index += 1
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
        String graph = ""
        if (dot) { graph = emitter.emitDot() }
        Sys.File programFile(programPath, "w")
        if (programFile.write(program) != program.length) {
            io.writeErrorLine(format("{}: incomplete write", programPath))
            return 1
        }
        programFile.close()
        if (dot) {
            Sys.File graphFile(graphPath, "w")
            if (graphFile.write(graph) != graph.length) {
                io.writeErrorLine(format("{}: incomplete write", graphPath))
                return 1
            }
            graphFile.close()
        }
        return 0
    }
}

start {
    GeneratorCli app()
    int result = app.run()
    Sys.Process().exit(result)
}

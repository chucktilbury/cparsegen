import system as Sys
import cli as Cli

include "grammar.cw"
include "analysis.cw"
include "emitter.cw"
include "c_emitter.cw"

class FileIdentity {
    int64 sameFile(String first, String second)
}

int64 FileIdentity.sameFile(String first, String second) from "cparsegen_same_file"

class GeneratorCli {
    Sys.StandardIO io
    Sys.Process process

    GeneratorCli() {
        io = Sys.StandardIO()
        process = Sys.Process()
    }

    String defaultOutput(String grammarPath, bool cTarget) {
        int64 extension = grammarPath.length
        int64 i = grammarPath.length - 1
        while (i >= 0 && int64(grammarPath[i]) != 47) {
            if (int64(grammarPath[i]) == 46 && extension == grammarPath.length) {
                extension = i
            }
            i -= 1
        }
        // A leading dot alone is a basename, not an extension.
        if (extension == i + 1) { extension = grammarPath.length }
        String suffix = ".cw"
        if (cTarget) { suffix = ".c" }
        return(format("{}{}", byteSpan(grammarPath, 0, extension), suffix))
    }

    String pathKey(String path) {
        Sys.FileSystem fs()
        String resolved = fs.absolutePath(path)
        if (!resolved.equals("")) { return(resolved) }
        String parent = fs.absolutePath(fs.dirname(path))
        if (parent.equals("")) { return("") }
        return(fs.join(parent, fs.basename(path)))
    }

    bool distinctPaths(String first, String second) {
        int64 same = FileIdentity().sameFile(first, second)
        String firstKey = pathKey(first)
        String secondKey = pathKey(second)
        if (same < 0 || firstKey.equals("") || secondKey.equals("")) {
            io.writeErrorLine(format("cannot resolve output paths: {} and {}", first, second))
            return(false)
        }
        if (same == 1 || firstKey.equals(secondKey)) {
            io.writeErrorLine(format("path collision: {} and {}", first, second))
            return(false)
        }
        return(true)
    }

    Cli.CommandLine parser() {
        Cli.CommandLine commandLine = Cli.CommandLine("cparsegen", "grammar code generator", "1.0.0")
        Cli.Option library = Cli.Option()
        library.longName = "library"
        library.name = "library"
        library.description = "emit a Cwhip library module"
        library.valueType = Cli.ValueType().COUNTER
        commandLine.addOption(library)
        Cli.Option target = Cli.Option()
        target.longName = "target"
        target.name = "target"
        target.description = "output language (c)"
        target.valueType = Cli.ValueType().STRING
        target.isList = true
        commandLine.addOption(target)
        Cli.Option dot = Cli.Option()
        dot.longName = "dot"
        dot.name = "dot"
        dot.description = "write a Graphviz DOT file"
        dot.valueType = Cli.ValueType().STRING
        dot.isList = true
        commandLine.addOption(dot)
        Cli.Option includePath = Cli.Option()
        includePath.longName = "include-path"
        includePath.name = "include-path"
        includePath.description = "colon-separated include directories"
        includePath.valueType = Cli.ValueType().STRING
        includePath.isList = true
        // Keep each --include-path argument intact; colon splitting matches the
        // historical empty-component rules in run().
        includePath.listSeparator = "\n"
        commandLine.addOption(includePath)
        Cli.Positional grammar = Cli.Positional()
        grammar.name = "grammar"
        grammar.description = "grammar input"
        grammar.required = true
        commandLine.addPositional(grammar)
        Cli.Positional output = Cli.Positional()
        output.name = "output"
        output.description = "output path"
        commandLine.addPositional(output)
        return(commandLine)
    }

    int64 run() {
        Cli.CommandLine commandLine = parser()
        try {
            commandLine.parseArgv()
        } except() {
            io.writeErrorLine("usage: cparsegen [--library | --target c] [--include-path DIR:DIR...] [--dot FILE] [--] GRAMMAR [OUTPUT]")
            return(2)
        }
        bool valid = true
        if (commandLine.count("library") > 1) { valid = false }
        bool library = commandLine.count("library") == 1
        bool cTarget = false
        list targetValues = commandLine.valuesFor("target")
        if (targetValues.length > 1) { valid = false }
        if (targetValues.length == 1) {
            if (!(targetValues[0] as String).equals("c")) { valid = false }
            else { cTarget = true }
        }
        if (library && cTarget) { valid = false }
        list dotValues = commandLine.valuesFor("dot")
        bool dot = false
        String graphPath = ""
        if (dotValues.length > 1) { valid = false }
        if (dotValues.length == 1) {
            graphPath = dotValues[0] as String
            if (graphPath.equals("") or graphPath.startsWith("--")) { valid = false }
            else { dot = true }
        }
        list paths = []
        list includeValues = commandLine.valuesFor("include-path")
        int64 includeIndex = 0
        while (includeIndex < includeValues.length) {
            String value = includeValues[includeIndex] as String
            if (value.startsWith("--")) { valid = false }
            int64 startIndex = 0
            int64 end = 0
            while (end <= value.length) {
                bool atColon = false
                if (end < value.length) {
                    if (int64(value[end]) == 58) { atColon = true }
                }
                if (end == value.length or atColon) {
                    String path = byteSpan(value, startIndex, end)
                    if (path.equals("")) { path = "." }
                    paths.append(path)
                    startIndex = end + 1
                }
                end = end + 1
            }
            includeIndex = includeIndex + 1
        }
        list positional = commandLine.allPositionalValues()
        if (positional.length < 1 || positional.length > 2) { valid = false }
        int64 index = 0
        while (index < positional.length) {
            if ((positional[index] as String).equals("")) { valid = false }
            index += 1
        }
        if (!valid) {
            io.writeErrorLine("usage: cparsegen [--library | --target c] [--include-path DIR:DIR...] [--dot FILE] [--] GRAMMAR [OUTPUT]")
            return(2)
        }

        String grammarPath = positional[0] as String
        String programPath = defaultOutput(grammarPath, cTarget)
        if (positional.length == 2) { programPath = positional[1] as String }
        GrammarSources reader(paths)
        GrammarModel grammar = reader.read(grammarPath)
        if (!reader.problem.equals("")) {
            io.writeErrorLine(reader.diagnostic(reader.problem))
            return(1)
        }

        if (dot && !distinctPaths(programPath, graphPath)) { return(1) }
        index = 0
        while (index < reader.files.length) {
            GrammarSource source = reader.files[index] as GrammarSource
            if (!distinctPaths(source.path, programPath)) { return(1) }
            if (dot && !distinctPaths(source.path, graphPath)) { return(1) }
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
                return(1)
            }
            program = cEmitter.emitProgram()
        }
        else { program = emitter.emitProgram(library) }
        String graph = ""
        if (dot) { graph = emitter.emitDot() }
        Sys.File programFile(programPath, "w")
        if (programFile.write(program) != program.length) {
            io.writeErrorLine(format("{}: incomplete write", programPath))
            return(1)
        }
        programFile.close()
        if (dot) {
            Sys.File graphFile(graphPath, "w")
            if (graphFile.write(graph) != graph.length) {
                io.writeErrorLine(format("{}: incomplete write", graphPath))
                return(1)
            }
            graphFile.close()
        }
        return(0)
    }

    int64 byteSpanBound(int64 value, int64 length) {
        int64 index = value
        if (index < 0) { index = index + length }
        if (index < 0) { return(0) }
        if (index > length) { return(length) }
        return(index)
    }
    String byteSpan(String text, int64 first, int64 last) {
        int64 lower = byteSpanBound(first, text.length)
        int64 end = byteSpanBound(last, text.length)
        if (end <= lower) { return("") }
        return(text[lower..(end - 1)])
    }
}

start {
    GeneratorCli app()
    int64 result = app.run()
    Sys.Process().exit(result)
}

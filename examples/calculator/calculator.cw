include "parser.cw"

class Variable {
    String name
    float value

    Variable(String variableName, float number) {
        name = variableName
        value = number
    }
}

class Calculator {
    list variables
    String problem
    Sys.StandardIO io
    bool endOfInput

    Calculator() {
        variables = []
        problem = ""
        io = Sys.StandardIO()
        endOfInput = false
    }

    AstNode child(AstNode node, int index) {
        return node.children[index] as AstNode
    }

    Variable findVariable(String name) {
        int i = 0
        while (i < variables.length) {
            Variable variable = variables[i] as Variable
            if (variable.name.equals(name)) { return variable }
            i += 1
        }
        return null
    }

    float evaluate(AstNode node) {
        if (!problem.equals("")) { return 0.0 }
        if (node.name.equals("number")) {
            String spelling = ""
            int i = 0
            while (i < node.children.length) {
                spelling.append(child(node, i).text)
                i += 1
            }
            return spelling.toFloat()
        }
        if (node.name.equals("IDENT")) {
            Variable variable = findVariable(node.text)
            if (variable == null) {
                problem = format("undefined variable '{}'", node.text)
                return 0.0
            }
            return variable.value
        }
        if (node.name.equals("primary")) {
            if (node.children.length == 3) { return evaluate(child(node, 1)) }
            return evaluate(child(node, 0))
        }
        if (node.name.equals("unary")) {
            if (node.children.length == 1) { return evaluate(child(node, 0)) }
            float value = evaluate(child(node, 1))
            if (child(node, 0).text.equals("-")) { return -value }
            return value
        }
        if (node.name.equals("expression") || node.name.equals("product")) {
            float result = evaluate(child(node, 0))
            int i = 1
            while (i < node.children.length && problem.equals("")) {
                String operation = child(node, i).text
                float value = evaluate(child(node, i + 1))
                if (!problem.equals("")) { return 0.0 }
                if (operation.equals("+")) { result += value }
                else {
                    if (operation.equals("-")) { result -= value }
                    else {
                        if (operation.equals("*")) { result *= value }
                        else {
                            if (value == 0.0) {
                                problem = "division by zero"
                                return 0.0
                            }
                            result /= value
                        }
                    }
                }
                i += 2
            }
            return result
        }
        problem = format("unexpected AST node '{}'", node.name)
        return 0.0
    }

    bool execute(String text) {
        problem = ""
        InputScanner scanner(text)
        if (!scanner.scan()) {
            problem = scanner.problem
            return false
        }
        GeneratedParser parser(scanner.tokens)
        AstNode statement = parser.parseAll()
        if (statement == null) {
            problem = parser.problem
            return false
        }
        bool assignment = statement.children.length == 3
        int expressionIndex = 0
        if (assignment) { expressionIndex = 2 }
        float value = evaluate(child(statement, expressionIndex))
        if (!problem.equals("")) { return false }
        if (assignment) {
            String name = child(statement, 0).text
            Variable variable = findVariable(name)
            if (variable == null) { variables.append(Variable(name, value)) }
            else { variable.value = value }
            io.writeLine(format("{} = {}", name, value))
        }
        else { io.writeLine(format("{}", value)) }
        return true
    }

    void listVariables() {
        int i = 0
        while (i < variables.length) {
            Variable variable = variables[i] as Variable
            io.writeLine(format("{} = {}", variable.name, variable.value))
            i += 1
        }
    }

    String readInputLine() {
        // StandardIO.readLine() cannot distinguish a blank line from EOF.
        String line = ""
        while (!endOfInput) {
            String byte = io.read(1)
            if (byte == null || byte.length == 0) {
                endOfInput = true
                break
            }
            if (byte.equals("\n")) { break }
            line.append(byte)
        }
        return line
    }

    int run() {
        Sys.Process process()
        if (process.argc() == 3 && process.arg(1).equals("-e")) {
            if (execute(process.arg(2))) { return 0 }
            io.writeErrorLine(format("error: {}", problem))
            return 1
        }
        bool batch = process.argc() == 2 && process.arg(1).equals("--batch")
        if (process.argc() == 2 && process.arg(1).equals("--help")) {
            io.writeLine("usage: calculator [-e EXPRESSION | --batch | --help]")
            io.writeLine("Without arguments: interactive CLI. Commands: :help, :vars, :quit")
            return 0
        }
        if (process.argc() != 1 && !batch) {
            io.writeErrorLine("usage: calculator [-e EXPRESSION | --batch | --help]")
            return 2
        }
        if (!batch) { io.writeLine("Calculator: :help for help, :quit to exit.") }
        int status = 0
        while (true) {
            if (!batch) { io.write("calc> ") }
            String input = readInputLine()
            if (endOfInput && input.length == 0) { break }
            String line = input.trim()
            if (line.equals(":quit")) { break }
            if (line.equals(":help")) {
                io.writeLine("Numbers, variables, =, +, -, *, /, parentheses. One statement per line.")
                io.writeLine(":vars lists variables; :quit exits. Example: x = 2 + 3 * 4")
            }
            else {
                if (line.equals(":vars")) { listVariables() }
                else {
                    if (line.length > 0 && !execute(line)) {
                        io.writeErrorLine(format("error: {}", problem))
                        status = 1
                    }
                }
            }
        }
        return status
    }
}

start {
    Calculator calculator()
    Sys.Process().exit(calculator.run())
}

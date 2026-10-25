// Lowers a checked SmallC AST to textual CVM v1 assembly (see CVM's
// doc/BYTECODE-ASSEMBLY.md). This backend never encodes CVM binary data: the
// separately installed `cvm-as` assembler resolves symbols, branch offsets,
// stack metadata and the container layout.

class SmallCAsmCode {
    String text
    int64 labelCounter

    SmallCAsmCode() {
        text = ""
        labelCounter = 0
    }

    void op(String instruction) {
        text.append("    ")
        text.append(instruction)
        text.append("\n")
    }

    void op1(String mnemonic, String operand) {
        op(format("{} {}", mnemonic, operand))
    }

    String newLabel() {
        String result = format("L{}", labelCounter)
        labelCounter += 1
        return(result)
    }

    void mark(String name) {
        text.append(name)
        text.append(":\n")
    }
}

class SmallCAsmVariable {
    String name
    String valueType
    bool global
    bool array
    int64 index
    String asmName

    SmallCAsmVariable(String variableName, String variableType,
            bool isGlobal, bool isArray, int64 tableIndex, String symbol) {
        name = variableName
        valueType = variableType
        global = isGlobal
        array = isArray
        index = tableIndex
        asmName = symbol
    }
}

class SmallCAsmScope {
    list variables
    SmallCAsmScope parent

    SmallCAsmScope(SmallCAsmScope outer) {
        variables = []
        parent = outer
    }
}

class SmallCAsmFunction {
    String name
    String asmName
    String returnType
    AstNode declaration
    AstNode parameters
    AstNode body
    list parameterTypes
    list parameterSymbols
    int64 localCount
    list declarations
    bool defined

    SmallCAsmFunction(String functionName, String resultType) {
        name = functionName
        asmName = format("sc_{}", functionName)
        returnType = resultType
        declaration = null
        parameters = null
        body = null
        parameterTypes = []
        parameterSymbols = []
        localCount = 0
        declarations = []
        defined = false
    }
}

class SmallCAsmArray {
    String asmName
    String elementType
    int64 length
    String staticInitializer
    bool isGlobal

    SmallCAsmArray(String symbol, String valueType, int64 capacity) {
        asmName = symbol
        elementType = valueType
        length = capacity
        staticInitializer = ""
        isGlobal = false
    }
}

class SmallCAsmLoop {
    String breakLabel
    String continueLabel
    SmallCAsmLoop parent

    SmallCAsmLoop(String breakTarget, String continueTarget,
            SmallCAsmLoop outer) {
        breakLabel = breakTarget
        continueLabel = continueTarget
        parent = outer
    }
}

class SmallCAssemblyCompiler {
    SmallCAsmFunction entryFunction
    list functions
    list globals
    list arrays
    list globalInitializers
    SmallCAsmFunction currentFunction
    SmallCAsmCode code
    SmallCAsmScope scope
    SmallCAsmLoop loop
    SmallCFrontend frontend
    SmallCIntrinsics intrinsics
    String problem
    AstNode errorNode
    int64 scalarGlobalCount
    String functionText

    SmallCAssemblyCompiler() {
        functions = []
        globals = []
        arrays = []
        globalInitializers = []
        entryFunction = null
        currentFunction = null
        code = null
        scope = null
        loop = null
        frontend = null
        intrinsics = SmallCIntrinsics()
        problem = ""
        errorNode = null
        scalarGlobalCount = 0
        functionText = ""
    }

    AstNode child(AstNode node, int64 index) {
        return(node.children[index] as AstNode)
    }

    void fail(AstNode node, String message) {
        if (problem.equals("")) {
            problem = message
            errorNode = node
        }
    }

    String elementType(String valueType) {
        if (valueType.equals("int[]")) { return("int") }
        if (valueType.equals("char[]")) { return("char") }
        return(valueType)
    }

    String asmType(String valueType) {
        if (valueType.equals("int") || valueType.equals("int[]")) { return("i32") }
        if (valueType.equals("char") || valueType.equals("char[]")) { return("u8") }
        return("void")
    }

    SmallCAsmFunction findFunction(String name) {
        int64 i = 0
        while (i < functions.length) {
            SmallCAsmFunction function = functions[i] as SmallCAsmFunction
            if (function.name.equals(name)) { return(function) }
            i += 1
        }
        return(null)
    }

    SmallCAsmVariable findGlobal(String name) {
        int64 i = 0
        while (i < globals.length) {
            SmallCAsmVariable variable = globals[i] as SmallCAsmVariable
            if (variable.name.equals(name)) { return(variable) }
            i += 1
        }
        return(null)
    }

    SmallCAsmVariable findVariable(String name) {
        SmallCAsmScope current = scope
        while (current != null) {
            int64 i = current.variables.length - 1
            while (i >= 0) {
                SmallCAsmVariable variable = current.variables[i] as SmallCAsmVariable
                if (variable.name.equals(name)) { return(variable) }
                i -= 1
            }
            current = current.parent
        }
        return(findGlobal(name))
    }

    void pushScope() {
        scope = SmallCAsmScope(scope)
    }

    void popScope() {
        if (scope != null) { scope = scope.parent }
    }

    int64 slotCount() {
        return(currentFunction.parameterTypes.length + currentFunction.localCount)
    }

    // Declares a scalar local in the current function and returns its symbol.
    String declareLocal(String name, String valueType, String prefix) {
        int64 slot = slotCount()
        String symbol = format("{}{}", prefix, slot)
        if (!name.equals("")) { symbol = format("{}{}_{}", prefix, slot, name) }
        currentFunction.localCount += 1
        currentFunction.declarations.append(
            format("    .local {}: {}\n", symbol, asmType(valueType)))
        return(symbol)
    }

    void addLocal(String name, String valueType) {
        String symbol = declareLocal(name, valueType, "v")
        scope.variables.append(SmallCAsmVariable(name, valueType, false, false, 0, symbol))
    }

    String addTemporary(String valueType) {
        return(declareLocal("", valueType, "t"))
    }

    int64 integerValue(String spelling, int64 limit, AstNode node) {
        int64 value = 0
        int64 i = 0
        while (i < spelling.length && problem.equals("")) {
            int64 digit = int64(spelling.byteAt(i)) - 48
            if (digit < 0 || digit > 9 || value > (limit - digit) / 10) {
                fail(node, format("integer literal '{}' is outside the CVM i32 range", spelling))
                return(0)
            }
            value = value * 10 + digit
            i += 1
        }
        return(value)
    }

    bool isMinimumIntegerLiteral(String spelling) {
        int64 first = 0
        while (first + 1 < spelling.length
                && int64(spelling.byteAt(first)) == 48) { first += 1 }
        return(spelling.slice(first, spelling.length).equals("2147483648"))
    }

    int64 decodeEscape(int64 value) {
        if (value == 110) { return(10) }
        if (value == 114) { return(13) }
        if (value == 116) { return(9) }
        if (value == 48) { return(0) }
        return(value)
    }

    int64 characterValue(String spelling) {
        int64 value = int64(spelling.byteAt(1))
        if (value == 92) { value = decodeEscape(int64(spelling.byteAt(2))) }
        return(value)
    }

    buffer stringBytes(String spelling) {
        buffer bytes = buffer[]
        int64 i = 1
        while (i + 1 < spelling.length) {
            int64 value = int64(spelling.byteAt(i))
            if (value == 92) {
                i += 1
                value = decodeEscape(int64(spelling.byteAt(i)))
            }
            bytes.append(value)
            i += 1
        }
        return(bytes)
    }

    String hexByte(int64 value) {
        String digits = "0123456789abcdef"
        return(format("{}{}", digits.slice(value / 16, value / 16 + 1),
            digits.slice(value % 16, value % 16 + 1)))
    }

    // Quotes decoded bytes as a CVM assembly string literal. Everything except
    // a conservative printable set is written as an exact \xHH escape, so
    // quotes, backslashes, semicolons, NULs and non-ASCII bytes survive.
    String assemblyString(buffer bytes) {
        String safe = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 _-.,:/!?()[]{}+=<>*&%#@^~|"
        String result = "\""
        int64 i = 0
        while (i < bytes.length) {
            int64 value = int64(bytes[i])
            int64 s = 0
            bool printable = false
            while (s < safe.length && !printable) {
                if (int64(safe.byteAt(s)) == value) { printable = true }
                else { s += 1 }
            }
            if (printable) { result.append(safe.slice(s, s + 1)) }
            else {
                result.append("\\x")
                result.append(hexByte(value))
            }
            i += 1
        }
        result.append("\"")
        return(result)
    }

    int64 initializerCount(AstNode initializer) {
        if (initializer == null) { return(0) }
        if (initializer.children.length == 1
                && child(initializer, 0).name.equals("STRING")) {
            return(stringBytes(child(initializer, 0).text).length + 1)
        }
        int64 count = 0
        int64 i = 0
        while (i < initializer.children.length) {
            if (child(initializer, i).name.equals("assignment")) { count += 1 }
            i += 1
        }
        return(count)
    }

    AstNode declarationInitializer(AstNode declarator) {
        int64 i = 1
        while (i < declarator.children.length
                && !child(declarator, i).text.equals("=")) { i += 1 }
        if (i < declarator.children.length && i + 1 < declarator.children.length) {
            return(child(declarator, i + 1))
        }
        return(null)
    }

    int64 declaredArrayLength(AstNode declarator, AstNode initializer) {
        if (declarator.children.length > 2
                && child(declarator, 2).name.equals("INTEGER")) {
            return(integerValue(child(declarator, 2).text, 2147483647, child(declarator, 2)))
        }
        return(initializerCount(initializer))
    }

    // Decimal spelling of a plain (optionally signed) literal expression, or
    // "" when the expression must be evaluated at run time.
    String literalText(AstNode node, String valueType) {
        AstNode current = node
        bool negative = false
        bool signSeen = false
        while (!current.name.equals("")) {
            if (current.name.equals("INTEGER")) {
                if (!valueType.equals("int")) { return("") }
                if (negative && isMinimumIntegerLiteral(current.text)) { return("-2147483648") }
                int64 value = integerValue(current.text, 2147483647, current)
                if (negative && value != 0) { return(format("-{}", value)) }
                return(format("{}", value))
            }
            if (current.name.equals("CHAR")) {
                if (!valueType.equals("char") || signSeen) { return("") }
                return(format("{}", characterValue(current.text)))
            }
            if (current.name.equals("unary") && current.children.length == 2
                    && !signSeen
                    && (child(current, 0).text.equals("-") || child(current, 0).text.equals("+"))) {
                negative = child(current, 0).text.equals("-")
                signSeen = true
                current = child(current, 1)
            }
            else {
                if (current.children.length == 1
                        && !current.name.equals("lvalue")) {
                    current = child(current, 0)
                }
                else { return("") }
            }
        }
        return("")
    }

    // Returns an assembly array initializer for a global when every element
    // is constant and fits, or "" to initialize with code before main runs.
    String staticArrayInitializer(String arrayElementType, int64 length,
            AstNode initializer, String name) {
        if (initializer == null) { return("") }
        if (initializer.children.length == 1
                && child(initializer, 0).name.equals("STRING")) {
            buffer bytes = stringBytes(child(initializer, 0).text)
            if (bytes.length > length) {
                fail(initializer, format("string initializer for '{}' exceeds array capacity {}",
                    name, length))
                return("")
            }
            if (bytes.length == length) { return("") }
            return(assemblyString(bytes))
        }
        if (initializerCount(initializer) > length) {
            fail(initializer, format("too many elements in initializer for '{}'", name))
            return("")
        }
        String result = "{"
        int64 count = 0
        int64 i = 0
        while (i < initializer.children.length && problem.equals("")) {
            AstNode value = child(initializer, i)
            if (value.name.equals("assignment")) {
                String literal = literalText(value, arrayElementType)
                if (literal.equals("")) { return("") }
                if (count > 0) { result.append(", ") }
                result.append(literal)
                count += 1
            }
            i += 1
        }
        result.append("}")
        return(result)
    }

    void collectGlobalDeclaration(AstNode declaration) {
        String baseType = child(child(declaration, 0), 0).text
        int64 i = 1
        while (i < declaration.children.length && problem.equals("")) {
            AstNode declarator = child(declaration, i)
            if (declarator.name.equals("declarator")) {
                AstNode nameNode = child(declarator, 0)
                bool isArray = declarator.children.length > 1 && child(declarator, 1).text.equals("[")
                AstNode initializer = declarationInitializer(declarator)
                bool needsCode = initializer != null
                if (isArray) {
                    int64 length = declaredArrayLength(declarator, initializer)
                    if (length <= 0) {
                        fail(nameNode, format("array '{}' requires a positive fixed size or inferable initializer", nameNode.text))
                    }
                    else {
                        String arrayElementType = "int"
                        String arrayType = "int[]"
                        if (baseType.equals("char")) {
                            arrayElementType = "char"
                            arrayType = "char[]"
                        }
                        SmallCAsmArray array = SmallCAsmArray(
                            format("a{}_{}", arrays.length, nameNode.text),
                            arrayElementType, length)
                        array.staticInitializer = staticArrayInitializer(
                            arrayElementType, length, initializer, nameNode.text)
                        if (!array.staticInitializer.equals("")) { needsCode = false }
                        array.isGlobal = true
                        arrays.append(array)
                        globals.append(SmallCAsmVariable(
                            nameNode.text, arrayType, true, true, arrays.length - 1,
                            array.asmName))
                    }
                }
                else {
                    SmallCAsmVariable variable = SmallCAsmVariable(
                        nameNode.text, baseType, true, false, scalarGlobalCount,
                        format("g_{}", nameNode.text))
                    globals.append(variable)
                    scalarGlobalCount += 1
                }
                if (needsCode && problem.equals("")) {
                    globalInitializers.append([declarator, initializer])
                }
            }
            i += 1
        }
    }

    void collectFunction(AstNode external) {
        String resultType = child(child(external, 0), 0).text
        AstNode nameNode = child(external, 1)
        SmallCAsmFunction function = findFunction(nameNode.text)
        if (function == null) {
            function = SmallCAsmFunction(nameNode.text, resultType)
            functions.append(function)
        }
        function.parameterTypes = []
        function.parameters = null
        function.declaration = nameNode
        int64 i = 0
        while (i < external.children.length) {
            AstNode part = child(external, i)
            if (part.name.equals("parameters")) {
                function.parameters = part
                int64 p = 0
                while (p < part.children.length) {
                    AstNode parameter = child(part, p)
                    if (parameter.name.equals("parameter")) {
                        function.parameterTypes.append(
                            child(child(parameter, 0), 0).text)
                    }
                    p += 1
                }
            }
            if (part.name.equals("compoundStatement")) { function.body = part }
            i += 1
        }
    }

    bool collectProgram(AstNode root) {
        int64 i = 0
        while (i < root.children.length && problem.equals("")) {
            AstNode external = child(root, i)
            if (external.children.length > 0) {
                AstNode declaration = child(external, 0)
                if (declaration.name.equals("declaration")) {
                    collectGlobalDeclaration(declaration)
                }
                else { collectFunction(external) }
            }
            i += 1
        }
        if (!problem.equals("")) { return(false) }
        entryFunction = findFunction("main")
        if (entryFunction == null || entryFunction.body == null) {
            fail(root, "SmallC program requires a definition of main()")
            return(false)
        }
        if (!entryFunction.returnType.equals("int")
                || entryFunction.parameterTypes.length != 0) {
            fail(entryFunction.declaration, "CVM entry point main must have type int main()")
            return(false)
        }
        int64 f = 0
        while (f < functions.length) {
            SmallCAsmFunction function = functions[f] as SmallCAsmFunction
            if (function.body != null) { function.defined = true }
            f += 1
        }
        return(true)
    }

    // Returns the complete assembly source, or null with `problem` set.
    String compile(AstNode root, SmallCFrontend frontendModel) {
        frontend = frontendModel
        problem = ""
        errorNode = root
        functionText = ""
        if (!collectProgram(root)) { return(null) }
        String initText = compileGlobalInitializers()
        if (!problem.equals("")) { return(null) }
        int64 i = 0
        while (i < functions.length && problem.equals("")) {
            SmallCAsmFunction function = functions[i] as SmallCAsmFunction
            if (function.defined) { compileUserFunction(function) }
            i += 1
        }
        if (!problem.equals("")) { return(null) }
        return(assemble(initText))
    }

    String assemble(String initText) {
        String result = "; SmallC compiler output: CVM v1 assembly.\n"
        result.append("; Assemble with: cvm-as INPUT.asm -o OUTPUT.cvm\n")
        result.append(".version 1.0\n.entry main\n")
        bool hasData = false
        int64 i = 0
        while (i < globals.length) {
            SmallCAsmVariable variable = globals[i] as SmallCAsmVariable
            if (!variable.array) {
                if (!hasData) { result.append("\n") }
                hasData = true
                result.append(format(".global {}: {} = 0\n", variable.asmName,
                    asmType(variable.valueType)))
            }
            i += 1
        }
        i = 0
        while (i < arrays.length) {
            SmallCAsmArray array = arrays[i] as SmallCAsmArray
            if (!array.isGlobal) {
                i += 1
                continue
            }
            if (!hasData) { result.append("\n") }
            hasData = true
            result.append(format(".array {}: {}[{}]", array.asmName,
                asmType(array.elementType), array.length))
            if (!array.staticInitializer.equals("")) {
                result.append(format(" = {}", array.staticInitializer))
            }
            result.append("\n")
            i += 1
        }
        result.append("\n.func main() -> i32\n")
        if (!initText.equals("")) { result.append("    call smallc_init_globals\n") }
        result.append(format("    call {}\n    ret.i32\n.end\n", entryFunction.asmName))
        if (!initText.equals("")) { result.append(initText) }
        result.append(functionText)
        return(result)
    }

    String compileGlobalInitializers() {
        if (globalInitializers.length == 0) { return("") }
        currentFunction = SmallCAsmFunction("smallc_init_globals", "void")
        code = SmallCAsmCode()
        scope = null
        loop = null
        int64 i = 0
        while (i < globalInitializers.length && problem.equals("")) {
            list pair = globalInitializers[i] as list
            AstNode declarator = pair[0] as AstNode
            AstNode initializer = pair[1] as AstNode
            SmallCAsmVariable variable = findGlobal(child(declarator, 0).text)
            if (variable != null && variable.array) {
                emitArrayInitializer(variable, initializer)
            }
            else {
                emitExpression(child(initializer, 0))
                emitStore(variable)
                code.op("pop")
            }
            i += 1
        }
        if (!problem.equals("")) { return("") }
        code.op("ret")
        String result = "\n.func smallc_init_globals() -> void\n"
        result.append(declarationText())
        result.append(code.text)
        result.append(".end\n")
        return(result)
    }

    String declarationText() {
        String result = ""
        int64 i = 0
        while (i < currentFunction.declarations.length) {
            result.append(currentFunction.declarations[i] as String)
            i += 1
        }
        return(result)
    }

    void compileUserFunction(SmallCAsmFunction function) {
        currentFunction = function
        function.localCount = 0
        function.declarations = []
        function.parameterSymbols = []
        code = SmallCAsmCode()
        scope = SmallCAsmScope(null)
        loop = null
        String header = format("\n.func {}(", function.asmName)
        int64 parameterIndex = 0
        if (function.parameters != null) {
            int64 i = 0
            while (i < function.parameters.children.length) {
                AstNode parameter = child(function.parameters, i)
                if (parameter.name.equals("parameter")) {
                    String valueType = function.parameterTypes[parameterIndex] as String
                    String symbol = format("p{}_{}", parameterIndex, child(parameter, 1).text)
                    function.parameterSymbols.append(symbol)
                    scope.variables.append(SmallCAsmVariable(child(parameter, 1).text,
                        valueType, false, false, 0, symbol))
                    if (parameterIndex > 0) { header.append(", ") }
                    header.append(format("{}:{}", symbol, asmType(valueType)))
                    parameterIndex += 1
                }
                i += 1
            }
        }
        header.append(format(") -> {}\n", asmType(function.returnType)))
        emitCompound(function.body, false)
        if (!problem.equals("")) { return }
        if (!guaranteesReturn(function.body) && !function.name.equals("main")) {
            fail(function.declaration,
                format("function '{}' may reach its end without returning", function.name))
            return
        }
        if (function.returnType.equals("char")) {
            code.op1("const.u8", "0")
            code.op("ret.u8")
        }
        else {
            code.op1("const.i32", "0")
            code.op("ret.i32")
        }
        functionText.append(header)
        functionText.append(declarationText())
        functionText.append(code.text)
        functionText.append(".end\n")
    }

    bool guaranteesReturn(AstNode node) {
        if (node == null) { return(false) }
        if (node.name.equals("simpleStatement")) {
            if (node.children.length > 0 && child(node, 0).text.equals("return")) {
                return(true)
            }
            int64 i = 0
            while (i < node.children.length) {
                if (child(node, i).name.equals("compoundStatement")) {
                    return(guaranteesReturn(child(node, i)))
                }
                i += 1
            }
            return(false)
        }
        if (node.name.equals("statement")) {
            int64 i = 0
            while (i < node.children.length) {
                if (guaranteesReturn(child(node, i))) { return(true) }
                i += 1
            }
            return(false)
        }
        if (node.name.equals("compoundStatement")) {
            int64 i = 0
            while (i < node.children.length) {
                AstNode item = child(node, i)
                if (item.name.equals("blockItem")) {
                    int64 j = 0
                    while (j < item.children.length) {
                        AstNode part = child(item, j)
                        if (part.name.equals("statement") && guaranteesReturn(part)) {
                            return(true)
                        }
                        j += 1
                    }
                }
                i += 1
            }
            return(false)
        }
        if (node.name.equals("matchedStatement")) {
            if (node.children.length > 0 && child(node, 0).text.equals("if")) {
                list statements = statementChildren(node)
                return((statements.length == 2
                    && guaranteesReturn(statements[0] as AstNode)
                    && guaranteesReturn(statements[1] as AstNode)))
            }
            if (node.children.length > 0
                    && child(node, 0).name.equals("simpleStatement")) {
                return(guaranteesReturn(child(node, 0)))
            }
        }
        if (node.name.equals("openStatement")) {
            if (node.children.length > 0 && child(node, 0).text.equals("if")) {
                list statements = statementChildren(node)
                return((statements.length == 2
                    && guaranteesReturn(statements[0] as AstNode)
                    && guaranteesReturn(statements[1] as AstNode)))
            }
            if (node.children.length > 0
                    && child(node, 0).name.equals("simpleStatement")) {
                return(guaranteesReturn(child(node, 0)))
            }
        }
        return(false)
    }

    bool isStatementNode(AstNode node) {
        return((node.name.equals("statement")
            || node.name.equals("matchedStatement")
            || node.name.equals("openStatement")
            || node.name.equals("simpleStatement")
            || node.name.equals("compoundStatement")
            || node.name.equals("switchStatement")))
    }

    list statementChildren(AstNode node) {
        list result = []
        int64 i = 0
        while (i < node.children.length) {
            AstNode part = child(node, i)
            if (isStatementNode(part)) { result.append(part) }
            i += 1
        }
        return(result)
    }

    void emitInt(int64 value) {
        code.op1("const.i32", format("{}", value))
    }

    void emitByte(int64 value) {
        code.op1("const.u8", format("{}", value))
    }

    void promoteToInt(String valueType) {
        if (valueType.equals("char")) { code.op("to.i32") }
    }

    // Discards an expression statement's value; void intrinsics push none.
    void discard(String valueType) {
        if (!valueType.equals("void")) { code.op("pop") }
    }

    void emitLoad(SmallCAsmVariable variable) {
        if (variable == null) { return }
        if (variable.array) {
            fail(errorNode, "internal attempt to load an array as a scalar")
            return
        }
        if (variable.global) { code.op1("ldglobal", variable.asmName) }
        else { code.op1("ldloc", variable.asmName) }
    }

    void emitStore(SmallCAsmVariable variable) {
        if (variable == null) { return }
        if (variable.global) { code.op1("stglobal", variable.asmName) }
        else { code.op1("stloc", variable.asmName) }
    }

    void emitArrayReference(SmallCAsmVariable variable) {
        if (variable == null || !variable.array) {
            fail(errorNode, "internal attempt to index a scalar")
            return
        }
        code.op1("array", variable.asmName)
    }

    void emitArrayInitializer(SmallCAsmVariable variable, AstNode initializer) {
        if (initializer == null || variable == null) { return }
        SmallCAsmArray array = arrays[variable.index] as SmallCAsmArray
        if (initializer.children.length == 1
                && child(initializer, 0).name.equals("STRING")) {
            buffer bytes = stringBytes(child(initializer, 0).text)
            if (bytes.length > array.length) {
                fail(initializer, format("string initializer for '{}' exceeds array capacity {}",
                    variable.name, array.length))
                return
            }
            int64 i = 0
            while (i < bytes.length && problem.equals("")) {
                emitArrayReference(variable)
                emitInt(i)
                emitByte(int64(bytes[i]))
                code.op("aset")
                code.op("pop")
                i += 1
            }
            if (bytes.length < array.length && problem.equals("")) {
                emitArrayReference(variable)
                emitInt(bytes.length)
                emitByte(0)
                code.op("aset")
                code.op("pop")
            }
            return
        }
        int64 element = 0
        int64 i = 0
        while (i < initializer.children.length && problem.equals("")) {
            AstNode value = child(initializer, i)
            if (value.name.equals("assignment")) {
                if (element >= array.length) {
                    fail(value, format("too many elements in initializer for '{}'", variable.name))
                    return
                }
                emitArrayReference(variable)
                emitInt(element)
                String actual = emitExpression(value)
                if (!actual.equals(array.elementType)) {
                    fail(value, format("initializer for '{}' requires {}, got {}",
                        variable.name, array.elementType, actual))
                    return
                }
                code.op("aset")
                code.op("pop")
                element += 1
            }
            i += 1
        }
    }

    void emitDeclaration(AstNode declaration) {
        String baseType = child(child(declaration, 0), 0).text
        int64 i = 1
        while (i < declaration.children.length && problem.equals("")) {
            AstNode declarator = child(declaration, i)
            if (declarator.name.equals("declarator")) {
                AstNode nameNode = child(declarator, 0)
                bool isArray = declarator.children.length > 1 && child(declarator, 1).text.equals("[")
                AstNode initializer = declarationInitializer(declarator)
                if (isArray) {
                    int64 length = declaredArrayLength(declarator, initializer)
                    if (length <= 0) {
                        fail(nameNode, format("array '{}' requires a positive fixed size or inferable initializer", nameNode.text))
                    }
                    else {
                        int64 index = arrays.length
                        String arrayElementType = "int"
                        String arrayType = "int[]"
                        if (baseType.equals("char")) {
                            arrayElementType = "char"
                            arrayType = "char[]"
                        }
                        SmallCAsmArray array = SmallCAsmArray(
                            format("a{}_{}", index, nameNode.text), arrayElementType, length)
                        arrays.append(array)
                        currentFunction.declarations.append(
                            format("    .array {}: {}[{}]\n", array.asmName,
                                asmType(arrayElementType), length))
                        SmallCAsmVariable variable = SmallCAsmVariable(
                            nameNode.text, arrayType, false, true, index, array.asmName)
                        scope.variables.append(variable)
                        emitArrayInitializer(variable, initializer)
                    }
                }
                else {
                    addLocal(nameNode.text, baseType)
                    SmallCAsmVariable variable = scope.variables[scope.variables.length - 1] as SmallCAsmVariable
                    if (initializer != null && initializer.children.length > 0) {
                        String actual = emitExpression(child(initializer, 0))
                        if (!actual.equals(baseType)) {
                            fail(initializer, format("initializer for '{}' requires {}, got {}",
                                nameNode.text, baseType, actual))
                        }
                        emitStore(variable)
                        code.op("pop")
                    }
                }
            }
            i += 1
        }
    }

    void emitCompound(AstNode node, bool nested) {
        if (nested) { pushScope() }
        int64 i = 0
        while (i < node.children.length && problem.equals("")) {
            AstNode item = child(node, i)
            if (item.name.equals("blockItem")) { emitBlockItem(item) }
            i += 1
        }
        if (nested) { popScope() }
    }

    void emitBlockItem(AstNode node) {
        int64 i = 0
        while (i < node.children.length && problem.equals("")) {
            AstNode part = child(node, i)
            if (part.name.equals("declaration")) { emitDeclaration(part) }
            else { if (part.name.equals("statement")) { emitStatement(part) } }
            i += 1
        }
    }

    void emitStatement(AstNode node) {
        if (node.name.equals("simpleStatement")) {
            emitAtomicStatement(node)
            return
        }
        if (node.name.equals("compoundStatement")) {
            emitCompound(node, true)
            return
        }
        if (node.name.equals("statement")
                || node.name.equals("matchedStatement")
                || node.name.equals("openStatement")) {
            if (node.children.length == 0) { return }
            String first = child(node, 0).text
            if (first.equals("if")) {
                emitIf(node)
                return
            }
            if (first.equals("while")) {
                emitWhile(node)
                return
            }
            if (first.equals("for")) {
                emitFor(node)
                return
            }
            if (node.children.length > 1
                    && child(node, 0).name.equals("IDENT")
                    && child(node, 1).text.equals(":")) {
                fail(child(node, 0), "CVM backend does not support labels or goto")
                return
            }
            int64 i = 0
            while (i < node.children.length && problem.equals("")) {
                AstNode part = child(node, i)
                if (part.name.equals("statement")
                        || part.name.equals("matchedStatement")
                        || part.name.equals("openStatement")
                        || part.name.equals("simpleStatement")
                        || part.name.equals("compoundStatement")) {
                    emitStatement(part)
                }
                i += 1
            }
            return
        }
        if (node.name.equals("switchStatement")) {
            fail(child(node, 0), "CVM backend does not support switch statements")
            return
        }
        fail(node, format("CVM backend does not support statement node '{}'", node.name))
    }

    void emitAtomicStatement(AstNode node) {
        if (node.children.length == 0) { return }
        AstNode first = child(node, 0)
        if (first.text.equals("switch")) {
            fail(first, "CVM backend does not support switch statements")
            return
        }
        if (first.text.equals("goto")) {
            fail(first, "CVM backend does not support labels or goto")
            return
        }
        if (first.text.equals("break")) {
            if (loop == null) {
                fail(first, "CVM backend does not support break outside a loop")
                return
            }
            code.op1("jmp", loop.breakLabel)
            return
        }
        if (first.text.equals("continue")) {
            if (loop == null) {
                fail(first, "CVM backend does not support continue outside a loop")
                return
            }
            code.op1("jmp", loop.continueLabel)
            return
        }
        if (first.text.equals("return")) {
            AstNode expression = null
            int64 i = 1
            while (i < node.children.length) {
                if (child(node, i).name.equals("expression")) {
                    expression = child(node, i)
                }
                i += 1
            }
            if (expression == null) {
                fail(first, "CVM backend requires a return value")
                return
            }
            String actual = emitExpression(expression)
            if (actual.equals("char")) { code.op("ret.u8") }
            else { code.op("ret.i32") }
            return
        }
        int64 i = 0
        while (i < node.children.length && problem.equals("")) {
            AstNode part = child(node, i)
            if (part.name.equals("expression")) {
                discard(emitExpression(part))
            }
            if (part.name.equals("compoundStatement")) { emitCompound(part, true) }
            if (part.name.equals("switchStatement")) {
                fail(child(part, 0), "CVM backend does not support switch statements")
            }
            i += 1
        }
    }

    void emitIf(AstNode node) {
        AstNode condition = null
        list statements = statementChildren(node)
        int64 i = 0
        while (i < node.children.length) {
            if (child(node, i).name.equals("expression")) { condition = child(node, i) }
            i += 1
        }
        if (condition == null || statements.length == 0) {
            fail(node, "invalid if statement AST")
            return
        }
        String otherwise = code.newLabel()
        String end = code.newLabel()
        String conditionType = emitExpression(condition)
        promoteToInt(conditionType)
        code.op1("jz", otherwise)
        emitStatement(statements[0] as AstNode)
        if (statements.length > 1) {
            code.op1("jmp", end)
            code.mark(otherwise)
            emitStatement(statements[1] as AstNode)
            code.mark(end)
        }
        else { code.mark(otherwise) }
    }

    void emitWhile(AstNode node) {
        AstNode condition = null
        list statements = statementChildren(node)
        int64 i = 0
        while (i < node.children.length) {
            if (child(node, i).name.equals("expression")) { condition = child(node, i) }
            i += 1
        }
        if (condition == null || statements.length == 0) {
            fail(node, "invalid while statement AST")
            return
        }
        String loopStart = code.newLabel()
        String end = code.newLabel()
        code.mark(loopStart)
        String conditionType = emitExpression(condition)
        promoteToInt(conditionType)
        code.op1("jz", end)
        loop = SmallCAsmLoop(end, loopStart, loop)
        emitStatement(statements[0] as AstNode)
        loop = loop.parent
        code.op1("jmp", loopStart)
        code.mark(end)
    }

    void emitFor(AstNode node) {
        AstNode initializer = null
        AstNode condition = null
        AstNode update = null
        list statements = statementChildren(node)
        bool afterInitializer = false
        bool afterCondition = false
        int64 i = 0
        while (i < node.children.length) {
            AstNode part = child(node, i)
            if (part.name.equals("forInitializer")) {
                initializer = part
                afterInitializer = true
            }
            else {
                if (afterInitializer && part.text.equals(";")) { afterCondition = true }
                else {
                    if (afterInitializer && part.name.equals("expression")) {
                        if (afterCondition) { update = part }
                        else { condition = part }
                    }
                }
            }
            i += 1
        }
        if (initializer == null || statements.length == 0) {
            fail(node, "invalid for statement AST")
            return
        }
        pushScope()
        emitForInitializer(initializer)
        String loopStart = code.newLabel()
        String updateLabel = code.newLabel()
        String end = code.newLabel()
        code.mark(loopStart)
        if (condition != null) {
            String conditionType = emitExpression(condition)
            promoteToInt(conditionType)
            code.op1("jz", end)
        }
        loop = SmallCAsmLoop(end, updateLabel, loop)
        emitStatement(statements[0] as AstNode)
        loop = loop.parent
        code.mark(updateLabel)
        if (update != null) { discard(emitExpression(update)) }
        code.op1("jmp", loopStart)
        code.mark(end)
        popScope()
    }

    void emitForInitializer(AstNode node) {
        int64 i = 0
        while (i < node.children.length && problem.equals("")) {
            AstNode part = child(node, i)
            if (part.name.equals("declaration")) { emitDeclaration(part) }
            else {
                if (part.name.equals("expression")) { discard(emitExpression(part)) }
            }
            i += 1
        }
    }

    String emitExpression(AstNode node) {
        if (problem.length > 0 || node == null) { return("") }
        if (node.name.equals("expression")) {
            return(emitExpression(child(node, 0)))
        }
        if (node.name.equals("assignment")) {
            if (node.children.length == 3) { return(emitAssignment(node)) }
            return(emitExpression(child(node, 0)))
        }
        if (node.name.equals("logicalOr")) {
            return(emitLogical(node, false))
        }
        if (node.name.equals("logicalAnd")) {
            return(emitLogical(node, true))
        }
        if (node.name.equals("equality") || node.name.equals("relational")
                || node.name.equals("additive") || node.name.equals("multiplicative")) {
            return(emitBinaryChain(node))
        }
        if (node.name.equals("unary")) { return(emitUnary(node)) }
        if (node.name.equals("primary")) { return(emitPrimary(node)) }
        if (node.name.equals("lvalue")) { return(emitLvalue(node)) }
        if (node.name.equals("INTEGER")) {
            emitInt(integerValue(node.text, 2147483647, node))
            return("int")
        }
        if (node.name.equals("CHAR")) {
            emitByte(characterValue(node.text))
            return("char")
        }
        fail(node, format("CVM backend does not support expression node '{}'", node.name))
        return("")
    }

    String binaryMnemonic(String operation) {
        if (operation.equals("+")) { return("add.i32") }
        if (operation.equals("-")) { return("sub.i32") }
        if (operation.equals("*")) { return("mul.i32") }
        if (operation.equals("/")) { return("div.i32") }
        if (operation.equals("%")) { return("rem.i32") }
        if (operation.equals("==")) { return("eq.i32") }
        if (operation.equals("!=")) { return("ne.i32") }
        if (operation.equals("<")) { return("lt.i32") }
        if (operation.equals("<=")) { return("le.i32") }
        if (operation.equals(">")) { return("gt.i32") }
        if (operation.equals(">=")) { return("ge.i32") }
        return("")
    }

    String emitBinaryChain(AstNode node) {
        String resultType = emitExpression(child(node, 0))
        int64 i = 1
        while (i + 1 < node.children.length && problem.equals("")) {
            String operation = child(node, i).text
            promoteToInt(resultType)
            String rightType = emitExpression(child(node, i + 1))
            promoteToInt(rightType)
            String mnemonic = binaryMnemonic(operation)
            if (mnemonic.equals("")) {
                fail(child(node, i), format("CVM backend does not support operator '{}'", operation))
            }
            else { code.op(mnemonic) }
            resultType = "int"
            i += 2
        }
        return(resultType)
    }

    String emitLogical(AstNode node, bool conjunction) {
        if (node.children.length == 1) { return(emitExpression(child(node, 0))) }
        String end = code.newLabel()
        String shortCircuit = code.newLabel()
        int64 i = 0
        while (i < node.children.length && problem.equals("")) {
            AstNode part = child(node, i)
            if (part.name.equals("logicalAnd") || part.name.equals("equality")) {
                String valueType = emitExpression(part)
                promoteToInt(valueType)
                if (conjunction) { code.op1("jz", shortCircuit) }
                else {
                    String next = code.newLabel()
                    code.op1("jz", next)
                    emitInt(1)
                    code.op1("jmp", end)
                    code.mark(next)
                }
            }
            if (part.text.equals("&&") || part.text.equals("||")) {
                if (part.text.equals("&&") != conjunction) {
                    fail(part, "invalid logical-expression AST")
                }
            }
            i += 1
        }
        if (conjunction) {
            emitInt(1)
            code.op1("jmp", end)
            code.mark(shortCircuit)
            emitInt(0)
        }
        else { emitInt(0) }
        code.mark(end)
        return("int")
    }

    String emitUnary(AstNode node) {
        if (node.children.length == 1) { return(emitExpression(child(node, 0))) }
        String operation = child(node, 0).text
        AstNode operand = child(node, 1)
        if (operation.equals("++") || operation.equals("--")) {
            return(emitIncrement(operand, false, operation.equals("++")))
        }
        if (operation.equals("-") && operand.name.equals("INTEGER")
                && isMinimumIntegerLiteral(operand.text)) {
            emitInt(-2147483648)
            return("int")
        }
        String valueType = emitExpression(operand)
        if (operation.equals("+")) {
            promoteToInt(valueType)
            return("int")
        }
        if (operation.equals("-")) {
            promoteToInt(valueType)
            code.op("neg.i32")
            return("int")
        }
        if (operation.equals("!")) {
            promoteToInt(valueType)
            emitInt(0)
            code.op("eq.i32")
            return("int")
        }
        fail(child(node, 0), format("CVM backend does not support unary operator '{}'", operation))
        return("")
    }

    String emitPrimary(AstNode node) {
        if (node.children.length >= 3 && child(node, 0).name.equals("IDENT")
                && child(node, 1).text.equals("(")) {
            return(emitCall(node))
        }
        if (node.children.length == 3 && child(node, 0).text.equals("(")) {
            return(emitExpression(child(node, 1)))
        }
        if (child(node, 0).name.equals("lvalue")) {
            if (node.children.length > 1) {
                String operation = child(node, 1).text
                return(emitIncrement(child(node, 0), true, operation.equals("++")))
            }
            return(emitLvalue(child(node, 0)))
        }
        return(emitExpression(child(node, 0)))
    }

    list callArguments(AstNode node) {
        list result = []
        int64 i = 0
        while (i < node.children.length) {
            AstNode part = child(node, i)
            if (part.name.equals("arguments")) {
                int64 a = 0
                while (a < part.children.length) {
                    AstNode argument = child(part, a)
                    if (argument.name.equals("assignment") || argument.name.equals("STRING")) { result.append(argument) }
                    a += 1
                }
            }
            i += 1
        }
        return(result)
    }

    String emitCall(AstNode node) {
        AstNode nameNode = child(node, 0)
        SmallCIntrinsic intrinsic = intrinsics.find(nameNode.text)
        if (intrinsic != null) { return(emitIntrinsic(node, intrinsic)) }
        SmallCAsmFunction function = findFunction(nameNode.text)
        if (function == null || !function.defined) {
            fail(nameNode, format("CVM backend has no definition for function '{}'", nameNode.text))
            return("")
        }
        list arguments = callArguments(node)
        int64 a = 0
        while (a < arguments.length && problem.equals("")) {
            emitExpression(arguments[a] as AstNode)
            a += 1
        }
        code.op1("call", function.asmName)
        return(function.returnType)
    }

    AstNode arrayArgumentName(AstNode argument) {
        AstNode current = argument
        while (!current.name.equals("lvalue") && current.children.length == 1) {
            current = child(current, 0)
        }
        return(child(current, 0))
    }

    // print(char[]): writes the bytes before the first NUL (or the whole array
    // when none), retrying short writes.
    String emitPrint(AstNode argument) {
        bool literal = argument.name.equals("STRING")
        SmallCAsmVariable variable = null
        if (!literal) { variable = findVariable(arrayArgumentName(argument).text) }
        String length = addTemporary("int")
        String done = addTemporary("int")
        String scan = code.newLabel()
        String scanEnd = code.newLabel()
        String send = code.newLabel()
        String sendEnd = code.newLabel()
        code.op("const.i32 0")
        code.op1("stloc", length)
        code.op("pop")
        if (literal) {
            code.op1("const.i32", format("{}", stringBytes(argument.text).length))
            code.op1("stloc", length)
            code.op("pop")
        }
        else {
            code.mark(scan)
            code.op1("ldloc", length)
            emitArrayReference(variable)
            code.op("alen")
            code.op("lt.i32")
            code.op1("jz", scanEnd)
            emitArrayReference(variable)
            code.op1("ldloc", length)
            code.op("aget")
            if (elementType(variable.valueType).equals("char")) { code.op("to.i32") }
            code.op1("jz", scanEnd)
            code.op1("ldloc", length)
            code.op("const.i32 1")
            code.op("add.i32")
            code.op1("stloc", length)
            code.op("pop")
            code.op1("jmp", scan)
            code.mark(scanEnd)
        }
        code.op("const.i32 0")
        code.op1("stloc", done)
        code.op("pop")
        code.mark(send)
        code.op1("ldloc", done)
        code.op1("ldloc", length)
        code.op("lt.i32")
        code.op1("jz", sendEnd)
        if (literal) { emitBufferArgument(argument) }
        else { emitArrayReference(variable) }
        code.op1("ldloc", done)
        code.op1("ldloc", length)
        code.op1("ldloc", done)
        code.op("sub.i32")
        code.op1("sys", "stdout_write")
        code.op1("ldloc", done)
        code.op("add.i32")
        code.op1("stloc", done)
        code.op("pop")
        code.op1("jmp", send)
        code.mark(sendEnd)
        return("void")
    }

    // Pushes a char array reference for a bare array name or a string literal.
    void emitBufferArgument(AstNode argument) {
        if (argument.name.equals("STRING")) {
            buffer bytes = stringBytes(argument.text)
            SmallCAsmArray array = SmallCAsmArray(
                format("s{}_literal", arrays.length), "char", bytes.length + 1)
            array.staticInitializer = assemblyString(bytes)
            array.isGlobal = true
            arrays.append(array)
            code.op1("array", array.asmName)
            return
        }
        emitArrayReference(findVariable(arrayArgumentName(argument).text))
    }

    String emitIntrinsic(AstNode node, SmallCIntrinsic intrinsic) {
        list arguments = callArguments(node)
        if (intrinsic.service.equals("stdout_write")) { return(emitPrint(arguments[0] as AstNode)) }
        bool transfer = intrinsic.service.equals("file_read_handle") || intrinsic.service.equals("file_write_handle")
        if (transfer) {
            // Source order is (handle, length, buffer); the service takes
            // (handle, buffer, length). Evaluate in source order via temporaries.
            String handleSlot = addTemporary("int")
            String lengthSlot = addTemporary("int")
            promoteToInt(emitExpression(arguments[0] as AstNode))
            code.op1("stloc", handleSlot)
            code.op("pop")
            promoteToInt(emitExpression(arguments[1] as AstNode))
            code.op1("stloc", lengthSlot)
            code.op("pop")
            code.op1("ldloc", handleSlot)
            emitBufferArgument(arguments[2] as AstNode)
            code.op1("ldloc", lengthSlot)
        }
        else {
            int64 a = 0
            while (a < arguments.length && problem.equals("")) {
                AstNode argument = arguments[a] as AstNode
                String expected = intrinsic.parameterTypes[a] as String
                if (expected.equals("char[]")) { emitBufferArgument(argument) }
                else { promoteToInt(emitExpression(argument)) }
                a += 1
            }
        }
        if (problem.equals("")) { code.op1("sys", intrinsic.service) }
        return(intrinsic.resultType)
    }

    String emitLvalue(AstNode node) {
        AstNode nameNode = child(node, 0)
        SmallCAsmVariable variable = findVariable(nameNode.text)
        if (variable == null) {
            fail(nameNode, format("undeclared variable '{}'", nameNode.text))
            return("")
        }
        if (node.children.length == 1) {
            if (variable.array) {
                fail(nameNode, format("array '{}' cannot be used as a scalar value", nameNode.text))
                return("")
            }
            emitLoad(variable)
            return(variable.valueType)
        }
        if (!variable.array) {
            fail(nameNode, format("variable '{}' is not an array", nameNode.text))
            return("")
        }
        emitArrayReference(variable)
        String indexType = emitExpression(child(node, 2))
        promoteToInt(indexType)
        code.op("aget")
        return(elementType(variable.valueType))
    }

    String evaluateIndex(AstNode lvalue) {
        String indexType = emitExpression(child(lvalue, 2))
        promoteToInt(indexType)
        String slot = addTemporary("int")
        code.op1("stloc", slot)
        code.op("pop")
        return(slot)
    }

    String emitAssignment(AstNode node) {
        AstNode lvalue = child(node, 0)
        String operation = child(node, 1).text
        AstNode right = child(node, 2)
        AstNode nameNode = child(lvalue, 0)
        SmallCAsmVariable variable = findVariable(nameNode.text)
        if (variable == null) {
            fail(nameNode, format("undeclared variable '{}'", nameNode.text))
            return("")
        }
        if (!variable.array) {
            if (operation.equals("=")) {
                String valueType = emitExpression(right)
                emitStore(variable)
                return(valueType)
            }
            emitLoad(variable)
            String rightType = emitExpression(right)
            promoteToInt(rightType)
            emitCompoundOperation(operation, child(node, 1))
            emitStore(variable)
            return("int")
        }
        String indexSlot = evaluateIndex(lvalue)
        if (operation.equals("=")) {
            String valueType = emitExpression(right)
            String valueSlot = addTemporary(valueType)
            code.op1("stloc", valueSlot)
            code.op("pop")
            emitArrayReference(variable)
            code.op1("ldloc", indexSlot)
            code.op1("ldloc", valueSlot)
            code.op("aset")
            return(valueType)
        }
        emitArrayReference(variable)
        code.op1("ldloc", indexSlot)
        code.op("aget")
        String rightType = emitExpression(right)
        promoteToInt(rightType)
        emitCompoundOperation(operation, child(node, 1))
        String resultSlot = addTemporary("int")
        code.op1("stloc", resultSlot)
        code.op("pop")
        emitArrayReference(variable)
        code.op1("ldloc", indexSlot)
        code.op1("ldloc", resultSlot)
        code.op("aset")
        return("int")
    }

    void emitCompoundOperation(String operation, AstNode operator) {
        String mnemonic = ""
        if (operation.equals("+=")) { mnemonic = "add.i32" }
        if (operation.equals("-=")) { mnemonic = "sub.i32" }
        if (operation.equals("*=")) { mnemonic = "mul.i32" }
        if (operation.equals("/=")) { mnemonic = "div.i32" }
        if (operation.equals("%=")) { mnemonic = "rem.i32" }
        if (mnemonic.equals("")) {
            fail(operator, format("CVM backend does not support operator '{}'", operation))
        }
        else { code.op(mnemonic) }
    }

    String emitIncrement(AstNode lvalue, bool postfix, bool increment) {
        AstNode nameNode = child(lvalue, 0)
        SmallCAsmVariable variable = findVariable(nameNode.text)
        if (variable == null) {
            fail(nameNode, format("undeclared variable '{}'", nameNode.text))
            return("")
        }
        String valueType = elementType(variable.valueType)
        String step = "sub.i32"
        if (increment) { step = "add.i32" }
        if (!variable.array) {
            String oldSlot = addTemporary(valueType)
            emitLoad(variable)
            code.op1("stloc", oldSlot)
            code.op("pop")
            emitLoad(variable)
            promoteToInt(valueType)
            emitInt(1)
            code.op(step)
            if (valueType.equals("char")) { code.op("to.u8") }
            emitStore(variable)
            if (postfix) {
                code.op("pop")
                code.op1("ldloc", oldSlot)
            }
            return(valueType)
        }
        String indexSlot = evaluateIndex(lvalue)
        emitArrayReference(variable)
        code.op1("ldloc", indexSlot)
        code.op("aget")
        String oldSlot = addTemporary(valueType)
        code.op1("stloc", oldSlot)
        code.op("pop")
        code.op1("ldloc", oldSlot)
        promoteToInt(valueType)
        emitInt(1)
        code.op(step)
        if (valueType.equals("char")) { code.op("to.u8") }
        String newSlot = addTemporary(valueType)
        code.op1("stloc", newSlot)
        code.op("pop")
        emitArrayReference(variable)
        code.op1("ldloc", indexSlot)
        code.op1("ldloc", newSlot)
        code.op("aset")
        if (postfix) {
            code.op("pop")
            code.op1("ldloc", oldSlot)
        }
        return(valueType)
    }
}

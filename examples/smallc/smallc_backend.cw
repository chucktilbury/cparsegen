class SmallCVMInstruction {
    int opcode
    int operand
    bool hasOperand
    String target

    SmallCVMInstruction(int instructionOpcode, int instructionOperand,
            bool operandPresent, String branchTarget) {
        opcode = instructionOpcode
        operand = instructionOperand
        hasOperand = operandPresent
        target = branchTarget
    }
}

class SmallCVMLabel {
    String name
    int instructionIndex

    SmallCVMLabel(String labelName, int index) {
        name = labelName
        instructionIndex = index
    }
}

class SmallCVMCode {
    list instructions
    list labels
    int stackDepth
    int maximumStack
    int labelCounter
    String problem

    SmallCVMCode() {
        instructions = []
        labels = []
        stackDepth = 0
        maximumStack = 0
        labelCounter = 0
        problem = ""
    }

    void setDepth(int depth) {
        stackDepth = depth
    }

    void emit(int opcode, int operand, int delta) {
        CVM.Opcode metadata = CVM.Opcode()
        bool hasOperand = metadata.operandWidth(opcode) > 0
        instructions.append(SmallCVMInstruction(opcode, operand, hasOperand, ""))
        stackDepth += delta
        if (stackDepth < 0 && problem.equals("")) {
            problem = format("internal bytecode stack underflow at opcode {}", opcode)
        }
        if (stackDepth > maximumStack) { maximumStack = stackDepth }
    }

    void emitNoOperand(int opcode, int delta) {
        instructions.append(SmallCVMInstruction(opcode, 0, false, ""))
        stackDepth += delta
        if (stackDepth < 0 && problem.equals("")) {
            problem = format("internal bytecode stack underflow at opcode {}", opcode)
        }
        if (stackDepth > maximumStack) { maximumStack = stackDepth }
    }

    String newLabel() {
        String result = format("_L{}", labelCounter)
        labelCounter += 1
        return result
    }

    void mark(String name) {
        labels.append(SmallCVMLabel(name, instructions.length))
    }

    void jump(int opcode, String target, int delta) {
        instructions.append(SmallCVMInstruction(opcode, 0, true, target))
        stackDepth += delta
        if (stackDepth < 0 && problem.equals("")) {
            problem = format("internal bytecode stack underflow at opcode {}", opcode)
        }
        if (stackDepth > maximumStack) { maximumStack = stackDepth }
    }

    int labelIndex(String name) {
        int i = 0
        while (i < labels.length) {
            SmallCVMLabel label = labels[i] as SmallCVMLabel
            if (label.name.equals(name)) { return label.instructionIndex }
            i += 1
        }
        return -1
    }

    int labelOffset(String name, list offsets) {
        int index = labelIndex(name)
        if (index < 0 || index >= offsets.length) { return -1 }
        return offsets[index] as int
    }

    buffer encode() {
        if (!problem.equals("")) { return null }
        list offsets = []
        int offset = 0
        CVM.Opcode metadata = CVM.Opcode()
        int i = 0
        while (i < instructions.length) {
            SmallCVMInstruction instruction = instructions[i] as SmallCVMInstruction
            offsets.append(offset)
            offset += 1
            if (instruction.hasOperand) {
                offset += metadata.operandWidth(instruction.opcode)
            }
            i += 1
        }
        CVM.InstructionBuilder builder = CVM.InstructionBuilder()
        i = 0
        while (i < instructions.length) {
            SmallCVMInstruction instruction = instructions[i] as SmallCVMInstruction
            bool ok = false
            if (instruction.target.equals("")) {
                if (instruction.hasOperand) {
                    ok = builder.emit(instruction.opcode, instruction.operand)
                }
                else { ok = builder.emitNoOperand(instruction.opcode) }
            }
            else {
                int target = labelOffset(instruction.target, offsets)
                if (target < 0) {
                    problem = format("internal bytecode label '{}' is unresolved", instruction.target)
                    return null
                }
                ok = builder.emit(instruction.opcode, target)
            }
            if (!ok) {
                problem = format("CVM instruction builder: {}", builder.errorMessage())
                return null
            }
            i += 1
        }
        return builder.bytes()
    }
}

class SmallCVMVariable {
    String name
    String valueType
    bool global
    bool array
    int index

    SmallCVMVariable(String variableName, String variableType,
            bool isGlobal, bool isArray, int tableIndex) {
        name = variableName
        valueType = variableType
        global = isGlobal
        array = isArray
        index = tableIndex
    }
}

class SmallCVMScope {
    list variables
    SmallCVMScope parent

    SmallCVMScope(SmallCVMScope outer) {
        variables = []
        parent = outer
    }
}

class SmallCVMFunction {
    String name
    String returnType
    AstNode declaration
    AstNode parameters
    AstNode body
    list parameterTypes
    list localTypes
    int index

    SmallCVMFunction(String functionName, String resultType) {
        name = functionName
        returnType = resultType
        declaration = null
        parameters = null
        body = null
        parameterTypes = []
        localTypes = []
        index = -1
    }
}

class SmallCVMArray {
    String name
    String elementType
    int owner
    int length
    AstNode initializer

    SmallCVMArray(String arrayName, String valueType, int functionOwner,
            int capacity, AstNode init) {
        name = arrayName
        elementType = valueType
        owner = functionOwner
        length = capacity
        initializer = init
    }
}

class SmallCVMLoop {
    String breakLabel
    String continueLabel
    SmallCVMLoop parent

    SmallCVMLoop(String breakTarget, String continueTarget,
            SmallCVMLoop outer) {
        breakLabel = breakTarget
        continueLabel = continueTarget
        parent = outer
    }
}

class SmallCVMCompiledFunction {
    String name
    buffer codeBytes
    buffer localTypes
    int parameterCount
    int localCount
    int maximumStack
    int returnType

    SmallCVMCompiledFunction(String functionName, buffer body,
            buffer types, int parameters, int locals, int stack, int result) {
        name = functionName
        codeBytes = body
        localTypes = types
        parameterCount = parameters
        localCount = locals
        maximumStack = stack
        returnType = result
    }
}

class SmallCVMCompiler {
    SmallCVMFunction entryFunction
    SmallCVMFunction initFunction
    list functions
    list globals
    list arrays
    list globalInitializers
    SmallCVMFunction currentFunction
    SmallCVMCode code
    SmallCVMScope scope
    SmallCVMLoop loop
    SmallCFrontend frontend
    String problem
    AstNode errorNode
    int scalarGlobalCount
    list compiledFunctions

    SmallCVMCompiler() {
        functions = []
        globals = []
        arrays = []
        globalInitializers = []
        entryFunction = null
        initFunction = null
        currentFunction = null
        code = null
        scope = null
        loop = null
        frontend = null
        problem = ""
        errorNode = null
        scalarGlobalCount = 0
        compiledFunctions = []
    }

    AstNode child(AstNode node, int index) {
        return node.children[index] as AstNode
    }

    void fail(AstNode node, String message) {
        if (problem.equals("")) {
            problem = message
            errorNode = node
        }
    }

    String elementType(String valueType) {
        if (valueType.equals("int[]")) { return "int" }
        if (valueType.equals("char[]")) { return "char" }
        return valueType
    }

    int cvmType(String valueType) {
        if (valueType.equals("int")) { return 1 }
        if (valueType.equals("char")) { return 2 }
        return 0
    }

    int returnType(String valueType) {
        return cvmType(valueType)
    }

    SmallCVMFunction findFunction(String name) {
        int i = 0
        while (i < functions.length) {
            SmallCVMFunction function = functions[i] as SmallCVMFunction
            if (function.name.equals(name)) { return function }
            i += 1
        }
        return null
    }

    SmallCVMVariable findGlobal(String name) {
        int i = 0
        while (i < globals.length) {
            SmallCVMVariable variable = globals[i] as SmallCVMVariable
            if (variable.name.equals(name)) { return variable }
            i += 1
        }
        return null
    }

    SmallCVMVariable findVariable(String name) {
        SmallCVMScope current = scope
        while (current != null) {
            int i = current.variables.length - 1
            while (i >= 0) {
                SmallCVMVariable variable = current.variables[i] as SmallCVMVariable
                if (variable.name.equals(name)) { return variable }
                i -= 1
            }
            current = current.parent
        }
        return findGlobal(name)
    }

    void pushScope() {
        scope = SmallCVMScope(scope)
    }

    void popScope() {
        if (scope != null) { scope = scope.parent }
    }

    void addLocal(String name, String valueType, bool isArray, int index) {
        scope.variables.append(SmallCVMVariable(name, valueType, false, isArray, index))
        if (!isArray && index >= currentFunction.parameterTypes.length) {
            currentFunction.localTypes.append(cvmType(valueType))
        }
    }

    int integerValue(String spelling, int limit, AstNode node) {
        int value = 0
        int i = 0
        while (i < spelling.length && problem.equals("")) {
            int digit = int(spelling.byteAt(i)) - 48
            if (digit < 0 || digit > 9 || value > (limit - digit) / 10) {
                fail(node, format("integer literal '{}' is outside the CVM i32 range", spelling))
                return 0
            }
            value = value * 10 + digit
            i += 1
        }
        return value
    }

    bool isMinimumIntegerLiteral(String spelling) {
        int first = 0
        while (first + 1 < spelling.length
                && int(spelling.byteAt(first)) == 48) { first += 1 }
        return spelling.slice(first, spelling.length).equals("2147483648")
    }

    int decodeEscape(int value) {
        if (value == 110) { return 10 }
        if (value == 114) { return 13 }
        if (value == 116) { return 9 }
        if (value == 48) { return 0 }
        return value
    }

    int characterValue(String spelling) {
        int value = int(spelling.byteAt(1))
        if (value == 92) { value = decodeEscape(int(spelling.byteAt(2))) }
        return value
    }

    buffer stringBytes(String spelling) {
        buffer bytes = buffer[]
        int i = 1
        while (i + 1 < spelling.length) {
            int value = int(spelling.byteAt(i))
            if (value == 92) {
                i += 1
                value = decodeEscape(int(spelling.byteAt(i)))
            }
            bytes.append(value)
            i += 1
        }
        return bytes
    }

    int initializerCount(AstNode initializer) {
        if (initializer == null) { return 0 }
        if (initializer.children.length == 1
                && child(initializer, 0).name.equals("STRING")) {
            return stringBytes(child(initializer, 0).text).length + 1
        }
        int count = 0
        int i = 0
        while (i < initializer.children.length) {
            if (child(initializer, i).name.equals("assignment")) { count += 1 }
            i += 1
        }
        return count
    }

    AstNode declarationInitializer(AstNode declarator) {
        int i = 1
        while (i < declarator.children.length
                && !child(declarator, i).text.equals("=")) { i += 1 }
        if (i < declarator.children.length && i + 1 < declarator.children.length) {
            return child(declarator, i + 1)
        }
        return null
    }

    int declaredArrayLength(AstNode declarator, AstNode initializer) {
        if (declarator.children.length > 2
                && child(declarator, 2).name.equals("INTEGER")) {
            return integerValue(child(declarator, 2).text, 2147483647, child(declarator, 2))
        }
        return initializerCount(initializer)
    }

    void collectGlobalDeclaration(AstNode declaration) {
        String baseType = child(child(declaration, 0), 0).text
        int i = 1
        while (i < declaration.children.length && problem.equals("")) {
            AstNode declarator = child(declaration, i)
            if (declarator.name.equals("declarator")) {
                AstNode nameNode = child(declarator, 0)
                bool isArray = declarator.children.length > 1 && child(declarator, 1).text.equals("[")
                AstNode initializer = declarationInitializer(declarator)
                String valueType = baseType
                if (isArray) {
                    valueType = "int[]"
                    if (baseType.equals("char")) { valueType = "char[]" }
                    int length = declaredArrayLength(declarator, initializer)
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
                        SmallCVMArray array = SmallCVMArray(
                            format("_cparsegen_array_{}", arrays.length),
                            arrayElementType, 65535, length, initializer)
                        arrays.append(array)
                        globals.append(SmallCVMVariable(
                            nameNode.text, arrayType, true, true, arrays.length - 1))
                    }
                }
                else {
                    SmallCVMVariable variable = SmallCVMVariable(
                        nameNode.text, valueType, true, false, scalarGlobalCount)
                    globals.append(variable)
                    scalarGlobalCount += 1
                }
                if (initializer != null) {
                    globalInitializers.append([declarator, initializer])
                }
            }
            i += 1
        }
    }

    void collectFunction(AstNode external) {
        String resultType = child(child(external, 0), 0).text
        AstNode nameNode = child(external, 1)
        SmallCVMFunction function = findFunction(nameNode.text)
        if (function == null) {
            function = SmallCVMFunction(nameNode.text, resultType)
            functions.append(function)
        }
        function.parameterTypes = []
        function.parameters = null
        function.declaration = nameNode
        int i = 0
        while (i < external.children.length) {
            AstNode part = child(external, i)
            if (part.name.equals("parameters")) {
                function.parameters = part
                int p = 0
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
        int i = 0
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
        if (!problem.equals("")) { return false }
        entryFunction = findFunction("main")
        if (entryFunction == null || entryFunction.body == null) {
            fail(root, "SmallC program requires a definition of main()")
            return false
        }
        if (!entryFunction.returnType.equals("int")
                || entryFunction.parameterTypes.length != 0) {
            fail(entryFunction.declaration, "CVM entry point main must have type int main()")
            return false
        }
        int nextIndex = 1
        bool hasGlobalInitializers = globalInitializers.length > 0
        if (hasGlobalInitializers) {
            initFunction = SmallCVMFunction("_cparsegen_init", "void")
            initFunction.index = nextIndex
            nextIndex += 1
        }
        int f = 0
        while (f < functions.length) {
            SmallCVMFunction function = functions[f] as SmallCVMFunction
            if (function.body != null) {
                function.index = nextIndex
                nextIndex += 1
            }
            f += 1
        }
        return true
    }

    buffer compile(AstNode root, SmallCFrontend frontendModel) {
        frontend = frontendModel
        problem = ""
        errorNode = root
        if (!collectProgram(root)) { return null }
        if (!compileFunctions()) { return null }
        return encodeContainer()
    }

    bool compileFunctions() {
        SmallCVMFunction wrapper = SmallCVMFunction("_cparsegen_entry", "int")
        wrapper.index = 0
        SmallCVMCompiledFunction entryCode = compileEntry(wrapper)
        if (entryCode == null) { return false }
        compiledFunctions.append(entryCode)
        if (initFunction != null) {
            SmallCVMCompiledFunction initCode = compileGlobalInitializers(initFunction)
            if (initCode == null) { return false }
            compiledFunctions.append(initCode)
        }
        int i = 0
        while (i < functions.length && problem.equals("")) {
            SmallCVMFunction function = functions[i] as SmallCVMFunction
            if (function.body != null) {
                SmallCVMCompiledFunction compiled = compileUserFunction(function)
                if (compiled == null) { return false }
                compiledFunctions.append(compiled)
            }
            i += 1
        }
        return problem.equals("")
    }

    SmallCVMCompiledFunction finishFunction(String name, int parameterCount,
            int returnCode) {
        if (code == null || !code.problem.equals("")) {
            if (code != null) { fail(errorNode, code.problem) }
            return null
        }
        buffer encoded = code.encode()
        if (encoded == null) {
            fail(errorNode, code.problem)
            return null
        }
        buffer types = buffer[]
        int i = 0
        while (i < currentFunction.parameterTypes.length) {
            types.append(cvmType(currentFunction.parameterTypes[i] as String))
            i += 1
        }
        int localIndex = 0
        while (localIndex < currentFunction.localTypes.length) {
            types.append(currentFunction.localTypes[localIndex] as int)
            localIndex += 1
        }
        int maximumStack = code.maximumStack
        if (maximumStack < 1) { maximumStack = 1 }
        return SmallCVMCompiledFunction(
            name, encoded, types, parameterCount,
            currentFunction.localTypes.length,
            maximumStack, returnCode)
    }

    SmallCVMCompiledFunction compileEntry(SmallCVMFunction wrapper) {
        currentFunction = wrapper
        currentFunction.parameterTypes = []
        currentFunction.localTypes = []
        code = SmallCVMCode()
        scope = null
        loop = null
        if (initFunction != null) {
            code.emit(CVM.Opcode.CALL, initFunction.index, 0)
        }
        code.emit(CVM.Opcode.CALL, entryFunction.index, 1)
        code.emitNoOperand(CVM.Opcode.RET_I32, -1)
        return finishFunction("main", 0, 1)
    }

    SmallCVMCompiledFunction compileGlobalInitializers(SmallCVMFunction function) {
        currentFunction = function
        currentFunction.parameterTypes = []
        currentFunction.localTypes = []
        code = SmallCVMCode()
        scope = null
        loop = null
        int i = 0
        while (i < globalInitializers.length && problem.equals("")) {
            list pair = globalInitializers[i] as list
            AstNode declarator = pair[0] as AstNode
            AstNode initializer = pair[1] as AstNode
            SmallCVMVariable variable = findGlobal(child(declarator, 0).text)
            if (variable != null && variable.array) {
                emitArrayInitializer(variable, initializer)
            }
            else {
                emitExpression(child(initializer, 0))
                code.emit(CVM.Opcode.STGLOBAL, variable.index, 0)
                code.emitNoOperand(CVM.Opcode.POP, -1)
            }
            i += 1
        }
        if (!problem.equals("")) { return null }
        code.emitNoOperand(CVM.Opcode.RET, 0)
        return finishFunction(function.name, 0, 0)
    }

    SmallCVMCompiledFunction compileUserFunction(SmallCVMFunction function) {
        currentFunction = function
        currentFunction.localTypes = []
        code = SmallCVMCode()
        scope = SmallCVMScope(null)
        loop = null
        int parameterIndex = 0
        if (function.parameters != null) {
            int i = 0
            while (i < function.parameters.children.length) {
                AstNode parameter = child(function.parameters, i)
                if (parameter.name.equals("parameter")) {
                    addLocal(child(parameter, 1).text,
                        function.parameterTypes[parameterIndex] as String,
                        false, parameterIndex)
                    parameterIndex += 1
                }
                i += 1
            }
        }
        emitCompound(function.body, false)
        if (!problem.equals("")) { return null }
        if (!guaranteesReturn(function.body) && !function.name.equals("main")) {
            fail(function.declaration,
                format("function '{}' may reach its end without returning", function.name))
            return null
        }
        if (function.returnType.equals("char")) {
            code.emit(CVM.Opcode.CONST_U8, 0, 1)
            code.emitNoOperand(CVM.Opcode.RET_U8, -1)
        }
        else {
            code.emit(CVM.Opcode.CONST_I32, 0, 1)
            code.emitNoOperand(CVM.Opcode.RET_I32, -1)
        }
        String emittedName = format("_cparsegen_function_{}", function.index)
        return finishFunction(emittedName, parameterIndex, returnType(function.returnType))
    }

    bool guaranteesReturn(AstNode node) {
        if (node == null) { return false }
        if (node.name.equals("simpleStatement")) {
            if (node.children.length > 0 && child(node, 0).text.equals("return")) {
                return true
            }
            int i = 0
            while (i < node.children.length) {
                if (child(node, i).name.equals("compoundStatement")) {
                    return guaranteesReturn(child(node, i))
                }
                i += 1
            }
            return false
        }
        if (node.name.equals("statement")) {
            int i = 0
            while (i < node.children.length) {
                if (guaranteesReturn(child(node, i))) { return true }
                i += 1
            }
            return false
        }
        if (node.name.equals("compoundStatement")) {
            int i = 0
            while (i < node.children.length) {
                AstNode item = child(node, i)
                if (item.name.equals("blockItem")) {
                    int j = 0
                    while (j < item.children.length) {
                        AstNode part = child(item, j)
                        if (part.name.equals("statement") && guaranteesReturn(part)) {
                            return true
                        }
                        j += 1
                    }
                }
                i += 1
            }
            return false
        }
        if (node.name.equals("matchedStatement")) {
            if (node.children.length > 0 && child(node, 0).text.equals("if")) {
                list statements = statementChildren(node)
                return (statements.length == 2
                    && guaranteesReturn(statements[0] as AstNode)
                    && guaranteesReturn(statements[1] as AstNode))
            }
            if (node.children.length > 0
                    && child(node, 0).name.equals("simpleStatement")) {
                return guaranteesReturn(child(node, 0))
            }
        }
        if (node.name.equals("openStatement")) {
            if (node.children.length > 0 && child(node, 0).text.equals("if")) {
                list statements = statementChildren(node)
                return (statements.length == 2
                    && guaranteesReturn(statements[0] as AstNode)
                    && guaranteesReturn(statements[1] as AstNode))
            }
            if (node.children.length > 0
                    && child(node, 0).name.equals("simpleStatement")) {
                return guaranteesReturn(child(node, 0))
            }
        }
        return false
    }

    buffer encodeContainer() {
        CVM.ContainerBuilder builder = CVM.ContainerBuilder()
        if (!builder.setEntry(0)) {
            fail(errorNode, format("CVM container builder: {}", builder.errorMessage()))
            return null
        }
        int i = 0
        while (i < compiledFunctions.length && problem.equals("")) {
            SmallCVMCompiledFunction function = compiledFunctions[i] as SmallCVMCompiledFunction
            if (!builder.addFunction(function.name, function.codeBytes,
                    function.localTypes, function.parameterCount,
                    function.localCount, function.maximumStack,
                    function.returnType)) {
                fail(errorNode, format("CVM container builder: {}", builder.errorMessage()))
            }
            i += 1
        }
        i = 0
        while (i < globals.length && problem.equals("")) {
            SmallCVMVariable variable = globals[i] as SmallCVMVariable
            if (!variable.array && !builder.addGlobal(
                    format("_cparsegen_global_{}", variable.index),
                    cvmType(variable.valueType), 0)) {
                fail(errorNode, format("CVM container builder: {}", builder.errorMessage()))
            }
            i += 1
        }
        i = 0
        while (i < arrays.length && problem.equals("")) {
            SmallCVMArray array = arrays[i] as SmallCVMArray
            if (!builder.addArray(array.name, array.owner,
                    cvmType(array.elementType), array.length, buffer[])) {
                fail(errorNode, format("CVM container builder: {}", builder.errorMessage()))
            }
            i += 1
        }
        if (!problem.equals("")) { return null }
        CVM.BuildResult built = builder.encode()
        if (!built.ok()) {
            fail(errorNode, format("CVM container builder: {}", built.message()))
            return null
        }
        CVM.ValidationResult validation = CVM.ContainerValidator().validate(built.bytes())
        if (!validation.valid()) {
            fail(errorNode, format("CVM validation failed in section {} at byte {}: {}",
                validation.section(), validation.offset(), validation.message()))
            return null
        }
        return built.bytes()
    }

    bool isStatementNode(AstNode node) {
        return (node.name.equals("statement")
            || node.name.equals("matchedStatement")
            || node.name.equals("openStatement")
            || node.name.equals("simpleStatement")
            || node.name.equals("compoundStatement")
            || node.name.equals("switchStatement"))
    }

    list statementChildren(AstNode node) {
        list result = []
        int i = 0
        while (i < node.children.length) {
            AstNode part = child(node, i)
            if (isStatementNode(part)) { result.append(part) }
            i += 1
        }
        return result
    }

    void emitInt(int value) {
        code.emit(CVM.Opcode.CONST_I32, value, 1)
    }

    void emitByte(int value) {
        code.emit(CVM.Opcode.CONST_U8, value, 1)
    }

    void promoteToInt(String valueType) {
        if (valueType.equals("char")) {
            code.emitNoOperand(CVM.Opcode.TO_I32, 0)
        }
    }

    int addTemporary(String valueType) {
        int index = (currentFunction.parameterTypes.length
            + currentFunction.localTypes.length)
        currentFunction.localTypes.append(cvmType(valueType))
        return index
    }

    void emitLoad(SmallCVMVariable variable) {
        if (variable == null) { return }
        if (variable.array) {
            fail(errorNode, "internal attempt to load an array as a scalar")
            return
        }
        if (variable.global) {
            code.emit(CVM.Opcode.LDGLOBAL, variable.index, 1)
        }
        else { code.emit(CVM.Opcode.LDLOC, variable.index, 1) }
    }

    void emitStore(SmallCVMVariable variable) {
        if (variable == null) { return }
        if (variable.global) {
            code.emit(CVM.Opcode.STGLOBAL, variable.index, 0)
        }
        else { code.emit(CVM.Opcode.STLOC, variable.index, 0) }
    }

    void emitArrayReference(SmallCVMVariable variable) {
        if (variable == null || !variable.array) {
            fail(errorNode, "internal attempt to index a scalar")
            return
        }
        code.emit(CVM.Opcode.ARRAY, variable.index, 1)
    }

    void emitArrayInitializer(SmallCVMVariable variable, AstNode initializer) {
        if (initializer == null || variable == null) { return }
        SmallCVMArray array = arrays[variable.index] as SmallCVMArray
        if (initializer.children.length == 1
                && child(initializer, 0).name.equals("STRING")) {
            buffer bytes = stringBytes(child(initializer, 0).text)
            if (bytes.length > array.length) {
                fail(initializer, format("string initializer for '{}' exceeds array capacity {}",
                    variable.name, array.length))
                return
            }
            int i = 0
            while (i < bytes.length && problem.equals("")) {
                emitArrayReference(variable)
                emitInt(i)
                emitByte(int(bytes[i]))
                code.emitNoOperand(CVM.Opcode.ASET, -2)
                code.emitNoOperand(CVM.Opcode.POP, -1)
                i += 1
            }
            if (bytes.length < array.length && problem.equals("")) {
                emitArrayReference(variable)
                emitInt(bytes.length)
                emitByte(0)
                code.emitNoOperand(CVM.Opcode.ASET, -2)
                code.emitNoOperand(CVM.Opcode.POP, -1)
            }
            return
        }
        int element = 0
        int i = 0
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
                code.emitNoOperand(CVM.Opcode.ASET, -2)
                code.emitNoOperand(CVM.Opcode.POP, -1)
                element += 1
            }
            i += 1
        }
    }

    void emitDeclaration(AstNode declaration) {
        String baseType = child(child(declaration, 0), 0).text
        int i = 1
        while (i < declaration.children.length && problem.equals("")) {
            AstNode declarator = child(declaration, i)
            if (declarator.name.equals("declarator")) {
                AstNode nameNode = child(declarator, 0)
                bool isArray = declarator.children.length > 1 && child(declarator, 1).text.equals("[")
                AstNode initializer = declarationInitializer(declarator)
                if (isArray) {
                    int length = declaredArrayLength(declarator, initializer)
                    if (length <= 0) {
                        fail(nameNode, format("array '{}' requires a positive fixed size or inferable initializer", nameNode.text))
                    }
                    else {
                        int index = arrays.length
                        String arrayElementType = "int"
                        String arrayType = "int[]"
                        if (baseType.equals("char")) {
                            arrayElementType = "char"
                            arrayType = "char[]"
                        }
                        SmallCVMArray array = SmallCVMArray(
                            format("_cparsegen_array_{}", index), arrayElementType,
                            currentFunction.index, length, initializer)
                        arrays.append(array)
                        addLocal(nameNode.text, arrayType, true, index)
                        SmallCVMVariable variable = scope.variables[scope.variables.length - 1] as SmallCVMVariable
                        emitArrayInitializer(variable, initializer)
                    }
                }
                else {
                    int index = (currentFunction.parameterTypes.length
                        + currentFunction.localTypes.length)
                    addLocal(nameNode.text, baseType, false, index)
                    SmallCVMVariable variable = scope.variables[scope.variables.length - 1] as SmallCVMVariable
                    if (initializer != null && initializer.children.length > 0) {
                        String actual = emitExpression(child(initializer, 0))
                        if (!actual.equals(baseType)) {
                            fail(initializer, format("initializer for '{}' requires {}, got {}",
                                nameNode.text, baseType, actual))
                        }
                        emitStore(variable)
                        code.emitNoOperand(CVM.Opcode.POP, -1)
                    }
                }
            }
            i += 1
        }
    }

    void emitCompound(AstNode node, bool nested) {
        if (nested) { pushScope() }
        int i = 0
        while (i < node.children.length && problem.equals("")) {
            AstNode item = child(node, i)
            if (item.name.equals("blockItem")) { emitBlockItem(item) }
            i += 1
        }
        if (nested) { popScope() }
    }

    void emitBlockItem(AstNode node) {
        int i = 0
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
            int i = 0
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
            code.jump(CVM.Opcode.JMP, loop.breakLabel, 0)
            return
        }
        if (first.text.equals("continue")) {
            if (loop == null) {
                fail(first, "CVM backend does not support continue outside a loop")
                return
            }
            code.jump(CVM.Opcode.JMP, loop.continueLabel, 0)
            return
        }
        if (first.text.equals("return")) {
            AstNode expression = null
            int i = 1
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
            if (actual.equals("char")) {
                code.emitNoOperand(CVM.Opcode.RET_U8, -1)
            }
            else { code.emitNoOperand(CVM.Opcode.RET_I32, -1) }
            code.setDepth(0)
            return
        }
        int i = 0
        while (i < node.children.length && problem.equals("")) {
            AstNode part = child(node, i)
            if (part.name.equals("expression")) {
                emitExpression(part)
                code.emitNoOperand(CVM.Opcode.POP, -1)
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
        int i = 0
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
        int baseDepth = code.stackDepth
        String conditionType = emitExpression(condition)
        promoteToInt(conditionType)
        code.jump(CVM.Opcode.JZ, otherwise, -1)
        code.setDepth(baseDepth)
        emitStatement(statements[0] as AstNode)
        if (statements.length > 1) {
            code.jump(CVM.Opcode.JMP, end, 0)
            code.mark(otherwise)
            code.setDepth(baseDepth)
            emitStatement(statements[1] as AstNode)
            code.mark(end)
        }
        else { code.mark(otherwise) }
        code.setDepth(baseDepth)
    }

    void emitWhile(AstNode node) {
        AstNode condition = null
        list statements = statementChildren(node)
        int i = 0
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
        int baseDepth = code.stackDepth
        code.mark(loopStart)
        String conditionType = emitExpression(condition)
        promoteToInt(conditionType)
        code.jump(CVM.Opcode.JZ, end, -1)
        code.setDepth(baseDepth)
        loop = SmallCVMLoop(end, loopStart, loop)
        emitStatement(statements[0] as AstNode)
        loop = loop.parent
        code.setDepth(baseDepth)
        code.jump(CVM.Opcode.JMP, loopStart, 0)
        code.mark(end)
        code.setDepth(baseDepth)
    }

    void emitFor(AstNode node) {
        AstNode initializer = null
        AstNode condition = null
        AstNode update = null
        list statements = statementChildren(node)
        bool afterInitializer = false
        bool afterCondition = false
        int i = 0
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
        int baseDepth = code.stackDepth
        code.mark(loopStart)
        if (condition != null) {
            String conditionType = emitExpression(condition)
            promoteToInt(conditionType)
            code.jump(CVM.Opcode.JZ, end, -1)
            code.setDepth(baseDepth)
        }
        loop = SmallCVMLoop(end, updateLabel, loop)
        emitStatement(statements[0] as AstNode)
        loop = loop.parent
        code.setDepth(baseDepth)
        code.mark(updateLabel)
        if (update != null) {
            emitExpression(update)
            code.emitNoOperand(CVM.Opcode.POP, -1)
        }
        code.jump(CVM.Opcode.JMP, loopStart, 0)
        code.mark(end)
        code.setDepth(baseDepth)
        popScope()
    }

    void emitForInitializer(AstNode node) {
        int i = 0
        while (i < node.children.length && problem.equals("")) {
            AstNode part = child(node, i)
            if (part.name.equals("declaration")) { emitDeclaration(part) }
            else {
                if (part.name.equals("expression")) {
                    emitExpression(part)
                    code.emitNoOperand(CVM.Opcode.POP, -1)
                }
            }
            i += 1
        }
    }

    String emitExpression(AstNode node) {
        if (problem.length > 0 || node == null) { return "" }
        if (node.name.equals("expression")) {
            return emitExpression(child(node, 0))
        }
        if (node.name.equals("assignment")) {
            if (node.children.length == 3) { return emitAssignment(node) }
            return emitExpression(child(node, 0))
        }
        if (node.name.equals("logicalOr")) {
            return emitLogical(node, false)
        }
        if (node.name.equals("logicalAnd")) {
            return emitLogical(node, true)
        }
        if (node.name.equals("equality") || node.name.equals("relational")
                || node.name.equals("additive") || node.name.equals("multiplicative")) {
            return emitBinaryChain(node)
        }
        if (node.name.equals("unary")) { return emitUnary(node) }
        if (node.name.equals("primary")) { return emitPrimary(node) }
        if (node.name.equals("lvalue")) { return emitLvalue(node) }
        if (node.name.equals("INTEGER")) {
            int value = integerValue(node.text, 2147483647, node)
            code.emit(CVM.Opcode.CONST_I32, value, 1)
            return "int"
        }
        if (node.name.equals("CHAR")) {
            code.emit(CVM.Opcode.CONST_U8, characterValue(node.text), 1)
            return "char"
        }
        fail(node, format("CVM backend does not support expression node '{}'", node.name))
        return ""
    }

    String emitBinaryChain(AstNode node) {
        String resultType = emitExpression(child(node, 0))
        int i = 1
        while (i + 1 < node.children.length && problem.equals("")) {
            String operation = child(node, i).text
            promoteToInt(resultType)
            String rightType = emitExpression(child(node, i + 1))
            promoteToInt(rightType)
            int opcode = 0
            if (operation.equals("+")) { opcode = CVM.Opcode.ADD_I32 }
            if (operation.equals("-")) { opcode = CVM.Opcode.SUB_I32 }
            if (operation.equals("*")) { opcode = CVM.Opcode.MUL_I32 }
            if (operation.equals("/")) { opcode = CVM.Opcode.DIV_I32 }
            if (operation.equals("%")) { opcode = CVM.Opcode.REM_I32 }
            if (operation.equals("==")) { opcode = CVM.Opcode.EQ_I32 }
            if (operation.equals("!=")) { opcode = CVM.Opcode.NE_I32 }
            if (operation.equals("<")) { opcode = CVM.Opcode.LT_I32 }
            if (operation.equals("<=")) { opcode = CVM.Opcode.LE_I32 }
            if (operation.equals(">")) { opcode = CVM.Opcode.GT_I32 }
            if (operation.equals(">=")) { opcode = CVM.Opcode.GE_I32 }
            if (opcode == 0) {
                fail(child(node, i), format("CVM backend does not support operator '{}'", operation))
            }
            if (opcode != 0) { code.emitNoOperand(opcode, -1) }
            resultType = "int"
            i += 2
        }
        return resultType
    }

    String emitLogical(AstNode node, bool conjunction) {
        if (node.children.length == 1) { return emitExpression(child(node, 0)) }
        String end = code.newLabel()
        String shortCircuit = code.newLabel()
        int baseDepth = code.stackDepth
        int i = 0
        while (i < node.children.length && problem.equals("")) {
            AstNode part = child(node, i)
            if (part.name.equals("logicalAnd") || part.name.equals("equality")) {
                String valueType = emitExpression(part)
                promoteToInt(valueType)
                if (conjunction) {
                    code.jump(CVM.Opcode.JZ, shortCircuit, -1)
                    code.setDepth(baseDepth)
                }
                else {
                    String next = code.newLabel()
                    code.jump(CVM.Opcode.JZ, next, -1)
                    code.setDepth(baseDepth)
                    emitInt(1)
                    code.jump(CVM.Opcode.JMP, end, 0)
                    code.mark(next)
                    code.setDepth(baseDepth)
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
            code.jump(CVM.Opcode.JMP, end, 0)
            code.mark(shortCircuit)
            code.setDepth(baseDepth)
            emitInt(0)
        }
        else { emitInt(0) }
        code.mark(end)
        code.setDepth(baseDepth + 1)
        return "int"
    }

    String emitUnary(AstNode node) {
        if (node.children.length == 1) { return emitExpression(child(node, 0)) }
        String operation = child(node, 0).text
        AstNode operand = child(node, 1)
        if (operation.equals("++") || operation.equals("--")) {
            return emitIncrement(operand, false, operation.equals("++"))
        }
        if (operation.equals("-") && operand.name.equals("INTEGER")
                && isMinimumIntegerLiteral(operand.text)) {
            code.emit(CVM.Opcode.CONST_I32, -2147483648, 1)
            return "int"
        }
        String valueType = emitExpression(operand)
        if (operation.equals("+")) {
            promoteToInt(valueType)
            return "int"
        }
        if (operation.equals("-")) {
            promoteToInt(valueType)
            code.emitNoOperand(CVM.Opcode.NEG_I32, 0)
            return "int"
        }
        if (operation.equals("!")) {
            promoteToInt(valueType)
            emitInt(0)
            code.emitNoOperand(CVM.Opcode.EQ_I32, -1)
            return "int"
        }
        fail(child(node, 0), format("CVM backend does not support unary operator '{}'", operation))
        return ""
    }

    String emitPrimary(AstNode node) {
        if (node.children.length >= 3 && child(node, 0).name.equals("IDENT")
                && child(node, 1).text.equals("(")) {
            return emitCall(node)
        }
        if (node.children.length == 3 && child(node, 0).text.equals("(")) {
            return emitExpression(child(node, 1))
        }
        if (child(node, 0).name.equals("lvalue")) {
            if (node.children.length > 1) {
                String operation = child(node, 1).text
                return emitIncrement(child(node, 0), true, operation.equals("++"))
            }
            return emitLvalue(child(node, 0))
        }
        return emitExpression(child(node, 0))
    }

    String emitCall(AstNode node) {
        AstNode nameNode = child(node, 0)
        SmallCVMFunction function = findFunction(nameNode.text)
        if (function == null || function.body == null) {
            fail(nameNode, format("CVM backend has no definition for function '{}'", nameNode.text))
            return ""
        }
        int i = 0
        while (i < node.children.length && problem.equals("")) {
            AstNode part = child(node, i)
            if (part.name.equals("arguments")) {
                int a = 0
                while (a < part.children.length && problem.equals("")) {
                    AstNode argument = child(part, a)
                    if (argument.name.equals("assignment")) {
                        emitExpression(argument)
                    }
                    a += 1
                }
            }
            i += 1
        }
        int delta = 0
        if (function.returnType.equals("int") || function.returnType.equals("char")) {
            delta = 1
        }
        delta -= function.parameterTypes.length
        code.emit(CVM.Opcode.CALL, function.index, delta)
        return function.returnType
    }

    String emitLvalue(AstNode node) {
        AstNode nameNode = child(node, 0)
        SmallCVMVariable variable = findVariable(nameNode.text)
        if (variable == null) {
            fail(nameNode, format("undeclared variable '{}'", nameNode.text))
            return ""
        }
        if (node.children.length == 1) {
            if (variable.array) {
                fail(nameNode, format("array '{}' cannot be used as a scalar value", nameNode.text))
                return ""
            }
            emitLoad(variable)
            return variable.valueType
        }
        if (!variable.array) {
            fail(nameNode, format("variable '{}' is not an array", nameNode.text))
            return ""
        }
        emitArrayReference(variable)
        String indexType = emitExpression(child(node, 2))
        promoteToInt(indexType)
        code.emitNoOperand(CVM.Opcode.AGET, -1)
        return elementType(variable.valueType)
    }

    int evaluateIndex(AstNode lvalue) {
        String indexType = emitExpression(child(lvalue, 2))
        promoteToInt(indexType)
        int slot = addTemporary("int")
        code.emit(CVM.Opcode.STLOC, slot, 0)
        code.emitNoOperand(CVM.Opcode.POP, -1)
        return slot
    }

    String emitAssignment(AstNode node) {
        AstNode lvalue = child(node, 0)
        String operation = child(node, 1).text
        AstNode right = child(node, 2)
        AstNode nameNode = child(lvalue, 0)
        SmallCVMVariable variable = findVariable(nameNode.text)
        if (variable == null) {
            fail(nameNode, format("undeclared variable '{}'", nameNode.text))
            return ""
        }
        if (!variable.array) {
            if (operation.equals("=")) {
                String valueType = emitExpression(right)
                emitStore(variable)
                return valueType
            }
            emitLoad(variable)
            String rightType = emitExpression(right)
            promoteToInt(rightType)
            emitCompoundOperation(operation, child(node, 1))
            emitStore(variable)
            return "int"
        }
        int indexSlot = evaluateIndex(lvalue)
        if (operation.equals("=")) {
            String valueType = emitExpression(right)
            int valueSlot = addTemporary(valueType)
            code.emit(CVM.Opcode.STLOC, valueSlot, 0)
            code.emitNoOperand(CVM.Opcode.POP, -1)
            emitArrayReference(variable)
            code.emit(CVM.Opcode.LDLOC, indexSlot, 1)
            code.emit(CVM.Opcode.LDLOC, valueSlot, 1)
            code.emitNoOperand(CVM.Opcode.ASET, -2)
            return valueType
        }
        emitArrayReference(variable)
        code.emit(CVM.Opcode.LDLOC, indexSlot, 1)
        code.emitNoOperand(CVM.Opcode.AGET, -1)
        String rightType = emitExpression(right)
        promoteToInt(rightType)
        emitCompoundOperation(operation, child(node, 1))
        int resultSlot = addTemporary("int")
        code.emit(CVM.Opcode.STLOC, resultSlot, 0)
        code.emitNoOperand(CVM.Opcode.POP, -1)
        emitArrayReference(variable)
        code.emit(CVM.Opcode.LDLOC, indexSlot, 1)
        code.emit(CVM.Opcode.LDLOC, resultSlot, 1)
        code.emitNoOperand(CVM.Opcode.ASET, -2)
        return "int"
    }

    void emitCompoundOperation(String operation, AstNode operator) {
        int opcode = 0
        if (operation.equals("+=")) { opcode = CVM.Opcode.ADD_I32 }
        if (operation.equals("-=")) { opcode = CVM.Opcode.SUB_I32 }
        if (operation.equals("*=")) { opcode = CVM.Opcode.MUL_I32 }
        if (operation.equals("/=")) { opcode = CVM.Opcode.DIV_I32 }
        if (operation.equals("%=")) { opcode = CVM.Opcode.REM_I32 }
        if (opcode == 0) { fail(operator, format("CVM backend does not support operator '{}'", operation)) }
        if (opcode != 0) { code.emitNoOperand(opcode, -1) }
    }

    String emitIncrement(AstNode lvalue, bool postfix, bool increment) {
        AstNode nameNode = child(lvalue, 0)
        SmallCVMVariable variable = findVariable(nameNode.text)
        if (variable == null) {
            fail(nameNode, format("undeclared variable '{}'", nameNode.text))
            return ""
        }
        String valueType = elementType(variable.valueType)
        if (!variable.array) {
            int oldSlot = addTemporary(valueType)
            emitLoad(variable)
            code.emit(CVM.Opcode.STLOC, oldSlot, 0)
            code.emitNoOperand(CVM.Opcode.POP, -1)
            emitLoad(variable)
            promoteToInt(valueType)
            emitInt(1)
            int opcode = CVM.Opcode.SUB_I32
            if (increment) { opcode = CVM.Opcode.ADD_I32 }
            code.emitNoOperand(opcode, -1)
            if (valueType.equals("char")) {
                code.emitNoOperand(CVM.Opcode.TO_U8, 0)
            }
            emitStore(variable)
            if (postfix) {
                code.emitNoOperand(CVM.Opcode.POP, -1)
                code.emit(CVM.Opcode.LDLOC, oldSlot, 1)
            }
            return valueType
        }
        int indexSlot = evaluateIndex(lvalue)
        emitArrayReference(variable)
        code.emit(CVM.Opcode.LDLOC, indexSlot, 1)
        code.emitNoOperand(CVM.Opcode.AGET, -1)
        int oldSlot = addTemporary(valueType)
        code.emit(CVM.Opcode.STLOC, oldSlot, 0)
        code.emitNoOperand(CVM.Opcode.POP, -1)
        code.emit(CVM.Opcode.LDLOC, oldSlot, 1)
        promoteToInt(valueType)
        emitInt(1)
        int opcode = CVM.Opcode.SUB_I32
        if (increment) { opcode = CVM.Opcode.ADD_I32 }
        code.emitNoOperand(opcode, -1)
        if (valueType.equals("char")) {
            code.emitNoOperand(CVM.Opcode.TO_U8, 0)
        }
        int newSlot = addTemporary(valueType)
        code.emit(CVM.Opcode.STLOC, newSlot, 0)
        code.emitNoOperand(CVM.Opcode.POP, -1)
        emitArrayReference(variable)
        code.emit(CVM.Opcode.LDLOC, indexSlot, 1)
        code.emit(CVM.Opcode.LDLOC, newSlot, 1)
        code.emitNoOperand(CVM.Opcode.ASET, -2)
        if (postfix) {
            code.emitNoOperand(CVM.Opcode.POP, -1)
            code.emit(CVM.Opcode.LDLOC, oldSlot, 1)
        }
        return valueType
    }
}

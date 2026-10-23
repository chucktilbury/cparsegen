include "parser.cw"

class SmallCLocation {
    AstNode node
    int offset

    SmallCLocation(AstNode value, int at) {
        node = value
        offset = at
    }
}

class SmallCTokenCursor {
    int index

    SmallCTokenCursor() {
        index = 0
    }
}

class SmallCScope {
    list symbols
    SmallCScope parent

    SmallCScope(SmallCScope outer) {
        symbols = []
        parent = outer
    }
}

class SmallCSymbol {
    String name
    String kind
    String valueType
    list parameterTypes
    bool hasPrototype
    bool hasDefinition

    SmallCSymbol(String symbolName, String symbolKind, String symbolType) {
        name = symbolName
        kind = symbolKind
        valueType = symbolType
        parameterTypes = []
        hasPrototype = false
        hasDefinition = false
    }
}

// Compiler-recognized pseudo-functions. They have no definitions or
// declarations in SmallC source; the checker validates calls against these
// signatures and the CVM backend lowers each one to a single `sys` service.
// "void" results may only be used as expression statements, "char[]" accepts
// only the bare name of a char array, and "byte" accepts char or int.
class SmallCIntrinsic {
    String name
    String resultType
    list parameterTypes
    String service

    SmallCIntrinsic(String intrinsicName, String result, list parameters,
            String serviceName) {
        name = intrinsicName
        resultType = result
        parameterTypes = parameters
        service = serviceName
    }
}

class SmallCIntrinsics {
    list entries

    SmallCIntrinsics() {
        entries = []
        entries.append(SmallCIntrinsic("cvm_print_int", "void", ["int"], "stdout_i32"))
        entries.append(SmallCIntrinsic("cvm_print_byte", "void", ["byte"], "stdout_byte"))
        entries.append(SmallCIntrinsic("cvm_read_byte", "int", [], "stdin_byte"))
        entries.append(SmallCIntrinsic("cvm_open_read", "file", ["char[]"], "file_open_read"))
        entries.append(SmallCIntrinsic("cvm_open_write", "file", ["char[]"], "file_open_write"))
        entries.append(SmallCIntrinsic("cvm_read", "int",
            ["file", "char[]", "int", "int"], "file_read"))
        entries.append(SmallCIntrinsic("cvm_write", "int",
            ["file", "char[]", "int", "int"], "file_write"))
        entries.append(SmallCIntrinsic("cvm_close", "void", ["file"], "file_close"))
    }

    SmallCIntrinsic find(String name) {
        int i = 0
        while (i < entries.length) {
            SmallCIntrinsic entry = entries[i] as SmallCIntrinsic
            if (entry.name.equals(name)) { return entry }
            i += 1
        }
        return null
    }
}

class SmallCSemanticChecker : GeneratedVisitor {
    SmallCIntrinsics intrinsics
    list locations
    list globals
    SmallCScope currentScope
    String problem
    int errorOffset
    String returnType
    list labels
    int loopDepth
    int switchDepth
    list parameterNames
    list checkedParameterTypes

    SmallCSemanticChecker() {
        super GeneratedVisitor()
        intrinsics = SmallCIntrinsics()
        locations = []
        globals = []
        currentScope = null
        problem = ""
        errorOffset = 0
        returnType = ""
        labels = []
        loopDepth = 0
        switchDepth = 0
        parameterNames = []
        checkedParameterTypes = []
    }

    AstNode child(AstNode node, int index) {
        return node.children[index] as AstNode
    }

    void indexLocations(AstNode node, list tokens, SmallCTokenCursor cursor) {
        if (node.children.length == 0) {
            int offset = 0
            if (cursor.index < tokens.length) {
                offset = (tokens[cursor.index] as LexToken).offset
                cursor.index += 1
            }
            locations.append(SmallCLocation(node, offset))
            return
        }
        int i = 0
        while (i < node.children.length) {
            indexLocations(child(node, i), tokens, cursor)
            i += 1
        }
        locations.append(SmallCLocation(node, offsetOf(child(node, 0))))
    }

    int offsetOf(AstNode node) {
        int i = 0
        while (i < locations.length) {
            SmallCLocation location = locations[i] as SmallCLocation
            if (location.node == node) { return location.offset }
            i += 1
        }
        return 0
    }

    void fail(AstNode node, String message) {
        if (problem.equals("")) {
            problem = message
            errorOffset = offsetOf(node)
        }
    }

    bool isArray(String valueType) {
        return valueType.equals("int[]") || valueType.equals("char[]")
    }

    String elementType(String valueType) {
        if (valueType.equals("int[]")) { return "int" }
        if (valueType.equals("char[]")) { return "char" }
        return valueType
    }

    bool isScalar(String valueType) {
        return valueType.equals("int") || valueType.equals("char")
    }

    bool isValue(String valueType) {
        return isScalar(valueType) || valueType.equals("file")
    }

    SmallCSymbol findGlobal(String name) {
        int i = 0
        while (i < globals.length) {
            SmallCSymbol symbol = globals[i] as SmallCSymbol
            if (symbol.name.equals(name)) { return symbol }
            i += 1
        }
        return null
    }

    SmallCSymbol findScoped(String name) {
        SmallCScope scope = currentScope
        while (scope != null) {
            int i = 0
            while (i < scope.symbols.length) {
                SmallCSymbol symbol = scope.symbols[i] as SmallCSymbol
                if (symbol.name.equals(name)) { return symbol }
                i += 1
            }
            scope = scope.parent
        }
        return null
    }

    SmallCSymbol findVariable(String name) {
        SmallCSymbol symbol = findScoped(name)
        if (symbol != null) { return symbol }
        return findGlobal(name)
    }

    bool currentScopeHas(String name) {
        if (currentScope == null) { return false }
        int i = 0
        while (i < currentScope.symbols.length) {
            if ((currentScope.symbols[i] as SmallCSymbol).name.equals(name)) { return true }
            i += 1
        }
        return false
    }

    void pushScope() {
        currentScope = SmallCScope(currentScope)
    }

    void popScope() {
        if (currentScope != null) { currentScope = currentScope.parent }
    }

    void addVariable(AstNode nameNode, String valueType, bool global) {
        String name = nameNode.text
        if (intrinsics.find(name) != null) {
            fail(nameNode, format("'{}' is a reserved compiler intrinsic name", name))
            return
        }
        if (global) {
            if (findGlobal(name) != null) {
                fail(nameNode, format("duplicate global declaration '{}'", name))
                return
            }
            globals.append(SmallCSymbol(name, "variable", valueType))
            return
        }
        if (currentScopeHas(name)) {
            fail(nameNode, format("duplicate variable declaration '{}'", name))
            return
        }
        currentScope.symbols.append(SmallCSymbol(name, "variable", valueType))
    }

    String exactType(String actual, String expected, AstNode node, String context) {
        if (actual.equals("void")) {
            fail(node, format("{} cannot use the result of a void intrinsic", context))
            return ""
        }
        if (!isValue(actual)) {
            fail(node, format("{} requires a scalar value", context))
            return ""
        }
        if (!actual.equals(expected)) {
            fail(node, format("{} requires {}, got {}", context, expected, actual))
            return ""
        }
        return actual
    }

    String lvalueType(AstNode node, bool writing) {
        AstNode nameNode = child(node, 0)
        SmallCSymbol symbol = findVariable(nameNode.text)
        if (symbol == null) {
            fail(nameNode, format("undeclared variable '{}'", nameNode.text))
            return ""
        }
        if (!symbol.kind.equals("variable")) {
            fail(nameNode, format("function '{}' is not a variable", nameNode.text))
            return ""
        }
        if (node.children.length == 1) {
            if (writing && isArray(symbol.valueType)) {
                fail(nameNode, format("array '{}' is not a modifiable scalar", nameNode.text))
                return ""
            }
            return symbol.valueType
        }
        if (!isArray(symbol.valueType)) {
            fail(nameNode, format("variable '{}' is not an array", nameNode.text))
            return ""
        }
        String indexType = expressionType(child(node, 2))
        if (!isScalar(indexType)) {
            fail(child(node, 2), "array index must have integral scalar type")
            return ""
        }
        return elementType(symbol.valueType)
    }

    // Returns the lvalue naming a whole array when an argument is exactly
    // that bare identifier, otherwise null.
    AstNode arrayArgument(AstNode argument) {
        AstNode current = argument
        while (!current.name.equals("lvalue") && current.children.length == 1) {
            current = child(current, 0)
        }
        if (current.name.equals("lvalue") && current.children.length == 1) { return current }
        return null
    }

    String intrinsicCallType(AstNode node, SmallCIntrinsic intrinsic) {
        AstNode nameNode = child(node, 0)
        int argumentCount = 0
        int i = 0
        while (i < node.children.length && !child(node, i).name.equals("arguments")) { i += 1 }
        if (i < node.children.length) {
            AstNode arguments = child(node, i)
            int a = 0
            while (a < arguments.children.length && problem.equals("")) {
                AstNode argument = child(arguments, a)
                if (argument.name.equals("assignment")) {
                    if (argumentCount >= intrinsic.parameterTypes.length) {
                        fail(argument, format("intrinsic '{}' called with too many arguments", intrinsic.name))
                    }
                    else {
                        String expected = intrinsic.parameterTypes[argumentCount] as String
                        String context = format("argument {} to '{}'", argumentCount + 1, intrinsic.name)
                        if (expected.equals("char[]")) {
                            AstNode target = arrayArgument(argument)
                            SmallCSymbol symbol = null
                            if (target != null) { symbol = findVariable(child(target, 0).text) }
                            if (symbol == null || !symbol.kind.equals("variable")
                                    || !symbol.valueType.equals("char[]")) {
                                fail(argument, format("{} requires the name of a char array", context))
                            }
                        }
                        else {
                            String actual = expressionType(argument)
                            if (problem.equals("")) {
                                if (expected.equals("byte") || expected.equals("int")) {
                                    if (actual.equals("void")) {
                                        fail(argument, format("{} cannot use the result of a void intrinsic", context))
                                    }
                                    else {
                                        if (!isScalar(actual)) {
                                            fail(argument, format("{} requires an integral scalar value", context))
                                        }
                                    }
                                }
                                else { exactType(actual, expected, argument, context) }
                            }
                        }
                    }
                    argumentCount += 1
                }
                a += 1
            }
        }
        if (problem.equals("") && argumentCount != intrinsic.parameterTypes.length) {
            fail(nameNode, format("intrinsic '{}' expects {} arguments, got {}", intrinsic.name, intrinsic.parameterTypes.length, argumentCount))
        }
        return intrinsic.resultType
    }

    String callType(AstNode node) {
        AstNode nameNode = child(node, 0)
        SmallCIntrinsic intrinsic = intrinsics.find(nameNode.text)
        if (intrinsic != null) { return intrinsicCallType(node, intrinsic) }
        SmallCSymbol local = findScoped(nameNode.text)
        if (local != null) {
            fail(nameNode, format("'{}' names a variable, not a function", nameNode.text))
            return ""
        }
        SmallCSymbol function = findGlobal(nameNode.text)
        if (function == null) {
            fail(nameNode, format("call to undeclared function '{}'", nameNode.text))
            return ""
        }
        if (!function.kind.equals("function")) {
            fail(nameNode, format("'{}' names a variable, not a function", nameNode.text))
            return ""
        }
        int argumentCount = 0
        int i = 0
        while (i < node.children.length && !child(node, i).name.equals("arguments")) { i += 1 }
        if (i < node.children.length) {
            AstNode arguments = child(node, i)
            int a = 0
            while (a < arguments.children.length && problem.equals("")) {
                AstNode argument = child(arguments, a)
                if (argument.name.equals("assignment")) {
                    String actual = expressionType(argument)
                    if (argumentCount >= function.parameterTypes.length) {
                        fail(argument, format("function '{}' called with too many arguments", function.name))
                    }
                    else {
                        String expected = function.parameterTypes[argumentCount] as String
                        exactType(actual, expected, argument, format("argument {} to '{}'", argumentCount + 1, function.name))
                    }
                    argumentCount += 1
                }
                a += 1
            }
        }
        if (problem.equals("") && argumentCount != function.parameterTypes.length) {
            fail(nameNode, format("function '{}' expects {} arguments, got {}", function.name, function.parameterTypes.length, argumentCount))
        }
        return function.valueType
    }

    String expressionType(AstNode node) {
        if (!problem.equals("")) { return "" }
        if (node.name.equals("INTEGER")) { return "int" }
        if (node.name.equals("CHAR")) { return "char" }
        if (node.name.equals("lvalue")) {
            String valueType = lvalueType(node, false)
            if (isArray(valueType)) {
                fail(child(node, 0), format("array '{}' cannot be used as a scalar value", child(node, 0).text))
                return ""
            }
            return valueType
        }
        if (node.name.equals("assignment") && node.children.length == 3) {
            String left = lvalueType(child(node, 0), true)
            String operation = child(node, 1).text
            String right = expressionType(child(node, 2))
            if (problem.equals("")) {
                if (operation.equals("=")) {
                    if (right.equals("void")) {
                        fail(child(node, 2), "assignment cannot use the result of a void intrinsic")
                    }
                    else {
                        if (!isValue(right)) { fail(child(node, 2), "assignment requires a scalar value") }
                        else {
                            if (!left.equals(right)) { fail(child(node, 0), format("assignment requires {}, got {}", left, right)) }
                        }
                    }
                }
                else {
                    if (!isScalar(left) || !isScalar(right)) {
                        fail(node, "compound assignment requires integral scalar operands")
                    }
                    else {
                        if (!left.equals("int")) {
                            fail(child(node, 0), format("compound assignment produces int, not {}", left))
                        }
                    }
                }
            }
            return left
        }
        if (node.name.equals("primary")) {
            if (node.children.length >= 3 && child(node, 0).name.equals("IDENT") && child(node, 1).text.equals("(")) {
                return callType(node)
            }
            if (node.children.length == 3 && child(node, 0).text.equals("(")) {
                return expressionType(child(node, 1))
            }
            if (child(node, 0).name.equals("lvalue")) {
                String valueType = lvalueType(child(node, 0), node.children.length > 1)
                if (node.children.length > 1 && !isScalar(valueType)) {
                    fail(child(node, 0), "increment/decrement requires a scalar variable")
                    return ""
                }
                if (isArray(valueType)) {
                    fail(child(child(node, 0), 0), format("array '{}' cannot be used as a scalar value", child(child(node, 0), 0).text))
                    return ""
                }
                return valueType
            }
            return expressionType(child(node, 0))
        }
        if (node.name.equals("unary")) {
            if (node.children.length == 1) { return expressionType(child(node, 0)) }
            if (node.children.length == 2 && (child(node, 0).text.equals("++") || child(node, 0).text.equals("--"))) {
                String target = lvalueType(child(node, 1), true)
                if (!isScalar(target)) {
                    fail(child(node, 1), "increment/decrement requires a scalar variable")
                    return ""
                }
                return target
            }
            String operand = expressionType(child(node, 1))
            if (!isScalar(operand)) {
                fail(child(node, 1), "unary operator requires an integral scalar operand")
                return ""
            }
            return "int"
        }
        if (node.children.length > 1) {
            String result = expressionType(child(node, 0))
            int i = 1
            while (i < node.children.length && problem.equals("")) {
                if (i + 1 < node.children.length) {
                    String right = expressionType(child(node, i + 1))
                    if (!isScalar(result) || !isScalar(right)) {
                        fail(child(node, i + 1), "operator requires integral scalar operands")
                        return ""
                    }
                    result = "int"
                    i += 2
                }
                else { i += 1 }
            }
            return result
        }
        if (node.children.length == 1) { return expressionType(child(node, 0)) }
        fail(node, format("unsupported expression node '{}'", node.name))
        return ""
    }

    void checkInitializer(AstNode initializer, String valueType, AstNode nameNode) {
        if (!problem.equals("")) { return }
        bool array = isArray(valueType)
        String target = elementType(valueType)
        if (initializer.children.length == 1 && child(initializer, 0).name.equals("STRING")) {
            if (!array || !target.equals("char")) {
                fail(initializer, "string initializer requires a char array")
            }
            return
        }
        if (initializer.children.length > 0 && child(initializer, 0).text.equals("{")) {
            if (!array) {
                fail(initializer, format("scalar '{}' cannot use an array initializer", nameNode.text))
                return
            }
            int i = 1
            while (i < initializer.children.length && problem.equals("")) {
                AstNode value = child(initializer, i)
                if (value.name.equals("assignment")) {
                    String actual = expressionType(value)
                    exactType(actual, target, value, format("array initializer for '{}'", nameNode.text))
                }
                i += 1
            }
            return
        }
        if (array) {
            fail(initializer, format("array '{}' requires a string or brace initializer", nameNode.text))
            return
        }
        if (initializer.children.length == 1) {
            String actual = expressionType(child(initializer, 0))
            exactType(actual, target, initializer, format("initializer for '{}'", nameNode.text))
            return
        }
        fail(initializer, format("invalid initializer for '{}'", nameNode.text))
    }

    void checkDeclaration(AstNode node, bool global) {
        String base = child(child(node, 0), 0).text
        int i = 1
        while (i < node.children.length && problem.equals("")) {
            AstNode declarator = child(node, i)
            if (declarator.name.equals("declarator")) {
                AstNode nameNode = child(declarator, 0)
                bool array = declarator.children.length > 1 && child(declarator, 1).text.equals("[")
                String valueType = base
                int initializerIndex = declarator.children.length
                if (array) {
                    valueType = "int[]"
                    if (base.equals("char")) { valueType = "char[]" }
                    int d = 1
                    while (d < declarator.children.length
                            && !child(declarator, d).text.equals("=")) { d += 1 }
                    initializerIndex = d
                }
                else {
                    if (declarator.children.length > 1 && child(declarator, 1).text.equals("=")) {
                        initializerIndex = 1
                    }
                }
                if (base.equals("file")) {
                    if (array) {
                        fail(nameNode, format("array '{}' cannot have element type file", nameNode.text))
                    }
                    else {
                        if (global) {
                            fail(nameNode, format("file variable '{}' must be local or a parameter", nameNode.text))
                        }
                    }
                }
                if (problem.equals("")) { addVariable(nameNode, valueType, global) }
                if (problem.equals("") && initializerIndex < declarator.children.length) {
                    checkInitializer(child(declarator, initializerIndex + 1), valueType, nameNode)
                }
            }
            i += 1
        }
    }

    list parameterTypes(AstNode parameters) {
        parameterNames = []
        checkedParameterTypes = []
        if (walk(parameters) != VISIT_CONTINUE && problem.equals("")) {
            fail(parameters, "parameter visitor failed")
        }
        return checkedParameterTypes
    }

    int enter_rule_parameter(AstNode node) {
        String valueType = node.childAt(0).childAt(0).lexeme()
        AstNode nameNode = node.childAt(1)
        int i = 0
        while (i < parameterNames.length) {
            if ((parameterNames[i] as String).equals(nameNode.lexeme())) {
                fail(nameNode, format("duplicate parameter '{}'", nameNode.lexeme()))
                return VISIT_ERROR
            }
            i += 1
        }
        parameterNames.append(nameNode.lexeme())
        checkedParameterTypes.append(valueType)
        return VISIT_SKIP
    }

    bool isLabel(AstNode node) {
        return ((node.name.equals("matchedStatement") || node.name.equals("openStatement"))
            && node.children.length == 3 && child(node, 0).name.equals("IDENT")
            && child(node, 1).text.equals(":"))
    }

    void collectLabels(AstNode node) {
        if (isLabel(node)) { labels.append(child(node, 0)) }
        int i = 0
        while (i < node.children.length) {
            collectLabels(child(node, i))
            i += 1
        }
    }

    AstNode findLabel(String name) {
        int i = 0
        while (i < labels.length) {
            AstNode label = labels[i] as AstNode
            if (label.text.equals(name)) { return label }
            i += 1
        }
        return null
    }

    String caseKey(AstNode node) {
        AstNode literal = child(node, node.children.length - 1)
        String text = literal.text
        if (literal.name.equals("CHAR")) {
            int value = int(text.byteAt(1))
            if (value == 92) {
                value = int(text.byteAt(2))
                if (value == 110) { value = 10 }
                else {
                    if (value == 114) { value = 13 }
                    else {
                        if (value == 116) { value = 9 }
                        else { if (value == 48) { value = 0 } }
                    }
                }
            }
            return format("{}", value)
        }
        // Compare decimal spellings without imposing a host integer width.
        int first = 0
        while (first + 1 < text.length && int(text.byteAt(first)) == 48) { first += 1 }
        String result = text.slice(first, text.length)
        if (child(node, 0).text.equals("-") && !result.equals("0")) {
            return format("-{}", result)
        }
        return result
    }

    void checkFunction(AstNode node) {
        String valueType = child(child(node, 0), 0).text
        AstNode nameNode = child(node, 1)
        AstNode parameters = null
        AstNode body = null
        bool definition = false
        int i = 0
        while (i < node.children.length) {
            AstNode part = child(node, i)
            if (part.name.equals("parameters")) { parameters = part }
            if (part.name.equals("compoundStatement")) { body = part
definition = true }
            i += 1
        }
        if (intrinsics.find(nameNode.text) != null) {
            fail(nameNode, format("'{}' is a reserved compiler intrinsic name", nameNode.text))
            return
        }
        list types = []
        if (parameters != null) { types = parameterTypes(parameters) }
        if (!problem.equals("")) { return }
        SmallCSymbol function = findGlobal(nameNode.text)
        if (function != null && !function.kind.equals("function")) {
            fail(nameNode, format("function '{}' conflicts with a global variable", nameNode.text))
            return
        }
        if (function == null) {
            function = SmallCSymbol(nameNode.text, "function", valueType)
            function.parameterTypes = types
            globals.append(function)
        }
        else {
            if (!function.valueType.equals(valueType) || function.parameterTypes.length != types.length) {
                fail(nameNode, format("incompatible function signature for '{}'", nameNode.text))
                return
            }
            int p = 0
            while (p < types.length && problem.equals("")) {
                if (!(function.parameterTypes[p] as String).equals(types[p] as String)) {
                    fail(nameNode, format("incompatible function signature for '{}'", nameNode.text))
                }
                p += 1
            }
        }
        if (!problem.equals("")) { return }
        if (definition && function.hasDefinition) {
            fail(nameNode, format("duplicate definition of function '{}'", nameNode.text))
            return
        }
        if (!definition && function.hasPrototype) {
            fail(nameNode, format("duplicate declaration of function '{}'", nameNode.text))
            return
        }
        if (definition) { function.hasDefinition = true }
        else { function.hasPrototype = true }
        if (definition) {
            returnType = valueType
            labels = []
            loopDepth = 0
            switchDepth = 0
            collectLabels(body)
            pushScope()
            if (parameters != null) {
                int p = 0
                int parameterIndex = 0
                while (p < parameters.children.length && problem.equals("")) {
                    AstNode parameter = child(parameters, p)
                    if (parameter.name.equals("parameter")) {
                        addVariable(child(parameter, 1), types[parameterIndex] as String, false)
                        parameterIndex += 1
                    }
                    p += 1
                }
            }
            if (problem.equals("")) { checkCompound(body, false) }
            popScope()
            returnType = ""
            labels = []
        }
    }

    void checkForInitializer(AstNode node) {
        int i = 0
        while (i < node.children.length && problem.equals("")) {
            AstNode part = child(node, i)
            if (part.name.equals("declaration")) { checkDeclaration(part, false) }
            else { if (part.name.equals("expression")) { expressionType(part) } }
            i += 1
        }
    }

    void checkCompound(AstNode node, bool nested) {
        if (nested) { pushScope() }
        int i = 0
        while (i < node.children.length && problem.equals("")) {
            AstNode part = child(node, i)
            if (part.name.equals("blockItem")) { checkBlockItem(part) }
            i += 1
        }
        if (nested) { popScope() }
    }

    void checkBlockItem(AstNode node) {
        int i = 0
        while (i < node.children.length && problem.equals("")) {
            AstNode part = child(node, i)
            if (part.name.equals("declaration")) { checkDeclaration(part, false) }
            else { if (part.name.equals("statement")) { checkStatement(part) } }
            i += 1
        }
    }

    void checkSwitch(AstNode node) {
        list cases = []
        bool hasDefault = false
        switchDepth += 1
        int i = 0
        while (i < node.children.length && problem.equals("")) {
            AstNode part = child(node, i)
            if (part.name.equals("expression")) {
                String valueType = expressionType(part)
                if (!isScalar(valueType)) { fail(part, "switch expression must have integral scalar type") }
            }
            else {
                if (part.name.equals("switchSection")) {
                    AstNode keyword = child(part, 0)
                    if (keyword.text.equals("default")) {
                        if (hasDefault) { fail(keyword, "duplicate default label") }
                        hasDefault = true
                    }
                    else {
                        AstNode value = child(part, 1)
                        String key = caseKey(value)
                        int c = 0
                        while (c < cases.length && problem.equals("")) {
                            if ((cases[c] as String).equals(key)) {
                                fail(value, format("duplicate case constant {}", key))
                            }
                            c += 1
                        }
                        cases.append(key)
                    }
                    int j = 0
                    while (j < part.children.length && problem.equals("")) {
                        AstNode item = child(part, j)
                        if (item.name.equals("blockItem")) { checkBlockItem(item) }
                        j += 1
                    }
                }
            }
            i += 1
        }
        switchDepth -= 1
    }

    void checkSimpleStatement(AstNode node) {
        AstNode keyword = child(node, 0)
        if (keyword.text.equals("break") && loopDepth == 0 && switchDepth == 0) {
            fail(keyword, "break requires an enclosing loop or switch")
        }
        if (keyword.text.equals("continue") && loopDepth == 0) {
            fail(keyword, "continue requires an enclosing loop")
        }
        if (keyword.text.equals("goto")) {
            AstNode target = child(node, 1)
            if (findLabel(target.text) == null) {
                fail(target, format("unresolved goto label '{}'", target.text))
            }
        }
        bool isReturn = false
        AstNode returnedValue = null
        int i = 0
        while (i < node.children.length && problem.equals("")) {
            AstNode part = child(node, i)
            if (part.text.equals("return")) { isReturn = true }
            else {
                if (part.name.equals("expression")) {
                    returnedValue = part
                    String actual = expressionType(part)
                    if (isReturn && problem.equals("")) { exactType(actual, returnType, part, "return value") }
                }
                else {
                    if (part.name.equals("compoundStatement")) { checkCompound(part, true) }
                    else { if (part.name.equals("switchStatement")) { checkSwitch(part) } }
                }
            }
            i += 1
        }
        if (isReturn && returnedValue == null && problem.equals("")) {
            fail(node, format("function returning {} requires a return value", returnType))
        }
    }

    void checkStatement(AstNode node) {
        if (node.name.equals("compoundStatement")) {
            checkCompound(node, true)
            return
        }
        if (node.name.equals("switchStatement")) {
            checkSwitch(node)
            return
        }
        if (node.name.equals("simpleStatement")) {
            checkSimpleStatement(node)
            return
        }
        bool loopScope = (node.name.equals("matchedStatement") || node.name.equals("openStatement")) && node.children.length > 0 && child(node, 0).text.equals("for")
        bool loop = loopScope || ((node.name.equals("matchedStatement") || node.name.equals("openStatement")) && node.children.length > 0 && child(node, 0).text.equals("while"))
        if (isLabel(node)) {
            AstNode label = child(node, 0)
            if (findLabel(label.text) != label) {
                fail(label, format("duplicate label '{}'", label.text))
            }
        }
        if (loopScope) { pushScope() }
        if (loop) { loopDepth += 1 }
        bool inUpdate = false
        int i = 0
        while (i < node.children.length && problem.equals("")) {
            AstNode part = child(node, i)
            if (part.name.equals("expression")) {
                String conditionType = expressionType(part)
                if (!(loopScope && inUpdate) && problem.equals("") && !isScalar(conditionType)) {
                    fail(part, "condition must have integral scalar type")
                }
            }
            else {
                if (part.text.equals(";") && loopScope) { inUpdate = true }
                if (part.name.equals("forInitializer")) { checkForInitializer(part) }
                else {
                    if (part.name.equals("compoundStatement")) { checkCompound(part, true) }
                    else {
                        if (part.name.equals("switchStatement")) { checkSwitch(part) }
                        else {
                            if (part.name.equals("blockItem")) { checkBlockItem(part) }
                            else {
                                if (part.name.equals("simpleStatement")
                                        || part.name.equals("statement")
                                        || part.name.equals("matchedStatement")
                                        || part.name.equals("openStatement")) { checkStatement(part) }
                            }
                        }
                    }
                }
            }
            i += 1
        }
        if (loopScope) { popScope() }
        if (loop) { loopDepth -= 1 }
    }

    bool check(AstNode root, list tokens) {
        problem = ""
        errorOffset = 0
        globals = []
        currentScope = null
        locations = []
        SmallCTokenCursor cursor()
        indexLocations(root, tokens, cursor)
        int i = 0
        while (i < root.children.length && problem.equals("")) {
            AstNode external = child(root, i)
            if (external.children.length > 0) {
                AstNode declaration = child(external, 0)
                if (declaration.name.equals("declaration")) { checkDeclaration(declaration, true) }
                else { checkFunction(external) }
            }
            i += 1
        }
        return problem.equals("")
    }
}

class SmallCFrontend {
    Sys.StandardIO io
    list tokens
    String problem
    int errorOffset
    SmallCSemanticChecker checker

    SmallCFrontend() {
        io = Sys.StandardIO()
        tokens = []
        problem = ""
        errorOffset = 0
        checker = null
    }

    AstNode parseInput(String input) {
        problem = ""
        errorOffset = 0
        InputScanner scanner(input)
        if (!scanner.scan()) {
            problem = scanner.problem
            errorOffset = scanner.errorOffset
            return null
        }
        tokens = scanner.tokens
        GeneratedParser parser(scanner.tokens)
        AstNode root = parser.parseAll()
        if (root == null) {
            errorOffset = input.length
            if (parser.errorPosition < scanner.tokens.length) {
                errorOffset = (scanner.tokens[parser.errorPosition] as LexToken).offset
            }
            problem = parser.problem
        }
        return root
    }

    bool check(AstNode root) {
        checker = SmallCSemanticChecker()
        if (checker.check(root, tokens)) { return true }
        problem = checker.problem
        errorOffset = checker.errorOffset
        return false
    }

    int offsetOf(AstNode node) {
        if (checker == null) { return 0 }
        return checker.offsetOf(node)
    }

    String jsonString(String value) {
        String result = "\""
        int i = 0
        while (i < value.length) {
            int byte = int(value.byteAt(i))
            if (byte == 34 || byte == 92) { result.append("\\") }
            if (byte == 10) { result.append("\\n") }
            else {
                if (byte == 13) { result.append("\\r") }
                else {
                    if (byte == 9) { result.append("\\t") }
                    else { result.append(value.slice(i, i + 1)) }
                }
            }
            i += 1
        }
        result.append("\"")
        return result
    }

    String jsonAst(AstNode node) {
        String result = "{\"name\":"
        result.append(jsonString(node.name))
        result.append(",\"text\":")
        result.append(jsonString(node.text))
        result.append(",\"children\":[")
        int i = 0
        while (i < node.children.length) {
            if (i > 0) { result.append(",") }
            result.append(jsonAst(node.children[i] as AstNode))
            i += 1
        }
        result.append("]}")
        return result
    }

    void report(String path, String input, int offset, String problem) {
        int line = 1
        int column = 1
        int i = 0
        while (i < offset && i < input.length) {
            if (int(input.byteAt(i)) == 10) {
                line += 1
                column = 1
            }
            else { column += 1 }
            i += 1
        }
        io.writeErrorLine(format("{}:{}:{}: {}", path, line, column, problem))
    }

}

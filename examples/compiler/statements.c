#define CPARSEGEN_NO_MAIN
#include "parser.c"

/* Primitive identities are nonpositive; positive identities index classes. */
typedef int Type;
enum { TYPE_BOOL = -1, TYPE_INT = 0 };

typedef struct {
    /* NULL denotes the implicit method receiver. */
    const Node *name;
    int initialized;
    Type type;
} Symbol;

typedef struct {
    const Node *node;
    const Node *name;
    size_t arity;
    Symbol *symbols;
    size_t count;
    int method;
    int constructor;
    Type *parameter_types;
    Type return_type;
} Function;

typedef struct {
    const Node *name;
    Symbol *fields;
    size_t field_count;
    Type parent;
} Class;

typedef struct {
    const Context *parser;
    const CpgVisitor *visitor;
    const CpgVisitor *type_visitor;
    Symbol *symbols;
    size_t count, capacity;
    size_t depth;
    Function *functions;
    size_t function_count;
    int in_function, in_constructor, falls_through;
    Class *classes;
    size_t class_count;
    int receiver;
    Type value_type, return_type;
    const char *problem;
    const Node *error;
} Compiler;

static CpgVisit semantic_error(Compiler *compiler, const Node *node, const char *problem) {
    /* Rule nodes have no source span; diagnose their first source token. */
    while (cpg_child_count(node)) node = cpg_child_at(node, 0);
    compiler->problem = problem;
    compiler->error = node;
    return CPG_ERROR;
}

static int same_name(const Compiler *compiler, const Node *left, const Node *right) {
    return cpg_node_text_length(left) == cpg_node_text_length(right) &&
        !memcmp(cpg_node_text(compiler->parser, left),
                cpg_node_text(compiler->parser, right), cpg_node_text_length(right));
}

static int find_class(const Compiler *compiler, const Node *name) {
    for (size_t i = 0; i < compiler->class_count; ++i)
        if (same_name(compiler, compiler->classes[i].name, name)) return (int)i + 1;
    return 0;
}

static int node_text_is(const Compiler *compiler, const Node *node, const char *text) {
    size_t length = strlen(text);
    return cpg_node_text_length(node) == length &&
        !memcmp(cpg_node_text(compiler->parser, node), text, length);
}

static int class_has_parent(const Compiler *compiler, const Node *node) {
    return cpg_child_count(node) > 2 &&
        node_text_is(compiler, cpg_child_at(node, 2), "extends");
}

static size_t class_member_start(const Compiler *compiler, const Node *node) {
    return class_has_parent(compiler, node) ? 5 : 3;
}

static const Node *function_parameters(const Node *node, int constructor) {
    return cpg_child_at(node, constructor ? 2 : 3);
}

static const Node *function_body(const Node *node) {
    return cpg_child_at(node, cpg_child_count(node) - 1);
}

static const Node *base_initializer(const Node *node) {
    for (size_t i = 0; i < cpg_child_count(node); ++i)
        if (!strcmp(cpg_node_kind(cpg_child_at(node, i)), "base_initializer"))
            return cpg_child_at(node, i);
    return NULL;
}

static const Node *base_arguments(const Node *node) {
    return node ? cpg_child_at(node, 3) : NULL;
}

static int is_subtype(const Compiler *compiler, Type actual, Type expected) {
    if (actual <= 0 || expected <= 0) return actual == expected;
    for (Type type = actual; type > 0; type = compiler->classes[type - 1].parent)
        if (type == expected) return 1;
    return 0;
}

static int compatible_type(const Compiler *compiler, Type actual, Type expected) {
    return is_subtype(compiler, actual, expected);
}

static CpgVisit resolve_type(Compiler *compiler, const Node *name, Type *type) {
    if (cpg_node_text_length(name) == 3 &&
        !memcmp(cpg_node_text(compiler->parser, name), "int", 3)) {
        *type = TYPE_INT;
        return CPG_CONTINUE;
    }
    if (cpg_node_text_length(name) == 4 &&
        !memcmp(cpg_node_text(compiler->parser, name), "bool", 4)) {
        *type = TYPE_BOOL;
        return CPG_CONTINUE;
    }
    *type = find_class(compiler, name);
    return *type ? CPG_CONTINUE : semantic_error(compiler, name, "unknown class type");
}

static size_t find_function(const Compiler *compiler, const Node *name) {
    for (size_t i = 0; i < compiler->function_count; ++i) {
        if (!compiler->functions[i].method &&
            same_name(compiler, compiler->functions[i].name, name)) return i;
    }
    return compiler->function_count;
}

static size_t find_symbol(const Compiler *compiler, const Node *name) {
    for (size_t i = 0; i < compiler->count; ++i) {
        const Node *symbol = compiler->symbols[i].name;
        if (!symbol) {
            if (cpg_node_text_length(name) == 4 &&
                !memcmp(cpg_node_text(compiler->parser, name), "self", 4)) return i;
            continue;
        }
        if (same_name(compiler, symbol, name)) {
            return i;
        }
    }
    return compiler->count;
}

static CpgVisit check_name(const Node *node, void *user) {
    Compiler *compiler = user;
    size_t index = find_symbol(compiler, node);
    if (index == compiler->count) {
        return semantic_error(compiler, node, "use before declaration (unknown name)");
    }
    if (!compiler->symbols[index].initialized) {
        return semantic_error(compiler, node, "read before definite initialization");
    }
    compiler->value_type = compiler->symbols[index].type;
    return CPG_CONTINUE;
}

static CpgVisit integer_magnitude(Compiler *compiler, const Node *node,
                                  unsigned long limit, unsigned long *value) {
    const unsigned char *text = cpg_node_text(compiler->parser, node);
    *value = 0;
    for (size_t i = 0; i < cpg_node_text_length(node); ++i) {
        unsigned long digit = text[i] - '0';
        if (*value > (limit - digit) / 10)
            return semantic_error(compiler, node, "integer literal outside int32 range");
        *value = *value * 10 + digit;
    }
    return CPG_CONTINUE;
}

static CpgVisit check_integer(const Node *node, void *user) {
    Compiler *compiler = user;
    unsigned long value;
    compiler->value_type = TYPE_INT;
    return integer_magnitude(compiler, node, 2147483647UL, &value);
}

/* Only a directly negated decimal token may have magnitude 2147483648. */
static const Node *negative_integer(const Compiler *compiler, const Node *node) {
    if (strcmp(cpg_node_kind(node), "unary") || cpg_child_count(node) != 2 ||
        *cpg_node_text(compiler->parser, cpg_child_at(node, 0)) != '-') return NULL;
    const Node *operand = cpg_child_at(node, 1);
    if (cpg_child_count(operand) != 1) return NULL;
    const Node *primary = cpg_child_at(operand, 0);
    if (strcmp(cpg_node_kind(primary), "primary") || cpg_child_count(primary) != 1)
        return NULL;
    const Node *token = cpg_child_at(primary, 0);
    return !strcmp(cpg_node_kind(token), "INTEGER") ? token : NULL;
}

static CpgVisit check_boolean(const Node *node, void *user) {
    Compiler *compiler = user;
    (void)node;
    compiler->value_type = TYPE_BOOL;
    return CPG_CONTINUE;
}

static CpgVisit add_symbol(Compiler *compiler, const Node *name, int initialized) {
    if (find_symbol(compiler, name) != compiler->count) {
        return semantic_error(compiler, name, "duplicate declaration");
    }
    if (compiler->count == compiler->capacity) {
        size_t capacity = compiler->capacity ? compiler->capacity * 2 : 8;
        if (capacity < compiler->capacity ||
            capacity > (size_t)-1 / sizeof(*compiler->symbols)) {
            return semantic_error(compiler, name, "symbol table too large");
        }
        Symbol *symbols = realloc(compiler->symbols, capacity * sizeof(*symbols));
        if (!symbols) return semantic_error(compiler, name, "symbol table allocation failed");
        compiler->symbols = symbols;
        compiler->capacity = capacity;
    }
    compiler->symbols[compiler->count++] = (Symbol){name, initialized, TYPE_INT};
    return CPG_CONTINUE;
}

static CpgVisit check_declaration(const Node *node, void *user) {
    Compiler *compiler = user;
    const Node *name = cpg_child_at(node, 1);
    if (find_symbol(compiler, name) != compiler->count) {
        return semantic_error(compiler, name, "duplicate declaration");
    }
    /* The new binding is not visible in its own initializer. */
    int initialized = cpg_child_count(node) > 3;
    if (initialized) {
        CpgVisit result = cpg_dispatch(cpg_child_at(node, 3), compiler->visitor, user);
        if (result != CPG_CONTINUE) return result;
    }
    Type type = initialized ? compiler->value_type : TYPE_INT;
    CpgVisit result = add_symbol(compiler, name, initialized);
    if (result == CPG_CONTINUE) compiler->symbols[compiler->count - 1].type = type;
    return result;
}

static CpgVisit check_numeric(const Node *node, void *user) {
    Compiler *compiler = user;
    const Node *integer = negative_integer(compiler, node);
    if (integer) {
        unsigned long value;
        compiler->value_type = TYPE_INT;
        return integer_magnitude(compiler, integer, 2147483648UL, &value);
    }
    size_t count = cpg_child_count(node);
    int unary = count == 2;
    int equality = !strcmp(cpg_node_kind(node), "equality");
    int comparison = !strcmp(cpg_node_kind(node), "comparison");
    Type left = TYPE_INT;
    for (size_t i = unary ? 1 : 0; i < count; i += 2) {
        const Node *child = cpg_child_at(node, i);
        CpgVisit result = cpg_dispatch(child, compiler->visitor, user);
        if (result != CPG_CONTINUE) return result;
        Type right = compiler->value_type;
        if (count == 1) return CPG_CONTINUE;
        if (equality) {
            if (right > 0 || (i && left != right))
                return semantic_error(compiler, child,
                                      "type mismatch: equality requires matching primitive types");
        } else if (right != TYPE_INT || (i && !unary && left != TYPE_INT)) {
            return semantic_error(compiler, child, "type mismatch: expected integer");
        }
        left = i && (equality || comparison) ? TYPE_BOOL : right;
    }
    compiler->value_type = comparison || equality ? TYPE_BOOL : TYPE_INT;
    return CPG_CONTINUE;
}

static CpgVisit require_type(Compiler *compiler, const Node *node, Type type,
                             const char *problem) {
    CpgVisit result = cpg_dispatch(node, compiler->visitor, compiler);
    if (result != CPG_CONTINUE) return result;
    return !compatible_type(compiler, compiler->value_type, type) ?
        semantic_error(compiler, node, problem) : CPG_CONTINUE;
}

static CpgVisit check_arguments(Compiler *compiler, const Node *arguments,
                                const Function *function) {
    for (size_t i = 0; i < cpg_child_count(arguments); i += 2) {
        const Node *argument = cpg_child_at(arguments, i);
        CpgVisit result = cpg_dispatch(argument, compiler->visitor, compiler);
        if (result != CPG_CONTINUE) return result;
        if (!compatible_type(compiler, compiler->value_type,
                             function->parameter_types[i / 2]))
            return semantic_error(compiler, argument, "argument type mismatch");
    }
    compiler->value_type = function->return_type;
    return CPG_CONTINUE;
}

static size_t find_constructor(const Compiler *compiler, Type type) {
    for (size_t i = 0; i < compiler->function_count; ++i)
        if (compiler->functions[i].constructor &&
            compiler->functions[i].method == type) return i;
    return compiler->function_count;
}

static size_t nearest_constructor(const Compiler *compiler, Type type) {
    while (type > 0) {
        size_t index = find_constructor(compiler, type);
        if (index != compiler->function_count) return index;
        type = compiler->classes[type - 1].parent;
    }
    return compiler->function_count;
}

static CpgVisit check_base_constructor(Compiler *compiler, const Node *node,
                                       Type owner, const Node *initializer) {
    Type parent = compiler->classes[owner - 1].parent;
    if (!parent) {
        if (initializer)
            return semantic_error(compiler, initializer,
                                  "base initializer requires a parent class");
        return CPG_CONTINUE;
    }
    size_t index = nearest_constructor(compiler, parent);
    size_t arity = index == compiler->function_count ? 0 :
        compiler->functions[index].arity;
    const Node *arguments = base_arguments(initializer);
    size_t supplied = arguments ? (cpg_child_count(arguments) + 1) / 2 : 0;
    if (supplied != arity)
        return semantic_error(compiler, initializer ? initializer : node,
                              "base constructor argument count mismatch");
    if (index == compiler->function_count) return CPG_CONTINUE;
    if (!initializer || !arguments) return CPG_CONTINUE;
    return check_arguments(compiler, arguments, &compiler->functions[index]);
}

typedef struct {
    const char *name;
    size_t arity;
    Type parameter_type;
    int output;
} Builtin;

static const Builtin builtins[] = {
    {"read_int", 0, TYPE_INT, 0},
    {"min", 2, TYPE_INT, 0},
    {"max", 2, TYPE_INT, 0},
    {"abs", 1, TYPE_INT, 0},
    {"print_int", 1, TYPE_INT, 1},
    {"println_int", 1, TYPE_INT, 1},
    {"print_bool", 1, TYPE_BOOL, 1},
    {"println_bool", 1, TYPE_BOOL, 1}
};

/* User functions retain precedence, so existing identifiers are not reserved. */
static const Builtin *find_builtin(const Compiler *compiler, const Node *name) {
    if (find_function(compiler, name) != compiler->function_count) return NULL;
    for (size_t i = 0; i < sizeof(builtins) / sizeof(*builtins); ++i) {
        if (cpg_node_text_length(name) == strlen(builtins[i].name) &&
            !memcmp(cpg_node_text(compiler->parser, name),
                    builtins[i].name, strlen(builtins[i].name))) return &builtins[i];
    }
    return NULL;
}

static CpgVisit check_builtin(Compiler *compiler, const Node *node,
                              const Builtin *builtin) {
    const Node *arguments = cpg_child_at(node, 2);
    if ((cpg_child_count(arguments) + 1) / 2 != builtin->arity)
        return semantic_error(compiler, cpg_child_at(node, 0), "argument count mismatch");
    for (size_t i = 0; i < cpg_child_count(arguments); i += 2) {
        CpgVisit result = require_type(compiler, cpg_child_at(arguments, i),
                                      builtin->parameter_type, "argument type mismatch");
        if (result != CPG_CONTINUE) return result;
    }
    compiler->value_type = TYPE_INT;
    return CPG_CONTINUE;
}

static CpgVisit check_call(const Node *node, void *user) {
    Compiler *compiler = user;
    const Node *name = cpg_child_at(node, 0);
    const Builtin *builtin = find_builtin(compiler, name);
    if (builtin) {
        if (builtin->output)
            return semantic_error(compiler, name, "output builtin requires a statement");
        return check_builtin(compiler, node, builtin);
    }
    size_t index = find_function(compiler, name);
    if (index == compiler->function_count) {
        return semantic_error(compiler, name, "unknown function");
    }
    const Node *arguments = cpg_child_at(node, 2);
    size_t arity = (cpg_child_count(arguments) + 1) / 2;
    if (arity != compiler->functions[index].arity) {
        return semantic_error(compiler, name, "argument count mismatch");
    }
    return check_arguments(compiler, arguments, &compiler->functions[index]);
}

static CpgVisit check_call_statement(const Node *node, void *user) {
    Compiler *compiler = user;
    const Node *call = cpg_child_at(node, 0);
    const Builtin *builtin = find_builtin(compiler, cpg_child_at(call, 0));
    if (builtin) return check_builtin(compiler, call, builtin);
    return check_call(call, user);
}

static CpgVisit check_return(const Node *node, void *user) {
    Compiler *compiler = user;
    if (compiler->in_constructor) {
        return semantic_error(compiler, cpg_child_at(node, 0),
                              "return is not allowed in a constructor");
    }
    if (!compiler->in_function) {
        return semantic_error(compiler, cpg_child_at(node, 0), "return outside function");
    }
    if (cpg_child_count(node) != 3) {
        return semantic_error(compiler, cpg_child_at(node, 0), "return requires a value");
    }
    CpgVisit result = require_type(compiler, cpg_child_at(node, 1),
                                  compiler->return_type, "return type mismatch");
    compiler->falls_through = 0;
    return result;
}

static CpgVisit check_function(const Node *node, void *user) {
    Compiler *compiler = user;
    size_t index = 0;
    while (compiler->functions[index].node != node) ++index;
    Function *function = &compiler->functions[index];
    Compiler local = *compiler;
    local.symbols = NULL;
    local.count = local.capacity = 0;
    local.in_function = local.falls_through = 1;
    local.in_constructor = function->constructor;
    local.receiver = function->method;
    local.return_type = function->return_type;
    CpgVisit result = CPG_CONTINUE;
    if (function->method) {
        result = add_symbol(&local, compiler->classes[function->method - 1].name, 1);
        if (result == CPG_CONTINUE) {
            local.symbols[0].type = function->method;
            local.symbols[0].name = NULL;
        }
    }
    const Node *parameters = function_parameters(node, function->constructor);
    for (size_t i = 0; i < cpg_child_count(parameters) && result == CPG_CONTINUE; i += 2) {
        result = add_symbol(&local, cpg_child_at(cpg_child_at(parameters, i), 0), 1);
        if (result == CPG_CONTINUE)
            local.symbols[local.count - 1].type = function->parameter_types[i / 2];
    }
    if (result == CPG_CONTINUE && function->constructor)
        result = check_base_constructor(&local, function->name, function->method,
                                        base_initializer(node));
    if (result == CPG_CONTINUE)
        result = cpg_dispatch(function_body(node), local.visitor, &local);
    if (result == CPG_CONTINUE && local.falls_through && !function->constructor) {
        result = semantic_error(&local, function->name, "function may finish without returning a value");
    }
    function->symbols = local.symbols;
    function->count = local.count;
    if (result != CPG_CONTINUE) {
        compiler->problem = local.problem;
        compiler->error = local.error;
    }
    return result;
}

static int find_field(const Compiler *compiler, Type type, const Node *name,
                      Type *owner, size_t *index);
static size_t find_method(const Compiler *compiler, Type type, const Node *name);

static CpgVisit collect_functions(const Node *root, Compiler *compiler) {
    size_t count = cpg_child_count(root);
    compiler->classes = calloc(count ? count : 1, sizeof(*compiler->classes));
    if (!compiler->classes) return semantic_error(compiler, root, "class table allocation failed");
    for (size_t i = 0; i < cpg_child_count(root); ++i) {
        const Node *node = cpg_child_at(root, i);
        if (strcmp(cpg_node_kind(node), "class_decl")) continue;
        const Node *name = cpg_child_at(node, 1);
        if (find_class(compiler, name))
            return semantic_error(compiler, name, "duplicate class");
        if (cpg_node_text_length(name) == 3 &&
            !memcmp(cpg_node_text(compiler->parser, name), "int", 3))
            return semantic_error(compiler, name, "class name conflicts with integer type");
        if (cpg_node_text_length(name) == 4 &&
            !memcmp(cpg_node_text(compiler->parser, name), "bool", 4))
            return semantic_error(compiler, name, "class name conflicts with boolean type");
        compiler->classes[compiler->class_count++].name = name;
        count += cpg_child_count(node);
    }
    for (size_t i = 0; i < cpg_child_count(root); ++i) {
        const Node *node = cpg_child_at(root, i);
        if (strcmp(cpg_node_kind(node), "class_decl") || !class_has_parent(compiler, node))
            continue;
        const Node *parent_name = cpg_child_at(node, 3);
        Type parent = find_class(compiler, parent_name);
        if (!parent) return semantic_error(compiler, parent_name, "unknown parent class");
        compiler->classes[find_class(compiler, cpg_child_at(node, 1)) - 1].parent = parent;
    }
    for (size_t i = 0; i < compiler->class_count; ++i) {
        Type type = (Type)i + 1;
        for (size_t depth = 0; type && depth <= compiler->class_count; ++depth) {
            if (depth == compiler->class_count)
                return semantic_error(compiler, compiler->classes[i].name,
                                      "inheritance cycle");
            type = compiler->classes[type - 1].parent;
        }
    }
    for (size_t i = 0; i < cpg_child_count(root); ++i) {
        const Node *node = cpg_child_at(root, i);
        if (strcmp(cpg_node_kind(node), "class_decl")) continue;
        Class *class_info = &compiler->classes[find_class(compiler, cpg_child_at(node, 1)) - 1];
        class_info->fields = calloc(cpg_child_count(node), sizeof(*class_info->fields));
        if (!class_info->fields) return semantic_error(compiler, node, "field table allocation failed");
        for (size_t j = class_member_start(compiler, node);
             j + 1 < cpg_child_count(node); ++j) {
            const Node *field = cpg_child_at(node, j);
            if (strcmp(cpg_node_kind(field), "field")) continue;
            const Node *name = cpg_child_at(field, 1);
            const Node *type = cpg_child_at(field, 3);
            Type field_type;
            if (resolve_type(compiler, type, &field_type) != CPG_CONTINUE) return CPG_ERROR;
            for (size_t k = 0; k < class_info->field_count; ++k) {
                if (same_name(compiler, class_info->fields[k].name, name))
                    return semantic_error(compiler, name, "duplicate member");
            }
            class_info->fields[class_info->field_count++] = (Symbol){name, 1, field_type};
        }
    }
    compiler->functions = calloc(count ? count : 1, sizeof(*compiler->functions));
    if (!compiler->functions) return semantic_error(compiler, root, "function table allocation failed");
    for (size_t i = 0; i < cpg_child_count(root); ++i) {
        const Node *node = cpg_child_at(root, i);
        int class_decl = !strcmp(cpg_node_kind(node), "class_decl");
        int owner = class_decl ? find_class(compiler, cpg_child_at(node, 1)) : 0;
        size_t first_member = class_decl ? class_member_start(compiler, node) : 0;
        size_t members = class_decl ? cpg_child_count(node) - 1 : 1;
        for (size_t j = first_member; j < members; ++j) {
            const Node *candidate = class_decl ? cpg_child_at(node, j) : node;
            int constructor = !strcmp(cpg_node_kind(candidate), "constructor");
            if (!constructor && strcmp(cpg_node_kind(candidate), "function")) continue;
            Class *class_info = owner ? &compiler->classes[owner - 1] : NULL;
            const Node *name = constructor ? class_info->name : cpg_child_at(candidate, 1);
            for (size_t k = 0; k < compiler->function_count; ++k) {
                if (compiler->functions[k].constructor && constructor &&
                    compiler->functions[k].method == owner)
                    return semantic_error(compiler, name, "duplicate constructor");
                if (!constructor && !compiler->functions[k].constructor &&
                    compiler->functions[k].method == owner &&
                    same_name(compiler, compiler->functions[k].name, name))
                    return semantic_error(compiler, name,
                                          class_decl ? "duplicate member" : "duplicate function");
            }
            for (size_t k = 0; !constructor && class_info && k < class_info->field_count; ++k) {
                if (same_name(compiler, class_info->fields[k].name, name))
                    return semantic_error(compiler, name, "duplicate member");
            }
            Function *function = &compiler->functions[compiler->function_count++];
            function->node = candidate;
            function->name = name;
            function->arity = (cpg_child_count(function_parameters(candidate, constructor)) + 1) / 2;
            function->method = owner;
            function->constructor = constructor;
            if (!constructor) {
                const Node *annotation = cpg_child_at(candidate, 5);
                if (cpg_child_count(annotation) &&
                    resolve_type(compiler, cpg_child_at(annotation, 1),
                                 &function->return_type) != CPG_CONTINUE)
                    return CPG_ERROR;
            }
            function->parameter_types = calloc(function->arity ? function->arity : 1,
                                                sizeof(*function->parameter_types));
            if (!function->parameter_types)
                return semantic_error(compiler, name, "parameter table allocation failed");
            const Node *parameters = function_parameters(candidate, constructor);
            for (size_t k = 0; k < function->arity; ++k) {
                const Node *parameter = cpg_child_at(parameters, k * 2);
                if (cpg_child_count(parameter) > 1 &&
                    resolve_type(compiler, cpg_child_at(parameter, 2),
                                 &function->parameter_types[k]) != CPG_CONTINUE)
                    return CPG_ERROR;
            }
        }
    }
    for (size_t i = 0; i < compiler->class_count; ++i) {
        Type parent = compiler->classes[i].parent;
        if (!parent) continue;
        for (size_t field = 0; field < compiler->classes[i].field_count; ++field) {
            Type inherited_owner;
            size_t inherited_index;
            if (find_field(compiler, parent, compiler->classes[i].fields[field].name,
                           &inherited_owner, &inherited_index) ||
                find_method(compiler, parent, compiler->classes[i].fields[field].name) !=
                    compiler->function_count)
                return semantic_error(compiler, compiler->classes[i].fields[field].name,
                                      "duplicate inherited member");
        }
    }
    for (size_t i = 0; i < compiler->function_count; ++i) {
        Function *function = &compiler->functions[i];
        if (!function->method || function->constructor) continue;
        Type parent = compiler->classes[function->method - 1].parent;
        if (!parent) continue;
        Type inherited_owner;
        size_t inherited_index;
        if (find_field(compiler, parent, function->name, &inherited_owner, &inherited_index))
            return semantic_error(compiler, function->name, "duplicate inherited member");
        size_t inherited = find_method(compiler, parent, function->name);
        if (inherited == compiler->function_count) continue;
        const Function *base = &compiler->functions[inherited];
        if (function->arity != base->arity || function->return_type != base->return_type)
            return semantic_error(compiler, function->name, "override signature mismatch");
        for (size_t p = 0; p < function->arity; ++p)
            if (function->parameter_types[p] != base->parameter_types[p])
                return semantic_error(compiler, function->name, "override signature mismatch");
    }
    for (Type type = 1; type <= (Type)compiler->class_count; ++type) {
        if (find_constructor(compiler, type) != compiler->function_count) continue;
        size_t inherited = nearest_constructor(compiler,
            compiler->classes[type - 1].parent);
        if (inherited != compiler->function_count &&
            compiler->functions[inherited].arity)
            return semantic_error(compiler, compiler->classes[type - 1].name,
                                  "base constructor argument count mismatch");
    }
    return CPG_CONTINUE;
}

static CpgVisit check_assignment(const Node *node, void *user) {
    Compiler *compiler = user;
    const Node *name = cpg_child_at(node, 0);
    size_t index = find_symbol(compiler, name);
    if (index == compiler->count) {
        return semantic_error(compiler, name, "assignment to unknown name");
    }
    CpgVisit result = cpg_dispatch(cpg_child_at(node, 2), compiler->visitor, user);
    if (result == CPG_CONTINUE &&
        !compatible_type(compiler, compiler->value_type, compiler->symbols[index].type))
        return semantic_error(compiler, name, "assignment type mismatch");
    if (result == CPG_CONTINUE) compiler->symbols[index].initialized = 1;
    return result;
}

static unsigned char *save_initialization(Compiler *compiler, const Node *node) {
    unsigned char *state = malloc(compiler->count ? compiler->count : 1);
    if (!state) {
        semantic_error(compiler, node, "initialization state allocation failed");
        return NULL;
    }
    for (size_t i = 0; i < compiler->count; ++i) {
        state[i] = (unsigned char)compiler->symbols[i].initialized;
    }
    return state;
}

static void restore_initialization(Compiler *compiler, const unsigned char *state,
                                   size_t count) {
    /* Keep textual bindings, including declarations in a skipped body. */
    for (size_t i = 0; i < compiler->count; ++i) {
        compiler->symbols[i].initialized = i < count ? state[i] : 0;
    }
}

static CpgVisit check_control(const Node *node, void *user) {
    Compiler *compiler = user;
    CpgVisit result = require_type(compiler, cpg_child_at(node, 2), TYPE_BOOL,
                                  "condition type mismatch: expected bool");
    if (result != CPG_CONTINUE) return result;
    size_t entry_count = compiler->count;
    int incoming = compiler->falls_through;
    unsigned char *entry = save_initialization(compiler, node);
    if (!entry) return CPG_ERROR;
    compiler->falls_through = 1;
    result = cpg_dispatch(cpg_child_at(node, 4), compiler->visitor, user);
    int then_live = compiler->falls_through;
    if (result == CPG_CONTINUE && cpg_child_count(node) > 5) {
        size_t then_count = compiler->count;
        unsigned char *then_state = save_initialization(compiler, node);
        if (!then_state) {
            free(entry);
            return CPG_ERROR;
        }
        restore_initialization(compiler, entry, entry_count);
        compiler->falls_through = 1;
        result = cpg_dispatch(cpg_child_at(node, 6), compiler->visitor, user);
        int else_live = compiler->falls_through;
        for (size_t i = 0; i < compiler->count; ++i) {
            compiler->symbols[i].initialized =
                (!else_live || compiler->symbols[i].initialized) &&
                (!then_live || (i < then_count && then_state[i]));
        }
        compiler->falls_through = incoming && (then_live || else_live);
        free(then_state);
    } else {
        /* An if without else or a while body may never execute. */
        restore_initialization(compiler, entry, entry_count);
        compiler->falls_through = incoming;
    }
    free(entry);
    return result;
}

static CpgVisit dispatch_children(const Node *node, void *user) {
    Compiler *compiler = user;
    for (size_t i = 0; i < cpg_child_count(node); ++i) {
        CpgVisit result = cpg_dispatch(cpg_child_at(node, i), compiler->visitor, user);
        if (result != CPG_CONTINUE) return result;
    }
    return CPG_CONTINUE;
}

static CpgVisit check_class(const Node *node, void *user) {
    Compiler *compiler = user;
    for (size_t i = class_member_start(compiler, node);
         i + 1 < cpg_child_count(node); ++i) {
        const Node *member = cpg_child_at(node, i);
        if (!strcmp(cpg_node_kind(member), "function") ||
            !strcmp(cpg_node_kind(member), "constructor")) {
            CpgVisit result = check_function(member, compiler);
            if (result != CPG_CONTINUE) return result;
        }
    }
    return CPG_CONTINUE;
}

static CpgVisit check_class_name(Compiler *compiler, const Node *name) {
    if (!find_class(compiler, name))
        return semantic_error(compiler, name, "unknown class");
    return CPG_CONTINUE;
}

static CpgVisit check_construction(const Node *node, void *user) {
    Compiler *compiler = user;
    compiler->value_type = find_class(compiler, cpg_child_at(node, 1));
    CpgVisit result = check_class_name(compiler, cpg_child_at(node, 1));
    if (result != CPG_CONTINUE) return result;
    const Node *arguments = cpg_child_at(node, 3);
    size_t constructor = find_constructor(compiler, compiler->value_type);
    size_t arity = (cpg_child_count(arguments) + 1) / 2;
    if (constructor == compiler->function_count) {
        size_t inherited = nearest_constructor(
            compiler, compiler->classes[compiler->value_type - 1].parent);
        size_t inherited_arity = inherited == compiler->function_count ? 0 :
            compiler->functions[inherited].arity;
        if (arity || inherited_arity)
            return semantic_error(compiler, cpg_child_at(node, 1),
                                  "constructor argument count mismatch");
        return CPG_CONTINUE;
    }
    if (arity != compiler->functions[constructor].arity)
        return semantic_error(compiler, cpg_child_at(node, 1),
                              "constructor argument count mismatch");
    result = check_arguments(compiler, arguments, &compiler->functions[constructor]);
    compiler->value_type = find_class(compiler, cpg_child_at(node, 1));
    return result;
}

static CpgVisit check_typed_declaration(const Node *node, void *user) {
    Compiler *compiler = user;
    const Node *name = cpg_child_at(node, 1);
    Type type;
    CpgVisit result = resolve_type(compiler, cpg_child_at(node, 3), &type);
    if (result != CPG_CONTINUE) return result;
    int initialized = cpg_child_count(node) > 5;
    if (initialized) {
        result = cpg_dispatch(cpg_child_at(node, 5), compiler->visitor, user);
        if (result != CPG_CONTINUE) return result;
        if (!compatible_type(compiler, compiler->value_type, type))
            return semantic_error(compiler, name, "initializer type mismatch");
    }
    result = add_symbol(compiler, name, initialized);
    if (result == CPG_CONTINUE) compiler->symbols[compiler->count - 1].type = type;
    return result;
}

static int find_field(const Compiler *compiler, Type type, const Node *name,
                      Type *owner, size_t *index) {
    for (Type current = type; current > 0;
         current = compiler->classes[current - 1].parent) {
        const Class *class_info = &compiler->classes[current - 1];
        for (size_t i = 0; i < class_info->field_count; ++i) {
            if (same_name(compiler, class_info->fields[i].name, name)) {
                if (owner) *owner = current;
                if (index) *index = i;
                return 1;
            }
        }
    }
    return 0;
}

static size_t find_method(const Compiler *compiler, Type type, const Node *name) {
    for (Type current = type; current > 0;
         current = compiler->classes[current - 1].parent)
        for (size_t i = 0; i < compiler->function_count; ++i)
            if (!compiler->functions[i].constructor &&
                compiler->functions[i].method == current &&
                same_name(compiler, compiler->functions[i].name, name)) return i;
    return compiler->function_count;
}

static CpgVisit check_path(const Node *node, size_t count, Compiler *compiler) {
    CpgVisit result = check_name(cpg_child_at(node, 0), compiler);
    if (result != CPG_CONTINUE) return result;
    for (size_t i = 2; i < count; i += 2) {
        const Node *name = cpg_child_at(node, i);
        Type type = compiler->value_type;
        if (type <= 0)
            return semantic_error(compiler, cpg_child_at(node, i - 2),
                                  "member access requires object");
        Type field_owner;
        size_t field;
        if (!find_field(compiler, type, name, &field_owner, &field))
            return semantic_error(compiler, name, "unknown field");
        compiler->value_type = compiler->classes[field_owner - 1].fields[field].type;
    }
    return CPG_CONTINUE;
}

static CpgVisit check_member(const Node *node, void *user) {
    Compiler *compiler = user;
    return check_path(node, cpg_child_count(node), compiler);
}

static CpgVisit check_member_assignment(const Node *node, void *user) {
    Compiler *compiler = user;
    CpgVisit result = check_member(cpg_child_at(node, 0), user);
    if (result != CPG_CONTINUE) return result;
    Type type = compiler->value_type;
    result = cpg_dispatch(cpg_child_at(node, 2), compiler->visitor, user);
    if (result == CPG_CONTINUE &&
        !compatible_type(compiler, compiler->value_type, type))
        return semantic_error(compiler, cpg_child_at(node, 0), "field assignment type mismatch");
    return result;
}

static CpgVisit check_method_call(const Node *node, void *user) {
    Compiler *compiler = user;
    const Node *path = cpg_child_at(node, 0);
    size_t count = cpg_child_count(path);
    CpgVisit result = check_path(path, count - 2, compiler);
    if (result != CPG_CONTINUE) return result;
    if (compiler->value_type <= 0)
        return semantic_error(compiler, cpg_child_at(path, count - 3),
                              "member access requires object");
    const Node *name = cpg_child_at(path, count - 1);
    size_t index = find_method(compiler, compiler->value_type, name);
    if (index == compiler->function_count) return semantic_error(compiler, name, "unknown method");
    const Node *arguments = cpg_child_at(node, 2);
    if ((cpg_child_count(arguments) + 1) / 2 != compiler->functions[index].arity)
        return semantic_error(compiler, name, "method argument count mismatch");
    return check_arguments(compiler, arguments, &compiler->functions[index]);
}

static CpgVisit check_output(const Node *node, void *user) {
    Compiler *compiler = user;
    CpgVisit result = cpg_dispatch(cpg_child_at(node, 1), compiler->visitor, user);
    if (result != CPG_CONTINUE) return result;
    return compiler->value_type > 0 ?
        semantic_error(compiler, cpg_child_at(node, 1),
                       "type mismatch: print requires a primitive") : CPG_CONTINUE;
}

static CpgVisit emit_name(const Node *node, void *user) {
    Compiler *compiler = user;
    size_t index = find_symbol(compiler, node);
    if (index == compiler->count) return semantic_error(compiler, node, "unresolved name during emission");
    /* Numeric slots cannot collide with C keywords, libc names, or user names. */
    compiler->value_type = compiler->symbols[index].type;
    if (compiler->receiver && index == 0) fputs("cpg_self ", stdout);
    else fprintf(stdout, "cpg_v%zu ", index);
    return ferror(stdout) ? CPG_ERROR : CPG_CONTINUE;
}

static CpgVisit emit_expression_as(Compiler *compiler, const Node *node, Type expected) {
    Compiler typing = *compiler;
    typing.visitor = compiler->type_visitor;
    for (size_t i = 0; i < typing.count; ++i) typing.symbols[i].initialized = 1;
    CpgVisit result = cpg_dispatch(node, compiler->type_visitor, &typing);
    if (result != CPG_CONTINUE) return result;
    Type actual = typing.value_type;
    if (actual > 0 && expected > 0 && actual != expected)
        fprintf(stdout, "cpg_cast%d_%d(", actual, expected);
    result = cpg_dispatch(node, compiler->visitor, compiler);
    if (result == CPG_CONTINUE && actual > 0 && expected > 0 && actual != expected)
        fputs(") ", stdout);
    return result;
}

static CpgVisit emit_integer(const Node *node, void *user) {
    Compiler *compiler = user;
    unsigned long value;
    if (integer_magnitude(compiler, node, 2147483647UL, &value) != CPG_CONTINUE)
        return CPG_ERROR;
    fprintf(stdout, "INT32_C(%lu) ", value);
    return ferror(stdout) ? CPG_ERROR : CPG_CONTINUE;
}

static CpgVisit emit_boolean(const Node *node, void *user) {
    Compiler *compiler = user;
    const Node *literal = cpg_child_at(node, 0);
    fputs(cpg_node_text_length(literal) == 4 ? "1 " : "0 ", stdout);
    compiler->value_type = TYPE_BOOL;
    return ferror(stdout) ? CPG_ERROR : CPG_CONTINUE;
}

static CpgVisit emit_literal(const Node *node, void *user) {
    Compiler *compiler = user;
    fwrite(cpg_node_text(compiler->parser, node), 1, cpg_node_text_length(node), stdout);
    fputc(' ', stdout);
    return ferror(stdout) ? CPG_ERROR : CPG_CONTINUE;
}

static CpgVisit emit_group(const Node *node, void *user) {
    if (fputc('(', stdout) == EOF) return CPG_ERROR;
    CpgVisit result = dispatch_children(node, user);
    if (result != CPG_CONTINUE) return result;
    return fputs(") ", stdout) == EOF ? CPG_ERROR : CPG_CONTINUE;
}

static CpgVisit emit_arithmetic(const Node *node, void *user) {
    Compiler *compiler = user;
    size_t count = cpg_child_count(node);
    const Node *integer = negative_integer(compiler, node);
    if (integer) {
        unsigned long value;
        if (integer_magnitude(compiler, integer, 2147483648UL, &value) != CPG_CONTINUE)
            return CPG_ERROR;
        if (value == 2147483648UL) fputs("INT32_MIN ", stdout);
        else fprintf(stdout, "(-INT32_C(%lu)) ", value);
    } else if (count == 2) {
        int negative = *cpg_node_text(compiler->parser, cpg_child_at(node, 0)) == '-';
        fputs(negative ? "cpg_sub(INT32_C(0), " : "(", stdout);
        CpgVisit result = cpg_dispatch(cpg_child_at(node, 1), compiler->visitor, user);
        if (result != CPG_CONTINUE) return result;
        fputs(") ", stdout);
    } else {
        for (size_t i = count - 1; i > 0; i -= 2) {
            unsigned char op = *cpg_node_text(compiler->parser, cpg_child_at(node, i - 1));
            fputs(op == '+' ? "cpg_add(" : op == '-' ? "cpg_sub(" : "cpg_mul(", stdout);
        }
        CpgVisit result = cpg_dispatch(cpg_child_at(node, 0), compiler->visitor, user);
        if (result != CPG_CONTINUE) return result;
        for (size_t i = 2; i < count; i += 2) {
            fputs(", ", stdout);
            result = cpg_dispatch(cpg_child_at(node, i), compiler->visitor, user);
            if (result != CPG_CONTINUE) return result;
            fputs(") ", stdout);
        }
    }
    return ferror(stdout) ? CPG_ERROR : CPG_CONTINUE;
}

static CpgVisit emit_comparison(const Node *node, void *user) {
    Compiler *compiler = user;
    size_t count = cpg_child_count(node);
    for (size_t i = 0; i < count / 2; ++i) fputc('(', stdout);
    for (size_t i = 0; i < count; ++i) {
        CpgVisit result = cpg_dispatch(cpg_child_at(node, i), compiler->visitor, user);
        if (result != CPG_CONTINUE) return result;
        if (i > 0 && i % 2 == 0) fputs(") ", stdout);
    }
    return ferror(stdout) ? CPG_ERROR : CPG_CONTINUE;
}

static void emit_indent(const Compiler *compiler) {
    for (size_t i = 0; i < compiler->depth; ++i) fputs("    ", stdout);
}

static CpgVisit emit_store(const Node *node, void *user) {
    Compiler *compiler = user;
    int typed = !strcmp(cpg_node_kind(node), "typed_declaration");
    int declaration = typed || !strcmp(cpg_node_kind(node), "declaration");
    if (declaration && cpg_child_count(node) == (typed ? 5u : 3u)) return CPG_CONTINUE;
    const Node *name = cpg_child_at(node, declaration ? 1 : 0);
    const Node *value = cpg_child_at(node, typed ? 5 : declaration ? 3 : 2);
    size_t index = find_symbol(compiler, name);
    emit_indent(compiler);
    CpgVisit result = emit_name(name, user);
    if (result != CPG_CONTINUE) return result;
    fputs("= ", stdout);
    result = emit_expression_as(compiler, value, compiler->symbols[index].type);
    if (result != CPG_CONTINUE) return result;
    fputs(";\n", stdout);
    return ferror(stdout) ? CPG_ERROR : CPG_CONTINUE;
}

static CpgVisit emit_construction(const Node *node, void *user) {
    Compiler *compiler = user;
    compiler->value_type = find_class(compiler, cpg_child_at(node, 1));
    fprintf(stdout, "cpg_new%d(", compiler->value_type);
    size_t constructor = find_constructor(compiler, compiler->value_type);
    CpgVisit result = CPG_CONTINUE;
    if (constructor == compiler->function_count) {
        result = dispatch_children(cpg_child_at(node, 3), user);
    } else {
        const Node *arguments = cpg_child_at(node, 3);
        const Function *function = &compiler->functions[constructor];
        for (size_t i = 0; i < cpg_child_count(arguments) && result == CPG_CONTINUE; i += 2) {
            if (i) fputs(", ", stdout);
            result = emit_expression_as(compiler, cpg_child_at(arguments, i),
                                        function->parameter_types[i / 2]);
        }
    }
    if (result != CPG_CONTINUE) return result;
    fputs(") ", stdout);
    compiler->value_type = find_class(compiler, cpg_child_at(node, 1));
    return ferror(stdout) ? CPG_ERROR : CPG_CONTINUE;
}

static int path_type(Compiler *compiler, const Node *node, size_t count) {
    int type = compiler->symbols[find_symbol(compiler, cpg_child_at(node, 0))].type;
    for (size_t i = 2; i < count; i += 2) {
        Type field_owner;
        size_t field;
        find_field(compiler, type, cpg_child_at(node, i), &field_owner, &field);
        type = compiler->classes[field_owner - 1].fields[field].type;
    }
    return type;
}

static void emit_base_field_prefix(const Compiler *compiler, Type type, Type owner) {
    while (type != owner) {
        fputs("cpg_base.", stdout);
        type = compiler->classes[type - 1].parent;
    }
}

static CpgVisit emit_path(const Node *node, size_t count, Compiler *compiler) {
    if (count == 1) return emit_name(cpg_child_at(node, 0), compiler);
    int type = path_type(compiler, node, count - 2);
    Type field_owner;
    size_t field;
    find_field(compiler, type, cpg_child_at(node, count - 1), &field_owner, &field);
    fprintf(stdout, "((cpg_class%d *)cpg_require(", type);
    CpgVisit result = emit_path(node, count - 2, compiler);
    if (result != CPG_CONTINUE) return result;
    fputs("))->", stdout);
    emit_base_field_prefix(compiler, type, field_owner);
    fprintf(stdout, "cpg_field%zu ", field);
    compiler->value_type = compiler->classes[field_owner - 1].fields[field].type;
    return ferror(stdout) ? CPG_ERROR : CPG_CONTINUE;
}

static CpgVisit emit_member(const Node *node, void *user) {
    return emit_path(node, cpg_child_count(node), user);
}

static CpgVisit emit_path_as(Compiler *compiler, const Node *node, size_t count,
                             Type expected) {
    Type actual = path_type(compiler, node, count);
    if (actual > 0 && expected > 0 && actual != expected)
        fprintf(stdout, "cpg_cast%d_%d(", actual, expected);
    CpgVisit result = emit_path(node, count, compiler);
    if (result == CPG_CONTINUE && actual > 0 && expected > 0 && actual != expected)
        fputs(") ", stdout);
    return result;
}

static CpgVisit emit_member_assignment(const Node *node, void *user) {
    Compiler *compiler = user;
    emit_indent(compiler);
    CpgVisit result = emit_member(cpg_child_at(node, 0), user);
    if (result != CPG_CONTINUE) return result;
    Type expected = compiler->value_type;
    fputs("= ", stdout);
    result = emit_expression_as(compiler, cpg_child_at(node, 2), expected);
    fputs(";\n", stdout);
    return result != CPG_CONTINUE || ferror(stdout) ? CPG_ERROR : CPG_CONTINUE;
}

static size_t virtual_root(const Compiler *compiler, size_t method) {
    const Function *function = &compiler->functions[method];
    Type owner = function->method;
    while (compiler->classes[owner - 1].parent) {
        size_t parent_method = find_method(compiler,
            compiler->classes[owner - 1].parent, function->name);
        if (parent_method == compiler->function_count) break;
        method = parent_method;
        function = &compiler->functions[method];
        owner = function->method;
    }
    return method;
}

static CpgVisit emit_arguments(Compiler *compiler, const Node *arguments,
                               const Function *function) {
    for (size_t i = 0; i < cpg_child_count(arguments); i += 2) {
        if (i) fputs(", ", stdout);
        CpgVisit result = emit_expression_as(compiler, cpg_child_at(arguments, i),
                                             function->parameter_types[i / 2]);
        if (result != CPG_CONTINUE) return result;
    }
    return CPG_CONTINUE;
}

static CpgVisit emit_method_call(const Node *node, void *user) {
    Compiler *compiler = user;
    const Node *path = cpg_child_at(node, 0);
    size_t count = cpg_child_count(path);
    int type = path_type(compiler, path, count - 2);
    size_t method = find_method(compiler, type, cpg_child_at(path, count - 1));
    size_t root = virtual_root(compiler, method);
    fprintf(stdout, "cpg_dispatch_%zu(cpg_require(", root);
    CpgVisit result = emit_path_as(compiler, path, count - 2,
                                   compiler->functions[root].method);
    if (result != CPG_CONTINUE) return result;
    fputc(')', stdout);
    const Node *arguments = cpg_child_at(node, 2);
    if (cpg_child_count(arguments)) fputs(", ", stdout);
    result = emit_arguments(compiler, arguments, &compiler->functions[method]);
    fputs(") ", stdout);
    return result != CPG_CONTINUE || ferror(stdout) ? CPG_ERROR : CPG_CONTINUE;
}

static CpgVisit emit_method_statement(const Node *node, void *user) {
    Compiler *compiler = user;
    emit_indent(compiler);
    fputs("(void)", stdout);
    CpgVisit result = emit_method_call(cpg_child_at(node, 0), user);
    fputs(";\n", stdout);
    return result != CPG_CONTINUE || ferror(stdout) ? CPG_ERROR : CPG_CONTINUE;
}

static CpgVisit emit_output(const Node *node, void *user) {
    Compiler *compiler = user;
    emit_indent(compiler);
    fputs("cpg_println_int((int32_t)", stdout);
    CpgVisit result = cpg_dispatch(cpg_child_at(node, 1), compiler->visitor, user);
    if (result != CPG_CONTINUE) return result;
    fputs(");\n", stdout);
    return ferror(stdout) ? CPG_ERROR : CPG_CONTINUE;
}

static CpgVisit emit_block(const Node *node, void *user) {
    Compiler *compiler = user;
    emit_indent(compiler);
    fputs("{\n", stdout);
    ++compiler->depth;
    for (size_t i = 1; i + 1 < cpg_child_count(node); ++i) {
        CpgVisit result = cpg_dispatch(cpg_child_at(node, i), compiler->visitor, user);
        if (result != CPG_CONTINUE) return result;
    }
    --compiler->depth;
    emit_indent(compiler);
    fputs("}\n", stdout);
    return ferror(stdout) ? CPG_ERROR : CPG_CONTINUE;
}

static CpgVisit emit_control(const Node *node, void *user) {
    Compiler *compiler = user;
    emit_indent(compiler);
    fputs(!strcmp(cpg_node_kind(node), "loop") ? "while (" : "if (", stdout);
    CpgVisit result = cpg_dispatch(cpg_child_at(node, 2), compiler->visitor, user);
    if (result != CPG_CONTINUE) return result;
    fputs(")\n", stdout);
    result = cpg_dispatch(cpg_child_at(node, 4), compiler->visitor, user);
    if (result != CPG_CONTINUE) return result;
    if (cpg_child_count(node) > 5) {
        emit_indent(compiler);
        fputs("else\n", stdout);
        result = cpg_dispatch(cpg_child_at(node, 6), compiler->visitor, user);
        if (result != CPG_CONTINUE) return result;
    }
    return ferror(stdout) ? CPG_ERROR : CPG_CONTINUE;
}

static CpgVisit emit_call(const Node *node, void *user) {
    Compiler *compiler = user;
    const Builtin *builtin = find_builtin(compiler, cpg_child_at(node, 0));
    size_t index = find_function(compiler, cpg_child_at(node, 0));
    if (!builtin && index == compiler->function_count) {
        return semantic_error(compiler, node, "unresolved function during emission");
    }
    if (builtin) fprintf(stdout, "cpg_%s(", builtin->name);
    else fprintf(stdout, "cpg_f%zu(", index);
    CpgVisit result = builtin ?
        cpg_dispatch(cpg_child_at(node, 2), compiler->visitor, user) :
        emit_arguments(compiler, cpg_child_at(node, 2), &compiler->functions[index]);
    if (result != CPG_CONTINUE) return result;
    fputs(") ", stdout);
    return ferror(stdout) ? CPG_ERROR : CPG_CONTINUE;
}

static CpgVisit emit_call_statement(const Node *node, void *user) {
    emit_indent(user);
    fputs("(void)", stdout);
    CpgVisit result = emit_call(cpg_child_at(node, 0), user);
    fputs(";\n", stdout);
    return result != CPG_CONTINUE || ferror(stdout) ? CPG_ERROR : CPG_CONTINUE;
}

static CpgVisit emit_return(const Node *node, void *user) {
    Compiler *compiler = user;
    emit_indent(compiler);
    fputs("return ", stdout);
    CpgVisit result = emit_expression_as(compiler, cpg_child_at(node, 1),
                                         compiler->return_type);
    if (result != CPG_CONTINUE) return result;
    fputs(";\n", stdout);
    return ferror(stdout) ? CPG_ERROR : CPG_CONTINUE;
}

static void emit_type(Type type) {
    if (type > 0) fprintf(stdout, "cpg_class%d *", type);
    else if (type == TYPE_BOOL) fputs("_Bool", stdout);
    else fputs("int32_t", stdout);
}

static void emit_signature(const Function *function, size_t index, int definition) {
    if (function->constructor) fputs("void", stdout);
    else emit_type(function->return_type);
    fprintf(stdout, " cpg_f%zu(", index);
    if (function->method) {
        emit_type(function->method);
        if (definition) fputs("cpg_self", stdout);
    }
    else if (!function->arity) fputs("void", stdout);
    for (size_t i = 0; i < function->arity; ++i) {
        if (i || function->method) fputs(", ", stdout);
        emit_type(function->parameter_types[i]);
        if (definition) fprintf(stdout, " cpg_v%zu", i + (function->method != 0));
    }
    fputc(')', stdout);
}

static void emit_virtual_signature(const Function *function, size_t index) {
    emit_type(function->return_type);
    fprintf(stdout, " cpg_dispatch_%zu(", index);
    emit_type(function->method);
    fputs(" cpg_self", stdout);
    for (size_t i = 0; i < function->arity; ++i) {
        fputs(", ", stdout);
        emit_type(function->parameter_types[i]);
        fprintf(stdout, " cpg_v%zu", i + 1);
    }
    fputc(')', stdout);
}

static void emit_derived_cast(const Compiler *compiler, Type from, Type to) {
    if (from == to) {
        fputs("cpg_self", stdout);
        return;
    }
    Type parent = compiler->classes[to - 1].parent;
    fprintf(stdout, "((cpg_class%d *)", to);
    emit_derived_cast(compiler, from, parent);
    fputc(')', stdout);
}

static void emit_object_base_pointer(const Compiler *compiler, Type from, Type to) {
    if (from == to) {
        fputs("object", stdout);
        return;
    }
    fputs("&object", stdout);
    Type current = from;
    while (current != to) {
        fputs(current == from ? "->cpg_base" : ".cpg_base", stdout);
        current = compiler->classes[current - 1].parent;
    }
}

static void emit_self_base_pointer(const Compiler *compiler, Type from, Type to) {
    if (from == to) {
        fputs("cpg_self", stdout);
        return;
    }
    fputs("&cpg_self", stdout);
    Type current = from;
    while (current != to) {
        fputs(current == from ? "->cpg_base" : ".cpg_base", stdout);
        current = compiler->classes[current - 1].parent;
    }
}

static void emit_object_type_field(const Compiler *compiler, Type type) {
    fputs("object->", stdout);
    while (compiler->classes[type - 1].parent) {
        fputs("cpg_base.", stdout);
        type = compiler->classes[type - 1].parent;
    }
    fputs("cpg_type", stdout);
}

static void emit_self_type_field(const Compiler *compiler, Type type) {
    fputs("cpg_self->", stdout);
    while (compiler->classes[type - 1].parent) {
        fputs("cpg_base.", stdout);
        type = compiler->classes[type - 1].parent;
    }
    fputs("cpg_type", stdout);
}

static CpgVisit emit_base_constructor_call(Compiler *compiler,
                                           const Function *function,
                                           Compiler *local) {
    Type parent = compiler->classes[function->method - 1].parent;
    if (!parent) return CPG_CONTINUE;
    size_t constructor = nearest_constructor(compiler, parent);
    if (constructor == compiler->function_count) return CPG_CONTINUE;
    const Function *base = &compiler->functions[constructor];
    const Node *initializer = base_initializer(function->node);
    const Node *arguments = base_arguments(initializer);
    fprintf(stdout, "    cpg_f%zu(", constructor);
    emit_self_base_pointer(compiler, function->method, base->method);
    if (arguments && cpg_child_count(arguments)) fputs(", ", stdout);
    CpgVisit result = CPG_CONTINUE;
    if (arguments) result = emit_arguments(local, arguments, base);
    fputs(");\n", stdout);
    return result != CPG_CONTINUE || ferror(stdout) ? CPG_ERROR : CPG_CONTINUE;
}

static void emit_virtual_dispatchers(const Compiler *compiler) {
    for (size_t i = 0; i < compiler->function_count; ++i) {
        const Function *root = &compiler->functions[i];
        if (!root->method || root->constructor || virtual_root(compiler, i) != i) continue;
        emit_virtual_signature(root, i);
        fputs(" {\n    switch (", stdout);
        emit_self_type_field(compiler, root->method);
        fputs(") {\n", stdout);
        for (Type dynamic = 1; dynamic <= (Type)compiler->class_count; ++dynamic) {
            if (!is_subtype(compiler, dynamic, root->method)) continue;
            size_t method = find_method(compiler, dynamic, root->name);
            if (method == compiler->function_count || virtual_root(compiler, method) != i)
                continue;
            const Function *implementation = &compiler->functions[method];
            fprintf(stdout, "    case %d: return cpg_f%zu(", dynamic, method);
            emit_derived_cast(compiler, root->method, implementation->method);
            for (size_t parameter = 0; parameter < root->arity; ++parameter)
                fprintf(stdout, ", cpg_v%zu", parameter + 1);
            fputs(");\n", stdout);
        }
        fputs("    default:\n"
              "        cpg_io_fail(\"invalid virtual dispatch\");\n", stdout);
        if (root->return_type > 0) fputs("        return NULL;\n", stdout);
        else fputs("        return 0;\n", stdout);
        fputs("    }\n}\n\n", stdout);
    }
}

static size_t class_depth(const Compiler *compiler, Type type) {
    size_t depth = 0;
    while (compiler->classes[type - 1].parent) {
        ++depth;
        type = compiler->classes[type - 1].parent;
    }
    return depth;
}

static void emit_class_cast_helpers(const Compiler *compiler) {
    for (Type actual = 1; actual <= (Type)compiler->class_count; ++actual) {
        for (Type expected = compiler->classes[actual - 1].parent;
             expected > 0; expected = compiler->classes[expected - 1].parent) {
            emit_type(expected);
            fprintf(stdout, " cpg_cast%d_%d(cpg_class%d *object) {\n"
                    "    if (!object) return NULL;\n    return &object",
                    actual, expected, actual);
            Type current = actual;
            while (current != expected) {
                fprintf(stdout, "%s cpg_base",
                        current == actual ? "->" : ".");
                current = compiler->classes[current - 1].parent;
            }
            fputs(";\n}\n\n", stdout);
        }
    }
}

static void emit_slots(const Compiler *compiler, size_t parameters) {
    /* Hoist storage, not initializers; blocks share their enclosing scope. */
    for (size_t i = 0; i < compiler->count; ++i) {
        if (compiler->receiver && i == 0) {
            fputs("    (void)cpg_self;\n", stdout);
            continue;
        }
        if (i >= parameters) {
            fputs("    ", stdout);
            emit_type(compiler->symbols[i].type);
            fprintf(stdout, " cpg_v%zu = %s;\n", i,
                    compiler->symbols[i].type > 0 ? "NULL" : "0");
        }
        fprintf(stdout, "    (void)cpg_v%zu;\n", i);
    }
}

static CpgVisit emit_program(const Node *root, void *user) {
    Compiler *compiler = user;
    fputs("#include <stdio.h>\n#include <stdlib.h>\n"
          "#include <stdint.h>\n#include <inttypes.h>\n\n"
          "int32_t cpg_checked(int_least64_t value, const char *operation) {\n"
          "    if (value < INT32_MIN || value > INT32_MAX) {\n"
          "        fprintf(stderr, \"integer overflow in %s\\n\", operation);\n"
          "        exit(EXIT_FAILURE);\n"
          "    }\n"
          "    return (int32_t)value;\n"
          "}\n\n"
          "int32_t cpg_add(int32_t left, int32_t right) {\n"
          "    return cpg_checked((int_least64_t)left + right, \"+\");\n"
          "}\n\n"
          "int32_t cpg_sub(int32_t left, int32_t right) {\n"
          "    return cpg_checked((int_least64_t)left - right, \"-\");\n"
          "}\n\n"
          "int32_t cpg_mul(int32_t left, int32_t right) {\n"
          "    return cpg_checked((int_least64_t)left * right, \"*\");\n"
          "}\n\n"
          "int32_t cpg_min(int32_t left, int32_t right) {\n"
          "    return left < right ? left : right;\n"
          "}\n\n"
          "int32_t cpg_max(int32_t left, int32_t right) {\n"
          "    return left > right ? left : right;\n"
          "}\n\n"
          "int32_t cpg_abs(int32_t value) {\n"
          "    return cpg_checked(value < 0 ? -(int_least64_t)value : value, \"abs\");\n"
          "}\n\n"
          "void cpg_io_fail(const char *message) {\n"
          "    fprintf(stderr, \"%s\\n\", message);\n"
          "    exit(EXIT_FAILURE);\n"
          "}\n\n"
          "void cpg_flush(void) {\n"
          "    if (fflush(stdout)) cpg_io_fail(\"output error\");\n"
          "}\n\n"
          "void cpg_print_int(int32_t value) {\n"
          "    if (printf(\"%\" PRId32, value) < 0) cpg_io_fail(\"output error\");\n"
          "}\n\n"
          "void cpg_print_bool(_Bool value) {\n"
          "    if (fputs(value ? \"true\" : \"false\", stdout) == EOF)\n"
          "        cpg_io_fail(\"output error\");\n"
          "}\n\n"
          "void cpg_newline(void) {\n"
          "    if (putchar('\\n') == EOF) cpg_io_fail(\"output error\");\n"
          "}\n\n"
          "void cpg_println_int(int32_t value) {\n"
          "    cpg_print_int(value);\n"
          "    cpg_newline();\n"
          "}\n\n"
          "void cpg_println_bool(_Bool value) {\n"
          "    cpg_print_bool(value);\n"
          "    cpg_newline();\n"
          "}\n\n"
          "int cpg_space(int ch) {\n"
          "    return ch == ' ' || ch == '\\t' || ch == '\\n' ||\n"
          "           ch == '\\r' || ch == '\\f' || ch == '\\v';\n"
          "}\n\n"
          "int32_t cpg_read_int(void) {\n"
          "    unsigned long value = 0;\n"
          "    int ch, negative = 0, digits = 0, malformed = 0, range = 0;\n"
          "    cpg_flush();\n"
          "    do { ch = fgetc(stdin); } while (cpg_space(ch));\n"
          "    if (ch == EOF) {\n"
          "        cpg_io_fail(ferror(stdin) ? \"input error\" : \"input EOF\");\n"
          "    }\n"
          "    if (ch == '+' || ch == '-') {\n"
          "        negative = ch == '-';\n"
          "        ch = fgetc(stdin);\n"
          "    }\n"
          "    while (ch != EOF && !cpg_space(ch)) {\n"
          "        if (ch < '0' || ch > '9') malformed = 1;\n"
          "        else {\n"
          "            unsigned long digit = (unsigned long)(ch - '0');\n"
          "            digits = 1;\n"
          "            if (value > (2147483648UL - digit) / 10) range = 1;\n"
          "            else if (!range) value = value * 10 + digit;\n"
          "        }\n"
          "        ch = fgetc(stdin);\n"
          "    }\n"
          "    if (ferror(stdin)) cpg_io_fail(\"input error\");\n"
          "    if (!digits || malformed) cpg_io_fail(\"input malformed integer\");\n"
          "    if (range || (!negative && value > 2147483647UL))\n"
          "        cpg_io_fail(\"input integer outside int32 range\");\n"
          "    if (negative && value == 2147483648UL) return INT32_MIN;\n"
          "    return negative ? -(int32_t)value : (int32_t)value;\n"
          "}\n\n", stdout);
    if (compiler->class_count) {
        fputs("typedef struct cpg_allocation {\n"
              "    void *object;\n"
              "    struct cpg_allocation *next;\n"
              "} cpg_allocation;\n"
              "cpg_allocation *cpg_allocations;\n\n"
              "void cpg_cleanup(void) {\n"
              "    while (cpg_allocations) {\n"
              "        cpg_allocation *entry = cpg_allocations;\n"
              "        cpg_allocations = entry->next;\n"
              "        free(entry->object);\n"
              "        free(entry);\n"
              "    }\n"
              "}\n\n"
              "void *cpg_allocate(size_t size) {\n"
              "    cpg_allocation *entry = malloc(sizeof(*entry));\n"
              "    void *object = malloc(size);\n"
              "    if (!entry || !object) {\n"
              "        free(entry);\n"
              "        free(object);\n"
              "        fputs(\"object allocation failed\\n\", stderr);\n"
              "        exit(EXIT_FAILURE);\n"
              "    }\n"
              "    entry->object = object;\n"
              "    entry->next = cpg_allocations;\n"
              "    cpg_allocations = entry;\n"
              "    return object;\n"
              "}\n\n"
              "void *cpg_require(void *object) {\n"
              "    if (!object) {\n"
              "        fputs(\"uninitialized object reference\\n\", stderr);\n"
              "        exit(EXIT_FAILURE);\n"
              "    }\n"
              "    return object;\n"
              "}\n\n", stdout);
        for (size_t i = 0; i < compiler->class_count; ++i)
            fprintf(stdout, "typedef struct cpg_class%zu cpg_class%zu;\n", i + 1, i + 1);
        for (size_t depth = 0; depth <= compiler->class_count; ++depth) {
            for (Type type = 1; type <= (Type)compiler->class_count; ++type) {
                if (class_depth(compiler, type) != depth) continue;
                const Class *class_info = &compiler->classes[type - 1];
                fprintf(stdout, "\nstruct cpg_class%d {\n", type);
                if (class_info->parent)
                    fprintf(stdout, "    cpg_class%d cpg_base;\n", class_info->parent);
                else
                    fputs("    int cpg_type;\n", stdout);
                for (size_t j = 0; j < class_info->field_count; ++j) {
                    fputs("    ", stdout);
                    emit_type(class_info->fields[j].type);
                    fprintf(stdout, " cpg_field%zu;\n", j);
                }
                if (!class_info->parent && !class_info->field_count)
                    fputs("    unsigned char cpg_empty;\n", stdout);
                fputs("};\n", stdout);
            }
        }
        emit_class_cast_helpers(compiler);
        for (size_t i = 0; i < compiler->function_count; ++i) {
            emit_signature(&compiler->functions[i], i, 0);
            fputs(";\n", stdout);
        }
        for (size_t i = 0; i < compiler->function_count; ++i) {
            const Function *function = &compiler->functions[i];
            if (!function->method || function->constructor ||
                virtual_root(compiler, i) != i) continue;
            emit_virtual_signature(function, i);
            fputs(";\n", stdout);
        }
        emit_virtual_dispatchers(compiler);
        for (size_t i = 0; i < compiler->class_count; ++i) {
            Type type = (Type)i + 1;
            size_t constructor_index = find_constructor(compiler, type);
            const Function *constructor = constructor_index == compiler->function_count ?
                NULL : &compiler->functions[constructor_index];
            fprintf(stdout, "\ncpg_class%zu *cpg_new%zu(", i + 1, i + 1);
            if (!constructor || !constructor->arity) {
                fputs("void", stdout);
            } else {
                for (size_t j = 0; j < constructor->arity; ++j) {
                    if (j) fputs(", ", stdout);
                    emit_type(constructor->parameter_types[j]);
                    fprintf(stdout, " cpg_arg%zu", j);
                }
            }
            fprintf(stdout, ") {\n"
                    "    cpg_class%zu *object = cpg_allocate(sizeof(*object));\n"
                    "    *object = (cpg_class%zu){0};\n", i + 1, i + 1);
            fputs("    ", stdout);
            emit_object_type_field(compiler, type);
            fprintf(stdout, " = %d;\n", type);
            if (constructor) {
                fprintf(stdout, "    cpg_f%zu(object", constructor_index);
                for (size_t j = 0; j < constructor->arity; ++j)
                    fprintf(stdout, ", cpg_arg%zu", j);
                fputs(");\n", stdout);
            } else {
                size_t inherited = nearest_constructor(compiler,
                    compiler->classes[type - 1].parent);
                if (inherited != compiler->function_count) {
                    fprintf(stdout, "    cpg_f%zu(", inherited);
                    emit_object_base_pointer(compiler, type,
                        compiler->functions[inherited].method);
                    fputs(");\n", stdout);
                }
            }
            fputs("    return object;\n}\n\n", stdout);
        }
    }
    if (!compiler->class_count) {
        for (size_t i = 0; i < compiler->function_count; ++i) {
            emit_signature(&compiler->functions[i], i, 0);
            fputs(";\n", stdout);
        }
    }
    for (size_t i = 0; i < compiler->function_count; ++i) {
        const Function *function = &compiler->functions[i];
        Compiler local = *compiler;
        local.symbols = function->symbols;
        local.count = function->count;
        local.depth = 1;
        local.receiver = function->method;
        local.return_type = function->return_type;
        emit_signature(function, i, 1);
        fputs(" {\n", stdout);
        emit_slots(&local, function->arity + (function->method != 0));
        CpgVisit result = CPG_CONTINUE;
        if (function->constructor)
            result = emit_base_constructor_call(compiler, function, &local);
        if (result == CPG_CONTINUE)
            result = cpg_dispatch(function_body(function->node), local.visitor, &local);
        if (result != CPG_CONTINUE) return result;
        fputs("}\n\n", stdout);
    }
    fputs("int main(void) {\n", stdout);
    if (compiler->class_count)
        fputs("    if (atexit(cpg_cleanup)) {\n"
              "        cpg_io_fail(\"object cleanup registration failed\");\n"
              "    }\n", stdout);
    emit_slots(compiler, 0);
    for (size_t i = 0; i < cpg_child_count(root); ++i) {
        const Node *node = cpg_child_at(root, i);
        if (!strcmp(cpg_node_kind(node), "function") ||
            !strcmp(cpg_node_kind(node), "class_decl")) continue;
        CpgVisit result = cpg_dispatch(node, compiler->visitor, user);
        if (result != CPG_CONTINUE) return result;
    }
    fputs("    cpg_flush();\n    return EXIT_SUCCESS;\n}\n", stdout);
    return ferror(stdout) ? CPG_ERROR : CPG_CONTINUE;
}

static void diagnostic(const Context *parser, size_t offset, const char *problem,
                       const Node *name) {
    size_t line = 1, column = 1;
    for (size_t i = 0; i < offset && i < parser->length; ++i) {
        if (parser->input[i] == '\n') { ++line; column = 1; }
        else ++column;
    }
    fprintf(stderr, "%s:%zu:%zu: byte %zu: %s", parser->path, line, column, offset, problem);
    if (name) {
        fputs(": '", stderr);
        fwrite(cpg_node_text(parser, name), 1, cpg_node_text_length(name), stderr);
        fputc('\'', stderr);
    }
    fputc('\n', stderr);
}

static unsigned char *read_source(const char *path, size_t *length) {
    FILE *file = fopen(path, "rb");
    if (!file) { perror(path); return NULL; }
    /* Match the generated C runtime's one-MiB input limit. */
    const size_t limit = 1024u * 1024u;
    unsigned char *source = malloc(limit);
    if (!source) {
        fprintf(stderr, "%s: input allocation failed\n", path);
        fclose(file);
        return NULL;
    }
    *length = fread(source, 1, limit, file);
    int extra = fgetc(file);
    int failed = ferror(file);
    if (fclose(file)) failed = 1;
    if (failed) {
        fprintf(stderr, "%s: input read/close failed\n", path);
        free(source);
        return NULL;
    }
    if (extra != EOF) {
        fprintf(stderr, "%s: input exceeds C runtime one-MiB limit\n", path);
        free(source);
        return NULL;
    }
    return source;
}

int main(int argc, char **argv) {
    if (argc != 2) {
        fputs("usage: statement-compiler SOURCE\n", stderr);
        return 2;
    }
    size_t length = 0;
    unsigned char *source = read_source(argv[1], &length);
    if (!source) return 1;
    Context parser;
    cpg_init(&parser, source, length, argv[1]);
    const Node *root = cpg_parse(&parser, 1);
    int status = 1;
    Compiler compiler = {0};
    compiler.parser = &parser;
    compiler.falls_through = 1;
    if (!root) {
        diagnostic(&parser, parser.error_offset, parser.problem, NULL);
    } else {
        CpgVisitor validator = {0};
        validator.on_rule_declaration = check_declaration;
        validator.on_rule_class_decl = check_class;
        validator.on_rule_typed_declaration = check_typed_declaration;
        validator.on_rule_construction = check_construction;
        validator.on_rule_member = check_member;
        validator.on_rule_member_assignment = check_member_assignment;
        validator.on_rule_method_call = check_method_call;
        validator.on_rule_output = check_output;
        validator.on_rule_equality = check_numeric;
        validator.on_rule_comparison = check_numeric;
        validator.on_rule_sum = check_numeric;
        validator.on_rule_product = check_numeric;
        validator.on_rule_unary = check_numeric;
        validator.on_rule_assignment = check_assignment;
        validator.on_rule_conditional = check_control;
        validator.on_rule_loop = check_control;
        validator.on_rule_function = check_function;
        validator.on_rule_call = check_call;
        validator.on_rule_call_statement = check_call_statement;
        validator.on_rule_returning = check_return;
        validator.on_token_IDENT = check_name;
        validator.on_token_INTEGER = check_integer;
        validator.on_rule_boolean = check_boolean;
        validator.on_node = dispatch_children;
        compiler.visitor = &validator;
        compiler.type_visitor = &validator;
        if (collect_functions(root, &compiler) != CPG_CONTINUE ||
            cpg_dispatch(root, &validator, &compiler) != CPG_CONTINUE) {
            diagnostic(&parser, compiler.error ? compiler.error->offset : 0,
                       compiler.problem ? compiler.problem : "validation failed", compiler.error);
        } else {
            CpgVisitor emitter = {0};
            emitter.on_rule_declaration = emit_store;
            emitter.on_rule_typed_declaration = emit_store;
            emitter.on_rule_construction = emit_construction;
            emitter.on_rule_member = emit_member;
            emitter.on_rule_member_assignment = emit_member_assignment;
            emitter.on_rule_method_call = emit_method_call;
            emitter.on_rule_method_statement = emit_method_statement;
            emitter.on_rule_assignment = emit_store;
            emitter.on_rule_output = emit_output;
            emitter.on_rule_conditional = emit_control;
            emitter.on_rule_loop = emit_control;
            emitter.on_rule_block = emit_block;
            emitter.on_rule_call = emit_call;
            emitter.on_rule_call_statement = emit_call_statement;
            emitter.on_rule_arguments = dispatch_children;
            emitter.on_rule_returning = emit_return;
            emitter.on_rule_expression = emit_group;
            emitter.on_rule_equality = emit_comparison;
            emitter.on_rule_comparison = emit_comparison;
            emitter.on_rule_sum = emit_arithmetic;
            emitter.on_rule_product = emit_arithmetic;
            emitter.on_rule_unary = emit_arithmetic;
            emitter.on_rule_primary = emit_group;
            emitter.on_rule_program = emit_program;
            emitter.on_rule_statement = dispatch_children;
            emitter.on_token_IDENT = emit_name;
            emitter.on_token_INTEGER = emit_integer;
            emitter.on_rule_boolean = emit_boolean;
            emitter.on_node = emit_literal;
            compiler.visitor = &emitter;
            compiler.depth = 1;
            CpgVisit result = cpg_dispatch(root, &emitter, &compiler);
            int failed = fflush(stdout) != 0 || ferror(stdout);
            if (result != CPG_CONTINUE || failed) {
                fputs("statement-compiler: C source output failed\n", stderr);
            } else status = 0;
        }
        for (size_t i = 0; i < compiler.function_count; ++i) {
            free(compiler.functions[i].symbols);
            free(compiler.functions[i].parameter_types);
        }
        free(compiler.functions);
        for (size_t i = 0; i < compiler.class_count; ++i) free(compiler.classes[i].fields);
        free(compiler.classes);
    }
    free(compiler.symbols);
    cpg_destroy(&parser);
    free(source);
    return status;
}

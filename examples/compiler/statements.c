#define CPARSEGEN_NO_MAIN
#include "parser.c"

typedef int Type;
enum { TYPE_BOOL = -1, TYPE_INT = 0 };

typedef struct {
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
    Type *parameter_types;
    Type return_type;
} Function;

typedef struct {
    const Context *parser;
    const CpgVisitor *visitor;
    Symbol *symbols;
    size_t count, capacity;
    size_t depth;
    Function *functions;
    size_t function_count;
    int in_function, falls_through;
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

static const Node *function_parameters(const Node *node) {
    return cpg_child_at(node, 3);
}

static const Node *function_body(const Node *node) {
    return cpg_child_at(node, cpg_child_count(node) - 1);
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
    return semantic_error(compiler, name, "unknown type");
}

static size_t find_function(const Compiler *compiler, const Node *name) {
    for (size_t i = 0; i < compiler->function_count; ++i) {
        if (same_name(compiler, compiler->functions[i].name, name)) return i;
    }
    return compiler->function_count;
}

static size_t find_symbol(const Compiler *compiler, const Node *name) {
    for (size_t i = 0; i < compiler->count; ++i) {
        if (same_name(compiler, compiler->symbols[i].name, name)) {
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
            if (i && left != right)
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
    return compiler->value_type != type ?
        semantic_error(compiler, node, problem) : CPG_CONTINUE;
}

static CpgVisit check_arguments(Compiler *compiler, const Node *arguments,
                                const Function *function) {
    for (size_t i = 0; i < cpg_child_count(arguments); i += 2) {
        CpgVisit result = require_type(compiler, cpg_child_at(arguments, i),
                                       function->parameter_types[i / 2],
                                       "argument type mismatch");
        if (result != CPG_CONTINUE) return result;
    }
    compiler->value_type = function->return_type;
    return CPG_CONTINUE;
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
    local.return_type = function->return_type;
    CpgVisit result = CPG_CONTINUE;
    const Node *parameters = function_parameters(node);
    for (size_t i = 0; i < cpg_child_count(parameters) && result == CPG_CONTINUE; i += 2) {
        result = add_symbol(&local, cpg_child_at(cpg_child_at(parameters, i), 0), 1);
        if (result == CPG_CONTINUE)
            local.symbols[local.count - 1].type = function->parameter_types[i / 2];
    }
    if (result == CPG_CONTINUE)
        result = cpg_dispatch(function_body(node), local.visitor, &local);
    if (result == CPG_CONTINUE && local.falls_through) {
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

static CpgVisit collect_functions(const Node *root, Compiler *compiler) {
    size_t count = cpg_child_count(root);
    compiler->functions = calloc(count ? count : 1, sizeof(*compiler->functions));
    if (!compiler->functions) return semantic_error(compiler, root, "function table allocation failed");
    for (size_t i = 0; i < count; ++i) {
        const Node *node = cpg_child_at(root, i);
        if (strcmp(cpg_node_kind(node), "function")) continue;
        const Node *name = cpg_child_at(node, 1);
        if (find_function(compiler, name) != compiler->function_count)
            return semantic_error(compiler, name, "duplicate function");
        Function *function = &compiler->functions[compiler->function_count++];
        const Node *parameters = function_parameters(node);
        function->node = node;
        function->name = name;
        function->arity = (cpg_child_count(parameters) + 1) / 2;
        const Node *annotation = cpg_child_at(node, 5);
        if (cpg_child_count(annotation) &&
            resolve_type(compiler, cpg_child_at(annotation, 1),
                         &function->return_type) != CPG_CONTINUE)
            return CPG_ERROR;
        function->parameter_types = calloc(function->arity ? function->arity : 1,
                                           sizeof(*function->parameter_types));
        if (!function->parameter_types)
            return semantic_error(compiler, name, "parameter table allocation failed");
        for (size_t k = 0; k < function->arity; ++k) {
            const Node *parameter = cpg_child_at(parameters, k * 2);
            if (cpg_child_count(parameter) > 1 &&
                resolve_type(compiler, cpg_child_at(parameter, 2),
                             &function->parameter_types[k]) != CPG_CONTINUE)
                return CPG_ERROR;
        }
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
    if (result == CPG_CONTINUE && compiler->value_type != compiler->symbols[index].type)
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
        if (compiler->value_type != type)
            return semantic_error(compiler, name, "initializer type mismatch");
    }
    result = add_symbol(compiler, name, initialized);
    if (result == CPG_CONTINUE) compiler->symbols[compiler->count - 1].type = type;
    return result;
}

static CpgVisit emit_name(const Node *node, void *user) {
    Compiler *compiler = user;
    size_t index = find_symbol(compiler, node);
    if (index == compiler->count) return semantic_error(compiler, node, "unresolved name during emission");
    /* Numeric slots cannot collide with C keywords, libc names, or user names. */
    compiler->value_type = compiler->symbols[index].type;
    fprintf(stdout, "cpg_v%zu ", index);
    return ferror(stdout) ? CPG_ERROR : CPG_CONTINUE;
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
    emit_indent(compiler);
    CpgVisit result = emit_name(name, user);
    if (result != CPG_CONTINUE) return result;
    fputs("= ", stdout);
    result = cpg_dispatch(value, compiler->visitor, user);
    if (result != CPG_CONTINUE) return result;
    fputs(";\n", stdout);
    return ferror(stdout) ? CPG_ERROR : CPG_CONTINUE;
}

static CpgVisit emit_arguments(Compiler *compiler, const Node *arguments) {
    for (size_t i = 0; i < cpg_child_count(arguments); i += 2) {
        if (i) fputs(", ", stdout);
        CpgVisit result = cpg_dispatch(cpg_child_at(arguments, i), compiler->visitor,
                                       compiler);
        if (result != CPG_CONTINUE) return result;
    }
    return CPG_CONTINUE;
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
    CpgVisit result = emit_arguments(compiler, cpg_child_at(node, 2));
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
    CpgVisit result = cpg_dispatch(cpg_child_at(node, 1), compiler->visitor, user);
    if (result != CPG_CONTINUE) return result;
    fputs(";\n", stdout);
    return ferror(stdout) ? CPG_ERROR : CPG_CONTINUE;
}

static void emit_type(Type type) {
    fputs(type == TYPE_BOOL ? "_Bool" : "int32_t", stdout);
}

static void emit_signature(const Function *function, size_t index, int definition) {
    emit_type(function->return_type);
    fprintf(stdout, " cpg_f%zu(", index);
    if (!function->arity) fputs("void", stdout);
    for (size_t i = 0; i < function->arity; ++i) {
        if (i) fputs(", ", stdout);
        emit_type(function->parameter_types[i]);
        if (definition) fprintf(stdout, " cpg_v%zu", i);
    }
    fputc(')', stdout);
}

static void emit_slots(const Compiler *compiler, size_t parameters) {
    /* Hoist storage, not initializers; blocks share their enclosing scope. */
    for (size_t i = 0; i < compiler->count; ++i) {
        if (i >= parameters) {
            fputs("    ", stdout);
            emit_type(compiler->symbols[i].type);
            fprintf(stdout, " cpg_v%zu = 0;\n", i);
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
    for (size_t i = 0; i < compiler->function_count; ++i) {
        emit_signature(&compiler->functions[i], i, 0);
        fputs(";\n", stdout);
    }
    for (size_t i = 0; i < compiler->function_count; ++i) {
        const Function *function = &compiler->functions[i];
        Compiler local = *compiler;
        local.symbols = function->symbols;
        local.count = function->count;
        local.depth = 1;
        local.return_type = function->return_type;
        emit_signature(function, i, 1);
        fputs(" {\n", stdout);
        emit_slots(&local, function->arity);
        CpgVisit result = cpg_dispatch(function_body(function->node), local.visitor, &local);
        if (result != CPG_CONTINUE) return result;
        fputs("}\n\n", stdout);
    }
    fputs("int main(void) {\n", stdout);
    emit_slots(compiler, 0);
    for (size_t i = 0; i < cpg_child_count(root); ++i) {
        const Node *node = cpg_child_at(root, i);
        if (!strcmp(cpg_node_kind(node), "function")) continue;
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
        validator.on_rule_typed_declaration = check_typed_declaration;
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
        if (collect_functions(root, &compiler) != CPG_CONTINUE ||
            cpg_dispatch(root, &validator, &compiler) != CPG_CONTINUE) {
            diagnostic(&parser, compiler.error ? compiler.error->offset : 0,
                       compiler.problem ? compiler.problem : "validation failed", compiler.error);
        } else {
            CpgVisitor emitter = {0};
            emitter.on_rule_declaration = emit_store;
            emitter.on_rule_typed_declaration = emit_store;
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
    }
    free(compiler.symbols);
    cpg_destroy(&parser);
    free(source);
    return status;
}

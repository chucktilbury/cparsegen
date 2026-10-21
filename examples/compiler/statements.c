#define CPARSEGEN_NO_MAIN
#include "parser.c"

typedef struct {
    /* NULL denotes the implicit method receiver. */
    const Node *name;
    int initialized;
    int type;
} Symbol;

typedef struct {
    const Node *node;
    const Node *name;
    size_t arity;
    Symbol *symbols;
    size_t count;
    int method;
    int constructor;
    int *parameter_types;
} Function;

typedef struct {
    const Node *name;
    Symbol *fields;
    size_t field_count;
} Class;

typedef struct {
    const Context *parser;
    const CpgVisitor *visitor;
    Symbol *symbols;
    size_t count, capacity;
    size_t depth;
    Function *functions;
    size_t function_count;
    int in_function, in_constructor, falls_through;
    Class *classes;
    size_t class_count;
    int receiver, value_type;
    const char *problem;
    const Node *error;
} Compiler;

static CpgVisit semantic_error(Compiler *compiler, const Node *node, const char *problem) {
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

static CpgVisit resolve_type(Compiler *compiler, const Node *name, int *type) {
    if (cpg_node_text_length(name) == 3 &&
        !memcmp(cpg_node_text(compiler->parser, name), "int", 3)) {
        *type = 0;
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

static CpgVisit check_integer(const Node *node, void *user) {
    Compiler *compiler = user;
    compiler->value_type = 0;
    if (cpg_node_text_length(node) > 9) {
        return semantic_error(compiler, node, "integer literal exceeds nine digits");
    }
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
    compiler->symbols[compiler->count++] = (Symbol){name, initialized, 0};
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
    int type = initialized ? compiler->value_type : 0;
    CpgVisit result = add_symbol(compiler, name, initialized);
    if (result == CPG_CONTINUE) compiler->symbols[compiler->count - 1].type = type;
    return result;
}

static CpgVisit check_numeric(const Node *node, void *user) {
    Compiler *compiler = user;
    for (size_t i = 0; i < cpg_child_count(node); ++i) {
        const Node *child = cpg_child_at(node, i);
        CpgVisit result = cpg_dispatch(child, compiler->visitor, user);
        if (result != CPG_CONTINUE) return result;
        size_t count = cpg_child_count(node);
        int operand = count == 2 ? i == 1 : i % 2 == 0;
        if (compiler->value_type && count > 1 && operand) {
            return semantic_error(compiler, child, "type mismatch: expected integer");
        }
    }
    return CPG_CONTINUE;
}

static CpgVisit require_integer(Compiler *compiler, const Node *node) {
    CpgVisit result = cpg_dispatch(node, compiler->visitor, compiler);
    if (result != CPG_CONTINUE) return result;
    return compiler->value_type ?
        semantic_error(compiler, node, "type mismatch: expected integer") : CPG_CONTINUE;
}

static CpgVisit check_arguments(Compiler *compiler, const Node *arguments,
                                const Function *function) {
    for (size_t i = 0; i < cpg_child_count(arguments); i += 2) {
        const Node *argument = cpg_child_at(arguments, i);
        CpgVisit result = cpg_dispatch(argument, compiler->visitor, compiler);
        if (result != CPG_CONTINUE) return result;
        if (compiler->value_type != function->parameter_types[i / 2])
            return semantic_error(compiler, argument, "argument type mismatch");
    }
    compiler->value_type = 0;
    return CPG_CONTINUE;
}

static CpgVisit check_call(const Node *node, void *user) {
    Compiler *compiler = user;
    const Node *name = cpg_child_at(node, 0);
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
    CpgVisit result = require_integer(compiler, cpg_child_at(node, 1));
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
    CpgVisit result = CPG_CONTINUE;
    if (function->method) {
        result = add_symbol(&local, compiler->classes[function->method - 1].name, 1);
        if (result == CPG_CONTINUE) {
            local.symbols[0].type = function->method;
            local.symbols[0].name = NULL;
        }
    }
    const Node *parameters = cpg_child_at(node, function->constructor ? 2 : 3);
    for (size_t i = 0; i < cpg_child_count(parameters) && result == CPG_CONTINUE; i += 2) {
        result = add_symbol(&local, cpg_child_at(cpg_child_at(parameters, i), 0), 1);
        if (result == CPG_CONTINUE)
            local.symbols[local.count - 1].type = function->parameter_types[i / 2];
    }
    if (result == CPG_CONTINUE) {
        result = cpg_dispatch(cpg_child_at(node, function->constructor ? 4 : 5),
                              local.visitor, &local);
    }
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
        compiler->classes[compiler->class_count++].name = name;
        count += cpg_child_count(node);
    }
    for (size_t i = 0; i < cpg_child_count(root); ++i) {
        const Node *node = cpg_child_at(root, i);
        if (strcmp(cpg_node_kind(node), "class_decl")) continue;
        Class *class_info = &compiler->classes[find_class(compiler, cpg_child_at(node, 1)) - 1];
        class_info->fields = calloc(cpg_child_count(node), sizeof(*class_info->fields));
        if (!class_info->fields) return semantic_error(compiler, node, "field table allocation failed");
        for (size_t j = 3; j + 1 < cpg_child_count(node); ++j) {
            const Node *field = cpg_child_at(node, j);
            if (strcmp(cpg_node_kind(field), "field")) continue;
            const Node *name = cpg_child_at(field, 1);
            const Node *type = cpg_child_at(field, 3);
            int field_type;
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
        size_t members = class_decl ? cpg_child_count(node) : 1;
        for (size_t j = 0; j < members; ++j) {
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
            function->arity = (cpg_child_count(cpg_child_at(candidate,
                constructor ? 2 : 3)) + 1) / 2;
            function->method = owner;
            function->constructor = constructor;
            function->parameter_types = calloc(function->arity ? function->arity : 1,
                                                sizeof(*function->parameter_types));
            if (!function->parameter_types)
                return semantic_error(compiler, name, "parameter table allocation failed");
            const Node *parameters = cpg_child_at(candidate, constructor ? 2 : 3);
            for (size_t k = 0; k < function->arity; ++k) {
                const Node *parameter = cpg_child_at(parameters, k * 2);
                if (cpg_child_count(parameter) > 1 &&
                    resolve_type(compiler, cpg_child_at(parameter, 2),
                                 &function->parameter_types[k]) != CPG_CONTINUE)
                    return CPG_ERROR;
            }
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
    CpgVisit result = require_integer(compiler, cpg_child_at(node, 2));
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
    for (size_t i = 3; i + 1 < cpg_child_count(node); ++i) {
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
    size_t constructor = compiler->function_count;
    for (size_t i = 0; i < compiler->function_count; ++i)
        if (compiler->functions[i].constructor &&
            compiler->functions[i].method == compiler->value_type) {
            constructor = i;
            break;
        }
    size_t arity = (cpg_child_count(arguments) + 1) / 2;
    if (constructor == compiler->function_count) {
        if (arity)
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

static CpgVisit check_object_declaration(const Node *node, void *user) {
    Compiler *compiler = user;
    const Node *name = cpg_child_at(node, 1);
    CpgVisit result = check_class_name(compiler, cpg_child_at(node, 3));
    if (result != CPG_CONTINUE) return result;
    int type = find_class(compiler, cpg_child_at(node, 3));
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

static size_t find_member(const Compiler *compiler, int type, const Node *name) {
    const Class *class_info = &compiler->classes[type - 1];
    for (size_t i = 0; i < class_info->field_count; ++i)
        if (same_name(compiler, class_info->fields[i].name, name)) return i;
    return class_info->field_count;
}

static size_t find_method(const Compiler *compiler, int type, const Node *name) {
    for (size_t i = 0; i < compiler->function_count; ++i)
        if (!compiler->functions[i].constructor &&
            compiler->functions[i].method == type &&
            same_name(compiler, compiler->functions[i].name, name)) return i;
    return compiler->function_count;
}

static CpgVisit check_path(const Node *node, size_t count, Compiler *compiler) {
    CpgVisit result = check_name(cpg_child_at(node, 0), compiler);
    if (result != CPG_CONTINUE) return result;
    for (size_t i = 2; i < count; i += 2) {
        const Node *name = cpg_child_at(node, i);
        int type = compiler->value_type;
        if (!type)
            return semantic_error(compiler, cpg_child_at(node, i - 2),
                                  "member access requires object");
        size_t field = find_member(compiler, type, name);
        if (field == compiler->classes[type - 1].field_count)
            return semantic_error(compiler, name, "unknown field");
        compiler->value_type = compiler->classes[type - 1].fields[field].type;
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
    int type = compiler->value_type;
    result = cpg_dispatch(cpg_child_at(node, 2), compiler->visitor, user);
    if (result == CPG_CONTINUE && type != compiler->value_type)
        return semantic_error(compiler, cpg_child_at(node, 0), "field assignment type mismatch");
    return result;
}

static CpgVisit check_method_call(const Node *node, void *user) {
    Compiler *compiler = user;
    const Node *path = cpg_child_at(node, 0);
    size_t count = cpg_child_count(path);
    CpgVisit result = check_path(path, count - 2, compiler);
    if (result != CPG_CONTINUE) return result;
    if (!compiler->value_type)
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
    return require_integer(user, cpg_child_at(node, 1));
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

static CpgVisit emit_integer(const Node *node, void *user) {
    Compiler *compiler = user;
    const unsigned char *text = cpg_node_text(compiler->parser, node);
    size_t length = cpg_node_text_length(node);
    while (length > 1 && *text == '0') {
        ++text;
        --length;
    }
    fwrite(text, 1, length, stdout);
    fputs(".0 ", stdout);
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
    int object = !strcmp(cpg_node_kind(node), "object_declaration");
    int declaration = object || !strcmp(cpg_node_kind(node), "declaration");
    if (declaration && cpg_child_count(node) == (object ? 5u : 3u)) return CPG_CONTINUE;
    const Node *name = cpg_child_at(node, declaration ? 1 : 0);
    const Node *value = cpg_child_at(node, object ? 5 : declaration ? 3 : 2);
    emit_indent(compiler);
    CpgVisit result = emit_name(name, user);
    if (result != CPG_CONTINUE) return result;
    fputs("= ", stdout);
    result = cpg_dispatch(value, compiler->visitor, user);
    if (result != CPG_CONTINUE) return result;
    fputs(";\n", stdout);
    return ferror(stdout) ? CPG_ERROR : CPG_CONTINUE;
}

static CpgVisit emit_construction(const Node *node, void *user) {
    Compiler *compiler = user;
    compiler->value_type = find_class(compiler, cpg_child_at(node, 1));
    fprintf(stdout, "cpg_new%d(", compiler->value_type);
    CpgVisit result = cpg_dispatch(cpg_child_at(node, 3), compiler->visitor, user);
    if (result != CPG_CONTINUE) return result;
    fputs(") ", stdout);
    compiler->value_type = find_class(compiler, cpg_child_at(node, 1));
    return ferror(stdout) ? CPG_ERROR : CPG_CONTINUE;
}

static int path_type(Compiler *compiler, const Node *node, size_t count) {
    int type = compiler->symbols[find_symbol(compiler, cpg_child_at(node, 0))].type;
    for (size_t i = 2; i < count; i += 2) {
        size_t field = find_member(compiler, type, cpg_child_at(node, i));
        type = compiler->classes[type - 1].fields[field].type;
    }
    return type;
}

static CpgVisit emit_path(const Node *node, size_t count, Compiler *compiler) {
    if (count == 1) return emit_name(cpg_child_at(node, 0), compiler);
    int type = path_type(compiler, node, count - 2);
    size_t field = find_member(compiler, type, cpg_child_at(node, count - 1));
    fprintf(stdout, "((cpg_class%d *)cpg_require(", type);
    CpgVisit result = emit_path(node, count - 2, compiler);
    if (result != CPG_CONTINUE) return result;
    fprintf(stdout, "))->cpg_field%zu ", field);
    compiler->value_type = compiler->classes[type - 1].fields[field].type;
    return ferror(stdout) ? CPG_ERROR : CPG_CONTINUE;
}

static CpgVisit emit_member(const Node *node, void *user) {
    return emit_path(node, cpg_child_count(node), user);
}

static CpgVisit emit_member_assignment(const Node *node, void *user) {
    Compiler *compiler = user;
    emit_indent(compiler);
    CpgVisit result = emit_member(cpg_child_at(node, 0), user);
    if (result != CPG_CONTINUE) return result;
    fputs("= ", stdout);
    result = cpg_dispatch(cpg_child_at(node, 2), compiler->visitor, user);
    fputs(";\n", stdout);
    return result != CPG_CONTINUE || ferror(stdout) ? CPG_ERROR : CPG_CONTINUE;
}

static CpgVisit emit_method_call(const Node *node, void *user) {
    Compiler *compiler = user;
    const Node *path = cpg_child_at(node, 0);
    size_t count = cpg_child_count(path);
    int type = path_type(compiler, path, count - 2);
    fprintf(stdout, "cpg_f%zu(cpg_require(",
            find_method(compiler, type, cpg_child_at(path, count - 1)));
    CpgVisit result = emit_path(path, count - 2, compiler);
    if (result != CPG_CONTINUE) return result;
    fputc(')', stdout);
    const Node *arguments = cpg_child_at(node, 2);
    if (cpg_child_count(arguments)) fputs(", ", stdout);
    result = cpg_dispatch(arguments, compiler->visitor, user);
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
    fputs("if (printf(\"%.17g\\n\", (double)", stdout);
    CpgVisit result = cpg_dispatch(cpg_child_at(node, 1), compiler->visitor, user);
    if (result != CPG_CONTINUE) return result;
    fputs(") < 0) exit(EXIT_FAILURE);\n", stdout);
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
    size_t index = find_function(compiler, cpg_child_at(node, 0));
    if (index == compiler->function_count) {
        return semantic_error(compiler, node, "unresolved function during emission");
    }
    fprintf(stdout, "cpg_f%zu(", index);
    CpgVisit result = cpg_dispatch(cpg_child_at(node, 2), compiler->visitor, user);
    if (result != CPG_CONTINUE) return result;
    fputs(") ", stdout);
    return ferror(stdout) ? CPG_ERROR : CPG_CONTINUE;
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

static void emit_type(int type) {
    if (type) fprintf(stdout, "cpg_class%d *", type);
    else fputs("double", stdout);
}

static void emit_signature(const Function *function, size_t index, int definition) {
    fprintf(stdout, "%s cpg_f%zu(", function->constructor ? "void" : "double", index);
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
                    compiler->symbols[i].type ? "NULL" : "0.0");
        }
        fprintf(stdout, "    (void)cpg_v%zu;\n", i);
    }
}

static CpgVisit emit_program(const Node *root, void *user) {
    Compiler *compiler = user;
    fputs("#include <stdio.h>\n#include <stdlib.h>\n\n", stdout);
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
        for (size_t i = 0; i < compiler->class_count; ++i) {
            const Class *class_info = &compiler->classes[i];
            fprintf(stdout, "\nstruct cpg_class%zu {\n", i + 1);
            for (size_t j = 0; j < class_info->field_count; ++j) {
                fputs("    ", stdout);
                emit_type(class_info->fields[j].type);
                fprintf(stdout, " cpg_field%zu;\n", j);
            }
            if (!class_info->field_count) fputs("    unsigned char cpg_empty;\n", stdout);
            fputs("};\n", stdout);
        }
        for (size_t i = 0; i < compiler->function_count; ++i) {
            emit_signature(&compiler->functions[i], i, 0);
            fputs(";\n", stdout);
        }
        for (size_t i = 0; i < compiler->class_count; ++i) {
            const Function *constructor = NULL;
            size_t constructor_index = 0;
            for (size_t j = 0; j < compiler->function_count; ++j) {
                if (compiler->functions[j].constructor &&
                    compiler->functions[j].method == (int)i + 1) {
                    constructor = &compiler->functions[j];
                    constructor_index = j;
                    break;
                }
            }
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
            if (constructor) {
                fprintf(stdout, "    cpg_f%zu(object", constructor_index);
                for (size_t j = 0; j < constructor->arity; ++j)
                    fprintf(stdout, ", cpg_arg%zu", j);
                fputs(");\n", stdout);
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
        emit_signature(function, i, 1);
        fputs(" {\n", stdout);
        emit_slots(&local, function->arity + (function->method != 0));
        CpgVisit result = cpg_dispatch(cpg_child_at(function->node,
            function->constructor ? 4 : 5), local.visitor, &local);
        if (result != CPG_CONTINUE) return result;
        fputs("}\n\n", stdout);
    }
    fputs("int main(void) {\n", stdout);
    if (compiler->class_count)
        fputs("    if (atexit(cpg_cleanup)) {\n"
              "        fputs(\"object cleanup registration failed\\n\", stderr);\n"
              "        return EXIT_FAILURE;\n"
              "    }\n", stdout);
    emit_slots(compiler, 0);
    for (size_t i = 0; i < cpg_child_count(root); ++i) {
        const Node *node = cpg_child_at(root, i);
        if (!strcmp(cpg_node_kind(node), "function") ||
            !strcmp(cpg_node_kind(node), "class_decl")) continue;
        CpgVisit result = cpg_dispatch(node, compiler->visitor, user);
        if (result != CPG_CONTINUE) return result;
    }
    fputs("    return fflush(stdout) ? 1 : 0;\n}\n", stdout);
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
        validator.on_rule_object_declaration = check_object_declaration;
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
        validator.on_rule_returning = check_return;
        validator.on_token_IDENT = check_name;
        validator.on_token_INTEGER = check_integer;
        validator.on_node = dispatch_children;
        compiler.visitor = &validator;
        if (collect_functions(root, &compiler) != CPG_CONTINUE ||
            cpg_dispatch(root, &validator, &compiler) != CPG_CONTINUE) {
            diagnostic(&parser, compiler.error ? compiler.error->offset : 0,
                       compiler.problem ? compiler.problem : "validation failed", compiler.error);
        } else {
            CpgVisitor emitter = {0};
            emitter.on_rule_declaration = emit_store;
            emitter.on_rule_object_declaration = emit_store;
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
            emitter.on_rule_arguments = dispatch_children;
            emitter.on_rule_returning = emit_return;
            emitter.on_rule_expression = emit_group;
            emitter.on_rule_equality = emit_comparison;
            emitter.on_rule_comparison = emit_comparison;
            emitter.on_rule_sum = emit_group;
            emitter.on_rule_product = emit_group;
            emitter.on_rule_unary = emit_group;
            emitter.on_rule_primary = emit_group;
            emitter.on_rule_program = emit_program;
            emitter.on_rule_statement = dispatch_children;
            emitter.on_token_IDENT = emit_name;
            emitter.on_token_INTEGER = emit_integer;
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

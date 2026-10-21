#define CPARSEGEN_NO_MAIN
#include "parser.c"

typedef struct {
    const Node *name;
    int initialized;
} Symbol;

typedef struct {
    const Node *node;
    const Node *name;
    size_t arity;
    Symbol *symbols;
    size_t count;
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

static size_t find_function(const Compiler *compiler, const Node *name) {
    for (size_t i = 0; i < compiler->function_count; ++i) {
        if (same_name(compiler, compiler->functions[i].name, name)) return i;
    }
    return compiler->function_count;
}

static size_t find_symbol(const Compiler *compiler, const Node *name) {
    for (size_t i = 0; i < compiler->count; ++i) {
        const Node *symbol = compiler->symbols[i].name;
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
    return CPG_CONTINUE;
}

static CpgVisit check_integer(const Node *node, void *user) {
    Compiler *compiler = user;
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
    compiler->symbols[compiler->count++] = (Symbol){name, initialized};
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
    return add_symbol(compiler, name, initialized);
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
    return cpg_dispatch(arguments, compiler->visitor, user);
}

static CpgVisit check_return(const Node *node, void *user) {
    Compiler *compiler = user;
    if (!compiler->in_function) {
        return semantic_error(compiler, cpg_child_at(node, 0), "return outside function");
    }
    if (cpg_child_count(node) != 3) {
        return semantic_error(compiler, cpg_child_at(node, 0), "return requires a value");
    }
    CpgVisit result = cpg_dispatch(cpg_child_at(node, 1), compiler->visitor, user);
    compiler->falls_through = 0;
    return result;
}

static CpgVisit check_function(const Node *node, void *user) {
    Compiler *compiler = user;
    size_t index = find_function(compiler, cpg_child_at(node, 1));
    Function *function = &compiler->functions[index];
    Compiler local = *compiler;
    local.symbols = NULL;
    local.count = local.capacity = 0;
    local.in_function = local.falls_through = 1;
    CpgVisit result = CPG_CONTINUE;
    const Node *parameters = cpg_child_at(node, 3);
    for (size_t i = 0; i < cpg_child_count(parameters) && result == CPG_CONTINUE; i += 2) {
        result = add_symbol(&local, cpg_child_at(parameters, i), 1);
    }
    if (result == CPG_CONTINUE) {
        result = cpg_dispatch(cpg_child_at(node, 5), local.visitor, &local);
    }
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
        if (find_function(compiler, name) != compiler->function_count) {
            return semantic_error(compiler, name, "duplicate function");
        }
        Function *function = &compiler->functions[compiler->function_count++];
        function->node = node;
        function->name = name;
        function->arity = (cpg_child_count(cpg_child_at(node, 3)) + 1) / 2;
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
    CpgVisit result = cpg_dispatch(cpg_child_at(node, 2), compiler->visitor, user);
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

static CpgVisit emit_name(const Node *node, void *user) {
    Compiler *compiler = user;
    size_t index = find_symbol(compiler, node);
    if (index == compiler->count) return semantic_error(compiler, node, "unresolved name during emission");
    /* Numeric slots cannot collide with C keywords, libc names, or user names. */
    fprintf(stdout, "cpg_v%zu ", index);
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
    int declaration = !strcmp(cpg_node_kind(node), "declaration");
    if (declaration && cpg_child_count(node) == 3) return CPG_CONTINUE;
    const Node *name = cpg_child_at(node, declaration ? 1 : 0);
    const Node *value = cpg_child_at(node, declaration ? 3 : 2);
    emit_indent(compiler);
    CpgVisit result = emit_name(name, user);
    if (result != CPG_CONTINUE) return result;
    fputs("= ", stdout);
    result = cpg_dispatch(value, compiler->visitor, user);
    if (result != CPG_CONTINUE) return result;
    fputs(";\n", stdout);
    return ferror(stdout) ? CPG_ERROR : CPG_CONTINUE;
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

static void emit_signature(const Function *function, size_t index, int definition) {
    fprintf(stdout, "double cpg_f%zu(", index);
    if (!function->arity) fputs("void", stdout);
    for (size_t i = 0; i < function->arity; ++i) {
        if (i) fputs(", ", stdout);
        fputs("double", stdout);
        if (definition) fprintf(stdout, " cpg_v%zu", i);
    }
    fputc(')', stdout);
}

static void emit_slots(const Compiler *compiler, size_t parameters) {
    /* Hoist storage, not initializers; blocks share their enclosing scope. */
    for (size_t i = 0; i < compiler->count; ++i) {
        if (i >= parameters) fprintf(stdout, "    double cpg_v%zu = 0.0;\n", i);
        fprintf(stdout, "    (void)cpg_v%zu;\n", i);
    }
}

static CpgVisit emit_program(const Node *root, void *user) {
    Compiler *compiler = user;
    fputs("#include <stdio.h>\n#include <stdlib.h>\n\n", stdout);
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
        emit_signature(function, i, 1);
        fputs(" {\n", stdout);
        emit_slots(&local, function->arity);
        CpgVisit result = cpg_dispatch(cpg_child_at(function->node, 5), local.visitor, &local);
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
        for (size_t i = 0; i < compiler.function_count; ++i) free(compiler.functions[i].symbols);
        free(compiler.functions);
    }
    free(compiler.symbols);
    cpg_destroy(&parser);
    free(source);
    return status;
}

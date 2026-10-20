#define CPARSEGEN_NO_MAIN
#include "parser.c"

typedef struct {
    const Context *parser;
    const CpgVisitor *emitter;
    const char *problem;
    size_t error_offset;
} Compiler;

static CpgVisit check_integer(const Node *node, void *user) {
    Compiler *compiler = user;
    if (cpg_node_text_length(node) > 9) {
        compiler->problem = "integer literal exceeds nine digits";
        compiler->error_offset = node->offset;
        return CPG_ERROR;
    }
    return CPG_CONTINUE;
}

static CpgVisit emit_integer(const Node *node, void *user) {
    Compiler *compiler = user;
    const unsigned char *text = cpg_node_text(compiler->parser, node);
    size_t length = cpg_node_text_length(node);
    /* Decimal floating constants avoid C's leading-zero octal interpretation. */
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
    fwrite(cpg_node_text(compiler->parser, node), 1,
           cpg_node_text_length(node), stdout);
    fputc(' ', stdout);
    return ferror(stdout) ? CPG_ERROR : CPG_CONTINUE;
}

static CpgVisit emit_group(const Node *node, void *user) {
    Compiler *compiler = user;
    if (fputc('(', stdout) == EOF) return CPG_ERROR;
    for (size_t i = 0; i < cpg_child_count(node); ++i) {
        CpgVisit result = cpg_dispatch(cpg_child_at(node, i), compiler->emitter, user);
        if (result != CPG_CONTINUE) return result;
    }
    return fputs(") ", stdout) == EOF ? CPG_ERROR : CPG_CONTINUE;
}

int main(int argc, char **argv) {
    if (argc != 2) {
        fputs("usage: expression-compiler EXPRESSION\n", stderr);
        return 2;
    }
    Context parser;
    cpg_init(&parser, (const unsigned char *)argv[1], strlen(argv[1]), "<argument>");
    const Node *root = cpg_parse(&parser, 1);
    if (!root) {
        fprintf(stderr, "%s:byte %zu: %s\n",
                parser.path, parser.error_offset, parser.problem);
        cpg_destroy(&parser);
        return 1;
    }

    CpgVisitor emitter = {0};
    emitter.on_rule_expression = emit_group;
    emitter.on_rule_product = emit_group;
    emitter.on_rule_unary = emit_group;
    emitter.on_rule_primary = emit_group;
    emitter.on_token_INTEGER = emit_integer;
    emitter.on_node = emit_literal;
    Compiler compiler = {&parser, &emitter, NULL, 0};
    CpgVisitor validator = {0};
    validator.enter_token_INTEGER = check_integer;
    /* Validate first so rejected input never produces a partial C program. */
    if (cpg_walk(root, &validator, &compiler) != CPG_CONTINUE) {
        fprintf(stderr, "%s:byte %zu: %s\n",
                parser.path, compiler.error_offset,
                compiler.problem ? compiler.problem : "validation failed");
        cpg_destroy(&parser);
        return 1;
    }

    fputs("#include <stdio.h>\n\nint main(void) {\n"
          "    double result = ", stdout);
    CpgVisit result = cpg_dispatch(root, &emitter, &compiler);
    if (result == CPG_CONTINUE) {
        fputs(";\n    if (printf(\"%.17g\\n\", result) < 0 || fflush(stdout)) return 1;\n"
              "    return 0;\n}\n", stdout);
    }
    cpg_destroy(&parser);
    int output_failed = fflush(stdout) != 0 || ferror(stdout);
    if (result != CPG_CONTINUE || output_failed) {
        fputs("expression-compiler: C source output failed\n", stderr);
        return 1;
    }
    return 0;
}

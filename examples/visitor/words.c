#define CPARSEGEN_NO_MAIN
#include "parser.c"

typedef struct {
    const Context *parser;
    size_t names;
    int first;
    const char *problem;
    size_t error_offset;
} Names;

static CpgVisit count_name(const Node *node, void *user) {
    Names *names = user;
    const unsigned char *text = cpg_node_text(names->parser, node);
    size_t length = cpg_node_text_length(node);
    if (length == 9 && !memcmp(text, "forbidden", length)) {
        names->problem = "identifier 'forbidden' is not allowed";
        names->error_offset = node->offset;
        return CPG_ERROR;
    }
    ++names->names;
    return names->first ? CPG_STOP : CPG_CONTINUE;
}

static CpgVisit dispatch_words(const Node *node, void *user) {
    CpgVisitor visitor = {0};
    visitor.on_token_IDENT = count_name;
    for (size_t i = 0; i < cpg_child_count(node); ++i) {
        CpgVisit result = cpg_dispatch(cpg_child_at(node, i), &visitor, user);
        if (result != CPG_CONTINUE) return result;
    }
    return CPG_CONTINUE;
}

int main(int argc, char **argv) {
    int first = argc == 3 && !strcmp(argv[1], "--first");
    int manual = argc == 3 && !strcmp(argv[1], "--dispatch");
    if (argc != 2 && !first && !manual) {
        fputs("usage: words-visitor [--first | --dispatch] TEXT\n", stderr);
        return 2;
    }
    const char *input = argv[(first || manual) ? 2 : 1];
    Context parser;
    cpg_init(&parser, (const unsigned char *)input, strlen(input), "<argument>");
    const Node *root = cpg_parse(&parser, 1);
    if (!root) {
        fprintf(stderr, "%s:byte %zu: %s\n",
                parser.path, parser.error_offset, parser.problem);
        cpg_destroy(&parser);
        return 1;
    }
    Names names = {&parser, 0, first, NULL, 0};
    CpgVisitor visitor = {0};
    visitor.enter_token_IDENT = count_name;
    visitor.on_rule_words = dispatch_words;
    CpgVisit result = manual ? cpg_dispatch(root, &visitor, &names)
                             : cpg_walk(root, &visitor, &names);
    int success = result == CPG_CONTINUE || (first && result == CPG_STOP);
    if (success) {
        printf("names=%zu%s\n", names.names, result == CPG_STOP ? " (stopped)" : "");
    } else {
        fprintf(stderr, "%s:byte %zu: %s\n", parser.path, names.error_offset,
                names.problem ? names.problem : "visitor failed");
    }
    cpg_destroy(&parser);
    if (fflush(stdout) || ferror(stdout)) {
        fputs("words-visitor: output write failed\n", stderr);
        return 1;
    }
    return success ? 0 : 1;
}

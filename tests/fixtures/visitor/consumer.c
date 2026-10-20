#define CPARSEGEN_NO_MAIN
#include "parser.c"
#include <assert.h>

typedef struct {
    char trace[4096];
    const char *mode;
    size_t count;
} State;

static void event(State *state, const char *phase, const Node *node) {
    size_t used = strlen(state->trace);
    int length = snprintf(state->trace + used, sizeof(state->trace) - used,
                          "%s:%s ", phase, cpg_node_kind(node));
    assert(length > 0 && (size_t)length < sizeof(state->trace) - used);
}

static CpgVisit enter(const Node *node, void *user) {
    State *state = user;
    event(state, "e", node);
    return CPG_CONTINUE;
}

static CpgVisit leave(const Node *node, void *user) {
    State *state = user;
    event(state, "l", node);
    return CPG_CONTINUE;
}

static CpgVisit pair(const Node *node, void *user) {
    State *state = user;
    event(state, "p", node);
    if (!strcmp(state->mode, "skip")) return CPG_SKIP;
    if (!strcmp(state->mode, "invalid-enter")) return (CpgVisit)99;
    return CPG_CONTINUE;
}

static CpgVisit leave_pair(const Node *node, void *user) {
    State *state = user;
    event(state, "q", node);
    if (!strcmp(state->mode, "leave-stop")) return CPG_STOP;
    if (!strcmp(state->mode, "leave-error")) return CPG_ERROR;
    if (!strcmp(state->mode, "leave-skip")) return CPG_SKIP;
    if (!strcmp(state->mode, "invalid-leave")) return (CpgVisit)99;
    return CPG_CONTINUE;
}

static CpgVisit number(const Node *node, void *user) {
    State *state = user;
    event(state, "n", node);
    ++state->count;
    if (!strcmp(state->mode, "stop")) return CPG_STOP;
    if (!strcmp(state->mode, "error")) return CPG_ERROR;
    return CPG_CONTINUE;
}

static CpgVisit literal(const Node *node, void *user) {
    event(user, "t", node);
    return CPG_CONTINUE;
}

static CpgVisit on_node(const Node *node, void *user) {
    event(user, "g", node);
    return CPG_CONTINUE;
}

static CpgVisit on_entry(const Node *node, void *user) {
    State *state = user;
    event(state, "d", node);
    if (!strcmp(state->mode, "dispatch-stop")) return CPG_STOP;
    if (!strcmp(state->mode, "dispatch-error")) return CPG_ERROR;
    if (!strcmp(state->mode, "dispatch-skip")) return CPG_SKIP;
    if (!strcmp(state->mode, "dispatch-invalid")) return (CpgVisit)99;
    return CPG_CONTINUE;
}

int main(int argc, char **argv) {
    assert(argc == 2);
    Context parser, other;
    cpg_init(&parser, (const unsigned char *)"12 + 34", 7, "one");
    cpg_init(&other, (const unsigned char *)"56+78", 5, "two");
    const Node *root = cpg_parse(&parser, 1);
    const Node *second = cpg_parse(&other, 1);
    assert(root && second && !parser.problem && !other.problem);
    const Node *first = cpg_child_at(cpg_child_at(root, 0), 0);
    assert(cpg_node_text_length(first) == 2);
    assert(!memcmp(cpg_node_text(&parser, first), "12", 2));
    assert(cpg_child_count(root) == 2 && !cpg_child_at(root, 2));
    assert(cpg_child_count(cpg_child_at(root, 1)) == 0);
    State state = {{0}, argv[1], 0}, independent = {{0}, "walk", 0};
    CpgVisitor visitor = {0};
    visitor.enter = enter;
    visitor.leave = leave;
    visitor.enter_rule_pair = pair;
    visitor.leave_rule_pair = leave_pair;
    visitor.enter_token_NUMBER = number;
    visitor.enter_literal_0 = literal;
    visitor.on_node = on_node;
    visitor.on_rule_entry = on_entry;
    CpgVisit result;
    if (!strncmp(argv[1], "dispatch", 8)) {
        result = cpg_dispatch(root, &visitor, &state);
        assert(cpg_dispatch(first, &visitor, &independent) == CPG_CONTINUE);
        assert(!strcmp(independent.trace, "g:NUMBER "));
    } else if (!strcmp(argv[1], "unknown")) {
        Node custom = {"custom", 0, 0, 0, NULL};
        result = cpg_walk(&custom, &visitor, &state);
    } else if (!strcmp(argv[1], "null")) {
        result = cpg_walk(NULL, &visitor, &state);
        assert(cpg_dispatch(root, NULL, &state) == CPG_ERROR);
    } else {
        result = cpg_walk(root, &visitor, &state);
    }
    assert(cpg_walk(second, &visitor, &independent) == CPG_CONTINUE);
    assert(independent.count == 2);
    printf("%d|%zu|%s\n", result, state.count, state.trace);
    state.mode = "walk";
    state.count = 0;
    state.trace[0] = '\0';
    assert(cpg_walk(root, &visitor, &state) == CPG_CONTINUE);
    assert(state.count == 2);
    cpg_destroy(&other);
    assert(!memcmp(cpg_node_text(&parser, first), "12", 2));
    cpg_destroy(&parser);
    cpg_destroy(&parser);
    return 0;
}

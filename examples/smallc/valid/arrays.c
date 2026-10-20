char greeting[] = "hello\n";
int digits[3] = {1, 2, 3};

char first() {
    return greeting[0];
}

int main() {
    /* Strings preserve their spelling in the AST, including // and escapes. */
    char markers[] = "/* not a comment */ //";
    char newline = '\n', quote = '\'';
    int sum = digits[0] + digits[1] + digits[2];
    greeting[0] = 'H';
    return sum + first() - 'H';
}

#define CPARSEGEN_NO_MAIN
#include "parser.c"

int main(void) {
    const unsigned char input[] = "alpha beta gamma";
    int count = inserted_word_count(input, sizeof(input) - 1);
    if (count < 0) {
        fputs("word parsing or visitor failed\n", stderr);
        return 1;
    }
    printf("words=%d\n", count);
    return 0;
}

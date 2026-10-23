int twice(int value);

int seed() { return 3; }
int bias = seed();
int numbers[] = {1, 2, 3,};
char greeting[] = "hello\n";
int calls;

int factorial(int n) {
    calls++;
    if (n <= 1) return 1;
    return n * factorial(n - 1);
}

char next(char letter) {
    letter++;
    return letter;
}

int main() {
    int local[4] = {bias, twice(2), factorial(3), 7};
    char letters[] = {'A', 'B', 'C'};
    char escapes[] = "\t\r\n\\\"\'\0";
    local[0] = local[1] + numbers[2];
    local[1] += 2;
    ++local[2];
    local[3]--;
    greeting[0] = 'H';
    letters[1] = next('B');
    if (greeting[0] != 'H' || letters[1] != 'C') return 1;
    if (escapes[0] != '\t' || escapes[6] != '\0') return 2;
    if (local[0] + local[1] + local[2] + local[3] != 26) return 3;
    if (calls != 3) return 4;
    return twice(factorial(4));
}

int twice(int value) { return value * 2; }

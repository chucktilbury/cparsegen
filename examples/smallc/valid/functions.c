// A prototype makes a later definition available to a single-pass compiler.
int twice(int value);

int factorial(int n) {
    if (n <= 1)
        return 1;
    return n * factorial(n - 1);
}

int main() {
    int answer = twice(factorial(4));
    return answer;
}

int twice(int value) {
    return value * 2;
}

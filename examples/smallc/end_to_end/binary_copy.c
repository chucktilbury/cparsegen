int main() {
    char buffer[64];
    char status[8];
    int input = open("input.bin", "r");
    int output = open("copy.bin", "w");
    int total = 0;
    int count = read(input, 64, buffer);
    while (count > 0) {
        int pending = count;
        while (pending > 0) {
            int written = write(output, pending, buffer);
            /* Each write starts at zero: shift the unwritten tail forward. */
            for (int i = 0; i < pending - written; i++) {
                buffer[i] = buffer[i + written];
            }
            pending -= written;
        }
        total += count;
        count = read(input, 64, buffer);
    }
    close(input);
    close(output);

    int log = open("copy.log", "w");
    write(log, 1, "O");
    close(log);
    log = open("copy.log", "a");
    write(log, 1, "K");
    write(log, 1, "\n");
    close(log);
    log = open("copy.log", "r");
    int logged = read(log, 8, status);
    int eof = read(log, 8, status);
    int empty = read(log, 0, status);
    close(log);
    if (logged != 3 || eof != 0 || empty != 0) return 1;
    print(status);
    return total;
}

// Zero means every arithmetic and control-flow check succeeded.
int main() {
    int value = 7, other = 0;
    value += 5;
    value -= 2;
    value *= 3;
    value /= 4;
    value %= 5;
    if (value != 2) return 1;
    other = value = 4;
    if (other != 4 || value != 4) return 2;
    if ((+value + 2) * 3 - 5 != 13) return 3;
    if (-7 / 2 != -3 || -7 % 2 != -1) return 4;
    if (!(value == 4 && value >= 4 && value <= 4)) return 5;
    if (value < 4 || value > 4) return 6;

    int effects = 0;
    if (0 && ++effects) return 7;
    if (1 || ++effects) {
        if (effects != 0) return 8;
    }
    else return 9;

    int total = 0;
    for (int i = 0; i < 8; i++) {
        if (i == 2) continue;
        if (i == 6) break;
        total += i;
    }
    if (total != 13) return 10;
    int count = 3;
    while (count > 0) {
        --count;
        total++;
    }
    if (total != 16) return 11;
    for (;;) {
        total--;
        break;
    }
    for (count = 0; count < 2;) ++count;
    if (count != 2 || total != 15) return 12;

    int shadow = 1;
    {
        int shadow = 10;
        if (shadow != 10) return 13;
        ;
    }
    if (shadow != 1) return 14;
    if (1) {
        if (0) return 15;
        else value = 9;
    }
    if (value != 9) return 16;
    return 0;
}

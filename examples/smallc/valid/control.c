int main() {
    int total = 0;
    for (int i = 0; i < 10; i++) {
        if (i == 3)
            continue;
        total += i;
    }
    int remaining = 3;
    while (remaining > 0) {
        total -= 1;
        --remaining;
    }
    switch (total) {
        case 39:
        case 40:
            total = total + 2;
            break;
        default:
            goto failed;
    }
    if (total != 0 && remaining == 0)
        goto done;
failed:
    return 1;
done:
    return 0;
}

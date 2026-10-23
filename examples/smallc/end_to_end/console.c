char heading[] = "SmallC -> CVM assembly -> binary\n";

int main() {
    char word[] = {'O', 'K', '\n'};
    char stopped[8] = "yes\0no";
    print(heading);
    print(word);
    print(stopped);
    print("\n");
    return 0;
}

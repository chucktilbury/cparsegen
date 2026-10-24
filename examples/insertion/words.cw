include "parser.cw"

start {
    InsertedWords words()
    int64 count = words.count("alpha beta gamma")
    if (count < 0) {
        Sys.StandardIO().writeErrorLine("word parsing or visitor failed")
        Sys.Process().exit(1)
    }
    print(format("words={}\n", count))
}

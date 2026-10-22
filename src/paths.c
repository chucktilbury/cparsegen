#define _POSIX_C_SOURCE 200809L
#include <cwhip/RuntimeGc.h>

#include <errno.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

static char *path_string(void *value) {
    const char *bytes;
    uint64_t length;
    cwhip_string_bytes(value, &bytes, &length);
    if (length == 0 || length >= SIZE_MAX || memchr(bytes, '\0', (size_t)length)) {
        return NULL;
    }
    char *path = malloc((size_t)length + 1);
    if (path) {
        memcpy(path, bytes, (size_t)length);
        path[length] = '\0';
    }
    return path;
}

static int path_stat(const char *path, struct stat *info) {
    if (stat(path, info) == 0) { return 1; }
    if (errno != ENOENT) { return -1; }
    /* Reject dangling symlinks rather than treating them as new output files. */
    if (lstat(path, info) == 0 || errno != ENOENT) { return -1; }
    return 0;
}

/* The SDK resolves symlinks, but does not expose device/inode identity. */
int64_t cparsegen_same_file(void *self, void *first, void *second) {
    (void)self;
    char *left = path_string(first);
    char *right = path_string(second);
    int64_t result = -1;
    if (left && right) {
        struct stat a, b;
        int a_status = path_stat(left, &a);
        int b_status = path_stat(right, &b);
        if (a_status >= 0 && b_status >= 0) {
            result = a_status && b_status && a.st_dev == b.st_dev && a.st_ino == b.st_ino;
        }
    }
    free(left);
    free(right);
    return result;
}

// memtool: tiny /proc/<pid>/mem scanner/patcher for app-debugging on Android (run via run-as).
//   memtool <pid> find  <hex8 qword>          -> addresses (8-aligned, rw regions) holding that qword
//   memtool <pid> read  <addr> <n>            -> hex dump
//   memtool <pid> write <addr> <hexbytes>     -> write bytes
//   memtool <pid> refs  <lo> <hi>             -> 8-aligned qwords in [lo,hi] (pointer search)
#define _FILE_OFFSET_BITS 64
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/uio.h>
static int memfd;
static void each_region(void (*cb)(uint64_t, uint64_t, const char *), int pid) {
    char p[64], line[512]; snprintf(p, sizeof p, "/proc/%d/maps", pid);
    FILE *f = fopen(p, "r"); if (!f) { perror("maps"); exit(1); }
    while (fgets(line, sizeof line, f)) {
        unsigned long long a, b; char perm[8];
        if (sscanf(line, "%llx-%llx %7s", &a, &b, perm) != 3) continue;
        if (perm[0] != 'r' || perm[1] != 'w') continue;
        cb(a, b, line);
    }
    fclose(f);
}
static uint64_t lo, hi; static int mode;
static void scan(uint64_t a, uint64_t b, const char *line) {
    static uint8_t buf[1 << 20];
    for (uint64_t s = a; s < b; s += sizeof buf) {
        size_t n = (b - s) < sizeof buf ? (b - s) : sizeof buf;
        ssize_t r = pread(memfd, buf, n, (off_t)s);
        if (r <= 0) break;
        for (ssize_t i = 0; i + 8 <= r; i += 8) {
            uint64_t q; memcpy(&q, buf + i, 8);
            if (q >= lo && q <= hi) printf("%llx %llx\n", (unsigned long long)(s + i), (unsigned long long)q);
        }
    }
}
int main(int c, char **v) {
    if (c < 4) { fprintf(stderr, "usage: memtool pid find|read|write|refs ...\n"); return 2; }
    int pid = atoi(v[1]); char p[64]; snprintf(p, sizeof p, "/proc/%d/mem", pid);
    memfd = open(p, strcmp(v[2], "write") ? O_RDONLY : O_RDWR); if (memfd < 0) { perror("mem"); return 1; }
    if (!strcmp(v[2], "find")) { lo = hi = strtoull(v[3], 0, 16); each_region(scan, pid); }
    else if (!strcmp(v[2], "refs")) { lo = strtoull(v[3], 0, 16); hi = strtoull(v[4], 0, 16); each_region(scan, pid); }
    else if (!strcmp(v[2], "read")) {
        uint64_t a = strtoull(v[3], 0, 16); int n = atoi(v[4]); uint8_t b[4096];
        if (n > 4096) n = 4096;
        ssize_t r = pread(memfd, b, n, (off_t)a);
        for (ssize_t i = 0; i < r; i++) printf("%02x%s", b[i], (i % 16 == 15) ? "\n" : "");
        if (r % 16) printf("\n");
    } else if (!strcmp(v[2], "write")) {
        uint64_t a = strtoull(v[3], 0, 16); const char *h = v[4]; uint8_t b[256]; int n = 0;
        while (h[0] && h[1] && n < 256) { unsigned x; sscanf(h, "%2x", &x); b[n++] = x; h += 2; }
        printf("wrote %zd\n", pwrite(memfd, b, n, (off_t)a));
    }
    return 0;
}

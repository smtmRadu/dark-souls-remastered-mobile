/* lock.c (included by dinput8.c): tap-to-lock. The app picks an enemy on screen and writes
   dsr_lock.txt = "<seq> lock <lockpoint hex> <handle hex>" or "<seq> unlock" (temp file + rename).
   lock_poll() (agent thread, 50 ms) reads it into a request; lock_apply() runs the request on the game's main
   thread (between two LockTgtMan updates): move the "target" flag 0x20 to the picked candidate and request the
   lock, the way the game's stick-flick switch does (0x14040c2c0). Details: docs/LOCKON.md. */

#define P_LOCKTGT 0x141c7a138ULL

static volatile LONG lock_seq, lock_done;
static uint64_t lock_lp;
static uint32_t lock_handle;
static int lock_mode;   /* 1 lock, 0 unlock */

static void lock_poll(void) {
    FILE *f = fopen("dsr_lock.txt", "r");
    if (!f) return;
    char cmd[16] = {0};
    unsigned long long lp = 0;
    unsigned h = 0;
    long seq = 0;
    int n = fscanf(f, "%ld %15s %llx %x", &seq, cmd, &lp, &h);
    fclose(f);
    DeleteFileA("dsr_lock.txt");
    if (n >= 2 && !strcmp(cmd, "unlock")) lock_mode = 0;
    else if (n == 4 && !strcmp(cmd, "lock")) { lock_mode = 1; lock_lp = lp; lock_handle = h; }
    else { logmsg("lock: bad request (%d fields)", n); return; }
    logmsg("lock: request %ld %s %llx %x", seq, cmd, lp, h);
    InterlockedIncrement(&lock_seq);
}

/* Main thread only: the candidate list and its flags change only there. */
static void lock_apply(void) {
    static int logged;
    if (!logged++) logmsg("lock: apply runs on thread %lu (main %lu)", GetCurrentThreadId(), main_tid);
    LONG s = lock_seq;
    if (s == lock_done) return;
    lock_done = s;
    uint8_t *lt = *(uint8_t * volatile *)P_LOCKTGT;
    if (!lt) return;
    if (!lt[0x156b]) { logmsg("lock: lock-on disabled now"); return; }
    if (!lock_mode) { lt[0x1431] = 0; logmsg("lock: unlock"); return; }
    uint8_t *pick = NULL;
    int n = 0;
    for (uint8_t *e = *(uint8_t **)(lt + 0x10); e && n < 64; e = *(uint8_t **)(e + 0x30), n++) {
        uint8_t *lp = *(uint8_t **)(e + 0x38);
        if (lp && (uint64_t)lp == lock_lp && *(uint32_t *)(lp + 0x14) == lock_handle) pick = e;
    }
    if (!pick || ((pick[0x40] & 0x50) != 0x10 && !(pick[0x40] & 0x20))) {
        logmsg("lock: %llx gone or not lockable", (unsigned long long)lock_lp);
        return;
    }
    n = 0;
    for (uint8_t *e = *(uint8_t **)(lt + 0x10); e && n < 64; e = *(uint8_t **)(e + 0x30), n++) e[0x40] &= (uint8_t)~0x20;
    pick[0x40] |= 0x20;
    *(float *)(lt + 0x1440) = 0.5f;   /* the stick switch's cooldown */
    lt[0x1431] = 1;
    logmsg("lock: locked %llx (handle %x)", (unsigned long long)lock_lp, lock_handle);
}

/* title.c (included by dinput8.c): one-row main menu (tools/patch_menu.py lays the title list out as 5 slots).
   The title list is rebuilt each frame from a static table of 10 entries {text id, action, ?} at 0x141a32250
   (FrpgMenuDlgTitle, list builder 0x1406940c0). Action 5 = "Log In" (text 0x61f9a) shows whenever the player is
   not signed in, which makes 6 entries: the game then scrolls a 4-entry window. Actions 7 and 8 are always
   filtered out, so turning Log In into action 7 leaves 5 entries and the game's no-scroll mode (entry i in slot i).
   The table is in .data (writable). Flag file dsr_stocktitle = keep it. */

#define P_TITLE_TABLE 0x141a32250ULL

static void patch_title_list(void) {
    static int done;
    if (done) return;
    done = 1;
    if (GetFileAttributesA("dsr_stocktitle") != INVALID_FILE_ATTRIBUTES) { logmsg("title: stock list kept (flag)"); return; }
    /* Logo higher: the title logos are full-screen 1920x1080 images drawn centred at the .rdata constant {960, 540}
       (0x1412f6150), used only by the two title draw functions 0x14025bcf0 / 0x14025c2a0. y 540 -> 450 = 60 units
       of the 720 menu space up, clear of the one-row menu. 2026-10-15: 400 (user: higher; the menu row is now 72 high). */
    float *logo_y = (float *)0x1412f6154ULL;
    DWORD old;
    if (*logo_y == 540.0f && VirtualProtect(logo_y, 4, PAGE_READWRITE, &old)) {
        *logo_y = 400.0f;
        VirtualProtect(logo_y, 4, old, &old);
        logmsg("title: logo y 540 -> 400");
    }
    uint32_t *e = (uint32_t *)P_TITLE_TABLE;
    for (int i = 0; i < 10; i++, e += 3) {
        if (e[0] == 0x61f9a && e[1] == 5) { e[1] = 7; logmsg("title: Log In entry %d hidden", i); return; }
    }
    logmsg("title: Log In entry not found (table changed?)");
}

/* "PRESS ANY BUTTON" on the title screen -> "TOUCH TO START". The text comes from the loaded message files
   (FMG Menu_others_ 130008 / System_message_win32_ 101000, UTF-16, two copies on the heap). The agent thread scans
   the writable memory once the files are loaded and overwrites the strings in place (shorter text + terminator).
   Retries every 2 s for 2 min (the files load a few seconds after start). Flag file dsr_stocktitle = keep it. */
static const WCHAR title_from[] = L"PRESS ANY BUTTON";
static const WCHAR title_to[] = L"TOUCH TO START";

static int replace_title_text(void) {
    /* ReadProcessMemory on our own process: a region freed mid-scan fails the read instead of crashing */
    static uint8_t buf[65536 + 64];
    int n = 0;
    HANDLE self = GetCurrentProcess();
    MEMORY_BASIC_INFORMATION mi;
    for (uint8_t *p = (uint8_t *)0x10000; (uint64_t)p < 0x7ff000000000ULL; p = (uint8_t *)mi.BaseAddress + mi.RegionSize) {
        if (!VirtualQuery(p, &mi, sizeof mi)) break;
        if (mi.State != MEM_COMMIT || mi.Protect != PAGE_READWRITE) continue;
        if ((uint64_t)mi.BaseAddress >= 0x140000000ULL && (uint64_t)mi.BaseAddress < 0x142000000ULL) continue;   /* image */
        uint8_t *base = mi.BaseAddress, *end = base + mi.RegionSize;
        for (uint8_t *c = base; c < end; c += 65536) {
            SIZE_T want = (SIZE_T)(end - c) < 65536 + sizeof title_from ? (SIZE_T)(end - c) : 65536 + sizeof title_from;
            SIZE_T got = 0;
            if (!ReadProcessMemory(self, c, buf, want, &got) || got < sizeof title_from) continue;
            for (SIZE_T i = 0; i + sizeof title_from <= got && i < 65536; i += 2) {
                if (buf[i] != 'P' || buf[i + 12] != 'A' || memcmp(buf + i, title_from, sizeof title_from)) continue;
                if (WriteProcessMemory(self, c + i, title_to, sizeof title_to, NULL)) n++;
            }
        }
    }
    return n;
}

static void patch_title_text(int tick) {   /* agent thread, called every 50 ms */
    static int done, off = -1;
    if (done) return;
    if (off < 0) off = GetFileAttributesA("dsr_stocktitle") != INVALID_FILE_ATTRIBUTES;
    if (off || tick > 20 * 120) { done = 1; return; }
    if (tick % 40) return;
    int n = replace_title_text();
    if (n) { done = 1; logmsg("title: \"PRESS ANY BUTTON\" -> \"TOUCH TO START\" (%d copies, %.1f s)", n, tick / 20.0); }
}

/* Tap on a main-menu entry: the app writes dsr_title.txt = "<entry index>" (temp file + rename) and presses A
   ~150 ms later. The FrpgMenuDlgTitle Update hook (vtable 0x1413b5b10 slot 16) moves the highlight first: in the
   no-scroll mode (+0x24d == 0, <= 5 entries) the highlighted slot +0x234 is the entry index (+0x244 = count). */
#define VT_DLG_TITLE 0x1413b5b10ULL
static void (*real_title_update)(uint8_t *dlg, float dt);
static volatile LONG title_pick = -1;

static void title_poll(void) {   /* agent thread */
    FILE *f = fopen("dsr_title.txt", "r");
    if (!f) return;
    int k = -1;
    if (fscanf(f, "%d", &k) != 1) k = -1;
    fclose(f);
    DeleteFileA("dsr_title.txt");
    logmsg("title: pick %d requested", k);
    if (k >= 0 && k < 8) InterlockedExchange(&title_pick, k);
}

static void title_update(uint8_t *dlg, float dt) {
    static uint8_t *published;
    if (dlg != published) {   /* the app reads +0x24c (list shown) from here to tell "touch to start" from the menu */
        published = dlg;
        FILE *f = fopen("dsr_title_dlg.tmp", "w");
        if (f) { fprintf(f, "%llx\n", (unsigned long long)dlg); fclose(f); MoveFileExA("dsr_title_dlg.tmp", "dsr_title_dlg.txt", MOVEFILE_REPLACE_EXISTING); }
    }
    /* a pick waits until the list takes input (+0x254/+0x255 = 1/1, the list fades in for a few seconds after
       "TOUCH TO START"), then moves the highlight and writes dsr_title_ack.txt: the app presses A only after the ack
       (an A sent earlier is queued by the game and runs on Continue). Picks older than 6 s are dropped. */
    static ULONGLONG pick_at;
    LONG k = title_pick;
    if (k >= 0) {
        if (!pick_at) pick_at = GetTickCount64();
        int count = *(int *)(dlg + 0x244);
        if (dlg[0x254] && dlg[0x255]) {
            InterlockedExchange(&title_pick, -1);
            pick_at = 0;
            if (!dlg[0x24d] && k < count) {
                *(int *)(dlg + 0x234) = k;
                FILE *f = fopen("dsr_title_ack.txt", "w");
                if (f) { fprintf(f, "%ld\n", k); fclose(f); }
                logmsg("title: tap entry %ld", k);
            } else logmsg("title: tap entry %ld rejected (scroll mode %d, count %d)", k, dlg[0x24d], count);
        } else if (GetTickCount64() - pick_at > 6000) {
            InterlockedExchange(&title_pick, -1);
            pick_at = 0;
            logmsg("title: tap entry %ld dropped (list never took input)", k);
        }
    }
    real_title_update(dlg, dt);
}

static void hook_title(void) {
    void **vt = (void **)VT_DLG_TITLE;
    DWORD old;
    if (!VirtualProtect(&vt[16], 8, PAGE_READWRITE, &old)) { logmsg("title: VirtualProtect failed %lu", GetLastError()); return; }
    real_title_update = (void (*)(uint8_t *, float))vt[16];
    vt[16] = (void *)title_update;
    VirtualProtect(&vt[16], 8, old, &old);
}

/* Big menu fonts. The Text font index (DRB params +0x1c) selects a preset in the .rdata table 0x1413d3950
   (13 entries x 0x18: name, font id, base size 24, scaleX +0x10, scaleY +0x14; read on every text Begin, never
   copied; docs/ui/FONTS_RE.md). Indexes 1 and 2 (16 / 18 pt) are used by no menu text, so they become the touch
   sizes: 1 = 2.0x (System list, item command menu), 2 = 1.4x (Options, Key settings); tools/patch_menu.py points
   those lists at them. The game shrinks text that does not fit its box, so the boxes are sized for it.
   Flag file dsr_stockfont = keep the table. */
#define P_FONT_TABLE 0x1413d3950ULL
static void patch_fonts(void) {
    if (GetFileAttributesA("dsr_stockfont") != INVALID_FILE_ATTRIBUTES) { logmsg("fonts: stock (flag)"); return; }
    static const struct { int idx; float scale; } big[] = { { 1, 2.0f }, { 2, 1.4f } };
    for (unsigned i = 0; i < sizeof big / sizeof big[0]; i++) {
        float *s = (float *)(P_FONT_TABLE + 0x18 * big[i].idx + 0x10);
        DWORD old;
        if (!VirtualProtect(s, 8, PAGE_READWRITE, &old)) { logmsg("fonts: VirtualProtect failed %lu", GetLastError()); return; }
        float was = s[0];
        s[0] = s[1] = big[i].scale;
        VirtualProtect(s, 8, old, &old);
        logmsg("fonts: preset %d scale %.3f -> %.2f", big[i].idx, was, big[i].scale);
    }
}

/* "Game will start in offline mode." never shown (user 2026-10-15: it came back on every return to the title).
   Two title state handlers show it (text id 0xc545, System_message_win32_ FMG) through the general dialog
   (0x140686bc0 init, 0x140686c20 set text, 0x140686f30 show):
   - 0x14028a720: show, then state 0xc. The 0xc handler (0x14028a810) goes on to 0xd at once when no general dialog
     is open (0x140681ea0 = MenuMan state 0x11 free).
   - 0x140804c60: show, then state 0x40. The 0x40 handler (0x140804cc2) waits for a button, then sets +0xc0 = 1 and
     state 0xa.
   MISTAKE (2026-10-15 20:56): patching those bytes in .text killed the game 2 s after start (anti-tamper).
   The handlers are function pointers that static init writes to .data (0x140013d70 -> 0x141c715c8,
   0x140037548 -> 0x141c8b278), so the agent swaps the pointers instead, once static init has filled them:
   site 1 -> state 0xc without the dialog, site 2 -> the OK result. Flag file dsr_offlinenotice = keep it. */
static void notice_skip1(uint8_t *self) { *(int *)(self + 0x10) = 0xc; }
static void notice_skip2(uint8_t *self) { *(int *)(self + 0xc0) = 1; *(int *)(self + 0x10) = 0xa; }

static void patch_offline_notice(void) {   /* agent thread, every tick until both slots are swapped */
    static int done, off = -1;
    if (done) return;
    if (off < 0) {
        off = GetFileAttributesA("dsr_offlinenotice") != INVALID_FILE_ATTRIBUTES;
        if (off) { logmsg("offline notice: kept (flag)"); done = 1; return; }
    }
    static const struct { uint64_t slot, orig; void *mine; } s[] = {
        { 0x141c715c8ULL, 0x14028a720ULL, (void *)notice_skip1 },
        { 0x141c8b278ULL, 0x140804c60ULL, (void *)notice_skip2 },
    };
    int n = 0;
    for (int i = 0; i < 2; i++) {
        void *volatile *slot = (void *volatile *)s[i].slot;
        if (*slot == s[i].mine) { n++; continue; }
        if ((uint64_t)*slot == s[i].orig) { *slot = s[i].mine; n++; logmsg("offline notice: handler %d swapped", i + 1); }
    }
    if (n == 2) done = 1;
}

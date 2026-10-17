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
   The same scan blanks every whole string "Log In" (Menu_others_ 0x61f9a): the title Log In row is hidden (above),
   and its text id serves as the blank padding of the no-save title row (title_pad). The FMGs have no empty string
   (an id without an entry prints "?MenuOther? ID", a null one prints the number).
   Retries every 2 s for 2 min (the files load a few seconds after start). Flag file dsr_stocktitle = keep it. */
static const struct { const WCHAR *from, *to; int whole; } title_repl[] = {
    { L"PRESS ANY BUTTON", L"TOUCH TO START", 0 },
    { L"Log In", L"", 1 },   /* whole = only at a string start (previous char 0) */
};

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
            SIZE_T want = (SIZE_T)(end - c) < 65536 + 40 ? (SIZE_T)(end - c) : 65536 + 40;
            SIZE_T got = 0;
            if (!ReadProcessMemory(self, c, buf, want, &got) || got < 16) continue;
            for (int r = 0; r < 2; r++) {
                const WCHAR *f = title_repl[r].from;
                SIZE_T len = (lstrlenW(f) + 1) * 2;   /* with the terminator */
                for (SIZE_T i = 0; i + len <= got && i < 65536; i += 2) {
                    if (buf[i] != (uint8_t)f[0] || buf[i + 2] != (uint8_t)f[1] || memcmp(buf + i, f, len)) continue;
                    if (title_repl[r].whole && (i < 2 ? c == base : buf[i - 2] || buf[i - 1])) continue;
                    if (WriteProcessMemory(self, c + i, title_repl[r].to, (lstrlenW(title_repl[r].to) + 1) * 2, NULL)) n += r ? 0x100 : 1;
                }
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
    if (n & 0xff) {
        done = 1;
        logmsg("title: \"PRESS ANY BUTTON\" -> \"TOUCH TO START\" (%d copies), \"Log In\" blanked (%d), %.1f s",
               n & 0xff, n >> 8, tick / 20.0);
    }
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

/* No save -> the list is New Game / System / Quit Game = slots 0..2 of the 5-slot row (left-heavy, user
   2026-10-17). The table is then rewritten to [blank, ..., New Game, System, Quit Game, blank]: the blanks are
   copies of the always-visible Log In row (action 5, offline) with the blanked "Log In" text. 3 entries ->
   5, centred. When a save appears (7 = 5 + 2 blanks) the original table comes back. Taps on blank slots are
   dropped and the highlight never rests on them. */
#define TITLE_BLANK_TEXT 0x61f9au   /* "Log In", blanked in memory (replace_title_text) */
static uint32_t title_orig[30];
static int title_padded;
static void title_pad(int on) {
    uint32_t *t = (uint32_t *)P_TITLE_TABLE;
    if (on) {
        memcpy(title_orig, t, sizeof title_orig);
        uint32_t pad[3] = { TITLE_BLANK_TEXT, 5, title_orig[5 * 3 + 2] };
        uint32_t n[30];
        memcpy(n, pad, 12);                       /* 0: blank */
        memcpy(n + 3, title_orig, 12 * 5);        /* 1..5: Continue, Load, New, System, Information */
        memcpy(n + 18, title_orig + 6 * 3, 12);   /* 6: Log Out */
        memcpy(n + 21, title_orig + 9 * 3, 12);   /* 7: Quit Game */
        memcpy(n + 24, pad, 12);                  /* 8: blank */
        memcpy(n + 27, title_orig + 7 * 3, 12);   /* 9: Switch Profile (always filtered) */
        memcpy(t, n, sizeof n);
    } else memcpy(t, title_orig, sizeof title_orig);
    title_padded = on;
    logmsg("title: blank padding %s", on ? "on (no save)" : "off");
}

static void title_update(uint8_t *dlg, float dt) {
    static uint8_t *published;
    static int stock = -1;
    if (stock < 0) stock = GetFileAttributesA("dsr_stocktitle") != INVALID_FILE_ATTRIBUTES;
    if (!stock) {
        int c = *(int *)(dlg + 0x244);
        if (!title_padded && c == 3) title_pad(1);
        else if (title_padded && c == 7) title_pad(0);
        if (title_padded && c == 5 && !dlg[0x24d]) {   /* keep the highlight off the blank slots */
            int *hl = (int *)(dlg + 0x234);
            if (*hl == 0) *hl = 1; else if (*hl == 4) *hl = 3;
        }
    }
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
            if (title_padded && (k == 0 || k == 4)) logmsg("title: tap on blank slot %ld dropped", k);
            else if (!dlg[0x24d] && k < count) {
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

/* Title version lines (user 2026-10-16): "App ver. 1.03.1-mobile" and a new line "Modder: kbRadu" under the
   regulation version. The title builder (0x1406935f8) shows FMG 401320 "App ver." + the global std::wstring at
   0x141c84c58 (L"1.03.1") and FMG 401322 "Regulation ver." + the one at 0x141c84c88 (L" 1.04"). Layout (MSVC with
   an allocator in front): +0 allocator, +8 buffer (inline when capacity < 8) or heap pointer, +0x18 size,
   +0x20 capacity. The agent calls the game's own assign 0x1400bd1b0(this, ptr, len) so the longer text lives in
   the game's allocator (freed normally at exit). Once, as soon as both hold the stock text (set at boot, before the
   title list is built). DRB info_versionReg is two lines tall (patch_menu.py). Flag file dsr_stockver = keep. */
typedef void *(*wassign_t)(void *self, const WCHAR *s, size_t n);
static int wstr_is(uint8_t *ws, const WCHAR *s) {
    size_t n = lstrlenW(s);
    if (*(size_t *)(ws + 0x18) != n) return 0;
    const WCHAR *b = *(size_t *)(ws + 0x20) >= 8 ? *(const WCHAR **)(ws + 8) : (const WCHAR *)(ws + 8);
    return memcmp(b, s, n * 2) == 0;
}
static void patch_version_text(void) {   /* agent thread, every tick until done */
    static int done, off = -1;
    if (done) return;
    if (off < 0) {
        off = GetFileAttributesA("dsr_stockver") != INVALID_FILE_ATTRIBUTES;
        if (off) { logmsg("version text: stock (flag)"); done = 1; return; }
    }
    static const struct { uint64_t ws; const WCHAR *from, *to; } v[] = {
        { 0x141c84c58ULL, L"1.03.1", L"1.03.1-mobile" },
        { 0x141c84c88ULL, L" 1.04", L" 1.04\nModder: kbRadu" },
    };
    wassign_t assign = (wassign_t)0x1400bd1b0ULL;
    int n = 0;
    for (int i = 0; i < 2; i++) {
        uint8_t *ws = (uint8_t *)v[i].ws;
        if (wstr_is(ws, v[i].to)) { n++; continue; }
        if (wstr_is(ws, v[i].from)) { assign(ws, v[i].to, lstrlenW(v[i].to)); n++; logmsg("version text %d set", i + 1); }
    }
    if (n == 2) done = 1;
}

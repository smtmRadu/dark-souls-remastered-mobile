/* In-game UI helpers + adb command channel (included by dinput8.c). Offsets: docs/ui/UI_RE.md.
   Commands: write lines to dsr_cmd.txt in the game folder; the agent runs them within 50 ms and deletes the file.
     statelog 0|1     log changes of MenuMan state[500] (MenuMan+0x30) to dsr_agent.log
     set ID V         state[ID] = V (hex or dec)
     get ID           log state[ID]
     menubar          open the menu bar (state[0x7d]=1, state[8]=7)
     tab N            open tab N of the open bar (0 inventory, 1 equipment, 2 status, 3 system)
     closeall         state[0x88]=1
     tap X Y          mouse click at client pixel (forces KB/mouse mode, hooks GetCursorPos)
     mouse 0|1        PadMan+0x68 (KB/mouse mode) */
#define P_MENUMAN 0x141c88d98ULL
#define P_PADMAN  0x141c6aea0ULL
#define UI_AT(T, base, off) (*(T *)((uint8_t *)(base) + (off)))

static uint8_t *ui_deref(uint64_t p) { return *(uint8_t * volatile *)p; }
static int ms_get(int id) {
    uint8_t *mm = ui_deref(P_MENUMAN);
    return (mm && id >= 0 && id < 500) ? UI_AT(volatile int, mm, 0x30 + 4 * id) : 0;
}
static void ms_set(int id, int v) {
    uint8_t *mm = ui_deref(P_MENUMAN);
    if (mm && id >= 0 && id < 500) UI_AT(volatile int, mm, 0x30 + 4 * id) = v;
}

static int statelog;
static void ui_log_state_diff(void) {
    static int prev[500], init;
    uint8_t *mm = ui_deref(P_MENUMAN);
    if (!mm) { init = 0; return; }
    for (int i = 0; i < 500; i++) {
        int v = UI_AT(volatile int, mm, 0x30 + 4 * i);
        if (init && v != prev[i]) logmsg("menustate[0x%x] %d -> %d", i, prev[i], v);
        prev[i] = v;
    }
    init = 1;
}

/* ---- tap = native mouse click: cursor from hooked GetCursorPos/ScreenToClient, button from the DI mouse cache ---- */
static volatile LONG tap_x = -1, tap_y = -1;
static volatile DWORD tap_release_at;
static BOOL (WINAPI *real_gcp)(LPPOINT);
static BOOL (WINAPI *real_s2c)(HWND, LPPOINT);
static BOOL WINAPI hook_gcp(LPPOINT p) {
    if (tap_x >= 0 && p) { p->x = tap_x; p->y = tap_y; return TRUE; }
    return real_gcp(p);
}
static BOOL WINAPI hook_s2c(HWND h, LPPOINT p) {
    if (tap_x >= 0) return TRUE;   /* GetCursorPos already returns client coordinates */
    return real_s2c(h, p);
}
static void ui_mouse_hooks(void) {
    real_gcp = hook_iat("USER32.dll", "GetCursorPos", (void *)hook_gcp);
    real_s2c = hook_iat("USER32.dll", "ScreenToClient", (void *)hook_s2c);
}
/* Called by the DirectInput cache on every mouse GetDeviceState (DIMOUSESTATE / DIMOUSESTATE2). */
static void ui_di_mouse_patch(uint8_t *b, DWORD size) {
    if (size < 16 || tap_x < 0) return;
    UI_AT(LONG, b, 0) = 0; UI_AT(LONG, b, 4) = 0;
    if (tap_release_at && (LONG)(GetTickCount() - tap_release_at) < 0) b[12] |= 0x80; else b[12] &= 0x7f;
}
static void ui_mouse_mode(int on) { uint8_t *pm = ui_deref(P_PADMAN); if (pm) UI_AT(volatile uint8_t, pm, 0x68) = (uint8_t)on; }

static void ui_command(char *l) {
    char cmd[32]; int a = 0, b = 0;
    int n = sscanf(l, "%31s %i %i", cmd, &a, &b);
    if (n < 1) return;
    if (!strcmp(cmd, "statelog")) statelog = a;
    else if (!strcmp(cmd, "set") && n == 3) ms_set(a, b);
    else if (!strcmp(cmd, "get") && n >= 2) logmsg("state[0x%x] = %d", a, ms_get(a));
    else if (!strcmp(cmd, "menubar")) { ms_set(0x7d, 1); ms_set(8, 7); }
    else if (!strcmp(cmd, "tab") && n >= 2) {
        if (ms_get(8) != 8) { logmsg("tab: bar not open (state[8]=%d)", ms_get(8)); return; }
        ms_set(0x4b, a);
        switch (a) {
        case 0: ms_set(0x75, 0); ms_set(2, 1); break;
        case 1: ms_set(3, 10); break;
        case 2: ms_set(0x15, 1); break;
        case 3: ms_set(0x2a, 1); *(volatile uint8_t *)0x141a32779ULL = 1; break;
        }
        ms_set(8, 2);
    }
    else if (!strcmp(cmd, "closeall")) ms_set(0x88, 1);
    else if (!strcmp(cmd, "mouse") && n >= 2) ui_mouse_mode(a);
    else if (!strcmp(cmd, "tap") && n == 3) {
        if (!real_gcp) ui_mouse_hooks();
        ui_mouse_mode(1); tap_x = a; tap_y = b; tap_release_at = GetTickCount() + 120;
    }
    else { logmsg("cmd? %s", l); return; }
    logmsg("cmd: %s", l);
}
static void ui_poll(void) {
    if (statelog) ui_log_state_diff();
    FILE *f = fopen("dsr_cmd.txt", "r");
    if (!f) return;
    char l[128];
    while (fgets(l, sizeof l, f)) { l[strcspn(l, "\r\n")] = 0; ui_command(l); }
    fclose(f); DeleteFileA("dsr_cmd.txt");
}

/* display.c (included by dinput8.c): native phone aspect, no black bars (docs/ui/ASPECT_RATIO.md).
   The app sizes the X screen / Wine desktop to the phone's ratio (e.g. 1584x648 on the Flip6). DSR renders Hor+
   and anchors its HUD by itself; only the saved PC display option can pull it back to 16:9 (1280x720 is not in the
   new mode list, so the game falls back to a captioned window). Pin it: screen mode 2 (borderless = desktop size)
   and window / fullscreen size = desktop size. Options = [[GameDataMan]+0x68]: +0xc4 mode, +0xd0/+0xd4 window
   W/H, +0xd8/+0xdc fullscreen W/H. Flag file dsr_keepdisplay = leave the game's setting alone. */

static void pin_display(void) {
    static int done, off = -1;
    if (done) return;
    if (off < 0) off = GetFileAttributesA("dsr_keepdisplay") != INVALID_FILE_ATTRIBUTES;
    if (off) { done = 1; logmsg("display: kept (flag)"); return; }
    uint64_t gdm = *(volatile uint64_t *)GAME_DATA_MAN;
    if (!gdm) return;
    uint8_t *opt = *(uint8_t * volatile *)(gdm + 0x68);
    if (!opt) return;
    int w = GetSystemMetrics(SM_CXSCREEN), h = GetSystemMetrics(SM_CYSCREEN);
    if (w <= 0 || h <= 0) return;
    int32_t *o = (int32_t *)opt;
    logmsg("display: mode %d window %dx%d full %dx%d -> borderless %dx%d", o[0xc4 / 4], o[0xd0 / 4], o[0xd4 / 4],
           o[0xd8 / 4], o[0xdc / 4], w, h);
    o[0xc4 / 4] = 2;
    o[0xd0 / 4] = w; o[0xd4 / 4] = h;
    o[0xd8 / 4] = w; o[0xdc / 4] = h;
    done = 1;
}

/* The game window must have no caption/border, or Wine draws a title bar strip over the top of the picture
   (the game creates its window before the option above is pinned). IAT hooks, installed from DllMain. */
#define CAPTION_BITS (WS_CAPTION | WS_THICKFRAME | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX)
static HWND (WINAPI *real_cwex)(DWORD, LPCWSTR, LPCWSTR, DWORD, int, int, int, int, HWND, HMENU, HINSTANCE, LPVOID);
static LONG_PTR (WINAPI *real_swlp)(HWND, int, LONG_PTR);
static HWND WINAPI hook_cwex(DWORD ex, LPCWSTR cls, LPCWSTR name, DWORD style, int x, int y, int w, int h,
                             HWND parent, HMENU menu, HINSTANCE inst, LPVOID param) {
    if (!(style & WS_CHILD) && (style & WS_CAPTION)) {
        logmsg("display: window %dx%d style %lx -> popup", w, h, style);
        style = (style & ~CAPTION_BITS) | WS_POPUP;
        ex &= ~(WS_EX_WINDOWEDGE | WS_EX_CLIENTEDGE | WS_EX_DLGMODALFRAME);
    }
    return real_cwex(ex, cls, name, style, x, y, w, h, parent, menu, inst, param);
}
static LONG_PTR WINAPI hook_swlp(HWND hw, int idx, LONG_PTR v) {
    if (idx == GWL_STYLE && !(v & WS_CHILD)) v = (v & ~(LONG_PTR)CAPTION_BITS) | WS_POPUP;
    return real_swlp(hw, idx, v);
}
static BOOL WINAPI hook_awr(LPRECT r, DWORD style, BOOL menu) { (void)r; (void)style; (void)menu; return TRUE; }   /* no frame */

static void hook_window(void) {
    if (GetFileAttributesA("dsr_keepdisplay") != INVALID_FILE_ATTRIBUTES) return;
    real_cwex = (void *)GetProcAddress(GetModuleHandleA("user32.dll"), "CreateWindowExW");
    real_swlp = (void *)GetProcAddress(GetModuleHandleA("user32.dll"), "SetWindowLongPtrW");
    int a = hook_iat("USER32.dll", "CreateWindowExW", (void *)hook_cwex) != NULL;
    int b = hook_iat("USER32.dll", "SetWindowLongPtrW", (void *)hook_swlp) != NULL;
    int c = hook_iat("USER32.dll", "AdjustWindowRect", (void *)hook_awr) != NULL;
    logmsg("display: window hooks %d%d%d", a, b, c);
}

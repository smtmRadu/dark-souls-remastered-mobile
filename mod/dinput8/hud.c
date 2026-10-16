/* hud.c (included by dinput8.c): hide the stock equipment-slot block (FrpgMenuDlgFeShortcut, bottom-left HUD)
   and the stock interaction prompt box (FrpgMenuDlgMapAction).
   The app draws the slots natively with the game's icons (design/final_wanted_controls.html), so the stock block
   only duplicates them and sits under the stick. Hidden only when the extracted icons exist (dsr_assets/items.json,
   tools/extract_assets.py): without them the app shows text labels and the stock block is the only icon view.
   Flag file dsr_stockhud = keep the stock block.

   How: patch FeShortcut's vtable slot 16 (+0x80, Update(this, float dt)); after the original update, clear the
   visible bit (bit 1 of obj+0x28) of every object in the dialog's list (dlg+0x18, count dlg+0x20) - the same
   visibility bit Overhaul's UIFeatures.cpp uses. */

/* FeShortcut = the slot icons; ShortcutItem = quick item select popup; MapAction = the "Pick up item" / "Talk" prompt
   box (the app's Interact pill shows the same text from prompts.json) */
static const uint64_t hud_vts[] = { 0x1413afe10ULL /* FrpgMenuDlgFeShortcut */, 0x1413a8958ULL /* FrpgMenuDlgShortcutItem */,
                                    0x1413b1b68ULL /* FrpgMenuDlgMapAction */ };
#define N_HUD_VT (sizeof hud_vts / sizeof hud_vts[0])
static void (*real_hud_update[N_HUD_VT])(uint8_t *dlg, float dt);

static void hide_objects(uint8_t *dlg) {
    uint64_t *list = *(uint64_t **)(dlg + 0x18);
    uint32_t n = *(uint32_t *)(dlg + 0x20);
    if (!list || n > 256) return;
    for (uint32_t i = 0; i < n; i++) {
        if (!list[i]) continue;
        /* FrpgMenuDlgObjItemSelect (vt 0x1413a85f0, the quick item's name line) still draws with the bit cleared
           (it owns sub-elements, 0x50 bytes each from +0x48, vt 0x1414f6988). Kept on purpose: tools/patch_menu.py
           moves it under the app's Estus slot. */
        *(uint8_t *)(list[i] + 0x28) &= (uint8_t)~0x02;
    }
}

/* FeShortcut updates once per gameplay frame on the game thread: tap-to-lock and the touch camera apply here. */
static void hud_update0(uint8_t *dlg, float dt) { lock_apply(); cam_apply(); real_hud_update[0](dlg, dt); hide_objects(dlg); }
static void hud_update1(uint8_t *dlg, float dt) { real_hud_update[1](dlg, dt); hide_objects(dlg); }
static void hud_update2(uint8_t *dlg, float dt) { real_hud_update[2](dlg, dt); hide_objects(dlg); }
static void (*const hud_hooks[N_HUD_VT])(uint8_t *, float) = { hud_update0, hud_update1, hud_update2 };

static void hook_hud(void) {
    if (GetFileAttributesA("dsr_stockhud") != INVALID_FILE_ATTRIBUTES) { logmsg("hud: stock slots kept (flag)"); return; }
    if (GetFileAttributesA("dsr_assets/items.json") == INVALID_FILE_ATTRIBUTES) { logmsg("hud: no extracted icons, stock slots kept"); return; }
    for (unsigned i = 0; i < N_HUD_VT; i++) {
        void **vt = (void **)hud_vts[i];
        real_hud_update[i] = (void (*)(uint8_t *, float))vt[16];
        DWORD old;
        if (!VirtualProtect(&vt[16], 8, PAGE_READWRITE, &old)) { logmsg("hud: VirtualProtect failed %lu", GetLastError()); return; }
        vt[16] = (void *)hud_hooks[i];
        VirtualProtect(&vt[16], 8, old, &old);
        logmsg("hud: vt %llx update %p hooked (hidden)", (unsigned long long)hud_vts[i], (void *)real_hud_update[i]);
    }
}

/* HUD hidden while a menu is open (HP / stamina gauges, souls, quick item name), locked ON everywhere else.
   The game's own HUD option: opts = [[GameDataMan]+0x58], byte +0x11 (1 on, 0 off).
   - Menu bar / tabs (MenuMan state[8]) and the Display / Sound pages (0x3b / 0x42): 0.
   - Everything else, including the System decide step (state[0x2a] == 3, before a page opens) and the Options /
     PC settings pages (0x13 / 0xb1, they show a HUD row and read it when they open): 1.
   - Locked ON, not "put the player's value back" (changed 2026-10-15 20:05): the 50 ms loop once missed the decide
     step, Options opened with HUD OFF, Back stored OFF, and every later restore put OFF back (no HP / souls / Estus
     name in gameplay). The touch UI needs the HUD, so a HUD OFF chosen on Options is undone when the menu closes.
   - Hiding the HUD dialogs by their visible bit (dlg+0x28) did nothing (tested 2026-10-15).
   Own thread, 2 ms: the decide step lasts only a frame or two. Flag file dsr_menuhud = leave the option alone. */
static void menu_hud(void) {
    static int off = -1, last = -1;
    if (off < 0) {
        off = GetFileAttributesA("dsr_menuhud") != INVALID_FILE_ATTRIBUTES;
        DeleteFileA("dsr_hud_saved.txt");   /* old scheme */
    }
    if (off) return;
    uint8_t *gdm = *(uint8_t * volatile *)GAME_DATA_MAN;
    uint8_t *opts = gdm ? *(uint8_t * volatile *)(gdm + 0x58) : NULL;
    if (!opts) return;
    volatile uint8_t *hud = opts + 0x11;
    int s13 = ms_get(0x13), sb1 = ms_get(0xb1);
    int env = (s13 != 0 && s13 != 5) || (sb1 != 0 && sb1 != 5);
    /* 0x9 = bonfire menu (2026-10-16): HUD hidden while resting too */
    int menu = (ms_get(8) != 0 || ms_get(9) != 0 || ms_get(0x3b) != 0 || ms_get(0x42) != 0) && ms_get(0x2a) != 3 && !env;
    int want = menu ? 0 : 1;
    if (*hud != want) {
        if (want != last || *hud > 1) logmsg("menuhud: %d -> %d (8=%d 2a=%d 13=%d b1=%d)", *hud, want, ms_get(8), ms_get(0x2a), s13, sb1);
        *hud = (uint8_t)want;
    }
    last = want;
}

static DWORD WINAPI menu_hud_thread(LPVOID unused) {
    (void)unused;
    for (;;) { menu_hud(); Sleep(2); }
}

// DSR in-game agent, loaded as a dinput8.dll proxy (Wine: WINEDLLOVERRIDES=dinput8=n,b).
// The Android app can read the game's memory but not write it (SELinux), so all writes happen here.
// v1: switch the frame pacer FrpgFlipper_60FPS -> FrpgFlipper_30FPS. The 60FPS pacer gives at most
// 2/60 s of game time per frame (slow motion below 30 FPS); the 30FPS pacer allows 2/30 s, so the
// game keeps real-time speed down to 15 FPS. Offsets: exe 1.03.1 (re/RE_NOTES.md).
#include <windows.h>
#include <stdio.h>
#include <stdint.h>
#define DIRECTINPUT_VERSION 0x0800
#include <dinput.h>

#define VT_FLIPPER_60 0x1412ab268ULL
#define TICK_DT 0x1412ccc78ULL   /* .rdata float: logic tick length (1/60 stock) */
#define VT_FLIPPER_30 0x1412ea688ULL
#define VT_FLIPPER_30NS 0x1412ea790ULL   /* FrpgFlipper_30FPS_NoSkip: never skips rendering */
#define VT_FLIPPER_MGR 0x1412ea400ULL   /* task object: +0x20 mode (4 = 60FPS, 0 = 30FPS), +0x28 FrpgFlipper* */

typedef HRESULT (WINAPI *DI8Create)(HINSTANCE, DWORD, REFIID, LPVOID *, LPUNKNOWN);
static DI8Create real_create;
static FILE *logf;
static void patch_tick(void);
static void governor(void);
static void ui_di_mouse_patch(uint8_t *b, DWORD size);

static void logmsg(const char *fmt, ...) {
    if (!logf) return;
    va_list ap; va_start(ap, fmt);
    SYSTEMTIME t; GetLocalTime(&t);
    fprintf(logf, "%02d:%02d:%02d ", t.wHour, t.wMinute, t.wSecond);
    vfprintf(logf, fmt, ap); fputc('\n', logf); fflush(logf);
    va_end(ap);
}

static void load_real(void) {
    if (real_create) return;
    char path[MAX_PATH]; GetSystemDirectoryA(path, MAX_PATH); strcat(path, "\\dinput8.dll");
    HMODULE h = LoadLibraryA(path);
    real_create = h ? (DI8Create)GetProcAddress(h, "DirectInput8Create") : NULL;
    logmsg("real dinput8 %s -> %p", path, (void *)real_create);
}

/* ---- DirectInput state cache (profile 2026-10-14: ~9% of the main thread in Wine's dinput8, Poll +
   GetDeviceState on mouse, keyboard and pads every frame). We hook the device vtables (slot 9 GetDeviceState,
   slot 25 Poll): the game gets a copy of the last state; the agent thread polls the real devices at 100 Hz.
   Mouse states (16/20 bytes) carry relative X/Y/Z: those are summed by the poller and cleared on read. ---- */
typedef HRESULT (WINAPI *GetState_t)(void *, DWORD, void *);
typedef HRESULT (WINAPI *Poll_t)(void *);
typedef ULONG (WINAPI *Release_t)(void *);
typedef HRESULT (WINAPI *CreateDev_t)(void *, REFGUID, void **, void *);
#define MAX_DEV 8
/* Originals per device vtable (Wine: one vtable for all W devices, one for A; A methods forward to W). */
static struct vtorig { void **vt; GetState_t gs; Poll_t poll; Release_t rel; } vts[4];
static int nvt;
static struct dev { void *d; struct vtorig *o; DWORD size; uint8_t buf[512]; HRESULT hr; int ok; } devs[MAX_DEV];
static int ndev;
static CRITICAL_SECTION dev_cs;
static CreateDev_t real_createdev[2];   /* [0] = A interface vtable, [1] = W */
static void *createdev_vt[2];
static struct dev *find_dev(void *d) { for (int i = 0; i < ndev; i++) if (devs[i].d == d) return &devs[i]; return NULL; }
static struct vtorig *find_vt(void *d) { void **vt = *(void ***)d; for (int i = 0; i < nvt; i++) if (vts[i].vt == vt) return &vts[i]; return NULL; }
static HRESULT WINAPI hook_poll(void *d) {
    struct dev *v; EnterCriticalSection(&dev_cs); v = find_dev(d); LeaveCriticalSection(&dev_cs);
    if (v) return DI_OK;   /* the poller thread polls cached devices */
    struct vtorig *o = find_vt(d); return o ? o->poll(d) : DI_OK;
}
/* The game may release a device (focus change, pad reconnect): drop it from the cache first,
   or the poller thread would use freed memory. */
static ULONG WINAPI hook_release(void *d) {
    struct vtorig *o = find_vt(d);
    EnterCriticalSection(&dev_cs);
    ULONG r = o->rel(d);
    struct dev *v = find_dev(d);
    if (v && r == 0) { logmsg("dinput device %p released", d); *v = devs[--ndev]; }
    LeaveCriticalSection(&dev_cs);
    return r;
}
static HRESULT WINAPI hook_getstate(void *d, DWORD size, void *out) {
    EnterCriticalSection(&dev_cs);
    struct dev *v = find_dev(d); HRESULT hr;
    if (!v || size > sizeof v->buf) { LeaveCriticalSection(&dev_cs); struct vtorig *o = find_vt(d); return o ? o->gs(d, size, out) : DIERR_INVALIDPARAM; }
    if (!v->ok || v->size != size) {   /* first call or new format: read through once */
        v->size = size; v->hr = v->o->gs(d, size, v->buf); v->ok = 1;
    }
    memcpy(out, v->buf, size); hr = v->hr;
    if (size == 16 || size == 20) { memset(v->buf, 0, 12); ui_di_mouse_patch((uint8_t *)out, size); }   /* DIMOUSESTATE: relative axes consumed */
    LeaveCriticalSection(&dev_cs);
    return hr;
}
static void poll_devices(void) {
    uint8_t tmp[512];
    EnterCriticalSection(&dev_cs);
    for (int i = 0; i < ndev; i++) {
        struct dev *v = &devs[i];
        if (!v->ok) continue;
        v->o->poll(v->d);
        HRESULT hr = v->o->gs(v->d, v->size, tmp);
        if (v->size == 16 || v->size == 20) {   /* accumulate mouse deltas */
            LONG *a = (LONG *)v->buf, *b = (LONG *)tmp;
            if (SUCCEEDED(hr)) { a[0] += b[0]; a[1] += b[1]; a[2] += b[2]; memcpy(v->buf + 12, tmp + 12, v->size - 12); }
        } else if (SUCCEEDED(hr)) memcpy(v->buf, tmp, v->size);
        v->hr = hr;
    }
    LeaveCriticalSection(&dev_cs);
}
static DWORD WINAPI poller(LPVOID _) {
    (void)_; timeBeginPeriod(1);
    for (;;) { poll_devices(); Sleep(10); }
    return 0;
}
static void patch_slot(void **vt, int slot, void *fn) {
    DWORD old; VirtualProtect(&vt[slot], 8, PAGE_READWRITE, &old); vt[slot] = fn; VirtualProtect(&vt[slot], 8, old, &old);
}
static HRESULT WINAPI hook_createdev(int w, void *di, REFGUID g, void **out, void *outer) {
    HRESULT hr = real_createdev[w](di, g, out, outer);
    if (SUCCEEDED(hr) && *out && ndev < MAX_DEV && GetFileAttributesA("dsr_nodicache") == INVALID_FILE_ATTRIBUTES) {
        void **vt = *(void ***)*out;
        EnterCriticalSection(&dev_cs);
        struct vtorig *o = find_vt(*out);
        if (!o && nvt < 4) {   /* first device of this vtable: save originals, then hook */
            o = &vts[nvt++];
            o->vt = vt; o->gs = (GetState_t)vt[9]; o->poll = (Poll_t)vt[25]; o->rel = (Release_t)vt[2];
            patch_slot(vt, 9, (void *)hook_getstate); patch_slot(vt, 25, (void *)hook_poll); patch_slot(vt, 2, (void *)hook_release);
        }
        if (o) {
            struct dev *v = &devs[ndev];
            memset(v, 0, sizeof *v); v->d = *out; v->o = o;
            if (ndev++ == 0) CreateThread(NULL, 0, poller, NULL, 0, NULL);
            logmsg("dinput device %p (vt %p) cached", *out, (void *)vt);
        }
        LeaveCriticalSection(&dev_cs);
    }
    return hr;
}
static HRESULT WINAPI hook_createdev_a(void *di, REFGUID g, void **out, void *outer) { return hook_createdev(0, di, g, out, outer); }
static HRESULT WINAPI hook_createdev_w(void *di, REFGUID g, void **out, void *outer) { return hook_createdev(1, di, g, out, outer); }

__declspec(dllexport) HRESULT WINAPI DirectInput8Create(HINSTANCE inst, DWORD ver, REFIID riid, LPVOID *out, LPUNKNOWN outer) {
    load_real();
    HRESULT hr = real_create ? real_create(inst, ver, riid, out, outer) : E_FAIL;
    if (SUCCEEDED(hr) && out && *out) {
        void **vt = *(void ***)*out;
        int w = IsEqualGUID(riid, &IID_IDirectInput8W);
        if (!createdev_vt[w]) {
            createdev_vt[w] = vt; real_createdev[w] = (CreateDev_t)vt[3];
            patch_slot(vt, 3, w ? (void *)hook_createdev_w : (void *)hook_createdev_a);
            logmsg("IDirectInput8%c %p: CreateDevice hooked", w ? 'W' : 'A', *out);
        }
    }
    return hr;
}

static uint64_t *flipper_obj;
/* Our copy of the FrpgFlipper_30FPS vtable with logging wrappers on slot 3 (run logic?) and slot 9 (skip rule). */
static uint64_t my_vt[10];
static volatile LONG vt_log;
typedef char (*slot3_t)(void *);
typedef void (*slot9_t)(void *, void *);
static char my_slot3(void *self) {
    char r = ((slot3_t)((uint64_t *)VT_FLIPPER_30)[3])(self);
    if (vt_log > 0 && vt_log < 200) { vt_log++; logmsg("s3 flag=%d -> %d ret=%p", ((uint8_t *)self)[8], r, __builtin_return_address(0)); }
    return r;
}
static void my_slot9(void *self, void *ctx) {
    if (vt_log > 0 && vt_log < 200) {
        vt_log++; uint32_t *r = (uint32_t *)ctx;
        logmsg("s9 flag=%d ctx=%p ret=%p | %08x %08x %08x %08x %08x %08x | %f %f n=%d | %08x %08x %08x %08x", ((uint8_t *)self)[8], ctx, __builtin_return_address(0),
               r[0], r[1], r[2], r[3], r[4], r[5], *(float *)&r[6], *(float *)&r[7], (int)r[8], r[9], r[10], r[11], r[12]);
    }
    ((slot9_t)((uint64_t *)VT_FLIPPER_30)[9])(self, ctx);
}
/* Walk committed private RW memory in 64 KB chunks copied with ReadProcessMemory. Reading the regions directly
   crashed the game now and then: the game frees memory between VirtualQuery and the read (boot loading, every
   rescan). A copy of a freed region just fails. fn(chunk copy, its real address, qword count). */
static uint64_t scan_buf[8192 + 8];
static void scan_private(void (*fn)(const uint64_t *, uint64_t *, size_t)) {
    MEMORY_BASIC_INFORMATION mi; uint8_t *a = 0; HANDLE self = GetCurrentProcess();
    while (VirtualQuery(a, &mi, sizeof mi)) {
        if (mi.State == MEM_COMMIT && mi.Type == MEM_PRIVATE && mi.Protect == PAGE_READWRITE) {
            uint8_t *c = mi.BaseAddress, *e = c + mi.RegionSize;
            for (; c < e; c += 65536) {
                /* +48 bytes overlap so a 6-qword pattern at a chunk end is still seen */
                SIZE_T want = (SIZE_T)(e - c) < 65536 + 48 ? (SIZE_T)(e - c) : 65536 + 48, got = 0;
                if (!ReadProcessMemory(self, c, scan_buf, want, &got) || got < 16) continue;
                size_t n = got / 8, lim = 65536 / 8;
                fn(scan_buf, (uint64_t *)c, n < lim + 6 ? n : lim + 6);
            }
        }
        a = (uint8_t *)mi.BaseAddress + mi.RegionSize;
        if ((uintptr_t)a >= 0x7ffffffeffffULL) break;
    }
}

/* Find 16-byte FrpgFlipper objects {vtable, flag byte, pad} and swap the pacer vtable. */
static int flip_found;
static void flip_chunk(const uint64_t *q, uint64_t *real, size_t n) {
    for (size_t i = 0; i + 2 <= n && i < 8192; i += 2) {   // heap blocks are 16-aligned
        if (q[i] != VT_FLIPPER_60 || (q[i + 1] & ~0xffULL) != 0) continue;
        uint64_t *p = real + i, vt;
        if (GetFileAttributesA("dsr_vt.go") != INVALID_FILE_ATTRIBUTES) {
            memcpy(my_vt, (void *)VT_FLIPPER_30, sizeof my_vt);
            my_vt[3] = (uint64_t)my_slot3; my_vt[9] = (uint64_t)my_slot9; vt_log = 1;
            vt = (uint64_t)my_vt;
        } else if (GetFileAttributesA("dsr_skip") != INVALID_FILE_ATTRIBUTES) vt = VT_FLIPPER_30;
        /* Default NoSkip: the skip variants run extra logic-only frames when rendering is slow
           (measured 45 logic ticks/s for 30 renders/s). NoSkip = 1 tick per render; the speed
           governor keeps real-time speed. */
        else vt = VT_FLIPPER_30NS;
        if (!WriteProcessMemory(GetCurrentProcess(), p, &vt, 8, NULL)) continue;
        flip_found++; flipper_obj = p;
        logmsg("flipper %p: 60FPS -> %llx", (void *)p, (unsigned long long)vt);
    }
}
static int swap_flipper(void) { flip_found = 0; scan_private(flip_chunk); return flip_found; }

static void report_chunk(const uint64_t *q, uint64_t *real, size_t n) {
    for (size_t i = 0; i + 6 <= n && i < 8192; i += 2)
        if (q[i] == VT_FLIPPER_MGR) logmsg("mgr %p mode %u flipper %p", (void *)(real + i), (uint32_t)q[i + 4], (void *)q[i + 5]);
}
static void report(void) { scan_private(report_chunk); }

/* ---- stack trace of the in-game-timer update (IGT += dt*1000 at 0x140758c5e) via a one-shot guard page ---- */
#define GAME_DATA_MAN 0x141c8a530ULL
static volatile LONG traced, flip_traced;
static void *guard_page;
static LONG CALLBACK veh(EXCEPTION_POINTERS *ep) {
    if (ep->ExceptionRecord->ExceptionCode != STATUS_GUARD_PAGE_VIOLATION) return EXCEPTION_CONTINUE_SEARCH;
    CONTEXT *c = ep->ContextRecord;
    uint64_t ea = ep->ExceptionRecord->ExceptionInformation[1];
    if (c->Rip >= 0x140204c80ULL && c->Rip < 0x140204d30ULL && flip_traced < 8) {   /* FrpgFlipper_30FPS slots */
        flip_traced++;
        uint32_t *r = (uint32_t *)c->Rdx;
        logmsg("flip rip=%llx rcx=%llx rdx=%llx", c->Rip, c->Rcx, c->Rdx);
        if (c->Rdx > 0x10000) for (int i = 0; i < 16; i++) logmsg("  rdx+%02x = %08x  %d  %f", i * 4, r[i], (int)r[i], *(float *)&r[i]);
        uint64_t *sp = (uint64_t *)c->Rsp;
        for (int i = 0, k = 0; i < 0x200 && k < 10; i++)
            if (sp[i] >= 0x140001000ULL && sp[i] < 0x142000000ULL) { logmsg("  [rsp+%03x] %llx", i * 8, sp[i]); k++; }
    }
    if (c->Rip >= 0x140758a30ULL && c->Rip < 0x140758c98ULL && traced < 3) {
        InterlockedIncrement(&traced);
        logmsg("IGT access rip=%llx addr=%llx xmm6(dt)=%f rsp=%llx", c->Rip, ea, c->Xmm6.Low ? *(float *)&c->Xmm6 : 0.f, c->Rsp);
        uint64_t *sp = (uint64_t *)c->Rsp;
        for (int i = 0; i < 0x400; i++)
            if (sp[i] >= 0x140001000ULL && sp[i] < 0x143000000ULL) logmsg("  [rsp+%03x] %llx", i * 8, sp[i]);
    }
    return EXCEPTION_CONTINUE_EXECUTION;   /* guard is one-shot; the agent thread re-arms it */
}
static void trace_igt(void) {
    uint64_t gdm = *(volatile uint64_t *)GAME_DATA_MAN;
    if (!gdm) return;
    if (!guard_page) { AddVectoredExceptionHandler(1, veh); guard_page = (void *)((gdm + 0xa4) & ~0xfffULL); logmsg("trace: guard page %p", guard_page); }
    DWORD old;
    VirtualProtect(guard_page, 1, PAGE_READWRITE | PAGE_GUARD, &old);
}

/* ---- sampling profiler: create "dsr_prof.go" (text: seconds) in the game dir -> the agent suspends the
   main thread ~1000x/s, unwinds its x86 stack (RtlVirtualUnwind) and writes one line per sample to
   dsr_prof.txt: "rip ret1 ret2 ...". Aggregate on the PC with tools/stackprof.py. No debugger needed. ---- */
static DWORD main_tid;
#define PROF_DEPTH 32
static void profile(int secs) {
    HANDLE th = OpenThread(THREAD_SUSPEND_RESUME | THREAD_GET_CONTEXT, FALSE, main_tid);
    FILE *f = fopen("dsr_prof.txt", "w");
    if (!th || !f) { logmsg("prof: open failed %lu", GetLastError()); if (f) fclose(f); return; }
    timeBeginPeriod(1);
    DWORD end = GetTickCount() + secs * 1000; int n = 0;
    while (GetTickCount() < end) {
        CONTEXT c; c.ContextFlags = CONTEXT_FULL; uint64_t st[PROF_DEPTH]; int d = 0;
        if (SuspendThread(th) == (DWORD)-1) break;
        if (GetThreadContext(th, &c)) {
            st[d++] = c.Rip;
            while (d < PROF_DEPTH) {
                DWORD64 base; RUNTIME_FUNCTION *rf = RtlLookupFunctionEntry(c.Rip, &base, NULL);
                if (!rf) break;   /* no unwind info (Arxan stubs, JIT): stop */
                void *hd; DWORD64 ef;
                RtlVirtualUnwind(UNW_FLAG_NHANDLER, base, c.Rip, rf, &c, &hd, &ef, NULL);
                if (!c.Rip) break;
                st[d++] = c.Rip;
            }
        }
        ResumeThread(th);
        for (int i = 0; i < d; i++) fprintf(f, i ? " %llx" : "%llx", (unsigned long long)st[i]);
        if (d) { fputc('\n', f); n++; }
        Sleep(1);
    }
    timeEndPeriod(1);
    fclose(f); CloseHandle(th);
    logmsg("prof: %d samples in %d s", n, secs);
}
static void check_profile(void) {
    FILE *g = fopen("dsr_prof.go", "r");
    if (!g) return;
    int secs = 20; fscanf(g, "%d", &secs); fclose(g); DeleteFileA("dsr_prof.go");
    logmsg("prof: start %d s, main tid %lu", secs, main_tid);
    profile(secs);
}

/* ---- input cost cuts (profile 2026-10-14: 13% of the main thread in GetAsyncKeyState, called for 236 keys
   every frame at 0x140ca06d9; each call is a wineserver round trip). The hooks serve a key table that the
   agent thread refreshes at 20 Hz. SystemParametersInfoA(SPI_GETMOUSE/SPI_SETMOUSE+SPIF_SENDCHANGE) runs every
   frame too (0x140ca1006): answer GET from a cache, drop SET. ---- */
static SHORT key_cache[256];
static SHORT (WINAPI *real_gaks)(int);
static BOOL (WINAPI *real_spi)(UINT, UINT, PVOID, UINT);
static int mouse_cache[3], mouse_cached;
static SHORT WINAPI hook_gaks(int vk) { return key_cache[vk & 0xff]; }
static BOOL WINAPI hook_spi(UINT a, UINT u, PVOID p, UINT w) {
    if (a == SPI_GETMOUSE && p) {
        if (!mouse_cached) { if (!real_spi(a, u, mouse_cache, w)) return FALSE; mouse_cached = 1; }
        memcpy(p, mouse_cache, sizeof mouse_cache); return TRUE;
    }
    if (a == SPI_SETMOUSE && p) { memcpy(mouse_cache, p, sizeof mouse_cache); mouse_cached = 1; return TRUE; }
    return real_spi(a, u, p, w);
}
static void refresh_keys(void) {
    if (!real_gaks) return;
    for (int vk = 1; vk < 256; vk++) key_cache[vk] = real_gaks(vk) & 0x8000;   /* held state only */
}
/* Replace an import of the exe (by DLL + function name). Returns the original pointer. */
static void *hook_iat(const char *dll, const char *fn, void *hook) {
    uint8_t *b = (uint8_t *)GetModuleHandleA(NULL);
    IMAGE_NT_HEADERS *nt = (IMAGE_NT_HEADERS *)(b + ((IMAGE_DOS_HEADER *)b)->e_lfanew);
    IMAGE_IMPORT_DESCRIPTOR *d = (IMAGE_IMPORT_DESCRIPTOR *)(b + nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT].VirtualAddress);
    for (; d->Name; d++) {
        if (_stricmp((char *)(b + d->Name), dll)) continue;
        IMAGE_THUNK_DATA *on = (IMAGE_THUNK_DATA *)(b + d->OriginalFirstThunk), *ft = (IMAGE_THUNK_DATA *)(b + d->FirstThunk);
        for (; on->u1.AddressOfData; on++, ft++) {
            if (IMAGE_SNAP_BY_ORDINAL(on->u1.Ordinal)) continue;
            if (strcmp((char *)((IMAGE_IMPORT_BY_NAME *)(b + on->u1.AddressOfData))->Name, fn)) continue;
            DWORD old; void *orig = (void *)ft->u1.Function;
            VirtualProtect(&ft->u1.Function, 8, PAGE_READWRITE, &old);
            ft->u1.Function = (ULONGLONG)hook;
            VirtualProtect(&ft->u1.Function, 8, old, &old);
            logmsg("iat %s!%s %p -> %p", dll, fn, orig, hook);
            return orig;
        }
    }
    logmsg("iat %s!%s not found", dll, fn);
    return NULL;
}
/* ---- event pool (profile: ~3% of the main thread in CreateEventW + CloseHandle; 0x140ccb9c7 creates an
   unnamed manual-reset event per request and closes it after). Under Wine both are wineserver round trips;
   Set/ResetEvent are not (esync). Unnamed manual-reset events are reused: CloseHandle parks them, CreateEventW
   takes a parked one and sets its state. Only handles this pool issued are parked. ---- */
#define POOL_MAX 256
static HANDLE (WINAPI *real_cev)(LPSECURITY_ATTRIBUTES, BOOL, BOOL, LPCWSTR);
static BOOL (WINAPI *real_close)(HANDLE);
static HANDLE pool_free[POOL_MAX]; static int npool_free;
static HANDLE pool_out[POOL_MAX * 4]; static int npool_out;   /* issued, not yet closed */
static CRITICAL_SECTION pool_cs;
static HANDLE WINAPI hook_cev(LPSECURITY_ATTRIBUTES sa, BOOL manual, BOOL init, LPCWSTR name) {
    if (sa || name || !manual) return real_cev(sa, manual, init, name);
    HANDLE h = NULL;
    EnterCriticalSection(&pool_cs);
    if (npool_free) h = pool_free[--npool_free];
    LeaveCriticalSection(&pool_cs);
    if (h) { if (init) SetEvent(h); else ResetEvent(h); }
    else h = real_cev(sa, manual, init, name);
    if (h) {
        EnterCriticalSection(&pool_cs);
        if (npool_out < POOL_MAX * 4) pool_out[npool_out++] = h;
        LeaveCriticalSection(&pool_cs);
    }
    return h;
}
static BOOL WINAPI hook_close(HANDLE h) {
    EnterCriticalSection(&pool_cs);
    for (int i = npool_out - 1; i >= 0; i--)
        if (pool_out[i] == h) {
            pool_out[i] = pool_out[--npool_out];
            if (npool_free < POOL_MAX) { pool_free[npool_free++] = h; LeaveCriticalSection(&pool_cs); return TRUE; }
            break;
        }
    LeaveCriticalSection(&pool_cs);
    return real_close(h);
}
static void hook_events(void) {
    if (GetFileAttributesA("dsr_nopool") != INVALID_FILE_ATTRIBUTES) return;
    InitializeCriticalSection(&pool_cs);
    real_cev = (void *)GetProcAddress(GetModuleHandleA("kernel32.dll"), "CreateEventW");
    real_close = (void *)GetProcAddress(GetModuleHandleA("kernel32.dll"), "CloseHandle");
    hook_iat("KERNEL32.dll", "CreateEventW", (void *)hook_cev);
    hook_iat("KERNEL32.dll", "CloseHandle", (void *)hook_close);
}

/* ---- character update LOD (0x14036e8d0 assigns chr+0x164 = update interval: 0 every tick, 2, 5, 30).
   Knobs in [0x141c77e88]: +0x2c = chars (by distance) at full rate (stock 10), +0x30 = chars considered
   near; others off-screen get interval 5 (stock 20), +0x34 = distance (m) for interval 5 vs 30 of
   inactive chars (stock 40). Tighter values = fewer full-rate character updates. Override: dsr_lod.txt
   "full near dist". ---- */
static void apply_lod(void) {
    static int full = 4, nearc = 8; static float dist = 25.0f; static int loaded;
    if (!loaded) {
        loaded = 1;
        FILE *f = fopen("dsr_lod.txt", "r");
        if (f) { if (fscanf(f, "%d %d %f", &full, &nearc, &dist) != 3) full = -1; fclose(f); }
        logmsg("lod: full %d near %d dist %.0f", full, nearc, dist);
    }
    if (full < 0) return;   /* "-1 0 0" = stock */
    uint8_t *w = *(uint8_t * volatile *)0x141c77e88ULL;
    if (!w) return;
    *(int *)(w + 0x2c) = full; *(int *)(w + 0x30) = nearc; *(float *)(w + 0x34) = dist;
}

#include "ui.c"
static void lock_apply(void);   /* lock.c / cam.c: run once per gameplay frame on the game thread, from the */
static void cam_apply(void);    /* HUD Update hook (hud.c). GetDeviceState runs on a separate input thread. */
#include "hud.c"
#include "lock.c"
#include "display.c"
#include "title.c"
#include "cam.c"

static void hook_input(void) {
    real_gaks = (SHORT (WINAPI *)(int))GetProcAddress(GetModuleHandleA("user32.dll"), "GetAsyncKeyState");
    refresh_keys();
    if (!hook_iat("USER32.dll", "GetAsyncKeyState", (void *)hook_gaks)) real_gaks = NULL;
    real_spi = (BOOL (WINAPI *)(UINT, UINT, PVOID, UINT))GetProcAddress(GetModuleHandleA("user32.dll"), "SystemParametersInfoA");
    hook_iat("USER32.dll", "SystemParametersInfoA", (void *)hook_spi);
}

static void trace_flip(void) {
    static int armed;
    if (!flipper_obj || flip_traced >= 8 || armed > 40) return;
    if (!guard_page) AddVectoredExceptionHandler(1, veh);
    guard_page = (void *)((uint64_t)flipper_obj & ~0xfffULL); armed++;
    DWORD old; VirtualProtect(guard_page, 1, PAGE_READWRITE | PAGE_GUARD, &old);
}

static DWORD WINAPI agent(LPVOID _) {
    logmsg("agent start");
    patch_tick();
    /* Pacer experiments (2026-10-14) are off: swapping FrpgFlipper_60FPS -> 30FPS did not change game
       speed, and the game re-applies mode 4 every frame. Kept for reference: swap_flipper(), report().
       report() can crash the game: it dereferences p[5] of false vtable matches. */
    (void)report; (void)trace_igt;
    hook_input();
    hook_events();
    hook_hud();
    hook_title();
    for (int t = 0, next = 0;; t++) {   /* 50 ms loop: key cache 20 Hz; once per second the slow jobs */
        refresh_keys();
        ui_poll();
        lock_poll();
        pin_display();
        patch_title_text(t);
        patch_offline_notice();
        title_poll();
        static int gov_off; if (t % 20 == 0) gov_off = GetFileAttributesA("dsr_nogov") != INVALID_FILE_ATTRIBUTES;
        if (!gov_off) governor(); else { *(float *)TICK_DT = 1.0f / 30.0f; }
        Sleep(50);
        if (t % 20) continue;
        int s = t / 20;   /* pacer (game may rebuild it): 1 s scans until found, then 10 s */
        if (s >= next) next = s + (swap_flipper() ? 10 : 1);
        check_profile();
        apply_lod();
        if (GetFileAttributesA("dsr_flip.go") != INVALID_FILE_ATTRIBUTES) trace_flip();
    }
    return 0;
}

/* Game logic runs fixed ticks of [TICK_DT] seconds (read once per frame at 0x14015cec9 and passed to every
   system); the FrpgFlipper pacer allows at most 2 ticks per rendered frame. DSR uses 1/60 -> needs 60 ticks/s
   for real-time speed. Patch to 1/30 (the original DS1 / Switch rate) + 30FPS pacer: one tick per frame at
   30 FPS (half the logic CPU), real-time speed down to 15 FPS. */
static void patch_tick(void) {
    DWORD old;
    float *t = (float *)TICK_DT;
    if (!VirtualProtect(t, 4, PAGE_READWRITE, &old)) { logmsg("tick: VirtualProtect failed %lu", GetLastError()); return; }
    float was = *t; *t = 1.0f / 30.0f;   /* page stays writable: the governor below retunes it */
    logmsg("tick dt %f -> %f", was, *t);
}

/* ---- speed governor: the number of logic ticks per frame varies with load (frame skip rules), so a fixed
   tick length never gives real-time speed at every FPS (measured 1.26-1.44x at 28-30 FPS, 1.04x at 15).
   Every 0.5 s: ticks run = dIGT / (int)(tick*1000) (IGT += (int)(tick*1000) once per tick, 0x140758c5e);
   new tick = real seconds / ticks, smoothed, clamped to [1/60, 1/10]. Game time then tracks real time. ---- */
static void governor(void) {
    static LARGE_INTEGER f, t0; static uint32_t igt0; static int have; static int n;
    float *tick = (float *)TICK_DT;
    uint64_t gdm = *(volatile uint64_t *)GAME_DATA_MAN;
    if (!gdm) { have = 0; return; }
    uint32_t igt = *(volatile uint32_t *)(gdm + 0xa4);
    LARGE_INTEGER t; QueryPerformanceCounter(&t);
    if (!f.QuadPart) QueryPerformanceFrequency(&f);
    if (have) {
        double real = (double)(t.QuadPart - t0.QuadPart) / f.QuadPart;
        int ms = (int)(*tick * 1000.0f);
        int32_t d = (int32_t)(igt - igt0);
        if (real < 0.3) return;   /* keep accumulating */
        if (d > 0 && ms > 0 && real < 2.0) {   /* d == 0: loading screen / paused -> leave the tick alone */
            double ticks = (double)d / ms, want = real / ticks, cur = *tick;
            double nt = cur + 0.5 * (want - cur);
            if (nt < 1.0 / 60) nt = 1.0 / 60;
            if (nt > 1.0 / 10) nt = 1.0 / 10;
            *tick = (float)nt;
            if (++n % 20 == 1) logmsg("gov: %.1f ticks/s -> tick %.4f (%.1f ms)", ticks / real, nt, nt * 1000);
        }
    }
    igt0 = igt; t0 = t; have = 1;
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD reason, LPVOID _) {
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(h);
        InitializeCriticalSection(&dev_cs);
        main_tid = GetCurrentThreadId();   /* static import: loaded on the game's main thread */
        logf = fopen("dsr_agent.log", "a");
        logmsg("dinput8 proxy loaded");
        /* flag file dsr_noagent: plain proxy, no patches / hooks / agent thread (A/B tests vs the stock game) */
        if (GetFileAttributesA("dsr_noagent") != INVALID_FILE_ATTRIBUTES) { logmsg("noagent flag: proxy only"); return TRUE; }
        hook_window();   /* before the game creates its window */
        patch_title_list();   /* static .data table, safe at load */
        patch_fonts();
        CreateThread(NULL, 0, agent, NULL, 0, NULL);
        CreateThread(NULL, 0, menu_hud_thread, NULL, 0, NULL);
    }
    return TRUE;
}

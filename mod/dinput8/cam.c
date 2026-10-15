/* cam.c (included by dinput8.c): faster touch camera. The app drives the camera with the right stick; the follow
   camera turns at (base + (max - base) * |stick|) rad/s (ChrExFollowCam update 0x14023704a, yaw += dt * stick *
   speed * 0.03 * ...), base 120 deg/s, max 260 deg/s: too slow for touch look on a 22:9 screen.
   cam_apply() (game thread, once per gameplay frame from hud.c) scales the speed fields +0x1fc..+0x228 (yaw/pitch
   base, max and acceleration pairs) by CAM_SPEED. The stock values are kept per camera object and re-applied when
   the game rebuilds or resets them.
   ChrExFollowCam = [[[0x141c7a488]+0x60]+0x60] (DSR-Gadget ChrFollowCam). Writing yaw (+0x144) / pitch (+0x140)
   directly does not hold: the update recomputes them each frame. Flag file dsr_stockcam = stock speed. */

#define P_CHRCAM_ROOT 0x141c7a488ULL
#define CAM_SPEED 1.5f
#define CAM_F0 (0x1fc / 4)
#define CAM_NF 12

static int cam_off = -1;

static uint8_t *follow_cam(void) {
    uint8_t *root = *(uint8_t * volatile *)P_CHRCAM_ROOT;
    if (!root) return NULL;
    uint8_t *chrcam = *(uint8_t * volatile *)(root + 0x60);
    if (!chrcam) return NULL;
    return *(uint8_t * volatile *)(chrcam + 0x60);
}

static void cam_apply(void) {
    static uint8_t *last;
    static float stock[CAM_NF];
    if (cam_off < 0) {
        cam_off = GetFileAttributesA("dsr_stockcam") != INVALID_FILE_ATTRIBUTES;
        if (cam_off) logmsg("cam: stock speed (flag)");
    }
    if (cam_off) return;
    uint8_t *fc = follow_cam();
    if (!fc) return;
    float *f = (float *)fc + CAM_F0;
    if (fc != last) {
        if (f[0] <= 0.1f || f[0] > 20.f) return;   /* not initialised yet */
        last = fc;
        for (int i = 0; i < CAM_NF; i++) stock[i] = f[i];
        logmsg("cam: follow cam %p, speed x%.2f (yaw base %.3f max %.3f)", (void *)fc, CAM_SPEED, stock[1], stock[7]);
    }
    for (int i = 0; i < CAM_NF; i++) if (f[i] == stock[i]) f[i] = stock[i] * CAM_SPEED;   /* (re)apply after resets */
}

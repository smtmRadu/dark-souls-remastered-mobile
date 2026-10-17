"""patch_menu.py: move stock HUD elements in menu/menu.drb.dcx so they sit next to the app's touch controls.

  python patch_menu.py [GAME_DIR] [OUT_FILE]     (default OUT_FILE: out/menu.drb.dcx)

The game folder is only read. The patched file replaces <game>/menu/menu.drb.dcx on the phone (part of the v1.0.0
mod set, .track/v1.0.0.md). Coordinates are DRB design units: 720 high, 1 unit = H/720 screen px. Elements with
scaling type 1 / 2 stick to the left edge (origin x 0), type 3 to the right (origin 1280), so at 22:9 a left-anchored
element keeps its x and the app's controls (placed in screen fractions) line up with x = fraction * 720 * W/H.

Shape params (SHPR): rect L,T,R,B (i16 x4), scaling origin X,Y (i16 x2), scaling type (i32), then type-specific
data. Text: byte +0x1e = alignment flags (1 right, 2 centre-x, 8 centre-y; 0 = top-left), byte +0x1c = font.
Mistake to avoid: +0x14 (values 0/1/3/7) looks like alignment but changes nothing.
"""
import os, struct, sys
from fromsoft.containers import dcx_decompress, dcx_compress
from fromsoft.drb import _chunks

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.join(HERE, '..', 'local', 'game')

# Flip6 / controls-6.icp: Estus slot centre x 0.125 * 2640 px = 330 px = 220 units, box ~139..297 x 127..284.
EDITS = {
    # (dialog, object): (rect, origin, scaling type, text alignment or None)
    # quick item name ("Estus Flask"): centred under the app's Estus slot (stock: right of the stock slot block)
    ('F20-00', 'text_item_name'): ((95, 294, 345, 318), (0, 0), 1, 0x02),
    # souls counter: right under the HP / stamina bars, same left edge (stock: bottom-right corner, origin 1280,720).
    # The dialog rect shifts its 1280x720 child space: parchment child x 1027, y 626 -> screen 386 + 0, 190
    ('F20-00', 'soul_param'): ((2 - 643, 6 - 442, 1282 - 643, 726 - 442), (0, 0), 1, None),
    # souls gained ("+1234"): right of the souls box instead of above it
    ('soul_param', 'text_param_getsoul'): ((1190, 630, 1318, 658), (-1, -1), 0, None),
    # souls number left-aligned, vertically centred (stock 0x09 = right + v-centre)
    ('soul_param', 'text_param_soul'): ((1041, 630, 1169, 658), (-1, -1), 0, 0x08),
}

# Main menu (T00-00): all entries in one row under the logo (stock: vertical list scrolled 4 at a time).
# Rows button3_0..button7_0 = 5 text slots. The agent (mod/dinput8/title.c) drops "Log In" from the entry table, so
# the list has 5 entries and the game's no-scroll mode puts entry i in slot i (highlight = cursor<i>_0 rect).
# Bigger font: 11 (35-unit titles) instead of 6 (28). Fade masks and scroll arrows go off-screen.
# The logo is not moved: shifting the Title00/02/03 dialogs or their title* sprites changed nothing.
# Full 22:9 width (user 2026-10-15): the visible design x range is about -240..1520, so the 5 entries spread over
# -60..1340 (350 apart, 300 wide) and are 72 units high (2x), text centred. The app's tap geometry
# (InputControlsView DSR_TITLE_*) must match.
MENU_Y, MENU_H, MENU_HALF_W = 520, 72, 150
MENU_SLOTS = (-60, 290, 640, 990, 1340)            # centre x of the 5 entries
FONTS = {}
NULL_RECTS = {}
for _i, _cx in enumerate(MENU_SLOTS):
    EDITS[('T00-00', f'button{_i + 3}_0')] = ((_cx - MENU_HALF_W, MENU_Y, _cx + MENU_HALF_W, MENU_Y + MENU_H), (-1, -1), 0, 0x0a)
    FONTS[('T00-00', f'button{_i + 3}_0')] = 11
    NULL_RECTS[('T00-00', f'cursor{_i}_0')] = (_cx - MENU_HALF_W, MENU_Y, _cx + MENU_HALF_W, MENU_Y + MENU_H)
# System list rows widened (stock 332..568): the 2x font needs room (the game does not shrink text to its box).
# Key settings (entry 2) hidden (user 2026-10-15: no key remapping on a phone): its text and hit rect go off-screen,
# entries 3..5 move up one row (30 units). Entry i is still drawn in button<i>_0 and hit-tested on cursor<i>_0; a
# d-pad step can still land on the hidden row (touch never does). Frame / parchment lose one row (SYS_TRIM).
SYS_ROW_Y = [160, 193, None, 226, 259, 292]     # stock 160, 191, 221, 251, 281, 311
SYS_ROW_H = 31   # 2026-10-16: rows spread over the frame's empty bottom band (pitch 30 -> 33; 38 overran the frame)
for _i, _y in enumerate(SYS_ROW_Y):
    if _y is None:
        EDITS[('I06-00', f'button{_i}_0')] = ((-2000, -2000, -1968, -1984), (-1, -1), 0, None)
        NULL_RECTS[('I06-00', f'cursor{_i}_0')] = (-2000, -2000, -1968, -1984)
        continue
    EDITS[('I06-00', f'button{_i}_0')] = ((332, _y, 800, _y + SYS_ROW_H), (-1, -1), 0, 0x08)   # text v-centred
    NULL_RECTS[('I06-00', f'cursor{_i}_0')] = (327, _y, 800, _y + SYS_ROW_H)
# System list (I06) and item command menu (I01-01): bigger by scaling the whole dialogs (DIALOG_SCALES below), so
# frames, divider lines and highlight rects grow with the rows. (Moving rows one by one left the frame and divider
# lines at the old spacing.)
# Game tab strip (R00 / R00-00: HOME < 4 icons > END + help line) hidden: the app draws big side tabs and clicks
# these icons. Frame, help texts, LB/RB arrows and the cursor go off-screen; the icons stay in place (click targets)
# with colour 0 (invisible).
HIDE_TAB_STRIP = True
TAB_STRIP_OFF = [('R00', 'BG'), ('R00', 'R04-02'), ('R00', 'R04-03'), ('R00-00', 'category_LR'),
                 ('R00-00', 'plate_black'), ('R00-00', 'R00_arrowlr'), ('R00-00', 'cursor'), ('R00-00', 'stay_cursor')]
TAB_STRIP_CLEAR = [('R00-00', f'{n}_{i}') for n in ('changeover',) for i in range(4)] +                   [('R00-00', n) for n in ('icon_inventory', 'icon_equip', 'icon_status', 'icon_qwc')]

# inventory / equipment item-type strip: the < > arrows at its ends (user: no sense on touch, the types are tapped)
TAB_STRIP_CLEAR += [('I01_tab_arrow', 'I01_arroe_l'), ('I01_tab_arrow', 'I01_arroe_r')]

# Rect-only edits (origin, scaling type and the rest of the params kept), optional new font: (rect, font or None).
RECTS = {}
# Item command menu (I01-01: Use Item / Drop / Change Order / Reset Order): rows 30 -> 65 child units inside the
# box (238..508, room for 4 such rows), on top of the dialog's x1.5 / y2.0 (DIALOG_SCALES). The divider-line sprite
# (lines 30 apart) is hidden: it cannot follow the new spacing.
for _i in range(4):
    _t = 243 + 65 * _i
    NULL_RECTS[('I01-01', f'cursor{_i}_0')] = (495, _t, 786, _t + 62)
    RECTS[('I01-01', f'button{_i}_0')] = ((514, _t + 16, 759, _t + 46), None)
for _i in range(2):   # greyed-out Use / Drop (36 high, centred on its row)
    _t = 243 + 65 * _i
    RECTS[('I01-01', f'grayout_drop0{_i}')] = ((502, _t + 13, 770, _t + 49), None)
RECTS[('I01-01', 'R03_note_line')] = ((-2000, -2000, -1968, -1984), None)
# General message box (R09: "Quit game?" OK / Cancel, "Game will start in offline mode." OK): buttons 40 -> 80 units
# high (user 2026-10-15: easy to press), font 9 -> preset 2 (1.4x). The box grows 20 down to hold them.
for _i, (_l, _r) in enumerate([(370, 608), (659, 897), (514, 752)]):
    NULL_RECTS[('R09-00', f'cursor_button0_{_i}')] = (_l, 500, _r, 580)
    RECTS[('R09-00', f'text_button0_{_i}')] = ((_l + 25, 525, _r - 21, 555), 2)
RECTS[('R09-00', 'R09_bg')] = ((201, 155, 1091, 593), None)
# Question box with OK / Cancel (F05-00: "Quit game?", text_question + text_ok / text_cancel; R09 alone did not
# change the Quit Game box, user 2026-10-15): buttons 40 -> 80 units high, 1.4x font; box 562..663 -> 562..703.
# The divider-line sprite is hidden (it cannot stretch).
RECTS[('F05-00', 'cursor_button0_0')] = ((392, 603, 637, 683), None)
RECTS[('F05-00', 'cursor_button0_1')] = ((646, 603, 892, 683), None)
RECTS[('F05-00', 'text_ok')] = ((418, 627, 610, 659), 2)
RECTS[('F05-00', 'text_cancel')] = ((673, 627, 865, 659), 2)
RECTS[('F05-00', 'R03_bg_2line')] = ((331, 562, 949, 703), None)
RECTS[('F05-00', 'R03_note_line')] = ((-2000, -2000, -1968, -1984), None)

# System list divider lines (parchment sprites F25_note_0 / note_line1) hidden: with the taller, re-spaced rows they
# no longer sat between the rows (user 2026-10-16: "the background no longer matches the buttons").
for _d in ('I06_parchment6r', 'I06_parchment5r', 'I06_parchment4r'):
    for _n in ('F25_note_0', 'note_line1'):
        RECTS[(_d, _n)] = ((-2000, -2000, -1968, -1984), None)
# Bonfire overlay (F23_Bonfire: full-screen tint BG, dark band BG_bar + gradients, "BONFIRE LIT" text): the full-width
# layers are 0..1280 wide, so at 22:9 the screen sides stayed uncovered (user 2026-10-16). Widened to -400..1680
# (covers up to ~3.1:1); off-screen on 16:9, so harmless there.
for _n, (_t, _b) in {'BG': (0, 720), 'BG_grad00': (283, 327), 'BG_grad01': (431, 475), 'BG_bar': (327, 431)}.items():
    RECTS[('F23_Bonfire', _n)] = ((-400, _t, 1680, _b), None)

# Question boxes (R03 family: "Are you sure you want to save the game and return to Title Menu?" = R03-02, OK /
# CANCEL; R03-01 one button, R03-03 number entry, R03-11 / R03-12 big box). R09 and F05 were wrong guesses (user
# 2026-10-16: still small). Buttons, their hit rects and the highlight (cursor dialog) 2x high around their middle,
# text 1.4x and centred (align 0x0a). Coordinates are in each box's own space (R03 places the boxes).
R03_BUTTONS = {
    'R03-01': [(174, 426, 184, 212)],
    'R03-02': [(40, 292, 182, 210), (304, 556, 182, 210)],
    'R03-03': [(107, 282, 213, 241), (302, 477, 213, 241)],
    'R03-11': [(273, 525, 331, 359)],
    'R03-12': [(103, 355, 333, 361), (422, 674, 334, 362)],
}
TEXT_ALIGN = {}
# R03-01 / R03-02 (user 2026-10-16): window 2x high and 1.5x wide (dialog scale in R03 around the screen centre),
# buttons 3x the 56-unit height above (84 child units x 2.0 = 168 on screen) and 1.5x wide (from the scale), button
# text preset 1 (2.0x), message text preset 2 (1.4x). Child space: message 64..123, buttons 140..224, box 0..233.
R03_BIG = {'R03-01', 'R03-02'}
FONT_BUMPS_R03 = {'R03-01': {8: 2}, 'R03-02': {8: 2}}   # text_message (button texts get preset 1 via RECTS)
for _d, _bs in R03_BUTTONS.items():
    for _i, (_l, _r, _t, _b) in enumerate(_bs):
        _c, _h = (_t + _b) / 2, _b - _t
        _big = (_l, 140, _r, 224) if _d in R03_BIG else (_l, round(_c - _h), _r, round(_c + _h))
        NULL_RECTS[(_d, f'cursor_button0_{_i}')] = _big
        RECTS[(_d, f'text_button0_{_i}')] = (_big, 1 if _d in R03_BIG else 2)
        TEXT_ALIGN[(_d, f'text_button0_{_i}')] = 0x0a
        if _i == 0 and _d != 'R03-03':   # the highlight: button size (R03-03's cursor is the number field's)
            RECTS[(_d, 'cursor')] = (_big, None)

_OFF = (-2000, -2000, -1968, -1984)
EDITS.update({(('T00-00', n)): (_OFF, (-1, -1), 0, None) for n in ('arrow_up', 'arrow_down', 'hide_top', 'hide_bottom')})

# HP / stamina group: right of the Estus slot (humanity ring left edge 96 -> 307, top 54 -> 127). Status / broken
# equipment icons go under the souls box. Shifted as a block: (dialog, name or prefix*, dx, dy).
HP_DX, HP_DY = 211, 73
SHIFTS = [
    ('F20-00', 'plate_hp*', HP_DX, HP_DY), ('F20-00', 'bar_*', HP_DX, HP_DY), ('F20-00', 'plate_sp', HP_DX, HP_DY),
    ('F20-00', 'HP_endbar', HP_DX, HP_DY), ('F20-00', 'SP_endbar', HP_DX, HP_DY),
    ('F20-00', 'F20-02', HP_DX, HP_DY),                                   # humanity ring + counter
    ('F20-00', 'icon_state*', HP_DX, HP_DY + 118), ('F20-00', 'icon_broke_*', HP_DX, HP_DY + 118),
    # System list: greyed-out rows (Quit Game / Load Game at the title) follow their entries up one row
    ('I06-00', 'grayout_loadgame3', 0, 259 - 281), ('I06-00', 'grayout_loadgame2', 0, 292 - 311),]

# System list frame + parchment one row (30 units) shorter (Key settings hidden). The game ships 6 / 5 / 4 row
# variants that differ exactly so: pieces below y 240 move up 30, pieces crossing it lose 30 at the bottom. The
# divider-line sprite note_line1 (3 lines, 30 apart) moves up whole: its first line lands on F25_note_0's last one.
SYS_TRIM_DLGS = {f'I06_{k}{n}r' for k in ('frame_big', 'parchment') for n in (6, 5, 4)}


def sys_trim(oname, r):
    l, t, rr, b = r
    if oname == 'note_line1' or t >= 240:
        return (l, t - 30, rr, b - 30)
    if b >= 240:
        return (l, t, rr, b - 30)
    return None


# Brightness page (T07-00, user 2026-10-16: make the < > bigger). The slider row (cy 566) doubles in height, text
# 1.4x; the < > pair (shared dialog R01_arrowlr) is drawn 1.3x wide / 2x high (arrows ~33 x 48 units, just outside
# the bar); OK / Defaults move down 44 like the other option pages, 2x text, hit rects 48 high.
RECTS[('T07-00', 'text_brightness')] = ((304, 538, 542, 594), 2)
RECTS[('T07-00', 'button0_0')] = ((558, 538, 916, 594), 2)
for _n in ('bar0_0', 'grayout_plate0'):
    RECTS[('T07-00', _n)] = ((563, 542, 912, 590), None)
RECTS[('T07-00', 'parame_plate00')] = ((552, 536, 924, 596), None)
RECTS[('T07-00', 'arrow0_0')] = ((469, 542, 1015, 590), None)
RECTS[('T07-00', 'text_apply')] = ((377, 624, 621, 668), 1)
RECTS[('T07-00', 'text_reset')] = ((660, 624, 904, 668), 1)
RECTS[('T07-00', 'Option_line_0')] = ((389, 663, 618, 670), None)
RECTS[('T07-00', 'Option_line_2')] = ((665, 663, 894, 670), None)
NULL_RECTS[('T07-00', 'cursor0_0')] = (297, 538, 552, 594)   # label cell (the highlight follows it)
NULL_RECTS[('T07-00', 'cursor1_0')] = (377, 622, 621, 670)
NULL_RECTS[('T07-00', 'cursor2_0')] = (660, 622, 904, 670)

# Bottom message boxes (R03-21: message + OK, e.g. "Cannot kindle while Hollow"; R03-22: message + two buttons),
# placed in R03 at y 563..663 = under the app's item slot row (user 2026-10-17: covered, too small). Moved to the
# screen centre, 1.5x wide / 2x high (the dest rect scales the child), message 1.4x and buttons 2x text.
for _d in ('R03-21', 'R03-22'):
    RECTS[('R03', _d)] = ((176, 260, 1107, 460), None)

# Rules applied to every object (not Null shapes: their params are not a rect):
# - in-game menus (inventory I*, equipment/status R*, system T07 ...) are anchored to the right edge: scaling origin
#   (1280, 0). Origin (640, 0) centres them on the 22:9 screen.
# - the key-guide line ("E:Item Menu  Q:Close ...") is hidden; the app draws touch buttons for those actions.
# Bigger screens: a Dialog shape is a dest rect + (at +0x20) the child-space source rect, so a bigger dest rect
# scales the child dialog. (parent, child dialog): factor around SCALE_CENTRE (1280x720 design units).
# (parent, child dialog): ((kx, ky), centre). Text does not scale with the dialog (glyphs keep their font size), so
# FONT_BUMPS raise the fonts of the scaled lists. The headers (*_category_name, holding the tab click targets) are
# never scaled: a counter-scaled header came out misplaced (tested 2026-10-15).
_SYS = ((1.15, 2.3), (640, 130))     # System list: rows 30 -> 69 units (finger size), frame grows down
DIALOG_SCALES = {
    # Options (R01): list, right column, frames; parchment and header stay
    # Options (R01): two columns (OPTION_COLUMNS below); parchment + outer frame widened to hold them
    ('R01_parchment', 'parchment1'): ((1.5, 1.0), (640, 384)), ('R01_parchment', 'R01_frame_big'): ((1.5, 1.0), (640, 384)),
    # System list (I06): list + frame stretched down; the parchment's lower sprites grow with it (STRETCH_DOWN)
    ('I06', 'I06-00'): _SYS, ('I06_parchment6r', 'I06_frame_big'): _SYS,
    ('I06_parchment5r', 'I06_frame_big_console'): _SYS, ('I06_parchment4r', 'I06_frame_big_console'): _SYS,
    # the row divider lines are parchment sprites (not in the frame): same stretch, so they stay under the rows
    **{(d, s): _SYS for d in ('I06_parchment6r', 'I06_parchment5r', 'I06_parchment4r') for s in ('F25_note_0', 'note_line1')},
    # item command menu (Use / Drop / Change order / Reset order): box + rows x1.4 around the box centre
    ('I01', 'I01-01'): ((1.5, 2.0), (640, 369)),   # rows 30 -> 60 units
}
# Bonfire menu / NPC talk choices = F04-01 (FrpgMenuDlgTalkMsgbox, docs/ui/BONFIRE_MENU_RE.md; F09 is the warp list).
# Stock: frame BG / F04_frame_PC 67..497 x 64..664 (own space 430x600), 11 rows of 30 units from y 191.
# User 2026-10-16: rows 2.5x taller, frame ~1.1x taller. Rows 30 -> 72 units (text box 70, 1.4x font, centred
# vertically). 8 rows (the longest bonfire list) need 576 units, so the frame grows to 10..710 (x1.17) and its
# ornaments move to the edges of its own 430x600 space: the inner box (stock 101..476) becomes 26..574 = screen
# 40..680. The row divider texture (C05_masic_note_line, stock 30-unit pitch) is hidden: it cannot match 72.
# Rows 8..10 (only long NPC lists) run past the frame.
TALK_TOP, TALK_PITCH, TALK_H = 72, 72, 70
TALK_FRAME = (67, 10, 497, 710)
RECTS[('F04-01', 'BG')] = (TALK_FRAME, None)
# scroll strip (F04_frame_PC: arrows + bar) and the scroll thumb hidden (user 2026-10-16: lists fit, no scrolling)
RECTS[('F04-01', 'F04_frame_PC')] = ((-2000, -2000, -1968, -1984), None)
for _i in range(11):
    _t = TALK_TOP + TALK_PITCH * _i
    RECTS[('F04-01', f'button{_i}_0')] = ((138, _t, 483, _t + TALK_H), 2)
    TEXT_ALIGN[('F04-01', f'button{_i}_0')] = 0x08
    NULL_RECTS[('F04-01', f'cursor{_i}_0')] = (138, _t, 483, _t + TALK_H)
    if _i < 5:
        NULL_RECTS[('F04-01', f'grayout_drop{_i}')] = (138, _t, 483, _t + TALK_H)
RECTS[('F04-01', 'scrollbar')] = ((-2000, -2000, -1968, -1984), None)
RECTS[('F04-01', 'text_key-guide')] = ((-2000, -2000, -1968, -1984), None)
# Covenant / bonfire warp list (F09 + F09-06, same frame; user 2026-10-17: covenant rows tiny). It can scroll (warp
# lists are long) and the game fills 11 rows per page, so all 11 must fit: pitch 30 -> 56 (text box 54, 1.4x font),
# rows 72..688 inside the same tall frame as the bonfire list. The scroll strip stays (frame size).
for _i in range(11):
    _t = TALK_TOP + 56 * _i
    RECTS[('F09-06', f'button{_i}_0')] = ((138, _t, 483, _t + 54), 2)
    TEXT_ALIGN[('F09-06', f'button{_i}_0')] = 0x08
    NULL_RECTS[('F09-06', f'cursor{_i}_0')] = (138, _t, 483, _t + 54)
RECTS[('F09', 'BG')] = (TALK_FRAME, None)
RECTS[('F09-06', 'F04_frame_PC')] = (TALK_FRAME, None)
RECTS[('F09-06', 'scrollbar')] = ((127, TALK_TOP, 137, TALK_TOP + 56 * 11), None)
RECTS[('F09-06', 'text_key-guide')] = ((-2000, -2000, -1968, -1984), None)
# frame ornaments (F04_bg, own space 430x600): corners / bars to the edges
for _n, _r in {'R03_bg_normal': (7, 0, 487, 600), 'F04_frame_3': (16, 2, 87, 79), 'F04_frame_4': (397, 2, 468, 79),
               'object2': (87, 8, 397, 23), 'F04_frame_6': (17, 519, 92, 600), 'F04_frame_7': (394, 519, 469, 600),
               'object3': (88, 578, 394, 593), 'object1': (24, 79, 39, 519), 'F04_frame_1': (446, 79, 461, 519)}.items():
    RECTS[('F04_bg', _n)] = (_r, None)
# inner box (F04_frame) and scroll strip (F04_frame_PC): stock 101..476 -> 26..574; small parts keep their size
def _talk_inner(r):
    l, t, rr, b = r
    if b - t < 40:   # end pieces: shift with the nearer end
        d = 26 - 101 if t < 290 else 574 - 476
        return (l, t + d, rr, b + d)
    k = (574 - 26) / (476 - 101)
    return (l, round(26 + (t - 101) * k), rr, round(26 + (b - 101) * k))
for _d, _parts in (('F04_frame', {'I01_simple_small_note_2': (68, 101, 420, 120), 'I01_simple_small_note_1': (68, 457, 420, 476),
                                  'I01_simple_small_note_3': (60, 107, 79, 468), 'I01_simple_small_note_4': (408, 107, 427, 468)}),
                   ('F04_frame_PC', {'I01_simple_small_note_2': (59, 101, 72, 120), 'I01_simple_small_note_1': (60, 457, 70, 476),
                                     'I01_simple_small_note_3': (49, 106, 68, 468), 'I01_simple_small_note_4': (58, 113, 71, 132),
                                     'scroll_>': (60, 110, 71, 121), 'scroll_>1': (60, 454, 71, 465),
                                     'I01_simple_small_note_5': (60, 446, 70, 465), 'I01_simple_small_note_6': (60, 107, 79, 468)})):
    for _n, _r in _parts.items():
        RECTS[(_d, _n)] = (_talk_inner(_r), None)
RECTS[('F04_frame', 'C05_masic_note_line')] = ((-2000, -2000, -1968, -1984), None)
# Level Up (C01-03, placed at (96, 135) in C01): the game's ACCEPT entry (text_param4 + tex_line_0) hidden, the app has
# its own Accept button (user 2026-10-16). Its hit rect cursor1_0 shrinks to a 4-unit dot at the entry's centre
# (175, 464) = screen design (271, 599): only the app's Accept click lands there, the highlight bar is a dot.
RECTS[('C01-03', 'text_param4')] = ((-2000, -2000, -1968, -1984), None)
RECTS[('C01-03', 'tex_line_0')] = ((-2000, -2000, -1968, -1984), None)
NULL_RECTS[('C01-03', 'cursor1_0')] = (173, 462, 177, 466)
# Character creation (T02 main screen, T03 face edit): the window moves 230 units left (it spans ~52..1231 of the
# centred 1280 space; the 22:9 screen starts at -240), so design x 1030..1520 on the right is free for the app's
# Select / Back / d-pad buttons (user 2026-10-16). BG = the parchment window + header + portrait: moves too.
CHAR_SHIFT = -230
for _d, _n in (('T02', 'BG'), ('T02', 'T02-00'), ('T02', 'T02-01'), ('T02', 'T02-02'), ('T03', 'BG'),
               *(('T03', _x) for _x in ('T03-01', 'T03_frame', 'T03-00', 'T03-02', 'T03-03', 'T03-05', 'T03-06',
                                        'T03-07', 'T03-08', 'T03-04'))):
    RECTS[(_d, _n)] = ((CHAR_SHIFT, -2 if _n == 'T03-04' else 0, 1280 + CHAR_SHIFT, 106 if _n == 'T03-04' else 720), None)
# Bandai Namco splash dark mode (user 2026-10-16): the logo texture is recoloured by dark_splash.py; the four white
# MonoRects around it (logo_BNG object1..4, the 22:9 side bars) become black. MonoRect params: rect, scale origin,
# scale type, palette index (+0x10), unk, colour RGBA (+0x18, stock ff ff ff ff).
MONO_COLOR = {('logo_BNG', f'object{_i}'): bytes((0, 0, 0, 255)) for _i in range(1, 5)}
# Title version block: info_versionReg two lines tall for "Regulation ver. 1.04" + "Modder: kbRadu" (agent title.c
# patch_version_text appends the second line; user 2026-10-16)
RECTS[('T00-00', 'info_versionReg')] = ((96, 130, 596, 186), None)
# Text shape byte +0x12 = line spacing (0 on single-line shapes: a 2nd line drew over the 1st; message boxes use
# 0x1c).
SHAPE_BYTES = {('T00-00', 'info_versionReg'): {0x12: 36}}   # 25 gave an 18-unit gap; 36 matches the 26-unit App -> Reg gap
# Key settings (R13 controller / R15 keyboard tab): the list fills the screen height, so only x1.1 + bigger fonts
for _r in ('R13', 'R15'):
    DIALOG_SCALES[(_r, f'{_r}-00')] = ((1.1, 1.1), (640, 384))
    DIALOG_SCALES[(f'{_r}_parchment', 'R13_frame_big')] = ((1.1, 1.1), (640, 384))
    DIALOG_SCALES[(f'{_r}_parchment', 'R13_note_line')] = ((1.1, 1.1), (640, 384))
# Options page (R01-00 + its bar frames R01_parame_plate): 14 rows of 30 units in one column -> two columns of 7
# rows of 68 units (the 22:9 screen is wide, not tall). Every object is assigned to the row whose highlight rect
# (cursor<i>_0) centre is nearest; it moves with the row; Text and Null (highlight / hit) rects grow x2 in height,
# sprites and dialogs (bars, arrows, bar frames) only move. Category labels (Controls / Display / Sound) and the row
# divider lines (R01_frame) are hidden. OK / Defaults move under the columns.
OPTION_ROWS = [160, 190, 220, 250, 280, 310, 340, 370, 400, 430, 460, 488, 518, 548]   # stock cursor<i>_0 tops
OPTION_TOP, OPTION_STEP, OPTION_H = 140, 68, 56
# per column: label x0 .. x0 + OPTION_LABEL_W (labels at font 2 = 1.4x: "Camera auto wall recovery" ~330 units;
# the game does not shrink text to its box width), then the value group (stock x 540..963: arrows, bar, value text)
# squeezed x0.8 from x0 + OPTION_LABEL_W + 10. Column ~680 units; both fit between the screen's left edge and the
# app's action buttons (x -240 .. ~1320 at 22:9).
OPTION_X0 = (-200, 560)
OPTION_LABEL_W, OPTION_VALUE_K = 330, 0.8
OPTION_FOOT_DY = 44                           # OK / Defaults row (stock y 586) -> 630
OPTION_HIDE = {('R01-00', 'text_key'), ('R01-00', 'text_screen'), ('R01-00', 'text_sound'), ('R01_parchment', 'R01_frame')}


def option_rect(dname, oname, stype, r):
    """New rect for an Options object, or None (not part of a row)."""
    if (dname, oname) in OPTION_HIDE:
        return OFF_SCREEN
    l, t, rr, b = r
    cy = (t + b) / 2
    if 575 <= t <= 615:                       # OK / Defaults + their highlight and underline
        return (l, t + OPTION_FOOT_DY, rr, b + OPTION_FOOT_DY)
    if not (150 <= cy <= 590 and rr > 300 and l < 1000 and b - t < 60):
        return None
    i = min(range(len(OPTION_ROWS)), key=lambda k: abs(OPTION_ROWS[k] + 14 - cy))
    if abs(OPTION_ROWS[i] + 14 - cy) > 18:
        return None
    c, j = divmod(i, 7)
    ncy = OPTION_TOP + j * OPTION_STEP + OPTION_H / 2 + (cy - OPTION_ROWS[i] - 14) * 2
    h = (b - t) * 2 if stype in ('Text', 'Null') else b - t
    x0 = OPTION_X0[c]
    if l >= 530:                              # value group
        vx = x0 + OPTION_LABEL_W + 10
        nl, nr = vx + (l - 540) * OPTION_VALUE_K, vx + (rr - 540) * OPTION_VALUE_K
    elif stype == 'Null':                     # highlight / hit rect: the label cell
        nl, nr = x0 - 20, x0 + OPTION_LABEL_W
    else:                                     # label
        nl, nr = x0 + (l - 331), x0 + OPTION_LABEL_W
    return (round(nl), round(ncy - h / 2), round(nr), round(ncy + h / 2))


# PC settings page (R14-00 + its value texts R14-01): 8 rows of 30 units -> 58 units in one column, same rules as
# option_rect (Text / Null x2 high, sprites and dialogs only move). Labels get a wider cell to the left (the category
# labels Controls / Sound that sat there are hidden): the game does not shrink the 1.4x text to its box.
PC_ROWS = [190, 220, 250, 280, 340, 370, 400, 430]          # stock cursor<i>_0 tops
PC_TOP, PC_STEP, PC_H = 146, 58, 50
PC_LABEL = (130, 562)
PC_HIDE = {('R14-00', 'text_key'), ('R14-00', 'text_sound'), ('R14_parchment', 'R01_frame')}
# Network settings (R16 = 6 rows, R17 = 5 rows; same frame as PC settings, user 2026-10-16: OK small, no way out):
# same treatment, rows 30 units apart from 190. page prefix -> stock row tops
PC_PAGES = {'R14': PC_ROWS, 'R16': [190, 220, 250, 280, 309, 339], 'R17': [190, 220, 250, 280, 310]}
PC_HIDE |= {('R16_parchment', 'R01_frame'), ('R17_parchment', 'R01_frame')}


def pc_rect(dname, oname, stype, r):
    """New rect for a PC settings object, or None (not part of a row)."""
    if (dname, oname) in PC_HIDE:
        return OFF_SCREEN
    rows = PC_PAGES[dname[:3]]
    l, t, rr, b = r
    cy = (t + b) / 2
    if 575 <= t <= 620:                       # Apply / Reset + their highlight and underline
        return (l, t + OPTION_FOOT_DY, rr, b + OPTION_FOOT_DY)
    i = min(range(len(rows)), key=lambda k: abs(rows[k] + 14 - cy))
    if abs(rows[i] + 14 - cy) > 18 or b - t > 60:
        return None
    ncy = PC_TOP + i * PC_STEP + PC_H / 2 + (cy - rows[i] - 14) * 2
    h = (b - t) * 2 if stype in ('Text', 'Null', 'MonoRect') else b - t
    if stype in ('Null', 'MonoRect'):         # highlight / hit rect / greyed-out row: from the label cell
        l = PC_LABEL[0]
    elif l < 540:                             # label
        l, rr = PC_LABEL
    return (round(l), round(ncy - h / 2), round(rr), round(ncy + h / 2))


# objects inside a scaled dialog that keep their screen place (inverse transform): the help line under the header
KEEP_PLACE = ('text_help',)
_SCALE_OF = {child: v for (parent, child), v in DIALOG_SCALES.items()}   # scaled dialog name -> its transform
# sprites whose bottom edge moves down (units) to cover a stretched dialog
STRETCH_DOWN = {(d, s): 270 for d in ('I06_parchment6r', 'I06_parchment5r', 'I06_parchment4r') for s in ('I06_BG_0', 'I06_BG_1')}
# dialog: {stock font: new font} for every Text object in it. Presets 1 / 2 are unused by the stock menus; the agent
# (mod/dinput8/title.c patch_fonts) makes them 2.0x / 1.4x (docs/ui/FONTS_RE.md). Font index != size order.
FONT_BUMPS = {'I06-00': {7: 1}, 'I01-01': {8: 1}, 'R01-00': {7: 2, 9: 1}, 'R13-00': {6: 2}, 'R15-00': {6: 2},
              'R14-00': {7: 2, 9: 1}, 'R14-01': {7: 2}, 'F04-01': {8: 2},
              'R03-21': {8: 2, 9: 1}, 'R03-22': {8: 2, 9: 1},
              'R16-00': {7: 2, 9: 1}, 'R16-01': {7: 2}, 'R17-00': {7: 2, 9: 1}, 'R17-01': {7: 2}}
FONT_BUMPS.update(FONT_BUMPS_R03)
for _d in R03_BIG:   # R03-01 / R03-02 window 1.5x wide, 2x high around the screen centre (see R03_BIG)
    DIALOG_SCALES[('R03', _d)] = ((1.5, 2.0), (641, 360))
_SCALE_OF = {child: v for (parent, child), v in DIALOG_SCALES.items()}
CENTRE_MENUS = True
HIDE_KEY_GUIDE = True
OFF_SCREEN = (-2000, -2000, -1968, -1984)


def _shift_for(dname, oname):
    for d, pat, dx, dy in SHIFTS:
        if d == dname and (oname == pat or pat.endswith('*') and oname.startswith(pat[:-1])):
            return dx, dy
    return None


def patch(buf):
    buf = bytearray(buf)
    ch = _chunks(buf)
    str0 = ch['STR'][0]

    def s(off):
        end = str0 + off
        while buf[end:end + 2] != b'\0\0':
            end += 2
        return buf[str0 + off:end].decode('utf-16-le')

    dlg0, ndlg = ch['DLG']
    dlgo0, shap0, shpr0 = ch['DLGO'][0], ch['SHAP'][0], ch['SHPR'][0]
    todo = dict(EDITS)
    shifted = nulls = centred = guides = strip = scaled = options = 0
    for i in range(ndlg):
        e = dlg0 + 0x40 * i
        dname = s(struct.unpack_from('<i', buf, e)[0])
        count, first = struct.unpack_from('<ii', buf, e + 0x20)
        for k in range(count):
            name_off, shap_off = struct.unpack_from('<ii', buf, dlgo0 + first + 32 * k)
            key = (dname, s(name_off))
            stype_name = s(struct.unpack_from('<i', buf, shap0 + shap_off)[0])
            if stype_name != 'Null':
                p = shpr0 + struct.unpack_from('<i', buf, shap0 + shap_off + 4)[0]
                # the copies of the strip in each tab header (*_category_name: Start_icon_0..7 + category_LR with
                # HOME / END): the icons are the click targets while a tab is open, so they stay in place, invisible
                if HIDE_TAB_STRIP and dname.endswith('_category_name') and key[1] == 'category_LR':
                    struct.pack_into('<4h', buf, p, *OFF_SCREEN)
                    strip += 1
                if HIDE_TAB_STRIP and dname.endswith('_category_name') and key[1].startswith('Start_icon_') and stype_name == 'Sprite':
                    struct.pack_into('<I', buf, p + 0x20, 0)   # invisible but in place: the click target while a tab is open
                    strip += 1
                if HIDE_TAB_STRIP and key in TAB_STRIP_OFF:
                    struct.pack_into('<4h', buf, p, *OFF_SCREEN)
                    strip += 1
                if HIDE_TAB_STRIP and key in TAB_STRIP_CLEAR and stype_name == 'Sprite':
                    struct.pack_into('<I', buf, p + 0x20, 0)   # sprite colour (RGBA) 0 = invisible
                    strip += 1
                if CENTRE_MENUS and struct.unpack_from('<2h', buf, p + 8) == (1280, 0):
                    struct.pack_into('<h', buf, p + 8, 640)
                    centred += 1
                if HIDE_KEY_GUIDE and key[1].startswith('text_key-guide'):
                    struct.pack_into('<4h', buf, p, *OFF_SCREEN)
                    guides += 1
            # before the scaling: the trim is in stock units
            if dname in SYS_TRIM_DLGS and stype_name == 'Sprite':
                p = shpr0 + struct.unpack_from('<i', buf, shap0 + shap_off + 4)[0]
                nr = sys_trim(key[1], struct.unpack_from('<4h', buf, p))
                if nr:
                    struct.pack_into('<4h', buf, p, *nr)
            if key in DIALOG_SCALES and stype_name != 'Null':   # dialogs (scale their children) and sprites
                p = shpr0 + struct.unpack_from('<i', buf, shap0 + shap_off + 4)[0]
                (kx, ky), (cx, cy) = DIALOG_SCALES[key]
                r = struct.unpack_from('<4h', buf, p)
                struct.pack_into('<4h', buf, p, *(round(c + (v - c) * k_) for v, c, k_ in zip(r, (cx, cy, cx, cy), (kx, ky, kx, ky))))
                scaled += 1
            if dname in ('R01-00', 'R01_parame_plate') or (dname, key[1]) in OPTION_HIDE:
                p = shpr0 + struct.unpack_from('<i', buf, shap0 + shap_off + 4)[0]
                nr = option_rect(dname, key[1], stype_name, struct.unpack_from('<4h', buf, p))
                if nr:
                    struct.pack_into('<4h', buf, p, *nr)
                    options += 1
            if (dname in ('R14-00', 'R14-01', 'R16-00', 'R16-01', 'R17-00', 'R17-01') or key in PC_HIDE) and key[1] not in ('text_help', 'cursor')                     and not key[1].startswith(('category_', 'text_key-guide')):
                p = shpr0 + struct.unpack_from('<i', buf, shap0 + shap_off + 4)[0]
                nr = pc_rect(dname, key[1], stype_name, struct.unpack_from('<4h', buf, p))
                if nr:
                    struct.pack_into('<4h', buf, p, *nr)
                    options += 1
            if key[1] in KEEP_PLACE and dname in _SCALE_OF and stype_name != 'Null':
                p = shpr0 + struct.unpack_from('<i', buf, shap0 + shap_off + 4)[0]
                (kx, ky), (cx, cy) = _SCALE_OF[dname]
                r = struct.unpack_from('<4h', buf, p)
                struct.pack_into('<4h', buf, p, *(round(c + (v - c) / k_) for v, c, k_ in zip(r, (cx, cy, cx, cy), (kx, ky, kx, ky))))
            if stype_name == 'Text' and dname in FONT_BUMPS:
                p = shpr0 + struct.unpack_from('<i', buf, shap0 + shap_off + 4)[0]
                buf[p + 0x1c] = FONT_BUMPS[dname].get(buf[p + 0x1c], buf[p + 0x1c])
            if key in STRETCH_DOWN:
                p = shpr0 + struct.unpack_from('<i', buf, shap0 + shap_off + 4)[0]
                struct.pack_into('<h', buf, p + 6, struct.unpack_from('<h', buf, p + 6)[0] + STRETCH_DOWN[key])
            if key in RECTS and stype_name != 'Null':
                p = shpr0 + struct.unpack_from('<i', buf, shap0 + shap_off + 4)[0]
                rect, font = RECTS[key]
                struct.pack_into('<4h', buf, p, *rect)
                if font is not None and stype_name == 'Text':
                    buf[p + 0x1c] = font
                if key in TEXT_ALIGN:
                    buf[p + 0x1e] = TEXT_ALIGN[key]
            if key in SHAPE_BYTES:
                p = shpr0 + struct.unpack_from('<i', buf, shap0 + shap_off + 4)[0]
                for _o, _v in SHAPE_BYTES[key].items():
                    buf[p + _o] = _v
            if key in MONO_COLOR and stype_name == 'MonoRect':
                p = shpr0 + struct.unpack_from('<i', buf, shap0 + shap_off + 4)[0]
                buf[p + 0x18:p + 0x1c] = MONO_COLOR[key]
            if key in NULL_RECTS:          # Null shapes: rect only (the 8 bytes after it belong to the next shape)
                p = shpr0 + struct.unpack_from('<i', buf, shap0 + shap_off + 4)[0]
                struct.pack_into('<4h', buf, p, *NULL_RECTS[key])
                nulls += 1
                continue
            shift = _shift_for(*key)
            if shift:
                p = shpr0 + struct.unpack_from('<i', buf, shap0 + shap_off + 4)[0]
                r = struct.unpack_from('<4h', buf, p)
                struct.pack_into('<4h', buf, p, r[0] + shift[0], r[1] + shift[1], r[2] + shift[0], r[3] + shift[1])
                shifted += 1
                continue
            if key not in todo:
                continue
            rect, origin, stype, align = todo.pop(key)
            p = shpr0 + struct.unpack_from('<i', buf, shap0 + shap_off + 4)[0]
            old = struct.unpack_from('<4h2hi', buf, p)
            struct.pack_into('<4h2hi', buf, p, *rect, *origin, stype)
            if align is not None:
                buf[p + 0x1e] = align
            if key in FONTS:
                buf[p + 0x1c] = FONTS[key]
            print(f'{dname}/{key[1]}: {old} -> {rect + origin + (stype,)}' + (f' align {align}' if align is not None else ''))
    print(f'shifted {shifted} objects, {nulls} cursor rects, {centred} menu anchors centred, {guides} key guides hidden, {strip} tab strip parts hidden, {scaled} dialogs scaled, {options} options objects laid out')
    if nulls < len(NULL_RECTS):
        raise SystemExit('cursor rects not all found')
    if todo:
        raise SystemExit(f'not found: {list(todo)}')
    return bytes(buf)


def main():
    game = sys.argv[1] if len(sys.argv) > 1 else GAME
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, 'out', 'menu.drb.dcx')
    with open(os.path.join(game, 'menu', 'menu.drb.dcx'), 'rb') as f:
        orig = f.read()
    plain = patch(dcx_decompress(orig))
    with open(out, 'wb') as f:
        f.write(dcx_compress(plain, orig))
    with open(out, 'rb') as f:
        assert dcx_decompress(f.read()) == plain
    print('wrote', out)


if __name__ == '__main__':
    main()

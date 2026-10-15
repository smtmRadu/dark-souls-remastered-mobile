# Menu text font size (DSR PC v1.04, base 0x140000000)

Static analysis only. Nothing was run.

## Path: DRB Text +0x1c to glyph scale
1. `CMenuTextShape` (EzMenu::DynamicUI, vt `0x1414f6bc0`). Ctor `0x140f02320` copies the 0x20-byte DRB Text params to obj+0x10. Font = word obj+0x2c (= params+0x1c). Align = byte obj+0x2e (= params+0x1e).
2. Draw `0x140f024b0` calls `dc->BeginText(font)` (FrpgMenuDc vt `0x1413d3858`, slot 22 `0x140724cb0`). This calls `FrpgMenuFontPrinter::Begin(font)` (vt `0x1413d3ca8`, slot 1 → `0x140724f90` → `0x1401e7c90`). That function queues render command `0x1401e7d00` with the font index.
3. Command `0x1401e7d00` reads the preset table through accessors `0x1407256f0` (font id), `0x140725720` (base size) and `0x140725750` (scale xy). Each accessor checks the index: `cmp ecx,0xc; ja`. An index above 12 uses entry 0.
4. Final glyph scale = preset scale × xmm3 from DrawText (`0x140f0287b`). xmm3 = min(W/1280, H/720) × ctx[+0x14] × ctx[+0x18].

## Table: VA `0x1413d3950` (.rdata, file offset `0x13d2150`), 13 entries, stride 0x18
`{+0 wchar* name, +8 u32 fontId, +0xc f32 baseSize, +0x10 f32 scaleX, +0x14 f32 scaleY}`

| idx | name | fontId | base | scale x/y |
|---|---|---|---|---|
| 0..11 | 日本語_10pt .. _32pt (step 2pt) | 1 (DSFont24) | 24 | (10+2i)/24: 0.417, 0.5, 0.583, 0.667, 0.75, 0.833, 0.917, **1.0 (7)**, 1.083, 1.167, **1.25 (10)**, **1.333 (11)** |
| 12 | 日本語字幕 (subtitles) | 2 (TalkFont24) | 24 | **1.5 / 1.5833** |
| 13..15 | not in table, use entry 0 | | | 0.417 |

Font ids match the FontStep load order at `0x1402607c0`: DbgFont14h, DSFont24, TalkFont24.

- **The glyph size comes from scaleX/scaleY.** baseSize 24 is the native size of the font. It also sets the default line height (24 × scaleY, ctx+0xf4). The menu printer then overrides the line height (printer slot 13).
- The table is **not copied at boot**. The accessors read .rdata through RIP-relative `lea` at every Begin. A runtime write applies to the next drawn frame. .rdata is read-only, so call `VirtualProtect(PAGE_READWRITE)` first. A file patch also works.

## Patch recipe (f32, little-endian; write the same value at +0x10 and +0x14)
| idx | VA scaleX / scaleY | file off (X) | 1.5× | 2× |
|---|---|---|---|---|
| 7 | `0x1413d3a08` / `a0c` | `0x13d2208` | 1.5 `0000c03f` | 2.0 `00000040` |
| 10 | `0x1413d3a50` / `a54` | `0x13d2250` | 1.875 `0000f03f` | 2.5 `00002040` |
| 11 | `0x1413d3a68` / `a6c` | `0x13d2268` | 2.0 `00000040` | 2.667 `abaa2a40` |
| 12 | `0x1413d3a80` / `a84` | `0x13d2280` | 2.25 `00001040` / 2.375 `00001840` | 3.0 / 3.167 |

## Open point (RT)
The phone showed font 9 smaller than font 7. The code gives the opposite: 9 = 1.167 and 7 = 1.0. Font 12 uses a different font (TalkFont, 1.5×). Check this at runtime. Possible causes: the text rect clips the glyphs, or the second scale factor (ctx+0x14/+0x18) is different per dialog.

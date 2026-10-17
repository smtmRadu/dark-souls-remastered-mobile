"""extract_assets.py: build HUD lookup tables + item icons from the user's own DSR (PC v1.04) game folder.
The game folder is only read, never written. Formats live in tools/fromsoft/ (DCX, BND3, TPF, DRB, PARAM, FMG).

Where the icons are: menu/menu.drb.dcx is the menu layout. Its DLGO objects named 'EquIcon_<iconId>' are
Sprite shapes whose texture rect points into atlas textures Icon00/01/10/11/12/20/21/30/40/50, stored in
menu/menu_0.tpf.dcx and menu/menu_3.tpf.dcx (DXT5). The loose menu/menu.drb next to it is the older PTDE
layout (half-resolution rects, fewer icons); it is only used if the .dcx is missing, with rects scaled x2.
Param rows reference the same icon id: EquipParamWeapon.iconId (+0xba), EquipParamProtector.iconIdM/F
(+0xa2/+0xa4), EquipParamAccessory.iconId (+0x22), EquipParamGoods.iconId (+0x2c), Magic.iconId (+0x10).

Outputs (in OUT, default tools/out/assets):
  icons/<iconId>.png   every EquIcon sprite, RGBA
  items.json           {category: {rowId: {name, icon}}} for weapon/protector/accessory/goods/magic
  text.json            {fmgName: {id: text}} for every FMG in menu.msgbnd and item.msgbnd (ENGLISH)
  prompts.json         {id: text} interaction prompts (Event_text_), for the Interact pill
  icons_montage.png    labelled contact sheet for a visual check
Usage:
  python extract_assets.py [GAME_DIR] [OUT_DIR]
"""
import io, json, os, re, sys
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fromsoft.containers import bnd3_read, tpf_read, dcx_decompress
from fromsoft.data import paramdef_read, param_read, fmg_read
from fromsoft.drb import drb_sprites

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.join(HERE, '..', 'local', 'game')
OUT = os.path.join(HERE, 'out', 'assets')

# category -> (param file stem, name FMG, icon field(s))
CATEGORIES = {
    'weapon': ('EquipParamWeapon', 'Weapon_name_', ['iconId']),
    'protector': ('EquipParamProtector', 'Armor_name_', ['iconIdM', 'iconIdF']),
    'accessory': ('EquipParamAccessory', 'Accessory_name_', ['iconId']),
    'goods': ('EquipParamGoods', 'Item_name_', ['iconId']),
    'magic': ('Magic', 'Magic_name_', ['iconId']),
}


def read(game, rel):
    with open(os.path.join(game, rel), 'rb') as f:
        return f.read()


def base_name(path):
    """'N:\\FRPG\\...\\Event_text_.fmg' -> 'Event_text_'"""
    return re.split(r'[\\/]', path)[-1].rsplit('.', 1)[0]


def load_text(game):
    """All ENGLISH FMGs, merged by file name (DSR repeats each FMG under a second bnd id; copies are identical)."""
    text = {}
    for bnd in ('menu', 'item'):
        for _id, name, data in bnd3_read(read(game, f'msg/ENGLISH/{bnd}.msgbnd.dcx')):
            text.setdefault(base_name(name), {}).update(fmg_read(data))
    return text


def load_params(game):
    """{param stem: {row id: {field: value}}} for the five item params, decoded with the game's own paramdefs."""
    defs = {}
    for _id, _name, data in bnd3_read(read(game, 'paramdef/paramdef.paramdefbnd.dcx')):
        ptype, fields = paramdef_read(data)
        defs[ptype] = fields
    wanted = {c[0] for c in CATEGORIES.values()}
    params = {}
    for _id, name, data in bnd3_read(read(game, 'param/GameParam/GameParam.parambnd.dcx')):
        stem = base_name(name)
        if stem in wanted:
            ptype = data[0xc:0x2c].split(b'\0')[0].decode()
            params[stem] = param_read(data, defs[ptype])[1]
    return params


def item_name(names, rid, category):
    """Exact FMG entry, else (weapons/armor) the entry of the base id: DS1 weapon ids are
    base + infusion*100 + level, so try id rounded down to 100s, then to 1000s."""
    for k in (rid, rid - rid % 100, rid - rid % 1000) if category in ('weapon', 'protector') else (rid,):
        if names.get(k):
            return names[k]
    return None


def build_items(params, text):
    items = {}
    for cat, (stem, fmg, icon_fields) in CATEGORIES.items():
        out = items[cat] = {}
        for rid, row in sorted(params[stem].items()):
            e = {'name': item_name(text[fmg], rid, cat), 'icon': row[icon_fields[0]]}
            if len(icon_fields) > 1 and row[icon_fields[1]] != e['icon']:
                e['iconF'] = row[icon_fields[1]]
            out[rid] = e
    return items


def icon_rects(game):
    """{icon id: (atlas name, DSR-resolution rect)} from the 'EquIcon_<id>' sprites.
    menu.drb.dcx (DSR layout) wins; the loose PTDE menu.drb (rects x2) fills ids the DSR file lacks
    or leaves empty (2168-2220 and 7018-7023 in v1.04). Where both have an id, PTDE x2 == DSR."""
    rects = {}
    for rel in ('menu/menu.drb.dcx', 'menu/menu.drb'):
        if not os.path.exists(os.path.join(game, rel)):
            continue
        dsr, sprites = drb_sprites(read(game, rel))
        scale = 1 if dsr else 2              # PTDE rects are half the DSR atlas resolution
        added = 0
        for name, tex, rect in sprites:
            if not re.fullmatch(r'EquIcon_\d+', name) or rect[2] <= rect[0] or rect[3] <= rect[1]:
                continue
            if int(name[8:]) not in rects:   # an icon placed in several dialogs keeps its first rect
                rects[int(name[8:])] = (tex, tuple(v * scale for v in rect))
                added += 1
        print(f'  {rel}: {"DSR" if dsr else "PTDE"} layout, {added} icons')
    return rects


def extract_icons(game, out_dir):
    """Crop every icon from its atlas. Returns {icon id: PIL image}."""
    rects = icon_rects(game)
    # Decode each needed atlas from whichever menu TPF holds the biggest copy (menu.tpf.dcx has 16x16 stubs).
    needed = {tex for tex, _r in rects.values()}
    atlases = {}
    menu = os.path.join(game, 'menu')
    for fn in sorted(os.listdir(menu)):
        if fn.endswith('.tpf.dcx'):
            for name, _fmt, dds in tpf_read(read(menu, fn)):
                if name in needed:
                    im = Image.open(io.BytesIO(dds))
                    if name not in atlases or im.size[0] > atlases[name].size[0]:
                        atlases[name] = im
    for name in atlases:
        atlases[name] = atlases[name].convert('RGBA')   # DXT5 decode happens here (Pillow BCn decoder)
    os.makedirs(os.path.join(out_dir, 'icons'), exist_ok=True)
    icons, outside = {}, []
    for icon_id, (tex, box) in sorted(rects.items()):
        atlas = atlases[tex]
        if box[2] > atlas.size[0] or box[3] > atlas.size[1]:
            outside.append(icon_id)          # PTDE-only rows cut from the smaller DSR Icon21 atlas
            continue
        icons[icon_id] = atlas.crop(box)
        icons[icon_id].save(os.path.join(out_dir, 'icons', f'{icon_id}.png'))
    if outside:
        print(f'  {len(outside)} PTDE icon rects lie outside the DSR atlas, skipped: {outside[0]}-{outside[-1]}')
    return icons



# HUD skin pieces for the touch controls (atlas, crop box): the stock slot frames (FrpgMenuDlgFeShortcut, DRB dialogs
# F20-00_item / F20-00_magic) and the souls box parchment. Same look as the game's own HUD.
UI_PIECES = {
    'slot_bg': ('Menu08', (197, 6, 387, 238)),          # one smoky square of the slot cross (FE_frame, top square), cropped: neighbour slivers at x 190-196 and x 387+ / y 238+
    'lineframe': ('Menu07_1', (766, 624, 946, 850)),    # bronze bracket around a slot (FE_lineframe_item)
    'plate': ('Menu07_7', (1878, 1416, 2050, 1500)),    # bronze plate under a slot icon (icon_plate_0)
    'parchment': ('Menu08', (286, 488, 984, 752)),      # dark panel (souls box bg_parchment_0)
    # menu tab bar (DRB R00-00): icon_* normal, changeover_* lit; 0 inventory, 1 equipment, 2 status, 3 system
    'tab0': ('Menu11', (114, 404, 220, 510)), 'tab1': ('Menu11', (0, 404, 106, 510)),
    'tab2': ('Menu11', (222, 404, 328, 510)), 'tab3': ('Menu11', (332, 404, 438, 510)),
    'tab0_lit': ('Menu11', (114, 298, 220, 404)), 'tab1_lit': ('Menu11', (0, 298, 106, 404)),
    'tab2_lit': ('Menu11', (222, 298, 328, 404)), 'tab3_lit': ('Menu11', (332, 298, 438, 404)),
}


def extract_ui(game, out_dir):
    """Crop UI_PIECES into <out>/ui/<name>.png."""
    needed = {tex for tex, _b in UI_PIECES.values()}
    atlases = {}
    menu = os.path.join(game, 'menu')
    for fn in sorted(os.listdir(menu)):
        if fn.endswith('.tpf.dcx'):
            for name, _fmt, dds in tpf_read(read(menu, fn)):
                if name in needed:
                    im = Image.open(io.BytesIO(dds))
                    if name not in atlases or im.size[0] > atlases[name].size[0]:
                        atlases[name] = im
    os.makedirs(os.path.join(out_dir, 'ui'), exist_ok=True)
    for name, (tex, box) in UI_PIECES.items():
        atlases[tex].convert('RGBA').crop(box).save(os.path.join(out_dir, 'ui', f'{name}.png'))
    return list(UI_PIECES)


def montage(icons, items, out_path, picks):
    """Contact sheet: picks = [(label, icon id)], 10 per row."""
    cell_w, cell_h, cols = 150, 170, 10
    rows = (len(picks) + cols - 1) // cols
    sheet = Image.new('RGBA', (cols * cell_w, rows * cell_h), (40, 40, 40, 255))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=11)
    for k, (label, icon_id) in enumerate(picks):
        x, y = (k % cols) * cell_w, (k // cols) * cell_h
        im = icons.get(icon_id)
        if im:
            im = im.copy()
            im.thumbnail((128, 128))
            sheet.alpha_composite(im, (x + (cell_w - im.size[0]) // 2, y + 4))
        draw.text((x + 4, y + 134), f'icon {icon_id}', fill='yellow', font=font)
        draw.text((x + 4, y + 150), label[:24], fill='white', font=font)
    sheet.save(out_path)


def main():
    game = sys.argv[1] if len(sys.argv) > 1 else GAME
    out = sys.argv[2] if len(sys.argv) > 2 else OUT
    os.makedirs(out, exist_ok=True)

    text = load_text(game)
    with open(os.path.join(out, 'text.json'), 'w', encoding='utf-8') as f:
        json.dump(text, f, ensure_ascii=False, indent=1)
    print(f'text.json: {len(text)} FMGs, {sum(map(len, text.values()))} entries')
    # Interaction prompts only (the app's Interact pill): MenuMan+0x828 holds an Event_text_ id, e.g. 10010103 = Pick up item
    prompts = {k: v for k, v in text.get('Event_text_', {}).items() if v and not v.startswith('<?')}
    with open(os.path.join(out, 'prompts.json'), 'w', encoding='utf-8') as f:
        json.dump(prompts, f, ensure_ascii=False, indent=1)
    print(f'prompts.json: {len(prompts)} entries')

    items = build_items(load_params(game), text)
    with open(os.path.join(out, 'items.json'), 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
    print('items.json:', ', '.join(f'{c} {len(v)}' for c, v in items.items()))

    icons = extract_icons(game, out)
    print('ui/:', ', '.join(extract_ui(game, out)))
    print(f'icons/: {len(icons)} PNGs')
    used = {e[k] for v in items.values() for e in v.values() for k in ('icon', 'iconF') if k in e}
    missing = sorted(i for i in used if i not in icons)
    print(f'icon ids referenced by params: {len(used)}, without a sprite: {len(missing)} {missing[:20]}')

    # Spot checks by name, then a spread of other items for the montage.
    checks = [('goods', 'Estus Flask'), ('weapon', 'Battle Axe'), ('weapon', 'Heater Shield'),
              ('goods', 'Cracked Red Eye Orb'), ('goods', 'White Sign Soapstone')]
    picks = []
    for cat, name in checks:
        hits = [(rid, e) for rid, e in items[cat].items() if e['name'] == name]
        print(f'  {cat} "{name}": ' + ', '.join(f'id {rid} icon {e["icon"]}' for rid, e in hits[:4]))
        picks += [(f'{name}', e['icon']) for _rid, e in hits[:1]]
    for cat, v in items.items():
        named = [(rid, e) for rid, e in v.items() if e['name'] and e['icon'] in icons and rid % 100 == 0]
        step = max(1, len(named) // 12)
        picks += [(f'{cat[0]}{rid} {e["name"]}', e['icon']) for rid, e in named[::step][:12]]
    montage(icons, items, os.path.join(out, 'icons_montage.png'), picks[:60])
    print('icons_montage.png:', len(picks[:60]), 'icons')

    ev = text.get('Event_text_', {})
    print('Event_text_ 10010103 (0x98bdf7):', repr(ev.get(10010103)))


if __name__ == '__main__':
    main()

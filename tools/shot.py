"""shot.py NAME [W] : landscape screenshot -> out/NAME.png (full) + out/NAME_s.png (thumbnail W px wide, default 1400)."""
import sys, phone
from PIL import Image
p = phone.screenshot(sys.argv[1])
im = Image.open(p)
if im.size[0] < im.size[1]:
    im = im.rotate(-90, expand=True)
im.save(p)
im.thumbnail((int(sys.argv[2]) if len(sys.argv) > 2 else 1400, 2000))
im.save(p[:-4] + '_s.png')

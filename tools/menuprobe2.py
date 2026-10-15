import time, sys, pcgame
from PIL import Image
g = pcgame.Game(); mm = g.u64(g.base + pcgame.MENU_MAN)
frames=[]
def st(tag):
    v=g.i32(mm+0x50); p=pcgame.shot("p"); im=Image.open(p); im.thumbnail((400,250)); frames.append((f"{tag} 0x50={v}",im)); print(tag, v)
st("start")
for k in sys.argv[1:]:
    pcgame.key(k); time.sleep(1.2); st(k)
W=400; out=Image.new('RGB',(W*3,(250+20)*((len(frames)+2)//3)),'white')
from PIL import ImageDraw
d=ImageDraw.Draw(out)
for i,(t,im) in enumerate(frames):
    x=(i%3)*W; y=(i//3)*270; out.paste(im,(x,y+20)); d.text((x+4,y+4),t,fill='black')
out.save('out/probe.png')

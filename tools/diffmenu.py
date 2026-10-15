import time, struct, sys, pcgame
g = pcgame.Game()
mm = g.u64(g.base + pcgame.MENU_MAN)
N = 0x3000
def snap(): return g.read(mm, N)
def snaps(k=3):
    out=[]; 
    for _ in range(k): out.append(snap()); time.sleep(0.4)
    return out
closed1 = snaps()
pcgame.key(sys.argv[1] if len(sys.argv)>1 else 'esc'); time.sleep(1.5)
opened = snaps()
pcgame.key(sys.argv[1] if len(sys.argv)>1 else 'esc'); time.sleep(1.5)
closed2 = snaps()
cands=[]
for off in range(0, N-3, 4):
    c = {struct.unpack_from('<i', s, off)[0] for s in closed1+closed2}
    o = {struct.unpack_from('<i', s, off)[0] for s in opened}
    if len(c)==1 and len(o)==1 and c!=o:
        cands.append((off, c.pop(), o.pop()))
print("menuman", hex(mm), "candidates:", len(cands))
for off,cv,ov in cands[:40]: print(hex(off), cv, '->', ov)

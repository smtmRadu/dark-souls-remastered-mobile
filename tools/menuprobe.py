import time, sys, pcgame
g = pcgame.Game()
mm = g.u64(g.base + pcgame.MENU_MAN)
def st(tag):
    print(f"{tag:28s} +0x50={g.i32(mm+0x50)} +0x80={g.i32(mm+0x80)}")
st("gameplay")
for k in sys.argv[1:]:
    pcgame.key(k); time.sleep(1.2); st(f"after {k}")

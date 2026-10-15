import struct, pcgame
g = pcgame.Game(); B=g.base
TEXT=(B+0x1000,B+0x129b400+0x1000); RDATA=(B+0x129d000,B+0x129d000+0x787c00)
wcm = g.u64(B+pcgame.WORLD_CHR_MAN); pc = g.u64(wcm+0x68)
print("WorldChrMan",hex(wcm),"PlayerIns",hex(pc),"vt",hex(g.u64(pc)),"hp",g.i32(pc+0x3e8),g.i32(pc+0x3ec),"handle?",hex(g.u64(pc+8)&0xffffffff))
def is_chr(a):
    vt=g.u64(a)
    if not (RDATA[0]<=vt<RDATA[1]): return False
    b=g.read(a+0x3e8,8)
    if not b: return False
    hp,mx=struct.unpack('<ii',b)
    return 0<=hp<=mx and 0<mx<200000
found={}
# depth-1: WorldChrMan fields pointing at arrays/lists of chr pointers
blk=g.read(wcm,0x4000)
for off in range(0,len(blk),8):
    p=struct.unpack_from('<Q',blk,off)[0]
    if p<0x10000 or p>0x7fffffffffff: continue
    arr=g.read(p,0x400)
    if not arr: continue
    hits=[]
    for j in range(0,len(arr),8):
        q=struct.unpack_from('<Q',arr,j)[0]
        if 0x10000<q<0x7fffffffffff and is_chr(q): hits.append((j,q))
    if len(hits)>=1: found[off]=hits
for off,h in found.items():
    print(f"WCM+{off:#x} -> {len(h)} chr ptrs; first:", [(hex(j),hex(q),g.i32(q+0x3e8),hex(g.u64(q))) for j,q in h[:4]])

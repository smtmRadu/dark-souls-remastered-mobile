import struct, math, pcgame
from PIL import Image, ImageDraw
g=pcgame.Game(); B=g.base; wcm=g.u64(B+pcgame.WORLD_CHR_MAN)
RD=(B+0x129d000,B+0x129d000+0x787c00)
cam=g.u64(g.u64(B+0x1c6e188)+0x10)
f=struct.unpack('<20f',g.read(cam+0x10,0x50))
R,U,F=f[0:3],f[4:7],f[8:11]; P=f[12:15]; fov=g.f32(cam+0x50)
def pos(c):
    a=g.u64(g.u64(c+0x68)+0x28)
    return struct.unpack('<3f',g.read(a+0x10,12)) if a else None
def proj(w,aspect):
    v=[w[i]-P[i] for i in range(3)]; z=sum(v[i]*F[i] for i in range(3))
    if z<0.3: return None
    x=sum(v[i]*R[i] for i in range(3))/z; y=sum(v[i]*U[i] for i in range(3))/z
    t=math.tan(fov/2); return (x/(t*aspect), y/t, z)
chrs=[]
for i in range(0,40):
    off=0x7b8+i*0xE8; cnt=g.u64(wcm+off-8); arr=g.u64(wcm+off)
    if not(0<cnt<2000 and arr): continue
    for k in range(cnt):
        c=g.u64(arr+k*0x38)
        if c and RD[0]<=g.u64(c)<RD[1]: chrs.append(c)
chrs.append(g.u64(wcm+0x68))
p=pcgame.shot("proj"); im=Image.open(p).convert('RGB'); W,H=im.size
import win32gui
# client area of game inside window grab: approximate full image as game view
d=ImageDraw.Draw(im); n=0
for c in chrs:
    w=pos(c)
    if not w: continue
    s=proj(w,16/9)
    if not s or abs(s[0])>1.2 or abs(s[1])>1.2 or s[2]>60: continue
    sx=(s[0]*0.5+0.5)*W; sy=(0.5-s[1]*0.5)*H
    col='lime' if g.u64(c)==0x141322e68 else 'cyan'
    d.ellipse((sx-12,sy-12,sx+12,sy+12),outline=col,width=4); d.text((sx+14,sy-10),f"{s[2]:.0f}m hp{g.i32(c+0x3e8)}",fill=col); n+=1
print("cam pos",[round(x,2) for x in P],"fov",fov,"drawn",n,"of",len(chrs)); im.thumbnail((1280,800)); im.save('out/proj_s.png')

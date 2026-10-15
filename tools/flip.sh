# flip.sh [30|60]: show (and optionally set) DSR's frame pacer. Chain: [0x141b690c8]+0x6a0 = FlipperMgr; +0x20 mode, +0x28 flipper {vtable}
# vtables: 60FPS 0x1412ab268, 30FPS 0x1412ea688. Run via run-as. toybox sh math is 32-bit: heap ptrs here are < 2^31 (Box64 MMAP32).
P=$(pidof DarkSoulsRemastered.exe | awk '{print $1}')
le() { echo $1 | sed 's/../& /g' | awk '{for(i=NF;i>0;i--)printf $i}'; }
rq() { le $(xxd -s $1 -l 8 -p /proc/$P/mem); }
o=$(rq 0x141b690c8); m=$(rq $(printf 0x%x $((0x$o + 0x6a0)))); f=$(rq $(printf 0x%x $((0x$m + 0x28))))
echo "sys=0x$o mgr=0x$m mode=$((0x$(le $(xxd -s $(printf 0x%x $((0x$m + 0x20))) -l 4 -p /proc/$P/mem)))) flipper=0x$f vt=0x$(rq 0x$f)"
case $1 in
  30) printf '\x88\xa6\x2e\x41\x01\x00\x00\x00' | dd of=/proc/$P/mem bs=1 seek=$((0x$f)) conv=notrunc 2>/dev/null ;;
  60) printf '\x68\xb2\x2a\x41\x01\x00\x00\x00' | dd of=/proc/$P/mem bs=1 seek=$((0x$f)) conv=notrunc 2>/dev/null ;;
esac
[ -n "$1" ] && echo "now vt=0x$(rq 0x$f)"

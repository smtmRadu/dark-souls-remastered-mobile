# ts.sh: print DSR play time in ms (run via run-as; the PC side times it). Play time = [0x141c8a530]+0xA4 (GameDataMan).
# toybox sh arithmetic is 32-bit and run-as can't read /proc/uptime -> 64-bit addresses passed to xxd as hex strings.
P=$(pidof DarkSoulsRemastered.exe | awk '{print $1}')
le() { echo $1 | sed 's/../& /g' | awk '{for(i=NF;i>0;i--)printf $i}'; }
g=$(le $(xxd -s 0x141c8a530 -l 8 -p /proc/$P/mem))
pa=$(printf 0x%x $((0x$g + 0xa4)))
echo $((0x$(le $(xxd -s $pa -l 4 -p /proc/$P/mem))))

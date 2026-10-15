# pos.sh: player position x y z (run via run-as). Player = [WorldChrMan(0x141c77e50)+0x68]; pos = [[player+0x68]+0x28]+0x10.
# Uses memtool (64-bit safe, unlike toybox sh math).
M=files/memtool; P=$(pidof DarkSoulsRemastered.exe | awk '{print $1}')
q() { $M $P read $1 8 | sed 's/../& /g' | awk '{for(i=8;i>0;i--)printf $i}'; }
w=$(q 141c77e50); p=$(q $(printf %x $((0x$w + 0x68)))); a=$(q $(printf %x $((0x$p + 0x68)))); b=$(q $(printf %x $((0x$a + 0x28))))
$M $P read $(printf %x $((0x$b + 0x10))) 12

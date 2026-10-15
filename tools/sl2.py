"""sl2.py: read/write DSR save files (DRAKS0005.sl2).
BND4 with 11 entries (0-9 = character slots, 10 = system data). Each entry = MD5(16) + IV(16) + AES-128-CBC data.
MD5 covers IV + ciphertext. Usage:
  python sl2.py dump FILE           list entries
  python sl2.py diff A B [ENTRY]    byte diff of decrypted entries
"""
import struct, sys, hashlib
from Crypto.Cipher import AES

KEY = bytes.fromhex('0123456789abcdeffedcba9876543210')


def entries(buf):
    n = struct.unpack_from('<I', buf, 0x0c)[0]
    hsz = struct.unpack_from('<Q', buf, 0x20)[0]
    out = []
    for i in range(n):
        o = 0x40 + i * hsz
        size, = struct.unpack_from('<Q', buf, o + 8)
        off, = struct.unpack_from('<I', buf, o + 0x10)
        out.append((off, size))
    return out


def decrypt(buf, off, size):
    raw = buf[off:off + size]
    iv, ct = raw[16:32], raw[32:]
    return AES.new(KEY, AES.MODE_CBC, iv).decrypt(ct)


def encrypt_into(buf, off, size, plain):
    raw = buf[off:off + size]
    iv = raw[16:32]
    ct = AES.new(KEY, AES.MODE_CBC, iv).encrypt(plain)
    buf[off + 16:off + size] = iv + ct
    buf[off:off + 16] = hashlib.md5(iv + ct).digest()


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'dump':
        b = open(sys.argv[2], 'rb').read()
        for i, (off, size) in enumerate(entries(b)):
            raw = b[off:off + size]
            ok = hashlib.md5(raw[16:]).digest() == raw[:16]
            print(i, hex(off), size, 'md5ok' if ok else 'md5BAD')
    elif cmd == 'diff':
        a, b = open(sys.argv[2], 'rb').read(), open(sys.argv[3], 'rb').read()
        sel = [int(sys.argv[4])] if len(sys.argv) > 4 else range(11)
        ea, eb = entries(a), entries(b)
        for i in sel:
            da, db = decrypt(a, *ea[i]), decrypt(b, *eb[i])
            d = [k for k in range(min(len(da), len(db))) if da[k] != db[k]]
            print(f'entry {i}: {len(d)} bytes differ')
            for k in d[:60]:
                print(f'  {k:#08x}: {da[k]:02x} -> {db[k]:02x}')

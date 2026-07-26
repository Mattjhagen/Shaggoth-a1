"""Generate a simple app icon as a PNG."""
import struct, zlib, math

W, H = 256, 256
cx, cy = W // 2, H // 2
R = W // 2 - 8

def gradient(y):
    t = y / H
    r = int((167 + (236 - 167) * t))
    g = int((139 + (72 - 139) * t))
    b = int((250 + (153 - 250) * t))
    return r, g, b

raw = b''
for y in range(H):
    raw += b'\x00'
    for x in range(W):
        dx, dy = x - cx, y - cy
        dist = math.sqrt(dx*dx + dy*dy)
        if dist <= R:
            r, g, b = gradient(y)
            alpha = 255
            if dist > R - 6:
                alpha = int(255 * (R - dist) / 6)
            raw += struct.pack('BBBB', r, g, b, alpha)
        else:
            raw += struct.pack('BBBB', 0, 0, 0, 0)

def png(w, h, data):
    def chunk(ctype, cdata):
        c = ctype + cdata
        return struct.pack('>I', len(cdata)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
    ihdr = struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', zlib.compress(data)) + chunk(b'IEND', b'')

with open('assets/icon.png', 'wb') as f:
    f.write(png(W, H, raw))
print("Generated assets/icon.png (256x256)")

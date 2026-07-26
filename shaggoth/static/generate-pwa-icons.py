"""Generate PWA icons."""
import struct, zlib, math, sys

def make_png(w, h, r, g, b):
    cx, cy = w // 2, h // 2
    R = w // 2 - 4
    raw = b''
    for y in range(h):
        raw += b'\x00'
        for x in range(w):
            dx, dy = x - cx, y - cy
            dist = math.sqrt(dx*dx + dy*dy)
            if dist <= R:
                t = y / h
                pr = int(r[0] + (r[1] - r[0]) * t)
                pg = int(g[0] + (g[1] - g[0]) * t)
                pb = int(b[0] + (b[1] - b[0]) * t)
                alpha = 255
                if dist > R - 4:
                    alpha = int(255 * (R - dist) / 4)
                raw += struct.pack('BBBB', pr, pg, pb, alpha)
            else:
                raw += struct.pack('BBBB', 0, 0, 0, 0)
    def chunk(ctype, cdata):
        c = ctype + cdata
        return struct.pack('>I', len(cdata)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
    ihdr = struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b'')

for size, name in [(192, 'pwa-192.png'), (512, 'pwa-512.png')]:
    data = make_png(size, size, (167, 236), (139, 114), (250, 153))
    with open(name, 'wb') as f:
        f.write(data)
    print(f"Generated {name} ({size}x{size})")

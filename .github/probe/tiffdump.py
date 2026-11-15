import struct, sys
data = open(sys.argv[1], 'rb').read()
bo = '<' if data[:2] == b'II' else '>'
magic = struct.unpack(bo + 'H', data[2:4])[0]
print('byteorder', bo, 'magic', magic, 'bytes read', len(data))
if magic == 43:
    off = struct.unpack(bo + 'Q', data[8:16])[0]
else:
    off = struct.unpack(bo + 'I', data[4:8])[0]
TYPES = {1: 'B', 2: 's', 3: 'H', 4: 'I', 5: 'II', 6: 'b', 7: 'B', 8: 'h', 9: 'i', 11: 'f', 12: 'd', 16: 'Q', 17: 'q'}
SIZES = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 11: 4, 12: 8, 16: 8, 17: 8}
n_ifd = 0
while off and off < len(data) and n_ifd < 3:
    print(f'--- IFD {n_ifd} at {off}')
    if magic == 43:
        n = struct.unpack(bo + 'Q', data[off:off + 8])[0]; p = off + 8; esz = 20
    else:
        n = struct.unpack(bo + 'H', data[off:off + 2])[0]; p = off + 2; esz = 12
    for i in range(n):
        e = data[p + i * esz: p + (i + 1) * esz]
        if magic == 43:
            tag, typ, cnt = struct.unpack(bo + 'HHQ', e[:12]); vraw = e[12:]
        else:
            tag, typ, cnt = struct.unpack(bo + 'HHI', e[:8]); vraw = e[8:]
        size = SIZES.get(typ, 1) * cnt
        inline = size <= len(vraw)
        if inline:
            buf = vraw[:size]
        else:
            vo = struct.unpack(bo + ('Q' if magic == 43 else 'I'), vraw)[0]
            buf = data[vo:vo + size] if vo + size <= len(data) else b''
        val = '?' if not buf else (buf.decode('latin1')[:200] if typ == 2 else
                str(struct.unpack(bo + TYPES[typ][-1] * (cnt * (2 if typ == 5 else 1)), buf)[:16]))
        print(f'tag {tag} type {typ} count {cnt} inline {inline} -> {val}')
    nxt = p + n * esz
    off = struct.unpack(bo + ('Q' if magic == 43 else 'I'), data[nxt:nxt + (8 if magic == 43 else 4)])[0]
    n_ifd += 1

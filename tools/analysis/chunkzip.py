import struct, zlib, sys
def unpack(d):
    assert d[:8]==b'chunkzip'
    ver, total, csz, nch, align = struct.unpack_from('>IIIII', d, 8)
    pos = 0x28; out = bytearray(); info=[]
    for i in range(nch):
        clen, ctype = struct.unpack_from('>II', d, pos); pos += 8
        raw = d[pos:pos+clen]
        if ctype == 1: chunk = zlib.decompress(raw, -15)
        else: chunk = raw
        info.append((pos-8, clen, ctype, len(chunk)))
        out += chunk; pos += clen
        pos = (pos + 8 + align-1)//align*align - 8  # chunk payload is aligned
    return dict(ver=ver,total=total,csz=csz,nch=nch,align=align,info=info,end=pos), bytes(out)
if __name__=='__main__':
    h, out = unpack(open(sys.argv[1],'rb').read())
    print(h, len(out)); open(sys.argv[2],'wb').write(out)

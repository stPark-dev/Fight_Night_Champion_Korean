import struct, sys, collections
def parse(path):
    d = open(path,'rb').read(0x4000000)
    magic, ver, count = struct.unpack_from('>2sHI', d, 0)
    flags, shift, _ = struct.unpack_from('>HBB', d, 8)
    names_off, names_sz = struct.unpack_from('>II', d, 0xC)
    nlen, dlen, ndirs = struct.unpack_from('>BBH', d, 0x14)
    total, = struct.unpack_from('>I', d, 0x1C)
    ents = [struct.unpack_from('>IIII', d, 0x30+i*16) for i in range(count)]
    flg = d[0x30+count*16:0x30+count*17]
    names = []
    for i in range(count):
        o = names_off + i*nlen
        di, = struct.unpack_from('>H', d, o)
        names.append((di, d[o+2:o+nlen].split(b'\0')[0].decode()))
    dbase = names_off + count*nlen
    dbase = (dbase + 0xF) & ~0xF
    dirs = [d[dbase+i*dlen:dbase+(i+1)*dlen].split(b'\0')[0].decode() for i in range(ndirs)]
    return dict(ver=ver,count=count,flags=flags,shift=shift,names_off=names_off,names_sz=names_sz,nlen=nlen,dlen=dlen,ndirs=ndirs,total=total,ents=ents,flg=flg,names=names,dirs=dirs,dbase=dbase)
if __name__=='__main__':
    p = parse(sys.argv[1])
    print({k:v for k,v in p.items() if k not in('ents','flg','names','dirs')})
    print('flag bytes', collections.Counter(p['flg']))
    print('mid field', collections.Counter(e[1] for e in p['ents']).most_common(5))
    for i,(e,(di,n)) in enumerate(zip(p['ents'],p['names'])):
        if len(sys.argv)>2 and sys.argv[2] not in n: continue
        print(i, hex(e[0]<<p['shift']), hex(e[1]), hex(e[2]), hex(e[3]), p['flg'][i], p['dirs'][di] if di<len(p['dirs']) else di, n)

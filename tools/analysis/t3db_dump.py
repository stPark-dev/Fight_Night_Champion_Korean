import struct, sys, json
def load(path):
    d=open(path,'rb').read()
    nrec,=struct.unpack_from('>H',d,0x36); rec0=0x78; tree=rec0+nrec*16
    NULL=0xFFFFFFFF
    first=min(v for i in range(nrec) for v in struct.unpack_from('>II',d,rec0+i*16) if v!=NULL)
    nodes=[struct.unpack_from('>HH',d,tree+4*i) for i in range(first//4)]
    def dec(pos,n):
        out=bytearray()
        while len(out)<n:
            node=0
            while True:
                ch=nodes[node][(d[pos>>3]>>(7-(pos&7)))&1]; pos+=1
                if ch&0xFF00: node=ch>>8
                else: break
            out.append(ch)
        return bytes(out)
    rows=[]
    for i in range(nrec):
        a,b,h,x=struct.unpack_from('>IIiI',d,rec0+i*16)
        sid=None if a==NULL else dec((tree+a+1)*8,d[tree+a]).decode()
        txt=None
        if b!=NULL:
            n=struct.unpack_from('>H',d,tree+b)[0]
            txt=dec((tree+b+2)*8,n).decode('utf-8')
        rows.append(dict(hash=h,id=sid,text=txt))
    return rows
if __name__=='__main__':
    rows=load(sys.argv[1]); json.dump(rows,open(sys.argv[2],'w'),ensure_ascii=False,indent=0); print(len(rows))

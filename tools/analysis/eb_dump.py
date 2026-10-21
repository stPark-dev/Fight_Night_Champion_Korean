import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from eb_probe import parse
src, out, pat = sys.argv[1], sys.argv[2], sys.argv[3]
p = parse(src)
f = open(src,'rb')
for e,(di,n) in zip(p['ents'],p['names']):
    if pat not in n: continue
    f.seek(e[0]<<p['shift']); data = f.read(e[2])
    path = os.path.join(out, p['dirs'][di], n); os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path,'wb').write(data); print(path, len(data))

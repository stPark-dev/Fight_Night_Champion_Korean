"""번역 작업 단위 나누기: work/source → work/batches/NN_<접두사>.json.

ID를 자연 정렬해 같은 계열(끝 번호만 다른 ID, 챔피언 모드 장면, IT_n 문단)이 한 묶음에 들어가게
하고, 원문 글자 수 기준으로 자른다. 번역 대상이 아닌 VK_(가상 키보드 문자표)는 뺀다.

사용: python tools/batches.py [--chars 12000]
"""
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = ("VK",)
SMALL = 2500  # 이보다 작은 접두사 묶음은 한 배치로 모은다


def natural(k):
    return [int(t) if t.isdigit() else t.upper() for t in re.split(r"(\d+)", k)]


def family(k):
    m = re.match(r"(CM_MM_[^_]+_SCENE[^_]+)", k)
    if m:
        return m.group(1)
    m = re.match(r"(IT_\d+)_", k)
    if m:
        return m.group(1)
    return re.sub(r"[_ ]*\d+$", "", k)


def split(strings, limit):
    out, cur, size, fam = [], {}, 0, None
    for k in sorted(strings, key=natural):
        f = family(k)
        if size >= limit and f != fam:
            out.append(cur)
            cur, size = {}, 0
        cur[k] = strings[k]
        size += len(strings[k])
        fam = f
    if cur:
        if out and size < limit // 4:  # 짧은 꼬리는 앞 배치에 붙인다
            out[-1].update(cur)
        else:
            out.append(cur)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=ROOT / "work" / "source")
    ap.add_argument("--out", default=ROOT / "work" / "batches")
    ap.add_argument("--chars", type=int, default=12000)
    args = ap.parse_args()
    groups = {f.stem: json.loads(f.read_text(encoding="utf-8"))
              for f in sorted(Path(args.source).glob("*.json")) if f.stem not in SKIP}
    small = {k: v for g, s in groups.items() if sum(map(len, s.values())) < SMALL for k, v in s.items()}
    groups = {g: s for g, s in groups.items() if sum(map(len, s.values())) >= SMALL}
    groups["ETC"] = small

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    for g in sorted(groups):
        for part in split(groups[g], args.chars):
            n += 1
            name = f"{n:02d}_{g}.json"
            (out / name).write_text(json.dumps(part, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"{name:20} {len(part):5} 문자열 {sum(map(len, part.values())):6} 자")


if __name__ == "__main__":
    main()

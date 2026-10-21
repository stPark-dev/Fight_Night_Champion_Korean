"""스트레스 시험용 의사 번역: 원문 + 공백 + KS X 1001 한글 음절(전역 순환).

사용: python3 tools/pseudoloc.py <출력.json>
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fnc import chunkzip, eb, t3db  # noqa: E402

ONLINE_PREFIXES = ("OSDK_",)


def ksx1001_hangul():
    out = []
    for hi in range(0xB0, 0xC9):
        for lo in range(0xA1, 0xFF):
            out.append(bytes([hi, lo]).decode("euc-kr"))
    return "".join(out)


def generate(rows):
    syl = ksx1001_hangul()
    pos, out = 0, {}
    for r in rows:
        if r.text is None or r.stringid.startswith(ONLINE_PREFIXES):
            continue
        n = max(2, len(r.text) // 3)
        suffix = "".join(syl[(pos + i) % len(syl)] for i in range(n))
        pos += n
        out[r.stringid] = f"{r.text} {suffix}"
    return out


def main():
    root = Path(__file__).resolve().parents[1]
    boot = (root / "work/extract/PS3_GAME/USRDIR/databigs/ps3/boot.big").read_bytes()
    db = t3db.LanguageDB.parse(chunkzip.unpack(
        eb.Archive.parse(boot).read("data/ps3/loc/eng/database/eng_us.db")))
    data = generate(db.rows)
    Path(sys.argv[1]).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(len(data), "strings")


if __name__ == "__main__":
    main()

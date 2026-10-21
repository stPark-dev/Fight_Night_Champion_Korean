"""번역 원문 추출: eng_us.db 오프라인 문자열 → work/source/<접두사>.json ({ID: 원문}).

게임 원문이므로 work/ 아래에만 쓴다(저장소에 올리지 않음).
사용: python tools/export_source.py [--out work/source]
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fnc import chunkzip, eb, t3db  # noqa: E402
from pseudoloc import ONLINE_PREFIXES  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BOOT_BIG = "PS3_GAME/USRDIR/databigs/ps3/boot.big"
ENG_DB = "data/ps3/loc/eng/database/eng_us.db"


def prefix(stringid):
    # 대소문자만 다른 접두사(TXT/txt/Txt)는 대소문자 무시 파일시스템에서 겹치므로 합친다
    return stringid.split("_", 1)[0].upper() if "_" in stringid else "MISC"


def group(rows):
    out = defaultdict(dict)
    for r in rows:
        if r.text is None or r.stringid is None or r.stringid.startswith(ONLINE_PREFIXES):
            continue
        out[prefix(r.stringid)][r.stringid] = r.text
    return dict(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--extract", default=ROOT / "work" / "extract")
    ap.add_argument("--out", default=ROOT / "work" / "source")
    args = ap.parse_args()
    boot = (Path(args.extract) / BOOT_BIG).read_bytes()
    db = t3db.LanguageDB.parse(chunkzip.unpack(eb.Archive.parse(boot).read(ENG_DB)))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, strings in sorted(group(db.rows).items(), key=lambda kv: -len(kv[1])):
        (out / f"{name}.json").write_text(json.dumps(strings, ensure_ascii=False, indent=1),
                                          encoding="utf-8")
        print(f"{name:12} {len(strings):6} 문자열 {sum(map(len, strings.values())):8} 자")


if __name__ == "__main__":
    main()

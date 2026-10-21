"""번역 검사: 원문(eng_us.db) 대비 오류·경고와 진행률.

오류(종료 코드 1): 미지 ID, 제어 토큰 불일치, 줄바꿈 구조 불일치, KS X 1001 밖 한글 음절
경고: 원문과 동일(미번역 의심), 짧은 항목이 원문보다 넓음(칸 폭 초과 의심)

사용: python tools/check_translations.py [번역 경로=translations/ko] [--warnings]
"""
import argparse
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build  # noqa: E402
from export_source import group  # noqa: E402
from fnc import chunkzip, eb, t3db  # noqa: E402
from pseudoloc import ksx1001_hangul  # noqa: E402

KSX = set(ksx1001_hangul())
HANGUL = re.compile("[가-힣]")
SHORT = 24  # 이 길이 이하 원문은 칸 폭 고정 UI 항목일 가능성이 높음


def newlines(s):
    return (s.count("\r\n"), s.count("\n") - s.count("\r\n"), s.count("\r") - s.count("\r\n"))


def width(s):
    """대략적인 표시 폭: 한글·전각 2, 그 외 1."""
    return sum(2 if HANGUL.match(c) else 1 for c in s)


def check(translations, source):
    errors, warnings = [], []
    unknown = sorted(k for k in translations if k not in source)
    errors += [f"미지 ID: {k}" for k in unknown]
    known = {k: v for k, v in translations.items() if k in source}
    errors += [f"토큰 불일치: {k}" for k in build.token_mismatches(known, source)]
    for k, v in known.items():
        if newlines(v) != newlines(source[k]):
            errors.append(f"줄바꿈 불일치: {k} 원문 {newlines(source[k])} 번역 {newlines(v)}")
        bad = sorted({c for c in v if HANGUL.match(c) and c not in KSX})
        if bad:
            errors.append(f"KS X 1001 밖 음절: {k} {''.join(bad)}")
        if v == source[k] and re.search("[A-Za-z]{3}", v):
            warnings.append(f"원문과 동일: {k}")
        if len(source[k]) <= SHORT and width(v) > len(source[k]) * 1.5 + 2:
            warnings.append(f"폭 초과 의심: {k} {source[k]!r} → {v!r}")
    return errors, warnings


def load_source(extract):
    boot = (Path(extract) / build.BOOT_BIG).read_bytes()
    db = t3db.LanguageDB.parse(chunkzip.unpack(eb.Archive.parse(boot).read(build.ENG_DB)))
    return db, group(db.rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default=build.ROOT / "translations" / "ko")
    ap.add_argument("--extract", default=build.ROOT / "work" / "extract")
    ap.add_argument("--warnings", action="store_true", help="경고 목록 전부 출력")
    args = ap.parse_args()
    translations = build.load_translations(args.path)
    db, groups = load_source(args.extract)
    source = {r.stringid: r.text for r in db.rows if r.stringid is not None and r.text is not None}
    errors, warnings = check(translations, source)

    total = Counter({g: len(s) for g, s in groups.items()})
    done = Counter({g: sum(k in translations for k in s) for g, s in groups.items()})
    for g in sorted(total, key=lambda g: -total[g])[:12]:
        print(f"{g:12} {done[g]:5}/{total[g]:<5}")
    print(f"{'합계':12} {sum(done.values()):5}/{sum(total.values()):<5} (전체)")
    for line in warnings if args.warnings else warnings[:10]:
        print("경고", line)
    if len(warnings) > 10 and not args.warnings:
        print(f"경고 {len(warnings)}건 (--warnings 로 전부 보기)")
    for line in errors:
        print("오류", line)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()

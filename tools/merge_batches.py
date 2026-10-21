"""배치 번역 결과(work/out/*.json)를 접두사별 translations/ko/<접두사>.json 으로 합친다.

기존 번역 파일에 덮어쓰며 합치고(같은 ID는 배치 결과가 우선), ID는 자연 정렬한다.
사용: python tools/merge_batches.py [배치 결과 파일 ...]   (생략 시 work/out/*.json 전부)
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build  # noqa: E402
from batches import natural  # noqa: E402
from export_source import prefix  # noqa: E402

KO = build.ROOT / "translations" / "ko"
MIN_FILE = 20  # 원문 문자열이 이보다 적은 접두사는 ETC.json 에 모은다


def main():
    files = [Path(a) for a in sys.argv[1:]] or sorted((build.ROOT / "work" / "out").glob("*.json"))
    merged = build.load_translations(KO) if any(KO.glob("*.json")) else {}
    seen = {}
    for f in files:
        for k, v in build.load_translations(f).items():
            if k in seen:
                raise ValueError(f"배치 간 중복 키 {k}: {seen[k].name}, {f.name}")
            seen[k] = f
            merged[k] = v
    sizes = Counter({f.stem: len(json.loads(f.read_text(encoding="utf-8")))
                     for f in (build.ROOT / "work" / "source").glob("*.json")})
    if not sizes:
        raise FileNotFoundError("work/source 없음: python tools/export_source.py 먼저 실행")
    groups = defaultdict(dict)
    for k in sorted(merged, key=natural):
        g = prefix(k)
        groups[g if sizes[g] >= MIN_FILE else "ETC"][k] = merged[k]
    KO.mkdir(parents=True, exist_ok=True)
    for old in KO.glob("*.json"):
        old.unlink()
    for g, strings in groups.items():
        (KO / f"{g}.json").write_text(json.dumps(strings, ensure_ascii=False, indent=1) + "\n",
                                      encoding="utf-8")
    print(f"{len(seen)} 문자열 반영, 합계 {len(merged)}")


if __name__ == "__main__":
    main()

"""제품 빌드: 불변 원본 추출본 + 번역 → 변경된 아카이브 → 게임 폴더.

사용: python tools/build.py <번역.json | 번역 디렉터리> [--out build/game]
"""
import argparse
import hashlib
import io
import json
import os
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

from fontTools.ttLib import TTFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fnc import bigf, chunkzip, dxt, eb, eboot, fontmerge, refpack, t3db  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BOOT_BIG = "PS3_GAME/USRDIR/databigs/ps3/boot.big"
FE_BIG = "PS3_GAME/USRDIR/databigs/ps3/fe.big"
ENG_DB = "data/ps3/loc/eng/database/eng_us.db"
FONT_DIR = "data/ps3/fe/fonts/"
FMV_DIR = "PS3_GAME/USRDIR/data/common/fmv"
IMAGES = ROOT / "assets" / "images" / "images.json"
EBOOT = "PS3_GAME/USRDIR/EBOOT.BIN"
DEFAULT_ELF = ROOT / "work" / "eboot" / "EBOOT.elf"
_FONT_CANDIDATES = (ROOT / "work" / "fonts" / "NanumGothic-Bold.ttf",
                    Path("/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"))
DEFAULT_HANGUL_FONT = next((p for p in _FONT_CANDIDATES if p.exists()), _FONT_CANDIDATES[-1])

# 번역에서 원문과 같은 개수·종류로 남아야 하는 제어 토큰
# (printf, 이름 변수 %PUNCHER, <n>, {cN}/{p0x..}, 버튼 아이콘 ^LT^)
TOKEN = re.compile(r"%[A-Z]{2,}|%[-\d.]*[a-z]|<\d+>|\{[cp][0-9a-fx]+\}|\^[A-Z]+\^")


def _no_duplicates(pairs):
    keys = [k for k, _ in pairs]
    dup = [k for k, n in Counter(keys).items() if n > 1]
    if dup:
        raise ValueError(f"중복 키: {dup[:5]}")
    return dict(pairs)


def _load_file(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=_no_duplicates)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: 번역 파일 최상위는 {{ID: 번역문}} 객체여야 함")
    bad = [k for k, v in data.items() if not isinstance(v, str)]
    if bad:
        raise ValueError(f"{path}: 문자열이 아닌 항목: {bad[:5]}")
    return data


def load_translations(path):
    """번역 JSON 파일 하나, 또는 디렉터리 안의 *.json 전부(파일 간 중복 ID 금지)."""
    path = Path(path)
    if not path.is_dir():
        return _load_file(path)
    merged, origin = {}, {}
    for f in sorted(path.glob("*.json")):
        for k, v in _load_file(f).items():
            if k in merged:
                raise ValueError(f"중복 키 {k}: {origin[k].name}, {f.name}")
            merged[k], origin[k] = v, f
    if not merged:
        raise ValueError(f"{path} 에 번역 파일 없음")
    return merged


def token_mismatches(translations, originals):
    return [k for k, v in translations.items()
            if Counter(TOKEN.findall(v)) != Counter(TOKEN.findall(originals.get(k) or ""))]


def needed_chars(translations):
    """폰트가 가져야 할 문자(제어문자 제외, ASCII 포함)."""
    return "".join(sorted({c for v in translations.values() for c in v if c >= " "}))


def build_boot(boot_raw, translations):
    arc = eb.Archive.parse(boot_raw)
    db = t3db.LanguageDB.parse(chunkzip.unpack(arc.read(ENG_DB)))
    bad = token_mismatches(translations, {r.stringid: r.text for r in db.rows})
    if bad:
        raise ValueError(f"제어 토큰 불일치: {bad[:10]}")
    packed = chunkzip.pack(db.with_texts(translations).build())
    return arc.replaced({ENG_DB: packed}).build()


def image_files(arc, manifest=IMAGES):
    """assets/images/images.json 의 텍스처 교체: 중첩 BIGF 항목(DXT5 DDS, RefPack)을 한글 그림으로."""
    from PIL import Image
    items = json.loads(Path(manifest).read_text(encoding="utf-8")) if Path(manifest).exists() else []
    by_big = {}
    for it in items:
        by_big.setdefault(it["big"], []).append(it)
    out = {}
    for big, its in by_big.items():
        nested = bigf.Bigf.parse(arc.read(big))
        cur = {e.name: e.data for e in nested.entries}
        new = {}
        for it in its:
            raw = cur[it["entry"]]
            dds = refpack.unpack(raw) if refpack.is_refpack(raw) else raw
            if hashlib.sha1(dds).hexdigest() != it["orig_sha1"]:
                raise ValueError(f"{big}:{it['entry']} 원본 텍스처가 다름")
            dds = dxt.replace_dds_dxt5(dds, Image.open(Path(manifest).parent / it["png"]))
            new[it["entry"]] = refpack.pack(dds) if refpack.is_refpack(raw) else dds
        out[big] = nested.replaced(new).build()
    return out


def build_fe(fe_raw, chars, hangul_font, images=True):
    arc = eb.Archive.parse(fe_raw)
    src = Path(hangul_font).read_bytes()
    files = {e.path: fontmerge.merge(arc.read(e.path), src, chars)
             for e in arc.entries if e.path.startswith(FONT_DIR) and e.path.endswith(".ttf")}
    if images:
        files.update(image_files(arc))
    return arc.replaced(files).build()


def verify(files, translations, chars):
    """빌드 산출물을 다시 읽어 번역 반영·폰트 커버리지를 확인."""
    db = t3db.LanguageDB.parse(chunkzip.unpack(eb.Archive.parse(files[BOOT_BIG]).read(ENG_DB)))
    ids = db.by_id()
    wrong = [k for k, v in translations.items() if ids[k].text != v]
    if wrong:
        raise ValueError(f"DB 재확인 실패: {wrong[:5]}")
    fe = eb.Archive.parse(files[FE_BIG])
    need = {ord(c) for c in chars}
    for e in fe.entries:
        if e.path.startswith(FONT_DIR) and e.path.endswith(".ttf"):
            missing = need - set(TTFont(io.BytesIO(fe.read(e.path))).getBestCmap())
            if missing:
                raise ValueError(f"{e.path}: 글리프 없음 {sorted(map(chr, missing))[:10]}")


def english_subtitles(extract):
    """영어 경로용 자막: 프랑스어 .sub(타이밍 + DB 문자열 ID)를 _eng.sub 로 복제."""
    fmv = Path(extract) / FMV_DIR
    out = {}
    for f in sorted(fmv.glob("*_fre.sub")):
        name = f"{f.name[:-len('_fre.sub')]}_eng.sub"
        if (fmv / name).exists():
            raise FileExistsError(f"원본에 이미 있음: {name}")
        out[f"{FMV_DIR}/{name}"] = f.read_bytes()
    if not out:
        raise FileNotFoundError(f"{fmv} 에 *_fre.sub 없음")
    return out


def build_eboot(elf_path):
    return eboot.apply(Path(elf_path).read_bytes(), eboot.ALL_PATCHES)


PARTS = ("db", "fonts", "subs", "eboot")


def build_files(extract, translations, hangul_font=DEFAULT_HANGUL_FONT):
    extract = Path(extract)
    chars = needed_chars(translations)
    files = {
        BOOT_BIG: build_boot((extract / BOOT_BIG).read_bytes(), translations),
        FE_BIG: build_fe((extract / FE_BIG).read_bytes(), chars, hangul_font),
    }
    verify(files, translations, chars)
    return files


def materialize(extract, out, files):
    """원본 트리를 하드링크로 복제하고 변경 파일만 새로 쓴다(원본 inode는 건드리지 않음)."""
    extract, out = Path(extract).resolve(), Path(out).resolve()
    if out == extract or out in extract.parents or extract in out.parents:
        raise ValueError(f"출력 경로 {out} 가 원본 {extract} 와 겹침")
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(extract, out, copy_function=os.link)
    for rel, data in files.items():
        target = out / rel
        target.unlink(missing_ok=True)
        target.write_bytes(data)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("translations")
    ap.add_argument("--extract", default=ROOT / "work" / "extract")
    ap.add_argument("--out", default=ROOT / "build" / "game")
    ap.add_argument("--font", default=DEFAULT_HANGUL_FONT)
    ap.add_argument("--elf", default=DEFAULT_ELF, help="복호화 EBOOT (RPCS3 --decrypt 결과)")
    ap.add_argument("--parts", default=",".join(PARTS),
                    help=f"넣을 구성 요소(쉼표 구분, 기본 전부): {','.join(PARTS)} — 문제 격리 시험용")
    args = ap.parse_args()
    parts = set(args.parts.split(","))
    if parts - set(PARTS):
        ap.error(f"알 수 없는 구성 요소: {sorted(parts - set(PARTS))}")
    extract = Path(args.extract)
    translations = load_translations(args.translations)
    files = {}
    if {"db", "fonts"} <= parts:
        files.update(build_files(extract, translations, args.font))
    elif "db" in parts:
        files[BOOT_BIG] = build_boot((extract / BOOT_BIG).read_bytes(), translations)
    elif "fonts" in parts:
        files[FE_BIG] = build_fe((extract / FE_BIG).read_bytes(), needed_chars(translations), args.font)
    if "subs" in parts:
        files.update(english_subtitles(extract))
    if "eboot" in parts:
        files[EBOOT] = build_eboot(args.elf)
    materialize(args.extract, args.out, files)
    for rel, data in files.items():
        print(f"{rel}  {len(data)}  sha256={hashlib.sha256(data).hexdigest()}")


if __name__ == "__main__":
    main()

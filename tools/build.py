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
import struct
import sys
from collections import Counter
from pathlib import Path

from fontTools.ttLib import TTFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fnc import bigf, chunkzip, dxt, eb, eboot, edat, fontmerge, refpack, t3db  # noqa: E402

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


def _translate_db(arc, translations, extra_ids=frozenset()):
    """arc 의 eng_us.db 에 있는 ID 만 번역. 없는 ID 는 extra_ids(다른 DB 에 있는 ID)여야 한다."""
    db = t3db.LanguageDB.parse(chunkzip.unpack(arc.read(ENG_DB)))
    have = {r.stringid: r.text for r in db.rows}
    unknown = sorted(set(translations) - set(have) - set(extra_ids))
    if unknown:
        raise KeyError(unknown[:5])
    mine = {k: v for k, v in translations.items() if k in have}
    bad = token_mismatches(mine, have)
    if bad:
        raise ValueError(f"제어 토큰 불일치: {bad[:10]}")
    return chunkzip.pack(db.with_texts(mine).build())


def build_boot(boot_raw, translations, extra_ids=frozenset()):
    arc = eb.Archive.parse(boot_raw)
    return arc.replaced({ENG_DB: _translate_db(arc, translations, extra_ids)}).build()


def image_files(arc, manifest=IMAGES, only_present=False):
    """assets/images/images.json 의 텍스처 교체: 중첩 BIGF 항목(DXT5 DDS, RefPack)을 한글 그림으로."""
    from PIL import Image
    items = json.loads(Path(manifest).read_text(encoding="utf-8")) if Path(manifest).exists() else []
    by_big = {}
    have = {e.path for e in arc.entries}
    for it in items:
        if only_present and it["big"] not in have:
            continue
        by_big.setdefault(it["big"], []).append(it)
    if any(it["png"].startswith("work:") and not (ROOT / "work" / it["png"][5:]).exists()
           for its in by_big.values() for it in its):
        sys.path.insert(0, str(ROOT / "tools" / "art"))
        import manual  # 원본에서 설명서 쪽 생성(게임 그림은 저장소 밖 work/ 에)
        manual.render_all()
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
            png = ROOT / "work" / it["png"][5:] if it["png"].startswith("work:") else Path(manifest).parent / it["png"]
            dds = dxt.replace_dds_dxt5(dds, Image.open(png))
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
    wrong = [k for k, v in translations.items() if k in ids and ids[k].text != v]
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


def param_sfo(path):
    """PARAM.SFO 의 문자열 항목 {키: 값}."""
    sfo = Path(path).read_bytes()
    if sfo[:4] != b"\0PSF":
        raise ValueError(f"{path}: PARAM.SFO 형식 아님")
    keys, data, n = struct.unpack_from("<III", sfo, 0x08)
    out = {}
    for i in range(n):
        koff, fmt, length, _max, doff = struct.unpack_from("<HHIII", sfo, 0x14 + 16 * i)
        key = sfo[keys + koff:sfo.index(b"\0", keys + koff)].decode()
        if fmt in (0x0004, 0x0204):  # utf8-s / utf8
            out[key] = sfo[data + doff:data + doff + length].rstrip(b"\0").decode("utf-8", "replace")
    return out


def title_id(extract):
    """추출본 PS3_GAME/PARAM.SFO 의 TITLE_ID."""
    tid = param_sfo(Path(extract) / "PS3_GAME" / "PARAM.SFO").get("TITLE_ID")
    if not tid:
        raise ValueError("PARAM.SFO 에 TITLE_ID 없음")
    return tid


def build_eboot(elf_path, extract=None):
    """복호화 EBOOT 에 지역판 프로필 패치. extract 를 주면 디스크 타이틀 ID 와 EBOOT 판이 같은지 확인."""
    elf = Path(elf_path).read_bytes()
    profile = eboot.detect_profile(elf)
    if extract is not None and title_id(extract) != profile.title:
        raise ValueError(f"추출본은 {title_id(extract)} 인데 EBOOT 는 {profile.title} 판")
    return eboot.apply_all(elf, profile=profile)


PARTS = ("db", "fonts", "subs", "eboot")


def build_files(extract, translations, hangul_font=DEFAULT_HANGUL_FONT, extra_ids=frozenset()):
    """extra_ids: 디스크 DB 에는 없고 업데이트 DLC DB 에만 있는 ID (그 번역은 build_update 가 넣는다)."""
    extract = Path(extract)
    chars = needed_chars(translations)
    files = {
        BOOT_BIG: build_boot((extract / BOOT_BIG).read_bytes(), translations, extra_ids),
        FE_BIG: build_fe((extract / FE_BIG).read_bytes(), chars, hangul_font),
    }
    verify(files, translations, chars)
    return files


DLC_TRANSLATIONS = "DLC.json"  # 번역 디렉터리 안의 업데이트 DLC 전용 문자열 파일
DLC_DIR = "USRDIR/dlc_pack1"
DLC_MAIN = f"{DLC_DIR}/dlc/data/ps3/dlc_main.big"
DLC_TOC = f"{DLC_DIR}/dlc.toc"
UPDATE_EBOOT = "USRDIR/EBOOT.BIN"


def toc_with_size(toc, old_size, new_size):
    """dlc.toc: 'DLC_TOC_' u32 버전, u32 개수, (8바이트 값, u32 크기) × 개수 — 크기만 고친다."""
    out = bytearray(toc)
    if toc[:8] != b"DLC_TOC_":
        raise ValueError("dlc.toc 형식 아님")
    n, = struct.unpack_from(">I", toc, 12)
    hits = [0x10 + 12 * i + 8 for i in range(n) if struct.unpack_from(">I", toc, 0x10 + 12 * i + 8)[0] == old_size]
    if len(hits) != 1:
        raise ValueError(f"dlc.toc 에서 크기 {old_size} 항목을 하나로 찾지 못함: {len(hits)}")
    struct.pack_into(">I", out, hits[0], new_size)
    return bytes(out)


def update_dlc_ids(update_dir):
    """업데이트 DLC DB 의 문자열 ID (디스크 빌드의 extra_ids)."""
    main, encrypted = _dlc_path(update_dir, DLC_MAIN)
    raw = main.read_bytes()
    raw = edat.decrypt(raw, edat.FNC_KLIC) if encrypted else raw
    db = t3db.LanguageDB.parse(chunkzip.unpack(eb.Archive.parse(raw).read(ENG_DB)))
    return {r.stringid for r in db.rows}


def _dlc_path(update_dir, rel):
    """일본판 업데이트는 평문, 북미판은 같은 파일이 .edat(NPDRM 암호화)."""
    plain, enc = Path(update_dir) / rel, Path(update_dir) / f"{rel}.edat"
    if plain.exists():
        return plain, False
    if enc.exists():
        return enc, True
    raise FileNotFoundError(plain)


def build_update(update_dir, elf_path, translations):
    """타이틀 업데이트 1.02 (설치 폴더 dev_hdd0/game/<ID> 기준 상대 경로) 의 바뀐 파일들.
    EBOOT 는 복호화본에 패치, DLC 의 eng_us.db 를 번역으로 덮고 진영 선택 그림을 바꾸고 dlc.toc 크기를 고친다."""
    info = param_sfo(Path(update_dir) / "PARAM.SFO")
    if info.get("APP_VER") != "01.02" or info.get("TITLE_ID") not in eboot.PROFILES:
        raise ValueError(f"{update_dir}: 타이틀 업데이트 1.02 폴더가 아님 ({info.get('TITLE_ID')} {info.get('APP_VER')})")
    elf = Path(elf_path).read_bytes()
    profile = eboot.detect_profile(elf)
    if profile.title != "UPDATE_1.02":
        raise ValueError(f"업데이트 EBOOT 가 아님: {profile.title}")
    main_path, encrypted = _dlc_path(update_dir, DLC_MAIN)
    toc_path, toc_enc = _dlc_path(update_dir, DLC_TOC)
    if encrypted != toc_enc:
        raise ValueError("dlc_main 과 dlc.toc 의 암호화 여부가 다름")
    unwrap = (lambda b: edat.decrypt(b, edat.FNC_KLIC)) if encrypted else (lambda b: b)
    main_raw, toc_raw = main_path.read_bytes(), toc_path.read_bytes()
    arc = eb.Archive.parse(unwrap(main_raw))
    files = {ENG_DB: _translate_db(arc, translations)}  # DLC DB 는 디스크 DB 의 상위 집합 → 모르는 ID 는 오류
    files.update(image_files(arc, only_present=True))
    new_main = arc.replaced(files).build()
    new_toc = toc_with_size(unwrap(toc_raw), len(arc.raw), len(new_main))
    if encrypted:
        plain_main, plain_toc = new_main, new_toc
        new_main = edat.encrypt_like(main_raw, new_main, edat.FNC_KLIC)
        new_toc = edat.encrypt_like(toc_raw, new_toc, edat.FNC_KLIC)
        if edat.decrypt(new_main, edat.FNC_KLIC) != plain_main or edat.decrypt(new_toc, edat.FNC_KLIC) != plain_toc:
            raise ValueError("EDAT 재암호화 결과를 다시 풀었을 때 내용이 다름")
    sfx = ".edat" if encrypted else ""
    return {UPDATE_EBOOT: eboot.apply_all(elf, profile=profile),
            f"{DLC_MAIN}{sfx}": new_main, f"{DLC_TOC}{sfx}": new_toc}


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
    ap.add_argument("--update", help="타이틀 업데이트 1.02 설치 폴더(USRDIR 가 들어 있는 폴더)")
    ap.add_argument("--update-elf", help="업데이트 EBOOT.BIN 복호화본")
    ap.add_argument("--update-out", help="업데이트 결과 폴더 (기본 <out>_update)")
    args = ap.parse_args()
    if args.update and not args.update_elf:
        ap.error("--update 에는 --update-elf (복호화한 업데이트 EBOOT) 가 필요함")
    parts = set(args.parts.split(","))
    if parts - set(PARTS):
        ap.error(f"알 수 없는 구성 요소: {sorted(parts - set(PARTS))}")
    extract = Path(args.extract)
    translations = load_translations(args.translations)
    if args.update:
        extra = update_dlc_ids(args.update)
    elif Path(args.translations, DLC_TRANSLATIONS).is_file():
        extra = set(_load_file(Path(args.translations, DLC_TRANSLATIONS)))
    else:
        extra = set()
    files = {}
    if {"db", "fonts"} <= parts:
        files.update(build_files(extract, translations, args.font, extra))
    elif "db" in parts:
        files[BOOT_BIG] = build_boot((extract / BOOT_BIG).read_bytes(), translations, extra)
    elif "fonts" in parts:
        files[FE_BIG] = build_fe((extract / FE_BIG).read_bytes(), needed_chars(translations), args.font)
    if "subs" in parts:
        files.update(english_subtitles(extract))
    if "eboot" in parts:
        files[EBOOT] = build_eboot(args.elf, args.extract)
    materialize(args.extract, args.out, files)
    for rel, data in files.items():
        print(f"{rel}  {len(data)}  sha256={hashlib.sha256(data).hexdigest()}")
    if args.update:
        upd = build_update(args.update, args.update_elf, translations)
        materialize(args.update, args.update_out or f"{args.out}_update", upd)
        for rel, data in upd.items():
            print(f"[update] {rel}  {len(data)}  sha256={hashlib.sha256(data).hexdigest()}")


if __name__ == "__main__":
    main()

import re
import struct
from pathlib import Path

import pytest

from fnc import eboot

ROOT = Path(__file__).resolve().parents[1]
ELF = ROOT / "work/eboot/EBOOT.elf"
JP102_ELF = ROOT / "work/eboot_jp102/EBOOT.elf"
US102_ELF = ROOT / "work/eboot_us102/EBOOT.elf"


def fake_elf():
    # 최소 ELF64 BE: 프로그램 헤더 1개(vaddr 0x10000, offset 0x100, size 0x100)
    d = bytearray(0x200)
    d[:6] = b"\x7fELF\x02\x02"
    struct.pack_into(">Q", d, 0x20, 0x40)          # phoff
    struct.pack_into(">HH", d, 0x36, 0x38, 1)      # phentsize, phnum
    struct.pack_into(">IIQQQQQQ", d, 0x40, 1, 5, 0x100, 0x10000, 0x10000, 0x100, 0x100, 0x10)
    struct.pack_into(">I", d, 0x100 + 0x10, 0x3BC00000)
    return bytes(d)


def test_patch_replaces_word_at_vaddr():
    out = eboot.apply(fake_elf(), [eboot.Patch(0x10010, 0x3BC00000, 0x60000000, "test")])
    assert struct.unpack_from(">I", out, 0x110)[0] == 0x60000000
    assert len(out) == len(fake_elf())


def test_patch_rejects_unexpected_original():
    with pytest.raises(ValueError):
        eboot.apply(fake_elf(), [eboot.Patch(0x10010, 0x12345678, 0x60000000, "test")])


def test_patch_rejects_unmapped_address():
    with pytest.raises(KeyError):
        eboot.apply(fake_elf(), [eboot.Patch(0x90000, 0, 0, "test")])


def test_patch_rejects_overlap():
    p = eboot.Patch(0x10010, 0x3BC00000, 0x60000000, "a")
    with pytest.raises(ValueError):
        eboot.apply(fake_elf(), [p, p])


def test_real_subtitle_patch_site_matches():
    if not ELF.exists():
        pytest.skip("복호화 EBOOT 없음")
    out = eboot.apply(ELF.read_bytes(), eboot.SUBTITLE_PATCHES)
    assert out != ELF.read_bytes()


def _dis(words, base):
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_PPC, capstone.CS_MODE_64 | capstone.CS_MODE_BIG_ENDIAN)
    code = b"".join(struct.pack(">I", w) for w in words)
    return [f"{i.mnemonic} {i.op_str}".strip() for i in md.disasm(code, base)]


def test_assembler_encodings():
    a = eboot.asm
    assert _dis([a.lis(3, 0x12C)], 0) == ["lis r3, 0x12c"]
    assert _dis([a.addic(3, 3, -0x7450)], 0) == ["addic r3, r3, -0x7450"]
    assert _dis([a.lwz(3, 0x5CCC, 3)], 0) == ["lwz r3, 0x5ccc(r3)"]
    assert _dis([a.cmpwi(3, 2)], 0) == ["cmpwi r3, 2"]
    assert _dis([a.beq(0x100, 0x120)], 0x100) == ["beq 0x120"]
    assert _dis([a.BLR, a.NOP], 0) == ["blr", "nop"]


def test_suffix_function_rewrite_disassembles_as_intended():
    p = [x for x in eboot.SUBTITLE_PATCHES if 0x28CC0C <= x.vaddr < 0x28CC50]
    assert len(p) == 17
    text = _dis([x.new for x in p], 0x28CC0C)
    assert text == [
        "lis r3, 0x172", "lwz r3, 0x5ccc(r3)",
        "cmpwi r3, 1", "beq 0x28cc30",
        "cmpwi r3, 2", "beq 0x28cc3c",
        "lis r3, 0x12c", "addic r3, r3, 0x59ac", "blr",
        "lis r3, 0x12d", "addic r3, r3, -0x7450", "blr",
        "lis r3, 0x12c", "addic r3, r3, 0x59bc", "blr",
        "nop", "nop",
    ]


def test_suffix_string_addresses():
    if not ELF.exists():
        pytest.skip("복호화 EBOOT 없음")
    import sys
    sys.path.insert(0, str(ROOT / "tools" / "analysis"))
    from ppc_xref import Elf
    e = Elf(str(ELF))
    for addr, s in ((eboot.ENG, b"eng\0"), (eboot.FRE, b"fre\0"), (eboot.GER, b"ger\0")):
        o = e.off(addr)
        assert e.d[o:o + 4] == s


def test_branch_encoding():
    assert _dis([eboot.asm.b(0x100, 0x140)], 0x100) == ["b 0x140"]


def test_playmovie_branch_rewrite_disassembles_as_intended():
    p = [x for x in eboot.SUBTITLE_PATCHES if 0xFC88C8 <= x.vaddr < 0xFC88FC]
    assert len(p) == 13
    assert _dis([x.new for x in p], 0xFC88C8) == [
        "beq 0xfc88ec",
        "cmpwi r3, 2", "beq 0xfc88e0",
        "lis r30, 0x12c", "addic r30, r30, 0x59ac", "b 0xfc88fc",
        "lis r30, 0x12c", "addic r30, r30, 0x59bc", "b 0xfc88fc",
        "lis r30, 0x12d", "addic r30, r30, -0x7450", "b 0xfc88fc",
        "nop",
    ]


def _branch_targets(data, base):
    """(명령 주소, 대상) — b/bl/bc 의 상대 분기만."""
    out = []
    for i in range(0, len(data), 4):
        w = struct.unpack_from(">I", data, i)[0]
        at = base + i
        if w >> 26 == 18 and not w & 2:
            li = w & 0x3FFFFFC
            out.append((at, at + (li - 0x4000000 if li & 0x2000000 else li)))
        elif w >> 26 == 16 and not w & 2:
            bd = w & 0xFFFC
            out.append((at, at + (bd - 0x10000 if bd & 0x8000 else bd)))
    return out


@pytest.mark.parametrize("elf,start,end", [
    (ELF, 0x28CC0C, 0x28CC50), (ELF, 0xFC88C8, 0xFC88FC),
    (JP102_ELF, 0x3113D4, 0x311418), (JP102_ELF, 0xFE9164, 0xFE9198),
])
def test_no_external_branch_into_rewritten_blocks(elf, start, end):
    if not elf.exists():
        pytest.skip("복호화 EBOOT 없음")
    import sys
    sys.path.insert(0, str(ROOT / "tools" / "analysis"))
    from ppc_xref import Elf
    e = Elf(str(elf))
    v, o, sz = e.code_segs()[0]
    inside = [(at, t) for at, t in _branch_targets(e.d[o:o + sz], v)
              if start < t < end and not start <= at < end]
    assert inside == []


def test_playmovie_patch_guards_preceding_compare():
    guards = [p for p in eboot.SUBTITLE_PATCHES if p.vaddr == 0xFC88C0]
    assert guards and guards[0].old == guards[0].new == 0x2C030001  # cmpwi r3,1


def test_date_patch_reorders_english_branch():
    code = {p.vaddr: p.new for p in eboot.DATE_PATCHES if p.vaddr < 0x1000000}
    assert _dis([code[0x381820], code[0x381824]], 0x381820) == ["lwz r7, 0x74(r1)", "ori r6, r29, 0"]
    assert _dis([code[0x381828]], 0x381828) == ["addic r5, r5, 0x2ef0"]
    assert _dis([code[0x381834]], 0x381834) == ["ori r8, r30, 0"]
    assert _dis([code[0x381850]], 0x381850) == ["addic r5, r5, 0x2f08"]


def test_date_patch_strings_fit_slots():
    def slot(base, size):
        words = [p.new for p in eboot.DATE_PATCHES if base <= p.vaddr < base + size]
        assert len(words) == size // 4
        return b"".join(struct.pack(">I", w) for w in words)
    ymd = slot(eboot.KO_DATE_YMD, 24)
    md = slot(eboot.KO_DATE_MD, 16)
    assert ymd.split(b"\0")[0].decode() == "%d년 %s %d일"
    assert md.split(b"\0")[0].decode() == "%s %d일"
    # 결과 문자열이 snprintf 버퍼(0x20) 안에 들어가는지: 가장 긴 경우 "2099년 12월 31일"
    assert len("2099년 12월 31일".encode()) < 0x20


def test_real_all_patches_apply():
    if not ELF.exists():
        pytest.skip("복호화 EBOOT 없음")
    eboot.apply_all(ELF.read_bytes())


def test_numeric_date_patch_orders_year_month_day():
    code = {p.vaddr: p.new for p in eboot.DATE_PATCHES if 0x381460 <= p.vaddr < 0x3814A0}
    words = [code[a] for a in (0x381468, 0x38146C)]
    assert _dis(words, 0x381468) == ["addic r5, r6, 0x78", "ori r7, r3, 0"]
    assert _dis([code[0x381478], code[0x38147C]], 0x381478) == ["ori r6, r29, 0", "ori r8, r30, 0"]
    assert _dis([code[0x381488]], 0x381488) == ["addic r5, r4, 0x78"]
    # 버퍼 주소로 덮이는 r3(월)는 addic r3 보다 먼저 읽혀야 한다
    assert 0x38146C < 0x381470


def test_numeric_date_target_strings():
    if not ELF.exists():
        pytest.skip("복호화 EBOOT 없음")
    elf = ELF.read_bytes()
    for va, s in ((0x12D2DC8 + 0x78, b"%04d.%02d.%02d"), (0x12D2DD8 + 0x78, b"%02d.%02d")):
        off = eboot._offset(elf, va)
        assert elf[off:off + len(s) + 1] == s + b"\0"


def test_pool_size_patch_changes_only_digits():
    if not ELF.exists():
        pytest.skip("복호화 EBOOT 없음")
    elf = ELF.read_bytes()
    out = eboot.apply_all(elf, {"FONT_GEN": 6, "FRONTEND_GEN": 32, "REPLAY_GEN": 8})
    off, cfg = eboot._memcfg(out)
    for name, mb in (("FONT_GEN", 6), ("FRONTEND_GEN", 32), ("REPLAY_GEN", 8)):
        assert re.search(rf"{name}[ 	]+\w+[ 	]+\[ size={mb}M".encode(), cfg), name
    changed = [i for i in range(len(elf)) if out[i] != elf[i] and off <= i < off + len(cfg)]
    assert len(changed) == 4  # 1→6, 24→32 두 자리, 4→8
    with pytest.raises(ValueError):
        eboot.memory_patches(elf, {"FONT_GEN": 16})  # 자릿수 다름


def test_race_fix_disassembles():
    if not ELF.exists():
        pytest.skip("복호화 EBOOT 없음")
    out = eboot.apply_all(ELF.read_bytes())
    word = lambda va: struct.unpack_from(">I", out, eboot._offset(out, va))[0]
    (cb_at, cb), (w_at, worker), (c_at, cancel) = eboot._caves()
    assert _dis([word(0x4A5010)], 0x4A5010) == [f"b {cb_at:#x}"]
    assert _dis([word(eboot.WORKER_DONE)], eboot.WORKER_DONE) == [f"bl {w_at:#x}"]
    assert _dis([word(eboot.CANCEL_DONE)], eboot.CANCEL_DONE) == [f"bl {c_at:#x}"]
    # 콜백은 아무 데도 쓰지 않는다
    assert _dis([word(cb_at + 4 * i) for i in range(len(cb))], cb_at) == [
        "lwz r5, 0x18(r3)", "cmpwi r5, 0", "bnelr", f"li r11, {eboot.MARK_SYSCALL:#x}", "sc", "blr"]
    for at, words, job, res in ((w_at, worker, 25, 5), (c_at, cancel, 30, 4)):
        dis = _dis([word(at + 4 * i) for i in range(len(words))], at)
        # 플래그 지우기 → lwsync → 완료 기록 순서
        assert dis[-3:] == ["lwsync", f"stw r{res}, 8(r{job})", "blr"]
        assert f"lwz r6, 0x18(r{job})" in dis and "stb r7, 0(r6)" in dis
        assert dis.index("stb r7, 0(r6)") < dis.index("lwsync")


def test_extend_text_only_grows_code_segment():
    if not ELF.exists():
        pytest.skip("복호화 EBOOT 없음")
    elf = ELF.read_bytes()
    out = eboot.extend_text(elf)
    phoff, = struct.unpack_from(">Q", elf, 0x20)
    assert struct.unpack_from(">QQ", out, phoff + 0x20) == (eboot.TEXT_END_NEW - 0x10000,) * 2
    assert [i for i in range(len(elf)) if out[i] != elf[i]] and len(out) == len(elf)


# --- 지역판(일본 BLJM60267 / 북미 BLUS30608) ---------------------------

US_ELF = ROOT / "work/eboot_us/EBOOT.elf"


def _need(p):
    if not p.exists():
        pytest.skip(f"{p.relative_to(ROOT)} 없음")
    return p.read_bytes()


def test_profiles_registered():
    assert set(eboot.PROFILES) == {"BLJM60267", "BLUS30608", "UPDATE_1.02"}
    assert eboot.PROFILES["BLJM60267"].eng == eboot.ENG  # 기존 이름은 일본판 값


def test_jp_profile_output_unchanged():
    import hashlib
    out = eboot.apply_all(_need(ELF))
    assert hashlib.sha256(out).hexdigest() == "f7d14125458aced9b5cf68fcddb31e53c420533330c0f22784e03aba7014eda4"


ALL_ELFS = [(ELF, "BLJM60267"), (US_ELF, "BLUS30608"), (JP102_ELF, "UPDATE_1.02"), (US102_ELF, "UPDATE_1.02")]


@pytest.mark.parametrize("path,title", ALL_ELFS)
def test_detect_profile(path, title):
    assert eboot.detect_profile(_need(path)).title == title


def test_detect_profile_rejects_unknown():
    with pytest.raises(ValueError):
        eboot.detect_profile(fake_elf())


def test_us_patches_apply():
    eboot.apply_all(_need(US_ELF))  # 모든 원래 값 검증 통과


@pytest.mark.parametrize("path", [p for p, _ in ALL_ELFS])
def test_profile_strings(path):
    import sys
    sys.path.insert(0, str(ROOT / "tools" / "analysis"))
    from ppc_xref import Elf
    _need(path)
    e = Elf(str(path))
    p = eboot.detect_profile(e.d)
    s = lambda a, n: e.d[e.off(a):e.off(a) + n]
    assert (s(p.eng, 4), s(p.fre, 4), s(p.ger, 4)) == (b"eng\0", b"fre\0", b"ger\0")
    assert s(p.date_en_fmt, 14) == b"%s %02d, %04d\0"
    assert s(p.date_en_fmt_noyear, 8) == b"%s %02d\0"
    assert s(p.ko_date_ymd, 19) == b"%02d de %s de %04d\0"
    assert s(p.ko_date_md, 11) == b"%02d de %s\0"
    assert s(p.num_date_table + 0x78, 15) == b"%04d.%02d.%02d\0"
    assert s(p.memcfg_at, 12) == b"AddAllocator"


def test_us_patched_code_matches_jp_semantics():
    """미국판 결과 코드는 일본판 결과와 주소 상수만 다르다(명령 종류·레지스터 동일)."""
    import sys
    sys.path.insert(0, str(ROOT / "tools" / "analysis"))
    from relocate import _mask
    jp, us = eboot.patches_for(eboot.PROFILES["BLJM60267"]), eboot.patches_for(eboot.PROFILES["BLUS30608"])
    assert len(jp) == len(us)
    code = [(a, b) for a, b in zip(jp, us) if a.vaddr < 0x1200000 or a.vaddr >= 0x1600000]
    assert all(_mask(a.new) == _mask(b.new) for a, b in code)


@pytest.mark.parametrize("path,title", ALL_ELFS)
def test_detect_profile_after_patch(path, title):
    assert eboot.detect_profile(eboot.apply_all(_need(path))).title == title


@pytest.mark.parametrize("path", [JP102_ELF, US102_ELF])
def test_update_102_patches_apply(path):
    eboot.apply_all(_need(path))  # 모든 원래 값 검증 통과


def test_update_102_worker_registers():
    p = eboot.PROFILES["UPDATE_1.02"]
    assert (p.worker_job, p.worker_res) == (23, 22)
    patches = {x.vaddr: x for x in eboot.race_patches(p)}
    assert patches[p.worker_done].old == 0x92D70008  # stw r22,8(r23)

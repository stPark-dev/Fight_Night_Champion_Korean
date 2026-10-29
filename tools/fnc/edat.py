"""PS3 NPDRM EDAT (NPD v3, 플래그 0x3C = 블록마다 메타데이터 선행) 복호화·재암호화.

북미판 타이틀 업데이트 1.02 의 DLC 파일(dlc_pack1/*.edat)을 고치기 위한 것이다.
형식은 RPCS3 Crypto/unedat.cpp 를 따른다.

  0x00 NPD 헤더: 'NPD\\0', 버전, 라이선스, 종류, content_id[0x30], digest(IV)[0x10], title_hash, dev_hash, ...
  0x80 EDAT 헤더: 플래그, 블록 크기, 원본 크기 / 0x90 메타데이터 해시 / 0xA0 헤더 해시 / 0xB0 ECDSA 서명 2개
  0x100 부터 블록마다 [메타데이터 0x20][데이터(블록 크기, 마지막은 16 정렬)], 끝에 16바이트 꼬리말
블록 키 = AES-ECB(klic, dev_hash[:12] + 블록 번호), 데이터는 AES-128-CBC(IV = digest), 블록마다 HMAC-SHA1.
ECDSA 서명은 다시 만들 수 없어 원본을 그대로 둔다 (RPCS3 는 검사하지 않음 → 실기에서는 쓸 수 없음).
"""
import hashlib
import hmac
import struct

from Crypto.Cipher import AES
from Crypto.Hash import CMAC

# 파이트 나이트 챔피언 1.02 업데이트 DLC 의 klicensee (게임이 sceNpDrmIsAvailable 에 넘기는 값, RPCS3 로그로 확인)
FNC_KLIC = bytes.fromhex("0eac00000be57f15754f17e0000f71cc")

NP_OMAC_KEY_2 = bytes.fromhex("6BA52976EFDA16EF3C339FB2971E256B")
EDAT_KEY_0 = bytes.fromhex("BE959CA8308DEFA2E5E180C63712A9AE")
HEADER = 0x100
META = 0x20
SUPPORTED_FLAGS = 0x3C  # 이 게임 파일의 플래그. 다른 조합은 받지 않는다


def _cmac(key, data):
    c = CMAC.new(key, ciphermod=AES)
    c.update(data)
    return c.digest()


def _ecb_enc(key, block):
    return AES.new(key, AES.MODE_ECB).encrypt(block)


def _ecb_dec(key, block):
    return AES.new(key, AES.MODE_ECB).decrypt(block)


def _header(d):
    if d[:4] != b"NPD\0":
        raise ValueError("NPD 헤더 아님")
    version, = struct.unpack_from(">I", d, 4)
    flags, block, size = struct.unpack_from(">IIQ", d, 0x80)
    if flags != SUPPORTED_FLAGS or version != 3:
        raise ValueError(f"지원하지 않는 EDAT (버전 {version}, 플래그 {flags:#x})")
    return version, block, size


def klic_ok(d, klic):
    """dev_hash = CMAC(klic ^ OMAC_KEY_2, NPD 헤더 앞 0x60) 확인."""
    return _cmac(bytes(a ^ b for a, b in zip(klic, NP_OMAC_KEY_2)), d[:0x60]) == d[0x60:0x70]


class _Keys:
    def __init__(self, d, klic):
        self.klic = klic
        self.erk = EDAT_KEY_0  # NPD v3 (v4 는 다른 키 — 지원하지 않음)
        self.iv = d[0x40:0x50]
        self.dev = d[0x60:0x6C]

    def block(self, i):
        """(AES 키, HMAC 키) — 플래그 0x08(암호화된 키)·0x10(해시 재암호화)·0x20(HMAC-SHA1 0x14)."""
        key_result = _ecb_enc(self.klic, self.dev + struct.pack(">I", i))
        hash_src = _ecb_enc(self.klic, key_result)
        return _ecb_dec(self.erk, key_result), _ecb_dec(self.erk, hash_src) + bytes(4)

    def header_hash_key(self):
        return _ecb_dec(self.erk, self.klic)


def _layout(block, size):
    n = -(-size // block)
    for i in range(n):
        length = block if i < n - 1 or size % block == 0 else size % block
        yield i, HEADER + i * (META + block), length, -(-length // 16) * 16


def decrypt(d, klic):
    _, block, size = _header(d)
    if not klic_ok(d, klic):
        raise ValueError("klicensee 가 맞지 않음")
    keys = _Keys(d, klic)
    out = bytearray()
    for i, at, length, padded in _layout(block, size):
        meta = d[at:at + META]
        want = bytes(a ^ b for a, b in zip(meta[:16], meta[16:32])) + meta[16:20]
        enc = d[at + META:at + META + padded]
        aes_key, mac_key = keys.block(i)
        if hmac.new(mac_key, enc, hashlib.sha1).digest() != want:
            raise ValueError(f"블록 {i} 해시 불일치")
        out += AES.new(aes_key, AES.MODE_CBC, keys.iv).decrypt(enc)[:length]
    return bytes(out)


def encrypt_like(template, plain, klic):
    """template EDAT 의 헤더(content_id·키·서명)를 그대로 쓰고 plain 을 다시 암호화.
    바뀌지 않은 블록은 template 과 같은 바이트가 된다."""
    _, block, old_size = _header(template)
    if not klic_ok(template, klic):
        raise ValueError("klicensee 가 맞지 않음")
    keys = _Keys(template, klic)
    old_blocks = {i: at for i, at, _, _ in _layout(block, old_size)}
    head = bytearray(template[:HEADER])
    struct.pack_into(">Q", head, 0x88, len(plain))
    body, metas = bytearray(), bytearray()
    for i, _, length, padded in _layout(block, len(plain)):
        chunk = plain[i * block:i * block + length].ljust(padded, b"\0")
        aes_key, mac_key = keys.block(i)
        enc = AES.new(aes_key, AES.MODE_CBC, keys.iv).encrypt(chunk)
        mac = hmac.new(mac_key, enc, hashlib.sha1).digest()
        old = template[old_blocks[i]:old_blocks[i] + META] if i in old_blocks else bytes(META)
        tail = mac[16:20] + old[20:32]
        meta = bytes(a ^ b for a, b in zip(mac[:16], tail)) + tail
        metas += meta
        body += meta + enc
    hkey = keys.header_hash_key()
    head[0x90:0xA0] = _cmac(hkey, bytes(metas))
    head[0xA0:0xB0] = _cmac(hkey, bytes(head[:0xA0]))
    return bytes(head) + bytes(body) + template[-16:]

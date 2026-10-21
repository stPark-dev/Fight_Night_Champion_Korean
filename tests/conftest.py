import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

EXTRACT = ROOT / "work" / "extract" / "PS3_GAME" / "USRDIR"
BOOT_BIG = EXTRACT / "databigs" / "ps3" / "boot.big"


@pytest.fixture(scope="session")
def boot_big():
    if not BOOT_BIG.exists():
        pytest.skip("원본 추출본 없음: work/extract")
    return BOOT_BIG.read_bytes()

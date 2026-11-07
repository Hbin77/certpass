"""tar 묶음 속 파일을 메모리에 올리지 않고 위치(오프셋)만 기억했다가 필요할 때 읽는다.

팀 서버(axgpu)는 메모리 16GB를 웹 서비스와 같이 쓴다. 이미지 전체를 메모리에 올리면 DataLoader 작업자마다
복사가 늘어 서버가 재시작된다(2026-11-07 15:43 실제 발생). 그래서 작업자는 파일 핸들만 열어 두고 읽는다.
"""
from __future__ import annotations

import tarfile
from pathlib import Path


class TarStore:
    def __init__(self, root: Path, pattern: str):
        self.index: dict[str, tuple[str, int, int]] = {}
        for tp in sorted(Path(root).glob(pattern)):
            shard = tp.stem.split("_")[1]
            with tarfile.open(tp) as tar:
                for m in tar:
                    if m.isfile():
                        self.index[f"{shard}/{m.name}"] = (str(tp), m.offset_data, m.size)
        self._fh: dict[str, object] = {}

    def __getitem__(self, key: str) -> bytes:
        path, off, size = self.index[key]
        fh = self._fh.get(path)
        if fh is None:  # 작업자 프로세스마다 처음 읽을 때 연다
            fh = self._fh[path] = open(path, "rb")
        fh.seek(off)
        return fh.read(size)

    def __getstate__(self):  # 작업자로 넘길 때 열린 파일은 빼고 넘긴다
        return {"index": self.index, "_fh": {}}

    def __len__(self):
        return len(self.index)

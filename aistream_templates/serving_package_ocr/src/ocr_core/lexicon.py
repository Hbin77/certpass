"""사전 제한 해독: 글자 인식 모델의 글자별 확률(CTC)로 식약처 성분명 사전의 단어 중 이미지와 가장 잘 맞는 것을 고른다.

- 탐욕 풀기(칸마다 가장 높은 글자)는 'BETAINE'를 'BETANNE'로 읽는 식으로 한두 글자를 틀린다.
  사전 단어의 CTC 우도(그 글자열이 이 이미지에서 나올 확률, 모든 정렬의 합)를 직접 계산해
  탐욕 결과의 우도와 비교하고, 사전 단어가 거의 같거나 더 그럴듯할 때만 바꾼다(사진 정보를 그대로 쓴다).
- 후보: 탐욕 결과와 글자 유사도가 높은 사전 단어 몇 개(rapidfuzz). 사전에 없는 일반 낱말은 우도 차이가 커서 바뀌지 않는다.
- 사전: 식약처 화장품 원료성분 사전(한글 표준명·이명, 영문 INCI를 띄어쓰기 단위로)과 대문자·첫 글자 대문자 형태.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

from rapidfuzz import fuzz, process

EDGE = re.compile(r"^([(\[\"'“‘]*)(.*?)([,.;:)\]\"'”’·]*)$")
SPLIT = re.compile(r"(?<!\d),(?![\s\d])|;")


def build_words(dict_csv: str | Path) -> list[str]:
    """사전 CSV(kr_name, inci, cas, synonyms) → 포장에 단어(띄어쓰기 단위)로 나타날 형태들."""
    out: set[str] = set()
    with open(dict_csv, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            for name in [r.get("kr_name") or ""] + SPLIT.split(r.get("synonyms") or ""):
                name = name.strip()
                if name:
                    out.add(name.replace(" ", ""))
            for inci in SPLIT.split(r.get("inci") or ""):
                for tok in inci.split():
                    tok = EDGE.match(tok).group(2)
                    if len(tok) >= 3 and re.search(r"[A-Za-z]", tok):
                        out.update({tok, tok.upper(), tok.capitalize()})
    return sorted(w for w in out if len(w) >= 2)


class Lexicon:
    def __init__(self, words: list[str], charset: list[str], margin: float = 4.0, conf_below: float = 0.97,
                 top: int = 8, min_ratio: float = 60):
        """margin: 사전 단어 우도가 탐욕 결과보다 이만큼(자연로그) 낮아도 사전 단어를 고른다.
        기본값은 lex_eval.py 실측(평가 1만 단어): margin 4.0·conf_below 0.97에서 망가뜨린 성분명 74.8→85.1%,
        깨끗한 성분명 97.7→98.7%, 맞던 단어를 망친 수는 고친 수의 4% 수준.
        conf_below: 탐욕 결과의 확신도가 이보다 낮은 단어만 다시 푼다(대부분의 깨끗한 단어는 건드리지 않음)."""
        self.idx = {c: i + 1 for i, c in enumerate(charset)}
        self.words = [w for w in words if all(c in self.idx for c in w)]
        self.margin, self.conf_below, self.top, self.min_ratio = margin, conf_below, top, min_ratio
        self.by_len: dict[int, list[str]] = {}
        self._pools: dict[int, list[str]] = {}
        for w in self.words:
            self.by_len.setdefault(len(w), []).append(w)

    @classmethod
    def from_csv(cls, dict_csv: str | Path, charset: list[str], **kw) -> "Lexicon":
        """사전 CSV, 또는 build_words 결과를 한 줄에 하나씩 담은 .txt.gz(서빙 템플릿에 넣는 형태)."""
        if str(dict_csv).endswith(".txt.gz"):
            import gzip
            words = [w for w in gzip.open(dict_csv, "rt", encoding="utf-8").read().splitlines() if w]
            return cls(words, charset, **kw)
        return cls(build_words(dict_csv), charset, **kw)

    def _pool(self, core: str) -> list[str]:
        """길이가 비슷한(0.7~1.4배) 사전 단어. 길이별로 한 번만 만들어 둔다."""
        n = len(core)
        if n not in self._pools:
            lo, hi = max(2, int(n * 0.7)), int(n * 1.4) + 1
            self._pools[n] = [w for L in range(lo, hi + 1) for w in self.by_len.get(L, [])]
        return self._pools[n]

    def _ll(self, logp, texts: list[str]) -> list[float]:
        """logp: T×C 로그 확률(torch). 각 글자열의 CTC 로그 우도."""
        import torch  # 사전 만들기(build_words)는 torch 없이 쓸 수 있게
        import torch.nn.functional as F

        T = logp.shape[0]
        tg = [torch.tensor([self.idx[c] for c in t], dtype=torch.long) for t in texts]
        ok = [i for i, t in enumerate(tg) if 0 < len(t) <= T]
        out = [float("-inf")] * len(texts)
        if not ok:
            return out
        lp = logp[:, None, :].expand(T, len(ok), logp.shape[1])
        tgt = torch.cat([tg[i] for i in ok])
        loss = F.ctc_loss(lp, tgt, torch.full((len(ok),), T, dtype=torch.long), torch.tensor([len(tg[i]) for i in ok]),
                          blank=0, reduction="none", zero_infinity=True)
        for j, i in enumerate(ok):
            out[i] = -float(loss[j])
        return out

    def correct(self, text: str, conf: float, logp) -> tuple[str, bool]:
        """탐욕 결과 text(확신도 conf)와 그 단어의 T×C 로그 확률 → (고친 글자, 고쳤는가)."""
        if conf >= self.conf_below or not text:
            return text, False
        lead, core, trail = EDGE.match(text).groups()
        if len(core) < 3 or not re.search(r"[A-Za-z가-힣]", core) or any(c not in self.idx for c in text):
            return text, False
        pool = self._pool(core)
        if not pool:
            return text, False
        cands = [c for c, s, _ in process.extract(core, pool, scorer=fuzz.ratio, limit=self.top, score_cutoff=self.min_ratio)
                 if c != core]
        if not cands:
            return text, False
        full = [lead + c + trail for c in cands]
        lls = self._ll(logp.float().cpu(), [text] + full)
        best = max(range(len(full)), key=lambda i: lls[i + 1])
        if lls[best + 1] >= lls[0] - self.margin:
            return full[best], True
        return text, False

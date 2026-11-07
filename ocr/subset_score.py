"""단어별 결과(pairs.tsv: 사진ID, 정답, 예측)를 전체·학습에 없던 제품 사진으로 나눠 잰다.

실행: python subset_score.py <pairs.tsv> <test_unseen_product_images.json> <ingredients_kr.txt>
"""
import json
import sys
from pathlib import Path

from baseline_easyocr import score

pairs = [l.split("\t") for l in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines() if l]
unseen = set(json.loads(Path(sys.argv[2]).read_text(encoding="utf-8")))
ing = {l.strip() for l in Path(sys.argv[3]).read_text(encoding="utf-8").splitlines() if l.strip()}
allp = [(t, p) for _, t, p in pairs]
newp = [(t, p) for i, t, p in pairs if i in unseen]
print(json.dumps({"all": score(allp, ing), "unseen_product": score(newp, ing)}, ensure_ascii=False))

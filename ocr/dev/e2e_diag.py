import json, zipfile, sys
from pathlib import Path
sys.path.insert(0, ".")
from e2e_eval import load_dict, standard, words_from_label
from pipeline import PackageOCR, extract_ingredients, group_lines
B = "../056.의약품,_화장품_패키징_OCR_데이터/01.데이터/2._Validation"
zi, zl = zipfile.ZipFile(f"{B}/원천데이터/VS1.zip"), zipfile.ZipFile(f"{B}/라벨링데이터/VL1.zip")
exact, names = load_dict("식약처_원료성분사전.csv")
unseen = set(json.load(open("../test_unseen_product_images.json")))
imgs = {Path(n).stem: n for n in zi.namelist() if "cosmetics" in n and n.lower().endswith((".jpg", ".png", ".jpeg"))}
ocr = PackageOCR("det.pt", "rec.pt"); k = 0
for n in sorted(zl.namelist()):
    s = Path(n).stem
    if "/cosmetics/" not in n or not n.endswith(".json") or s not in unseen or s not in imgs: continue
    ann = json.loads(zl.read(n)); gw = words_from_label(ann)
    gt_raw = extract_ingredients(group_lines(gw)); gt = {x for x in (standard(r, exact, names) for r in gt_raw) if x}
    if len(gt) < 5: continue
    r = ocr.read(zi.read(imgs[s])); pred = {x for x in (standard(q, exact, names) for q in r["ingredients"]) if x}
    miss = gt - pred
    print(f"== {s} gt {len(gt)} pred {len(pred)} miss {len(miss)} | 단어 gt {len(gw)} 예측 {len(r['words'])}")
    print("  miss:", list(miss)[:8])
    print("  pred raw 앞:", r["ingredients"][:6], "... 끝:", r["ingredients"][-4:])
    print("  gt raw 끝:", gt_raw[-4:])
    k += 1
    if k >= 6: break

import io, json, random, tarfile, os
from PIL import Image, ImageDraw, ImageFont
os.makedirs("fake_det", exist_ok=True); lines = []
font = ImageFont.load_default(size=28)
with tarfile.open("fake_det/det_00.tar", "w") as tar:
    for i in range(300):
        im = Image.new("L", (960, 1280), 235); d = ImageDraw.Draw(im); boxes = []
        y = 30
        while y < 1220:
            x = 20
            while x < 860:
                t = random.choice(["정제수,", "글리세린,", "Niacinamide", "1,2-Hexanediol", "부틸렌글라이콜"])
                b = d.textbbox((x, y), t, font=font)
                if b[2] > 940: break
                d.text((x, y), t, fill=20, font=font); boxes.append([b[0], b[1], b[2], b[3]]); x = b[2] + random.randint(15, 60)
            y += random.randint(45, 90)
        buf = io.BytesIO(); im.save(buf, "JPEG"); n = f"d_{i:04d}.jpg"; ti = tarfile.TarInfo(n); ti.size = buf.tell(); buf.seek(0); tar.addfile(ti, buf)
        lines.append(json.dumps({"path": f"00/{n}", "w": 960, "h": 1280, "split": "test" if i % 10 == 0 else "train", "boxes": boxes}))
open("fake_det/boxes.jsonl", "w").write("\n".join(lines) + "\n")

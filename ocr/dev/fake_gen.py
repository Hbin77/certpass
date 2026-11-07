import io, random, tarfile, os
from PIL import Image, ImageDraw
os.makedirs("fake", exist_ok=True); rows = []
words = ["Water", "Glycerin", "Niacinamide", "Butylene", "Glycol", "Extract", "1,2-Hexanediol", "Panthenol", "Allantoin", "Adenosine"]
with tarfile.open("fake/shard_00.tar", "w") as tar:
    for i in range(4000):
        t = random.choice(words); im = Image.new("L", (8 * len(t) + 8, 32), 255); ImageDraw.Draw(im).text((4, 10), t, fill=0)
        b = io.BytesIO(); im.save(b, "JPEG"); n = f"f_{i:05d}.jpg"; ti = tarfile.TarInfo(n); ti.size = b.tell(); b.seek(0); tar.addfile(ti, b)
        rows.append(f"00/{n}\t{t}\t{'test' if i % 10 == 0 else 'train'}\tf{i // 50}")
open("fake/labels.tsv", "w").write("path\ttext\tsplit\timage_id\n" + "\n".join(rows) + "\n")

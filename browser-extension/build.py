"""Generate the extension's arrow icons and a ZIP for unpacked Chrome installation."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "chrome"
ICONS = SOURCE / "icons"
ICONS.mkdir(exist_ok=True)
image = Image.new("RGBA", (256, 256))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((8, 8, 248, 248), radius=56, fill="#f4f4f5")
draw.line([(128, 52), (128, 168)], fill="#18181b", width=24)
draw.line([(80, 124), (128, 172), (176, 124)], fill="#18181b", width=24)
draw.line([(68, 204), (188, 204)], fill="#18181b", width=20)
for size in (16, 32, 48, 128):
    image.resize((size, size), Image.Resampling.LANCZOS).save(ICONS / f"icon-{size}.png")

output = ROOT.parent / "artifacts" / "video-grabber-chrome-extension.zip"
output.parent.mkdir(exist_ok=True)
with ZipFile(output, "w", ZIP_DEFLATED) as archive:
    for file in sorted(SOURCE.rglob("*")):
        if file.is_file() and file.suffix in {".js", ".json", ".html", ".css", ".png"}:
            archive.write(file, file.relative_to(SOURCE).as_posix())
print(f"Chrome extension prepared: {output}")

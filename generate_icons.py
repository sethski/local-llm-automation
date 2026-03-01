"""
generate_icons.py — Creates SethOS app icons for all platforms
Run: python generate_icons.py
Requires: pip install Pillow
"""
import os
from pathlib import Path

def create_icon():
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("Install Pillow first: pip install Pillow")
        return

    assets = Path(__file__).parent / "assets"
    assets.mkdir(exist_ok=True)

    # Create base 512x512 icon
    size = 512
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Background rounded square
    bg_color = (10, 10, 15, 255)     # #0a0a0f
    accent   = (124, 106, 247, 255)  # #7c6af7
    accent2  = (247, 79, 168, 255)   # #f74fa8

    # Draw rounded rect background
    draw.rounded_rectangle([0, 0, size, size], radius=100, fill=bg_color)

    # Draw gradient-ish circle
    for i in range(80):
        alpha = int(255 * (1 - i / 80))
        r = int(accent[0] + (accent2[0] - accent[0]) * i / 80)
        g = int(accent[1] + (accent2[1] - accent[1]) * i / 80)
        b = int(accent[2] + (accent2[2] - accent[2]) * i / 80)
        draw.ellipse([156 - i, 156 - i, 356 + i, 356 + i],
                     outline=(r, g, b, max(0, alpha - i * 2)), width=2)

    # Draw "S" letter
    draw.rounded_rectangle([160, 160, 352, 352], radius=40, fill=(20, 20, 30, 255))
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 180)
    except:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), "S", font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((size - tw) / 2 - bbox[0], (size - th) / 2 - bbox[1] - 10),
              "S", font=font, fill=(124, 106, 247, 255))

    # Save PNG (Linux + general)
    img.save(str(assets / "icon.png"))
    print("✓ icon.png")

    # Tray icon (22x22 for macOS, white/dark)
    tray = img.resize((64, 64), Image.LANCZOS)
    tray.save(str(assets / "iconTemplate.png"))
    print("✓ iconTemplate.png")

    # Windows ICO (multiple sizes)
    ico_sizes = [(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)]
    ico_imgs = [img.resize(s, Image.LANCZOS) for s in ico_sizes]
    ico_imgs[0].save(str(assets / "icon.ico"), format="ICO",
                     sizes=ico_sizes, append_images=ico_imgs[1:])
    print("✓ icon.ico")

    # macOS ICNS — save as PNG, electron-builder converts it
    img.resize((1024, 1024), Image.LANCZOS).save(str(assets / "icon.icns"))
    print("✓ icon.icns (PNG — electron-builder will convert)")

    print("\nAll icons created in ./assets/")

if __name__ == "__main__":
    create_icon()

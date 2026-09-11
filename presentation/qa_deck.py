"""
QA for the generated deck.

LibreOffice is not installed here, so instead of rendering to images this
measures every text frame directly against the real Windows font files that
PowerPoint will use. That is stricter than a LibreOffice preview, which
substitutes fonts and reports approximate widths.

Checks: text overflow, slide-edge margins, shape overlaps, and content dump.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import ImageFont
from pptx import Presentation
from pptx.util import Emu

DECK = Path(sys.argv[1] if len(sys.argv) > 1 else "Supply-Chain-Risk-Monitor.pptx")
FONTS = Path(r"C:\Windows\Fonts")
SLIDE_W, SLIDE_H = 13.3, 7.5
MIN_MARGIN = 0.5

FONT_FILES = {
    ("Calibri", False, False): "calibri.ttf",
    ("Calibri", True, False): "calibrib.ttf",
    ("Calibri", False, True): "calibrii.ttf",
    ("Calibri", True, True): "calibriz.ttf",
    ("Cambria", False, False): "cambria.ttc",
    ("Cambria", True, False): "cambriab.ttf",
    ("Cambria", False, True): "cambriai.ttf",
    ("Cambria", True, True): "cambriaz.ttf",
    ("Consolas", False, False): "consola.ttf",
    ("Consolas", True, False): "consolab.ttf",
}
_cache: dict = {}


def font(name: str, size: float, bold: bool, italic: bool):
    key = (name, bold, italic, round(size, 1))
    if key in _cache:
        return _cache[key]
    fn = FONT_FILES.get((name, bold, italic)) or FONT_FILES.get((name, False, False))
    if not fn:
        fn = "calibri.ttf"
    px = max(1, int(round(size * 96 / 72)))  # pt -> px at 96 dpi
    path = FONTS / fn
    f = ImageFont.truetype(str(path), px, index=0) if path.exists() else ImageFont.load_default()
    _cache[key] = f
    return f


def text_width_in(s: str, name: str, size: float, bold: bool, italic: bool) -> float:
    f = font(name, size, bold, italic)
    return f.getlength(s) / 96.0


def wrap_lines(text: str, width_in: float, name: str, size: float, bold: bool,
               italic: bool) -> int:
    """Greedy word wrap; returns the number of rendered lines."""
    total = 0
    for para in text.split("\n"):
        words = para.split()
        if not words:
            total += 1
            continue
        line, n = "", 1
        for w in words:
            trial = w if not line else f"{line} {w}"
            if text_width_in(trial, name, size, bold, italic) <= width_in or not line:
                line = trial
            else:
                n += 1
                line = w
        total += n
    return total


prs = Presentation(str(DECK))
issues: list[str] = []
warnings: list[str] = []

print(f"Deck: {DECK.name}")
print(f"Slide size: {Emu(prs.slide_width).inches:.2f}in x {Emu(prs.slide_height).inches:.2f}in")
print(f"Slides: {len(prs.slides)}\n")

for idx, slide in enumerate(prs.slides, start=1):
    boxes = []
    for sh in slide.shapes:
        if sh.left is None or sh.top is None:
            continue
        x, y = Emu(sh.left).inches, Emu(sh.top).inches
        w, h = Emu(sh.width).inches, Emu(sh.height).inches
        boxes.append((sh, x, y, w, h))

        # --- slide-edge margin -------------------------------------------
        if x < MIN_MARGIN - 0.01 or y < MIN_MARGIN - 0.01 \
                or x + w > SLIDE_W - MIN_MARGIN + 0.01 \
                or y + h > SLIDE_H - MIN_MARGIN + 0.01:
            name = (sh.text_frame.text[:34] if sh.has_text_frame else sh.shape_type)
            warnings.append(
                f"S{idx}: near/over edge  x={x:.2f} y={y:.2f} w={w:.2f} h={h:.2f}  «{name}»"
            )

        # --- off-slide (hard failure) -------------------------------------
        if x + w > SLIDE_W + 0.01 or y + h > SLIDE_H + 0.01 or x < -0.01 or y < -0.01:
            issues.append(f"S{idx}: OFF-SLIDE  x={x:.2f} y={y:.2f} w={w:.2f} h={h:.2f}")

        # --- text overflow --------------------------------------------------
        if not sh.has_text_frame:
            continue
        tf = sh.text_frame
        txt = tf.text
        if not txt.strip():
            continue

        total_h = 0.0
        max_size = 0.0
        for para in tf.paragraphs:
            ptext = "".join(r.text for r in para.runs)
            if not ptext:
                total_h += (max_size or 12) * 1.2 / 72.0
                continue
            r0 = para.runs[0]
            size = (r0.font.size.pt if r0.font.size else 12.0)
            bold = bool(r0.font.bold)
            italic = bool(r0.font.italic)
            fname = r0.font.name or "Calibri"
            max_size = max(max_size, size)
            spacing = para.line_spacing if isinstance(para.line_spacing, float) else 1.0
            # pptxgenjs bullets indent the text; account for it
            avail = w - 0.06
            if para.level or ptext.startswith(("•", "-")):
                avail -= 0.2
            nlines = wrap_lines(ptext, max(avail, 0.4), fname, size, bold, italic)
            line_h = size * 1.21 * spacing / 72.0
            total_h += nlines * line_h
            after = para.space_after.pt / 72.0 if para.space_after else 0.0
            total_h += after

        if total_h > h + 0.035:
            issues.append(
                f"S{idx}: TEXT OVERFLOW  needs {total_h:.2f}in, box {h:.2f}in  "
                f"(+{total_h - h:.2f})  «{txt[:56]}…»"
            )

    # --- overlap between text-bearing shapes -----------------------------
    texts = [b for b in boxes if b[0].has_text_frame and b[0].text_frame.text.strip()]
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            _, ax, ay, aw, ah = texts[i]
            _, bx, by, bw, bh = texts[j]
            ox = min(ax + aw, bx + bw) - max(ax, bx)
            oy = min(ay + ah, by + bh) - max(ay, by)
            if ox > 0.06 and oy > 0.06:
                area = ox * oy
                if area > 0.05:
                    warnings.append(
                        f"S{idx}: text boxes overlap {area:.2f}in²  "
                        f"«{texts[i][0].text_frame.text[:26]}» / "
                        f"«{texts[j][0].text_frame.text[:26]}»"
                    )

print("=" * 74)
print("CONTENT")
print("=" * 74)
for idx, slide in enumerate(prs.slides, start=1):
    lines = [sh.text_frame.text.replace("\n", " | ")
             for sh in slide.shapes
             if sh.has_text_frame and sh.text_frame.text.strip()]
    print(f"\n--- Slide {idx} ---")
    for ln in lines[:4]:
        print(f"   {ln[:96]}")
    if len(lines) > 4:
        print(f"   … +{len(lines) - 4} more text shapes")
    notes = slide.notes_slide.notes_text_frame.text if slide.has_notes_slide else ""
    print(f"   NOTES: {'yes' if notes.strip() else 'MISSING'}")

print("\n" + "=" * 74)
print(f"HARD ISSUES: {len(issues)}")
print("=" * 74)
for i in issues:
    print("  ✗", i)
print(f"\nWARNINGS: {len(warnings)}")
for wn in warnings:
    print("  !", wn)

sys.exit(1 if issues else 0)

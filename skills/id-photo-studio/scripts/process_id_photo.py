#!/usr/bin/env python3
"""
ID Photo Studio - Precision Cropping, Background Normalization & L-Size Sheet Generator.

Usage examples:
  # Auto-detect head from uniform background and create Resume (40x30mm) + L-size sheet
  python process_id_photo.py --input ai_portrait.png --output-dir ./output --preset resume

  # Specify exact head-top and chin y-positions (normalized 0.0 to 1.0) for pixel-perfect framing
  python process_id_photo.py --input ai_portrait.png --output-dir ./output --preset mynumber --head-top 0.12 --chin-bottom 0.62

  # Create multiple presets on a single L-size sheet (e.g., resume + license)
  python process_id_photo.py --input ai_portrait.png --output-dir ./output --preset resume --bg-color blue --replace-bg
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont


@dataclass(frozen=True)
class PhotoSpec:
    preset_id: str
    label_en: str
    label_ja: str
    width_mm: float
    height_mm: float
    top_margin_ratio: float   # Distance from top of photo to top of head / total height
    head_height_ratio: float  # Distance from top of head to chin / total height


PRESETS: Dict[str, PhotoSpec] = {
    "resume": PhotoSpec(
        preset_id="resume",
        label_en="Resume / General (30x40mm)",
        label_ja="履歴書・一般証明 (縦40×横30mm)",
        width_mm=30.0,
        height_mm=40.0,
        top_margin_ratio=0.12,   # ~4.8mm
        head_height_ratio=0.65,  # ~26mm
    ),
    "mynumber": PhotoSpec(
        preset_id="mynumber",
        label_en="MyNumber / Passport (35x45mm)",
        label_ja="マイナンバー・パスポート (縦45×横35mm)",
        width_mm=35.0,
        height_mm=45.0,
        top_margin_ratio=0.09,   # ~4.0mm
        head_height_ratio=0.75,  # ~33.8mm
    ),
    "passport": PhotoSpec(
        preset_id="passport",
        label_en="Passport (35x45mm)",
        label_ja="パスポート・国際規格 (縦45×横35mm)",
        width_mm=35.0,
        height_mm=45.0,
        top_margin_ratio=0.09,   # ~4.0mm
        head_height_ratio=0.75,  # ~33.8mm
    ),
    "license": PhotoSpec(
        preset_id="license",
        label_en="Driver License (24x30mm)",
        label_ja="運転免許証 (縦30×横24mm)",
        width_mm=24.0,
        height_mm=30.0,
        top_margin_ratio=0.10,   # ~3.0mm
        head_height_ratio=0.67,  # ~20.0mm
    ),
    "toeic": PhotoSpec(
        preset_id="toeic",
        label_en="TOEIC / Qualification (30x40mm)",
        label_ja="TOEIC・各種資格試験 (縦40×横30mm)",
        width_mm=30.0,
        height_mm=40.0,
        top_margin_ratio=0.12,
        head_height_ratio=0.65,
    ),
    "us_visa": PhotoSpec(
        preset_id="us_visa",
        label_en="US Visa (51x51mm)",
        label_ja="米国ビザ (縦51×横51mm)",
        width_mm=51.0,
        height_mm=51.0,
        top_margin_ratio=0.15,   # ~7.6mm
        head_height_ratio=0.59,  # ~30mm
    ),
}

BG_COLORS: Dict[str, Tuple[int, int, int]] = {
    "white": (255, 255, 255),
    "blue": (212, 230, 246),      # #D4E6F6 Standard Japanese ID photo light blue
    "gray": (230, 232, 234),      # #E6E8EA Clean neutral light gray
    "sky": (195, 222, 248),       # Slightly deeper sky blue
}

SHEET_SIZES_MM: Dict[str, Tuple[float, float]] = {
    "L": (127.0, 89.0),   # Landscape 127x89mm
    "2L": (178.0, 127.0), # Landscape 178x127mm
}


def mm_to_px(mm: float, dpi: int) -> int:
    return int(round(mm * dpi / 25.4))


def load_ui_font(size_px: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a system font supporting Japanese/English on Windows/macOS/Linux, with fallback."""
    candidates = [
        r"C:\Windows\Fonts\meiryo.ttc",
        r"C:\Windows\Fonts\YuGothM.ttc",
        r"C:\Windows\Fonts\msgothic.ttc",
        r"C:\Windows\Fonts\arial.ttf",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size_px)
            except Exception:
                continue
    return ImageFont.load_default()


def parse_color(color_str: str) -> Tuple[int, int, int]:
    key = color_str.strip().lower()
    if key in BG_COLORS:
        return BG_COLORS[key]
    if key.startswith("#") and len(key) == 7:
        return (int(key[1:3], 16), int(key[3:5], 16), int(key[5:7], 16))
    raise ValueError(f"Unsupported color '{color_str}'. Use one of {list(BG_COLORS.keys())} or #RRGGBB.")


def sample_corner_bg_color(img_rgb: np.ndarray) -> np.ndarray:
    """Estimate background color from top-left and top-right corners."""
    h, w, _ = img_rgb.shape
    patch = max(4, min(h, w) // 25)
    tl = img_rgb[:patch, :patch].reshape(-1, 3)
    tr = img_rgb[:patch, w - patch:].reshape(-1, 3)
    samples = np.vstack([tl, tr])
    return np.median(samples, axis=0)


def compute_foreground_mask(img_rgb: np.ndarray, tolerance: float = 28.0) -> np.ndarray:
    """
    Compute a soft alpha mask (0.0 background to 1.0 foreground) by flood-filling
    from the top and side borders against the estimated corner background color.
    """
    h, w, _ = img_rgb.shape
    bg_color = sample_corner_bg_color(img_rgb)
    diff = np.linalg.norm(img_rgb.astype(np.float32) - bg_color[None, None, :], axis=2)

    try:
        from scipy import ndimage
        bg_candidates = diff < tolerance
        # Seed from top/left/right borders (excluding bottom torso area)
        seeds = np.zeros((h, w), dtype=bool)
        seeds[0, :] = bg_candidates[0, :]
        seeds[: int(h * 0.7), 0] = bg_candidates[: int(h * 0.7), 0]
        seeds[: int(h * 0.7), w - 1] = bg_candidates[: int(h * 0.7), w - 1]

        labeled, _ = ndimage.label(bg_candidates)
        seed_labels = np.unique(labeled[seeds])
        seed_labels = seed_labels[seed_labels > 0]
        connected_bg = np.isin(labeled, seed_labels)

        # Fill small holes inside foreground
        fg_binary = ~connected_bg
        fg_binary = ndimage.binary_fill_holes(fg_binary)

        # Soft feathering at boundary
        alpha_img = Image.fromarray((fg_binary.astype(np.uint8) * 255), mode="L")
        alpha_img = alpha_img.filter(ImageFilter.GaussianBlur(radius=1.2))
        alpha = np.asarray(alpha_img, dtype=np.float32) / 255.0
        # Keep transition tight around edges
        alpha = np.clip((alpha - 0.15) / 0.75, 0.0, 1.0)
        return alpha
    except Exception:
        # Fallback without scipy
        alpha = np.clip((diff - tolerance * 0.6) / (tolerance * 0.8), 0.0, 1.0)
        return alpha


def replace_background(
    img: Image.Image, target_rgb: Tuple[int, int, int], tolerance: float = 28.0
) -> Tuple[Image.Image, np.ndarray]:
    """Replace uniform background with exact target RGB color and return (new_image, fg_mask)."""
    rgb_arr = np.asarray(img.convert("RGB"))
    fg_mask = compute_foreground_mask(rgb_arr, tolerance=tolerance)
    bg_arr = np.full_like(rgb_arr, target_rgb, dtype=np.uint8)
    blended = (
        rgb_arr.astype(np.float32) * fg_mask[:, :, None]
        + bg_arr.astype(np.float32) * (1.0 - fg_mask[:, :, None])
    )
    out_img = Image.fromarray(np.clip(blended, 0, 255).astype(np.uint8), mode="RGB")
    return out_img, fg_mask


def detect_head_landmarks(
    img: Image.Image,
    fg_mask: Optional[np.ndarray] = None,
    head_top_arg: Optional[float] = None,
    chin_bottom_arg: Optional[float] = None,
    center_x_arg: Optional[float] = None,
) -> Tuple[float, float, float, str]:
    """
    Return (head_top_y_ratio, chin_bottom_y_ratio, center_x_ratio, detection_method).
    Uses explicit args if given; otherwise combines foreground silhouette top detection
    with head-width contour analysis.
    """
    rgb_arr = np.asarray(img.convert("RGB"))
    h, w, _ = rgb_arr.shape

    if fg_mask is None:
        fg_mask = compute_foreground_mask(rgb_arr)

    method_parts = []

    # 1. Find top of head from foreground silhouette
    row_fg_counts = (fg_mask > 0.5).sum(axis=1)
    min_head_pixels = max(5, int(w * 0.04))
    fg_rows = np.where(row_fg_counts >= min_head_pixels)[0]

    if head_top_arg is not None:
        head_top_ratio = head_top_arg
        method_parts.append("explicit_head_top")
    elif len(fg_rows) > 0 and fg_rows[0] > 2 and fg_rows[0] < int(h * 0.55):
        head_top_ratio = float(fg_rows[0]) / float(h)
        method_parts.append("silhouette_head_top")
    else:
        head_top_ratio = 0.12
        method_parts.append("default_head_top")

    # 2. Estimate horizontal center of the head (upper portion of foreground)
    head_band_top = int(head_top_ratio * h)
    head_band_bottom = min(h, int((head_top_ratio + 0.35) * h))
    band_mask = fg_mask[head_band_top:head_band_bottom, :] > 0.5

    if center_x_arg is not None:
        center_x_ratio = center_x_arg
        method_parts.append("explicit_center_x")
    elif band_mask.any():
        cols = np.where(band_mask.any(axis=0))[0]
        center_x_ratio = float(cols[0] + cols[-1]) / (2.0 * w)
        method_parts.append("silhouette_center_x")
    else:
        center_x_ratio = 0.5
        method_parts.append("default_center_x")

    # 3. Estimate chin position
    if chin_bottom_arg is not None:
        chin_bottom_ratio = chin_bottom_arg
        method_parts.append("explicit_chin")
    else:
        # Try OpenCV Haar cascade if installed
        chin_detected = None
        try:
            import cv2  # type: ignore
            gray = cv2.cvtColor(rgb_arr, cv2.COLOR_RGB2GRAY)
            cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            face_cascade = cv2.CascadeClassifier(cascade_path)
            faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
            if len(faces) > 0:
                # Pick largest face
                fx, fy, fw, fh = max(faces, key=lambda b: b[2] * b[3])
                chin_detected = float(fy + fh) / float(h)
                if center_x_arg is None:
                    center_x_ratio = float(fx + fw / 2.0) / float(w)
                method_parts.append("opencv_face_chin")
        except Exception:
            pass

        if chin_detected is not None and (chin_detected - head_top_ratio) > 0.20:
            chin_bottom_ratio = chin_detected
        else:
            # Estimate from head silhouette width:
            # Measure horizontal width of the head around temple/cheek level
            temple_y1 = min(h - 1, int((head_top_ratio + 0.08) * h))
            temple_y2 = min(h, int((head_top_ratio + 0.25) * h))
            widths = []
            for ry in range(temple_y1, temple_y2):
                cols = np.where(fg_mask[ry, :] > 0.5)[0]
                if len(cols) > 10:
                    widths.append(cols[-1] - cols[0])
            if widths:
                head_width_px = float(np.percentile(widths, 75))
                # Human head aspect ratio (total head height from hair top to chin / head width with hair)
                # is typically ~1.30 to 1.38
                estimated_head_h_ratio = (head_width_px * 1.34) / float(h)
                estimated_head_h_ratio = float(np.clip(estimated_head_h_ratio, 0.32, 0.68))
                chin_bottom_ratio = head_top_ratio + estimated_head_h_ratio
                method_parts.append("head_width_aspect_chin")
            else:
                chin_bottom_ratio = head_top_ratio + 0.48
                method_parts.append("default_chin")

    return head_top_ratio, chin_bottom_ratio, center_x_ratio, "+".join(method_parts)


def crop_and_frame_id_photo(
    img: Image.Image,
    spec: PhotoSpec,
    dpi: int,
    head_top_ratio: float,
    chin_bottom_ratio: float,
    center_x_ratio: float,
    pad_rgb: Tuple[int, int, int],
) -> Image.Image:
    """
    Scale and crop/pad `img` so that:
    - Output size is exact (target_w_px, target_h_px)
    - Head top is placed at `spec.top_margin_ratio * target_h_px`
    - Chin is placed at `(spec.top_margin_ratio + spec.head_height_ratio) * target_h_px`
    - Horizontal center of head is at `0.5 * target_w_px`
    """
    target_w = mm_to_px(spec.width_mm, dpi)
    target_h = mm_to_px(spec.height_mm, dpi)

    src_w, src_h = img.size
    src_head_top_px = head_top_ratio * src_h
    src_chin_px = chin_bottom_ratio * src_h
    src_head_h_px = max(10.0, src_chin_px - src_head_top_px)
    src_center_x_px = center_x_ratio * src_w

    # Required head height in target image
    target_head_h_px = spec.head_height_ratio * target_h
    scale = target_head_h_px / src_head_h_px

    scaled_w = max(1, int(round(src_w * scale)))
    scaled_h = max(1, int(round(src_h * scale)))
    scaled_img = img.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)

    # Where the head top and center X are in scaled_img
    scaled_head_top_y = src_head_top_px * scale
    scaled_center_x = src_center_x_px * scale

    # Desired position in final canvas
    desired_head_top_y = spec.top_margin_ratio * target_h
    desired_center_x = 0.5 * target_w

    # Offset to paste scaled_img onto canvas of size (target_w, target_h)
    paste_x = int(round(desired_center_x - scaled_center_x))
    paste_y = int(round(desired_head_top_y - scaled_head_top_y))

    canvas = Image.new("RGB", (target_w, target_h), pad_rgb)

    # If the bottom of scaled_img doesn't reach the bottom of canvas, extend bottom rows first
    if paste_y + scaled_h < target_h:
        # Clamp or stretch bottom strip slightly if needed, or warn
        bottom_gap = target_h - (paste_y + scaled_h)
        bottom_strip = scaled_img.crop((0, scaled_h - 2, scaled_w, scaled_h)).resize(
            (scaled_w, bottom_gap + 2), Image.Resampling.BILINEAR
        )
        canvas.paste(bottom_strip, (paste_x, paste_y + scaled_h - 1))

    canvas.paste(scaled_img, (paste_x, paste_y))
    return canvas


def create_verification_preview(
    single_img: Image.Image,
    spec: PhotoSpec,
    dpi: int,
    output_path: Path,
) -> None:
    """
    Create a side-by-side verification image:
    Left: Clean final ID photo
    Right: Annotated photo showing millimeter ruler, Top Margin line, Head Center line, and Chin line.
    """
    w, h = single_img.size
    margin = 40
    canvas_w = w * 2 + margin * 3
    canvas_h = h + margin * 2 + 55
    preview = Image.new("RGB", (canvas_w, canvas_h), (245, 247, 250))
    draw = ImageDraw.Draw(preview)
    font_title = load_ui_font(15)
    font_small = load_ui_font(13)

    # Left: Clean photo
    left_x, top_y = margin, margin + 30
    preview.paste(single_img, (left_x, top_y))
    draw.rectangle([left_x - 1, top_y - 1, left_x + w, top_y + h], outline=(180, 180, 180), width=1)
    draw.text((left_x, 12), f"Clean: {spec.width_mm:.0f}x{spec.height_mm:.0f}mm ({w}x{h}px)", fill=(30, 30, 30), font=font_title)

    # Right: Annotated photo
    right_x = margin * 2 + w
    preview.paste(single_img, (right_x, top_y))
    draw.rectangle([right_x - 1, top_y - 1, right_x + w, top_y + h], outline=(100, 100, 100), width=1)
    draw.text((right_x, 12), "Alignment & Margin Check (位置検証)", fill=(30, 30, 30), font=font_title)

    # Guide lines on right image
    head_top_y = int(round(top_y + spec.top_margin_ratio * h))
    chin_y = int(round(top_y + (spec.top_margin_ratio + spec.head_height_ratio) * h))
    center_x = int(round(right_x + w * 0.5))

    # Center vertical dashed-like line
    for y in range(top_y, top_y + h, 8):
        draw.line([(center_x, y), (center_x, min(y + 4, top_y + h))], fill=(0, 140, 255), width=1)

    # Head top line (Green)
    draw.line([(right_x, head_top_y), (right_x + w, head_top_y)], fill=(0, 180, 80), width=2)
    top_mm = spec.top_margin_ratio * spec.height_mm
    draw.text((right_x + 6, max(top_y + 2, head_top_y - 18)), f"Head Top (~{top_mm:.1f}mm)", fill=(0, 130, 50), font=font_small)

    # Chin bottom line (Red/Orange)
    draw.line([(right_x, chin_y), (right_x + w, chin_y)], fill=(230, 70, 30), width=2)
    head_mm = spec.head_height_ratio * spec.height_mm
    draw.text((right_x + 6, min(top_y + h - 20, chin_y + 4)), f"Chin (Head ~{head_mm:.1f}mm)", fill=(200, 50, 20), font=font_small)

    # Footer info
    footer_text = f"Preset: {spec.preset_id} ({spec.label_ja}) | DPI: {dpi}"
    draw.text((margin, top_y + h + 15), footer_text, fill=(80, 80, 80), font=font_small)

    preview.save(output_path, quality=95)


def generate_print_sheet(
    single_img: Image.Image,
    spec: PhotoSpec,
    sheet_type: str,
    dpi: int,
    output_path: Path,
    count: Optional[int] = None,
) -> int:
    """
    Arrange multiple copies of `single_img` onto an L-size (89x127mm) or 2L-size (127x178mm) sheet
    with cut marks (トンボ), a 50mm calibration scale, and convenience-store printing notes.
    Automatically picks portrait vs landscape orientation to maximize the number of photos.
    Returns the number of photos placed on the sheet.
    """
    if sheet_type not in SHEET_SIZES_MM:
        raise ValueError(f"Unsupported sheet size '{sheet_type}'. Choose from {list(SHEET_SIZES_MM.keys())}.")

    base_long_mm, base_short_mm = SHEET_SIZES_MM[sheet_type]
    photo_w, photo_h = single_img.size
    gap_px = mm_to_px(3.5, dpi)  # 3.5mm spacing between photos for easy cutting

    def calc_grid(w_mm: float, h_mm: float) -> Tuple[int, int, int, int]:
        sw_px = mm_to_px(w_mm, dpi)
        sh_px = mm_to_px(h_mm, dpi)
        avail_w = sw_px - 2 * mm_to_px(7.0, dpi)
        avail_h = sh_px - mm_to_px(9.0, dpi) - mm_to_px(12.0, dpi)
        c = max(1, (avail_w + gap_px) // (photo_w + gap_px))
        r = max(1, (avail_h + gap_px) // (photo_h + gap_px))
        return c, r, sw_px, sh_px

    # Compare Landscape (127x89) vs Portrait (89x127) and pick whichever fits more photos
    c_land, r_land, sw_land, sh_land = calc_grid(base_long_mm, base_short_mm)
    c_port, r_port, sw_port, sh_port = calc_grid(base_short_mm, base_long_mm)

    if (c_port * r_port) > (c_land * r_land):
        cols, rows, sheet_w_px, sheet_h_px = c_port, r_port, sw_port, sh_port
        sheet_w_mm, sheet_h_mm = base_short_mm, base_long_mm
    else:
        cols, rows, sheet_w_px, sheet_h_px = c_land, r_land, sw_land, sh_land
        sheet_w_mm, sheet_h_mm = base_long_mm, base_short_mm

    safe_margin_y_top = mm_to_px(9.0, dpi)
    safe_margin_y_bottom = mm_to_px(12.0, dpi)
    avail_h = sheet_h_px - safe_margin_y_top - safe_margin_y_bottom

    max_capacity = cols * rows
    total_photos = min(count, max_capacity) if count is not None else max_capacity

    sheet = Image.new("RGB", (sheet_w_px, sheet_h_px), (255, 255, 255))
    draw = ImageDraw.Draw(sheet)
    font_header = load_ui_font(max(12, mm_to_px(1.55, dpi)))
    font_ruler = load_ui_font(max(11, mm_to_px(1.45, dpi)))

    grid_w = cols * photo_w + (cols - 1) * gap_px
    grid_h = rows * photo_h + (rows - 1) * gap_px

    start_x = (sheet_w_px - grid_w) // 2
    start_y = safe_margin_y_top + max(0, (avail_h - grid_h) // 2)

    trim_len = mm_to_px(2.5, dpi)
    trim_offset = mm_to_px(0.8, dpi)
    trim_color = (120, 120, 120)
    border_color = (210, 210, 210)

    placed = 0
    for r in range(rows):
        for c in range(cols):
            if placed >= total_photos:
                break
            x0 = start_x + c * (photo_w + gap_px)
            y0 = start_y + r * (photo_h + gap_px)
            x1 = x0 + photo_w
            y1 = y0 + photo_h

            sheet.paste(single_img, (x0, y0))
            draw.rectangle([x0, y0, x1 - 1, y1 - 1], outline=border_color, width=1)

            # Corner crop marks (トンボ)
            draw.line([(x0 - trim_offset - trim_len, y0), (x0 - trim_offset, y0)], fill=trim_color, width=1)
            draw.line([(x0, y0 - trim_offset - trim_len), (x0, y0 - trim_offset)], fill=trim_color, width=1)
            draw.line([(x1 + trim_offset, y0), (x1 + trim_offset + trim_len, y0)], fill=trim_color, width=1)
            draw.line([(x1 - 1, y0 - trim_offset - trim_len), (x1 - 1, y0 - trim_offset)], fill=trim_color, width=1)
            draw.line([(x0 - trim_offset - trim_len, y1 - 1), (x0 - trim_offset, y1 - 1)], fill=trim_color, width=1)
            draw.line([(x0, y1 + trim_offset), (x0, y1 + trim_offset + trim_len)], fill=trim_color, width=1)
            draw.line([(x1 + trim_offset, y1 - 1), (x1 + trim_offset + trim_len, y1 - 1)], fill=trim_color, width=1)
            draw.line([(x1 - 1, y1 + trim_offset), (x1 - 1, y1 + trim_offset + trim_len)], fill=trim_color, width=1)

            placed += 1

    # Header text
    header_y = mm_to_px(3.2, dpi)
    header_text = f"{spec.label_ja} | {sheet_type}判 ({sheet_w_mm:.0f}x{sheet_h_mm:.0f}mm) | フチあり/実寸(100%)印刷推奨"
    draw.text((start_x, header_y), header_text, fill=(80, 80, 80), font=font_header)

    # Bottom calibration ruler (50mm scale bar with 10mm ticks)
    ruler_y = sheet_h_px - mm_to_px(6.0, dpi)
    ruler_x0 = start_x
    ruler_len_mm = 50
    ruler_x1 = ruler_x0 + mm_to_px(ruler_len_mm, dpi)
    draw.line([(ruler_x0, ruler_y), (ruler_x1, ruler_y)], fill=(70, 70, 70), width=2)

    for mm_tick in range(0, ruler_len_mm + 1, 10):
        tx = ruler_x0 + mm_to_px(mm_tick, dpi)
        tick_h = mm_to_px(1.8, dpi) if mm_tick in (0, 50) else mm_to_px(1.2, dpi)
        draw.line([(tx, ruler_y - tick_h), (tx, ruler_y + tick_h)], fill=(70, 70, 70), width=2)

    draw.text(
        (ruler_x1 + mm_to_px(2.0, dpi), ruler_y - mm_to_px(1.6, dpi)),
        "← 50mm実寸確認スケール",
        fill=(90, 90, 90),
        font=font_ruler,
    )

    sheet.save(output_path, quality=95, dpi=(dpi, dpi))
    return placed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Process an AI-retouched or studio portrait into standard ID photo + L-size print sheet."
    )
    parser.add_argument("--input", "-i", required=True, help="Path to input portrait image")
    parser.add_argument("--output-dir", "-o", required=True, help="Directory to save generated outputs")
    parser.add_argument(
        "--preset",
        "-p",
        default="resume",
        choices=list(PRESETS.keys()) + ["custom"],
        help="ID photo preset specification (default: resume)",
    )
    parser.add_argument("--width-mm", type=float, help="Custom width in mm (used when --preset custom)")
    parser.add_argument("--height-mm", type=float, help="Custom height in mm (used when --preset custom)")
    parser.add_argument("--dpi", type=int, default=300, help="Output resolution in DPI (default: 300)")
    parser.add_argument(
        "--bg-color",
        default="white",
        help="Background color name (white, blue, gray, sky) or hex (#RRGGBB). Used for padding or --replace-bg.",
    )
    parser.add_argument(
        "--replace-bg",
        action="store_true",
        help="Actively replace the uniform background of the input image with --bg-color.",
    )
    parser.add_argument(
        "--bg-tolerance",
        type=float,
        default=28.0,
        help="Color distance tolerance for background detection/replacement (default: 28.0)",
    )
    parser.add_argument(
        "--head-top",
        type=float,
        default=None,
        help="Optional manual override: Y ratio (0.0 to 1.0) of the very top of the hair/head in input image",
    )
    parser.add_argument(
        "--chin-bottom",
        type=float,
        default=None,
        help="Optional manual override: Y ratio (0.0 to 1.0) of the bottom of the chin in input image",
    )
    parser.add_argument(
        "--center-x",
        type=float,
        default=None,
        help="Optional manual override: X ratio (0.0 to 1.0) of the horizontal center of the face",
    )
    parser.add_argument(
        "--sheet-size",
        default="L",
        choices=["L", "2L", "none"],
        help="Generate printable multi-up sheet (L=127x89mm, 2L=178x127mm, none=skip)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=None,
        help="Number of photos to place on the print sheet (defaults to max capacity that fits)",
    )
    parser.add_argument(
        "--prefix",
        default="id_photo",
        help="Filename prefix for generated outputs (default: id_photo)",
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        return 1

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.preset == "custom":
        if not args.width_mm or not args.height_mm:
            print("Error: --width-mm and --height-mm are required when --preset custom is used.", file=sys.stderr)
            return 1
        spec = PhotoSpec(
            preset_id="custom",
            label_en=f"Custom ({args.width_mm:.0f}x{args.height_mm:.0f}mm)",
            label_ja=f"カスタム (縦{args.height_mm:.0f}×横{args.width_mm:.0f}mm)",
            width_mm=args.width_mm,
            height_mm=args.height_mm,
            top_margin_ratio=0.12,
            head_height_ratio=0.65,
        )
    else:
        spec = PRESETS[args.preset]

    target_bg_rgb = parse_color(args.bg_color)
    img = Image.open(input_path).convert("RGB")
    rgb_arr = np.asarray(img)

    if args.replace_bg:
        working_img, fg_mask = replace_background(img, target_bg_rgb, tolerance=args.bg_tolerance)
        pad_rgb = target_bg_rgb
    else:
        working_img = img
        fg_mask = compute_foreground_mask(rgb_arr, tolerance=args.bg_tolerance)
        # Use actual corner background color for seamless canvas padding unless user explicitly asked for bg replacement
        corner_rgb = sample_corner_bg_color(rgb_arr)
        pad_rgb = (int(corner_rgb[0]), int(corner_rgb[1]), int(corner_rgb[2]))

    head_top, chin_bottom, center_x, method = detect_head_landmarks(
        working_img,
        fg_mask=fg_mask,
        head_top_arg=args.head_top,
        chin_bottom_arg=args.chin_bottom,
        center_x_arg=args.center_x,
    )

    single_img = crop_and_frame_id_photo(
        working_img,
        spec=spec,
        dpi=args.dpi,
        head_top_ratio=head_top,
        chin_bottom_ratio=chin_bottom,
        center_x_ratio=center_x,
        pad_rgb=pad_rgb,
    )

    single_filename = f"{args.prefix}_{spec.preset_id}_{int(spec.height_mm)}x{int(spec.width_mm)}mm.jpg"
    single_path = output_dir / single_filename
    single_img.save(single_path, quality=96, dpi=(args.dpi, args.dpi))

    preview_filename = f"{args.prefix}_{spec.preset_id}_verification_preview.png"
    preview_path = output_dir / preview_filename
    create_verification_preview(single_img, spec=spec, dpi=args.dpi, output_path=preview_path)

    sheet_path_str = None
    placed_count = 0
    if args.sheet_size != "none":
        sheet_filename = f"{args.prefix}_{spec.preset_id}_sheet_{args.sheet_size}.jpg"
        sheet_path = output_dir / sheet_filename
        placed_count = generate_print_sheet(
            single_img,
            spec=spec,
            sheet_type=args.sheet_size,
            dpi=args.dpi,
            output_path=sheet_path,
            count=args.count,
        )
        sheet_path_str = str(sheet_path.resolve())

    summary = {
        "status": "success",
        "preset": spec.preset_id,
        "label_ja": spec.label_ja,
        "size_mm": {"width_mm": spec.width_mm, "height_mm": spec.height_mm},
        "size_px": {"width_px": single_img.width, "height_px": single_img.height},
        "dpi": args.dpi,
        "landmarks_detected": {
            "head_top_ratio": round(head_top, 4),
            "chin_bottom_ratio": round(chin_bottom, 4),
            "center_x_ratio": round(center_x, 4),
            "method": method,
        },
        "outputs": {
            "single_photo": str(single_path.resolve()),
            "verification_preview": str(preview_path.resolve()),
            "print_sheet": sheet_path_str,
            "sheet_photo_count": placed_count,
        },
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())


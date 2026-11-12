#!/usr/bin/env python3
"""
Pattern C Helper: Head Tilt Leveling & 2-Stage Pixel-Lock Inner-Face Compositor for ID Photo Studio.

Modes:
1. Coordinate Grid Helper (`--draw-grid`):
   Draws a 50px numbered X/Y grid on the input photo so any multimodal LLM/agent can read
   exact pixel coordinates (e.g., left eye and right eye centers).

2. Head Tilt Leveling & Canonical 3:4 Pre-Crop (`--level-and-crop`):
   Given `--left-eye x1,y1` and `--right-eye x2,y2` (in original image pixels), calculates the
   exact head tilt angle `theta = degrees(atan2(y2 - y1, x2 - x1))` and inter-pupillary distance
   `d_eye = hypot(x2 - x1, y2 - y1)`. Rotates the image counter-clockwise by `theta` so the eyes
   and mouth become 100% horizontal, and crops a canonical 896x1200 (3:4) bust portrait where
   the eyes are normalized to y ~ 427 and x_center = 448.

3. Stage 1 Head Placement (`--orig-box`):
   Extracts the original head/hair/face ROI and composites it onto an AI-generated studio body
   & background canvas so an AI image editor can harmonize the neck/collar transition.

4. Stage 2 Inner-Face Frequency-Matched Blending (`--blend-inner-from`):
   Automatically aligns the leveled original portrait to the AI studio portrait via 2D high-pass
   normalized cross-correlation, pre-masks non-face regions so external hair/objects never bleed
   into the Gaussian low-pass filter, and blends ONLY the interior facial features (eyebrows,
   eyes, nose, smiling mouth/teeth, cheek mole) strictly inside the face skin.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage


def parse_box(box_str: str) -> tuple[int, int, int, int]:
    parts = [int(x.strip()) for x in box_str.split(",")]
    if len(parts) != 4:
        raise ValueError("Box must be 'x0,y0,x1,y1' in pixels.")
    return parts[0], parts[1], parts[2], parts[3]


def parse_point(pt_str: str) -> tuple[float, float]:
    parts = [float(x.strip()) for x in pt_str.split(",")]
    if len(parts) != 2:
        raise ValueError("Point must be 'x,y' in pixels.")
    return parts[0], parts[1]


def draw_coordinate_grid(img: Image.Image, step: int = 50) -> Image.Image:
    out = img.copy()
    draw = ImageDraw.Draw(out)
    w, h = out.size
    for x in range(0, w, step):
        draw.line([(x, 0), (x, h)], fill=(255, 0, 0), width=1)
        draw.text((x + 2, 4), str(x), fill=(255, 0, 0))
    for y in range(0, h, step):
        draw.line([(0, y), (w, y)], fill=(0, 120, 255), width=1)
        draw.text((4, y + 2), str(y), fill=(0, 120, 255))
    return out


def level_and_crop_portrait(
    src: Image.Image,
    left_eye: tuple[float, float],
    right_eye: tuple[float, float],
    crop_scale: float = 6.0,
    pad_rgb: tuple[int, int, int] = (230, 232, 234),
) -> tuple[Image.Image, dict]:
    """
    Rotate `src` so the line connecting `left_eye` (viewer's left) and `right_eye` (viewer's right)
    becomes horizontal, and crop a canonical 896x1200 (3:4) portrait normalized by inter-pupillary distance.
    """
    lx, ly = left_eye
    rx, ry = right_eye
    dx = rx - lx
    dy = ry - ly
    angle_deg = math.degrees(math.atan2(dy, dx))
    d_eye = math.hypot(dx, dy)
    if d_eye < 8.0:
        raise ValueError(f"Inter-pupillary distance too small ({d_eye:.1f}px). Check --left-eye and --right-eye.")

    pad = int(max(src.width, src.height) * 0.5)
    padded = Image.new("RGB", (src.width + 2 * pad, src.height + 2 * pad), pad_rgb)
    padded.paste(src, (pad, pad))

    cx = (lx + rx) / 2.0 + pad
    cy = (ly + ry) / 2.0 + pad

    # PIL.Image.rotate rotates counter-clockwise by angle_deg, leveling a clockwise head tilt (+dy)
    rotated = padded.rotate(angle_deg, resample=Image.Resampling.BICUBIC, center=(cx, cy))

    crop_w = int(round(crop_scale * d_eye))
    crop_h = int(round(crop_w * 4.0 / 3.0))
    x0 = int(round(cx - crop_w / 2.0))
    y0 = int(round(cy - 0.356 * crop_h))  # Places eye line at ~427px in 1200px height

    cropped = rotated.crop((x0, y0, x0 + crop_w, y0 + crop_h)).resize(
        (896, 1200), Image.Resampling.LANCZOS
    )
    info = {
        "status": "success",
        "mode": "level_and_crop",
        "left_eye": [lx, ly],
        "right_eye": [rx, ry],
        "inter_pupillary_px": round(d_eye, 2),
        "tilt_corrected_deg": round(angle_deg, 2),
        "canonical_size": [896, 1200],
        "recommended_inner_oval": "440,485,100,122",
    }
    return cropped, info


def auto_align_face(orig: Image.Image, ai: Image.Image, cx: float, cy: float, rx: float, ry: float) -> Image.Image:
    """
    Find optimal rigid (scale, dx, dy) within a tight range (scale 0.98..1.02, shift -8..+8px)
    via high-pass normalized cross-correlation on the lower face (eyes, nose, and mouth) so
    that `--level-and-crop` portraits lock cleanly without distorting individual eye geometry.
    """
    W, H = ai.size
    orig_r = orig.resize((W, H), Image.Resampling.LANCZOS)
    o_hp = np.asarray(orig_r.convert("L"), dtype=np.float32) - np.asarray(
        orig_r.convert("L").filter(ImageFilter.GaussianBlur(radius=6)), dtype=np.float32
    )
    a_hp = np.asarray(ai.convert("L"), dtype=np.float32) - np.asarray(
        ai.convert("L").filter(ImageFilter.GaussianBlur(radius=6)), dtype=np.float32
    )

    x0 = max(40, int(round(cx - rx * 0.82)))
    x1 = min(W - 40, int(round(cx + rx * 0.82)))
    y0 = max(40, int(round(cy - ry * 0.58)))
    y1 = min(H - 40, int(round(cy + ry * 0.85)))
    ph, pw = y1 - y0, x1 - x0

    target_patch = a_hp[y0:y1, x0:x1]
    target_norm = target_patch / (np.linalg.norm(target_patch) + 1e-6)

    best_score = -1e18
    best_params = (1.0, 0, 0)

    for s in np.linspace(0.97, 1.03, 13):
        sw, sh = int(round(W * s)), int(round(H * s))
        o_s = Image.fromarray(np.clip(o_hp + 128, 0, 255).astype(np.uint8)).resize(
            (sw, sh), Image.Resampling.BILINEAR
        )
        o_s_arr = np.asarray(o_s, dtype=np.float32) - 128.0
        cx_off = (sw - W) // 2
        cy_off = (sh - H) // 2
        for dy in range(-16, 17, 1):
            for dx in range(-16, 17, 1):
                py0 = y0 + cy_off - dy
                px0 = x0 + cx_off - dx
                if py0 < 0 or px0 < 0 or py0 + ph > sh or px0 + pw > sw:
                    continue
                cand = o_s_arr[py0 : py0 + ph, px0 : px0 + pw]
                score = float(np.sum(cand * target_norm) / (np.linalg.norm(cand) + 1e-6))
                if score > best_score:
                    best_score = score
                    best_params = (float(s), int(dx), int(dy))

    s, dx, dy = best_params
    sw, sh = int(round(W * s)), int(round(H * s))
    orig_scaled = orig_r.resize((sw, sh), Image.Resampling.LANCZOS)
    cx_off = (sw - W) // 2 - dx
    cy_off = (sh - H) // 2 - dy
    return orig_scaled.crop((cx_off, cy_off, cx_off + W, cy_off + H))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pattern C helper: grid inspection, head tilt leveling, Stage 1 placement, and Stage 2 inner-face blending."
    )
    parser.add_argument("--orig-crop", help="Path to original photo or pre-cropped image")
    parser.add_argument(
        "--ai-body", help="Path to AI-generated studio body/background (or neck-harmonized) image"
    )
    parser.add_argument("--output", required=True, help="Path to save output image")

    # Mode 1: Draw coordinate grid
    parser.add_argument(
        "--draw-grid",
        action="store_true",
        help="Draw a 50px coordinate grid on --orig-crop and save to --output for reading eye/head coordinates.",
    )
    parser.add_argument("--grid-step", type=int, default=50, help="Grid line spacing in pixels (default: 50)")

    # Mode 2: Level head tilt and crop canonical 896x1200 portrait
    parser.add_argument(
        "--level-and-crop",
        action="store_true",
        help="Rotate --orig-crop to level the eyes horizontally and crop a canonical 896x1200 (3:4) portrait.",
    )
    parser.add_argument(
        "--left-eye",
        help="Viewer's left eye center 'x,y' in --orig-crop pixels (used with --level-and-crop)",
    )
    parser.add_argument(
        "--right-eye",
        help="Viewer's right eye center 'x,y' in --orig-crop pixels (used with --level-and-crop)",
    )
    parser.add_argument(
        "--crop-scale",
        type=float,
        default=6.0,
        help="Crop width as a multiple of inter-pupillary distance (default: 6.0)",
    )

    # Mode 3: Stage 1 head placement
    parser.add_argument("--orig-box", help="Stage 1: Pixel bounding box 'x0,y0,x1,y1' around the head in --orig-crop")
    parser.add_argument("--orig-chin-y", type=float, help="Stage 1: Y coordinate (relative to y0) of the bottom of the chin")
    parser.add_argument("--orig-center-x", type=float, help="Stage 1: X coordinate (relative to x0) of the head center")
    parser.add_argument("--ai-collar-y", type=int, help="Stage 1: Y coordinate in --ai-body where the collar top begins")
    parser.add_argument("--ai-chin-y", type=float, help="Stage 1: Target Y coordinate in --ai-body for the chin bottom")
    parser.add_argument("--ai-center-x", type=float, help="Stage 1: Target X coordinate in --ai-body for the head center")
    parser.add_argument("--scale", type=float, default=1.0, help="Stage 1: Scale factor for the original head ROI")
    parser.add_argument("--collar-half-width", type=float, default=68.0, help="Stage 1: Half-width of neck/collar opening")

    # Mode 4: Stage 2 inner-face frequency-matched blending
    parser.add_argument(
        "--blend-inner-from",
        default=None,
        help="Stage 2 mode: Path to Stage-1 / pre-leveled image to blend ONLY the inner face oval onto --ai-body.",
    )
    parser.add_argument(
        "--inner-oval",
        default="436,485,98,120",
        help="Stage 2: Center and radii 'cx,cy,rx,ry' for inner face oval (default: 436,485,98,120)",
    )

    args = parser.parse_args()
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if args.draw_grid:
        if not args.orig_crop:
            print("Error: --orig-crop is required with --draw-grid", file=sys.stderr)
            return 1
        src = Image.open(args.orig_crop).convert("RGB")
        grid_img = draw_coordinate_grid(src, step=args.grid_step)
        grid_img.save(out_path, quality=95)
        print(json.dumps({"status": "success", "mode": "draw_grid", "size": list(src.size), "output": str(out_path.resolve())}))
        return 0

    if args.level_and_crop:
        if not args.orig_crop or not args.left_eye or not args.right_eye:
            print("Error: --orig-crop, --left-eye, and --right-eye are required with --level-and-crop", file=sys.stderr)
            return 1
        src = Image.open(args.orig_crop).convert("RGB")
        leveled_img, info = level_and_crop_portrait(
            src,
            left_eye=parse_point(args.left_eye),
            right_eye=parse_point(args.right_eye),
            crop_scale=args.crop_scale,
        )
        leveled_img.save(out_path, quality=96)
        info["output"] = str(out_path.resolve())
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return 0

    if args.blend_inner_from:
        if not args.ai_body:
            print("Error: --ai-body is required with --blend-inner-from", file=sys.stderr)
            return 1
        comp = Image.open(args.blend_inner_from).convert("RGB")
        ret = Image.open(args.ai_body).convert("RGB")
        cx, cy, rx, ry = [float(v.strip()) for v in args.inner_oval.split(",")]

        comp_aligned = auto_align_face(comp, ret, cx, cy, rx, ry)
        c_arr = np.asarray(comp_aligned, dtype=np.float32)
        r_arr = np.asarray(ret, dtype=np.float32)
        H, W, _ = r_arr.shape

        yy, xx = np.mgrid[0:H, 0:W]
        dist_clean = np.sqrt(((xx - cx) / (rx * 1.10)) ** 2 + ((yy - cy) / (ry * 1.08)) ** 2)
        valid_skin = dist_clean <= 1.05
        valid_w = (
            np.asarray(
                Image.fromarray((valid_skin.astype(np.uint8) * 255)).filter(ImageFilter.GaussianBlur(radius=8.0)),
                dtype=np.float32,
            )[:, :, None]
            / 255.0
        )

        # Pre-mask outside the face oval with r_arr before GaussianBlur so adjacent hair/objects never bleed into c_low
        c_clean = c_arr * valid_w + r_arr * (1.0 - valid_w)
        c_clean_img = Image.fromarray(np.clip(c_clean, 0, 255).astype(np.uint8))

        c_low = np.asarray(c_clean_img.filter(ImageFilter.GaussianBlur(radius=32.0)), dtype=np.float32)
        r_low = np.asarray(ret.filter(ImageFilter.GaussianBlur(radius=32.0)), dtype=np.float32)
        c_harmonized = np.clip(c_clean - c_low + r_low, 0, 255)

        dist = np.sqrt(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2)
        inner_mask = np.clip((1.05 - dist) * 3.0, 0.0, 1.0)
        inner_mask = (
            np.asarray(
                Image.fromarray((inner_mask * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(radius=14.0)),
                dtype=np.float32,
            )[:, :, None]
            / 255.0
        )

        final_arr = c_harmonized * inner_mask + r_arr * (1.0 - inner_mask)
        Image.fromarray(np.clip(final_arr, 0, 255).astype(np.uint8)).save(out_path, quality=96)
        print(f"Saved Stage-2 auto-aligned inner-face composite to: {out_path.resolve()}")
        return 0

    pre = Image.open(args.orig_crop).convert("RGB")
    ai = Image.open(args.ai_body).convert("RGB")

    pre_arr = np.asarray(pre).astype(np.float32)
    ai_arr = np.asarray(ai).astype(np.float32)
    H, W, _ = ai_arr.shape

    canvas = ai_arr.copy()
    yy_ai, xx_ai = np.mgrid[0:H, 0:W]
    collar_y = args.ai_collar_y
    chin_target_y = int(round(args.ai_chin_y))

    collar_half_w = args.collar_half_width + np.maximum(0.0, yy_ai - float(collar_y)) * 3.2
    erase_zone = (yy_ai < collar_y) | (
        (yy_ai < chin_target_y + 4) & (np.abs(xx_ai - args.ai_center_x) > collar_half_w)
    )
    erase_mask = (
        np.asarray(
            Image.fromarray((erase_zone.astype(np.uint8) * 255)).filter(ImageFilter.GaussianBlur(radius=2.0)),
            dtype=np.float32,
        )[:, :, None]
        / 255.0
    )

    margin_w = max(20, W // 8)
    bg_ref = np.zeros_like(ai_arr)
    for r_idx in range(H):
        l_col = np.median(ai_arr[r_idx, 20 : 20 + margin_w], axis=0)
        r_col = np.median(ai_arr[r_idx, W - 20 - margin_w : W - 20], axis=0)
        t = np.linspace(0.0, 1.0, W)[:, None]
        bg_ref[r_idx] = l_col * (1.0 - t) + r_col * t

    canvas = canvas * (1.0 - erase_mask) + bg_ref * erase_mask

    x0, y0, x1, y1 = parse_box(args.orig_box)
    roi = pre_arr[y0:y1, x0:x1]
    rh, rw, _ = roi.shape
    yy, xx = np.mgrid[0:rh, 0:rw]

    r, g, b = roi[:, :, 0], roi[:, :, 1], roi[:, :, 2]
    luma = 0.299 * r + 0.587 * g + 0.114 * b
    chroma_rb = r - b

    jaw_split_y = int(args.orig_chin_y * 0.78)
    chin_y_int = int(round(args.orig_chin_y))

    is_upper_fg = (yy < jaw_split_y) & ((luma < 222) | (chroma_rb > 16))
    is_mouth_interior = (
        (yy >= int(args.orig_chin_y * 0.72))
        & (yy <= int(args.orig_chin_y * 0.93))
        & (np.abs(xx - args.orig_center_x) < rw * 0.22)
    )
    is_lower_skin = (
        (yy >= jaw_split_y)
        & (yy <= chin_y_int + 2)
        & (np.abs(xx - args.orig_center_x) < rw * 0.36)
        & (((chroma_rb > 16) & (luma > 105)) | is_mouth_interior)
    )

    fg_raw = is_upper_fg | is_lower_skin
    labeled_fg, _ = ndimage.label(fg_raw)
    counts = np.bincount(labeled_fg.ravel())
    counts[0] = 0
    head_mask_bin = ndimage.binary_fill_holes(labeled_fg == np.argmax(counts))

    lower_eroded = ndimage.binary_erosion(head_mask_bin, iterations=2)
    head_mask_clean = np.where(yy >= jaw_split_y, lower_eroded, head_mask_bin)

    alpha_base = (
        np.asarray(
            Image.fromarray((head_mask_clean.astype(np.uint8) * 255)).filter(
                ImageFilter.GaussianBlur(radius=2.0)
            ),
            dtype=np.float32,
        )
        / 255.0
    )

    hair_split_y = int(args.orig_chin_y * 0.56)
    hair_matte = np.clip((235.0 - luma) / 45.0, 0.0, 1.0)
    hair_fringe = (yy < hair_split_y) & (alpha_base > 0.02) & (alpha_base < 0.92) & (chroma_rb < 18)
    alpha_final = np.where(hair_fringe, np.minimum(alpha_base, hair_matte), alpha_base)

    scale = args.scale
    new_w = int(round(rw * scale))
    new_h = int(round(rh * scale))

    roi_img = Image.fromarray(np.clip(roi, 0, 255).astype(np.uint8)).resize(
        (new_w, new_h), Image.Resampling.LANCZOS
    )
    alpha_img = Image.fromarray(np.clip(alpha_final * 255, 0, 255).astype(np.uint8)).resize(
        (new_w, new_h), Image.Resampling.BILINEAR
    )

    roi_scaled = np.asarray(roi_img, dtype=np.float32)
    alpha_scaled = np.asarray(alpha_img, dtype=np.float32)[:, :, None] / 255.0

    yy_s, _ = np.mgrid[0:new_h, 0:new_w]
    chroma_s = roi_scaled[:, :, 0] - roi_scaled[:, :, 2]
    is_hair_edge = (
        (yy_s < int(hair_split_y * scale))
        & (alpha_scaled[:, :, 0] > 0.02)
        & (alpha_scaled[:, :, 0] < 0.90)
        & (chroma_s < 18)
    )
    hair_dark = np.array([35.0, 33.0, 32.0])[None, None, :]
    edge_weight = np.clip((0.90 - alpha_scaled) / 0.90, 0.0, 1.0)
    roi_dehalo = np.where(
        is_hair_edge[:, :, None],
        roi_scaled * (1.0 - edge_weight * 0.80) + hair_dark * (edge_weight * 0.80),
        roi_scaled,
    )

    paste_x = int(round(args.ai_center_x - args.orig_center_x * scale))
    paste_y = int(round(args.ai_chin_y - args.orig_chin_y * scale))

    sub = canvas[paste_y : paste_y + new_h, paste_x : paste_x + new_w]
    blended = roi_dehalo * alpha_scaled + sub * (1.0 - alpha_scaled)
    canvas[paste_y : paste_y + new_h, paste_x : paste_x + new_w] = blended

    Image.fromarray(np.clip(canvas, 0, 255).astype(np.uint8)).save(out_path, quality=96)
    print(f"Saved Pattern C composite to: {out_path.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

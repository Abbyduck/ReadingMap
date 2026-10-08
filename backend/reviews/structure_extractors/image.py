"""Offline screenshot/cover-grid candidate generation, with optional local OCR."""
from __future__ import annotations
import base64
import io

from PIL import Image, ImageOps, UnidentifiedImageError


def _runs(indices: list[bool], minimum: int, *, max_gap: int = 4) -> list[tuple[int, int]]:
    starts = []
    a = None
    last = None
    for i, value in enumerate(indices):
        if value:
            if a is None:
                a = i
            last = i
        elif a is not None and i - last > max_gap:
            if last - a + 1 >= minimum:
                starts.append((a, last + 1))
            a = None
    if a is not None and last - a + 1 >= minimum:
        starts.append((a, last + 1))
    return starts


def _try_ocr(crop: Image.Image) -> tuple[str, bool]:
    try:
        import pytesseract
        text = pytesseract.image_to_string(crop, config="--psm 11", lang="eng")
    except (ImportError, OSError, RuntimeError):
        return "", False
    lines = [" ".join(row.split()) for row in text.splitlines()]
    lines = [x for x in lines if 2 <= len(x) <= 90 and any(c.isalpha() for c in x)]
    return " ".join(lines[:2])[:160], True


def analyze_image(raw: bytes) -> dict:
    if len(raw) > 10 * 1024 * 1024:
        raise ValueError("图片不能超过 10MB")
    try:
        image = Image.open(io.BytesIO(raw))
        image.verify()
        image = Image.open(io.BytesIO(raw))
        image = ImageOps.exif_transpose(image).convert("RGB")
    except (ValueError, UnidentifiedImageError, OSError) as error:
        raise ValueError("无法读取图片，请上传有效的 PNG、JPEG 或 WebP") from error
    if image.width * image.height > 30_000_000:
        raise ValueError("图片像素过大")
    scale = min(1, 800 / max(1, image.width))
    small = image.resize((round(image.width * scale), round(image.height * scale)))
    w, h = small.size
    pixels = small.load()
    # White-gutter segmentation is a deterministic first-pass for cover collages.
    # On natural photographs it may be unable to segment; fall back to manual input.
    row_hits = [sum(1 for x in range(w) if min(pixels[x, y]) < 232)
                for y in range(h)]
    bands = _runs([n >= max(9, int(w * .065)) for n in row_hits], minimum=30, max_gap=7)
    bounds = []
    for y0, y1 in bands:
        if y1 - y0 < 48:
            continue
        col_hits = [sum(1 for y in range(y0, y1) if min(pixels[x, y]) < 232)
                    for x in range(w)]
        columns = _runs([n >= max(5, int((y1-y0)*.12)) for n in col_hits],
                        minimum=25, max_gap=5)
        for x0, x1 in columns:
            width = x1 - x0
            height = y1 - y0
            if 0.38 <= width / height <= 1.5 and height >= 45:
                bounds.append((x0, y0, x1, y1))
    # Do not guess a giant image is a book. Manual corrections are always available.
    bounds = bounds[:120]
    rows = []
    ocr_ready = None
    for index, (x0, y0, x1, y1) in enumerate(bounds):
        coordinates = tuple(round(v / scale) for v in (x0, y0, x1, y1))
        crop = image.crop(coordinates)
        name, available = _try_ocr(crop)
        ocr_ready = available if ocr_ready is None else ocr_ready
        resized = crop.copy()
        resized.thumbnail((180, 260))
        buf = io.BytesIO()
        resized.save(buf, format="JPEG", quality=66)
        rows.append({
            "title": name, "url": None, "image": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode(),
            "position": None, "source_kind": "image", "confidence": 0.4 if name else 0.1,
            "candidate_index": index + 1,
        })
    return {
        "members": rows,
        "group": None,
        "declared_count": None,
        "diagnostics": {
            "strategy": "image_crop_ocr" if ocr_ready else "image_crop_manual",
            "candidate_group_count": len(bands), "candidate_link_count": 0,
            "accepted_member_count": len(rows),
            "confidence": 0.4 if ocr_ready else 0.1,
            "messages": [
                ("已尝试本地 OCR，请逐本核对书名。" if ocr_ready else
                 "当前服务未配置 Tesseract OCR；已尝试分割封面，请手动填写标题。"),
                "图片分组/官方身份未经证实，需人工确认。",
            ],
        },
    }

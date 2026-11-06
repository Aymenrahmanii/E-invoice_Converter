"""Turn a digital PDF into a 'scanned' one: image-only pages, slightly rotated, noisy, blurred.

The result has no text layer, so extraction must go through OCR, as with a real scan.
"""

from __future__ import annotations

import io
import random

import numpy as np
import pypdfium2 as pdfium
from PIL import Image, ImageFilter


def degrade_pdf(pdf: bytes, seed: int, dpi: int = 150) -> bytes:
    rng = random.Random(seed)
    nrng = np.random.default_rng(seed)
    doc = pdfium.PdfDocument(pdf)
    pages: list[Image.Image] = []
    for page in doc:
        img = page.render(scale=dpi / 72, grayscale=rng.random() < 0.6).to_pil().convert("L")
        angle = rng.uniform(1.0, 3.0) * rng.choice([-1, 1])
        img = img.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=255)
        img = img.filter(ImageFilter.GaussianBlur(radius=rng.uniform(0.4, 1.1)))
        arr = np.asarray(img, dtype=np.float32)
        arr = arr * rng.uniform(0.85, 1.0) + rng.uniform(0, 18)  # contrast loss, grey paper
        arr += nrng.normal(0, rng.uniform(6, 16), arr.shape)  # sensor noise
        speckle = nrng.random(arr.shape) < rng.uniform(0.0005, 0.002)
        arr[speckle] = 0  # dust
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
        buf = io.BytesIO()  # JPEG round trip for compression artefacts
        img.save(buf, "JPEG", quality=rng.randint(45, 75))
        pages.append(Image.open(io.BytesIO(buf.getvalue())))
    doc.close()
    out = io.BytesIO()
    pages[0].save(out, "PDF", save_all=True, append_images=pages[1:], resolution=dpi)
    return out.getvalue()

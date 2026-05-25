"""Bbox-rasterized PNG rendering of PDF regions."""

from dataclasses import dataclass
from typing import Tuple

import pymupdf


class RegionRenderError(ValueError):
    """Raised when render input is invalid (bad bbox, page index, etc.)."""


class MalformedPdfError(ValueError):
    """Raised when the input bytes do not parse as a PDF."""


@dataclass(frozen=True)
class RenderMetadata:
    width_px: int
    height_px: int
    dpi_used: int
    page_index: int
    clipped_to_page: bool
    downscaled: bool


# Reasonable upper bounds to keep the service from rendering pathological
# inputs (e.g. dpi=10000 with no max_dim_px caller default).
MAX_DPI = 600
MIN_DPI = 36
MAX_MAX_DIM_PX = 8192


SUPPORTED_FORMATS = ("png", "jpg")
# PyMuPDF accepts "jpeg" as the encode name; "jpg" is the public alias.
_FORMAT_TO_PIXMAP_OUTPUT = {"png": "png", "jpg": "jpeg"}


def render_region(
    pdf_data: bytes,
    page_index: int,
    bbox: Tuple[float, float, float, float],
    dpi: int = 144,
    max_dim_px: int = 2048,
    output_format: str = "png",
) -> Tuple[bytes, RenderMetadata]:
    """
    Render a bbox of a single PDF page as image bytes.

    Args:
        pdf_data: Raw PDF bytes.
        page_index: 0-indexed page number.
        bbox: (x0, y0, x1, y1) in PDF point coordinates (1/72 inch).
        dpi: Target render DPI (default 144 = 2x). Clamped to [MIN_DPI, MAX_DPI].
        max_dim_px: If the rendered image's larger dimension exceeds this, the
            image is re-rendered at a proportionally lower DPI. Clamped to
            [1, MAX_MAX_DIM_PX].
        output_format: "png" (default) or "jpg".

    Returns:
        (image_bytes, metadata)

    Raises:
        MalformedPdfError: PDF cannot be parsed.
        RegionRenderError: invalid bbox, page index, dpi, max_dim_px, or format.
        RuntimeError: PyMuPDF raster operation failed.
    """
    x0, y0, x1, y1 = bbox

    if not (x0 < x1):
        raise RegionRenderError(f"Invalid bbox: x0 ({x0}) must be < x1 ({x1})")
    if not (y0 < y1):
        raise RegionRenderError(f"Invalid bbox: y0 ({y0}) must be < y1 ({y1})")
    if x0 < 0 or y0 < 0:
        raise RegionRenderError(
            f"Invalid bbox: coordinates must be non-negative (got x0={x0}, y0={y0})"
        )
    if dpi < MIN_DPI or dpi > MAX_DPI:
        raise RegionRenderError(
            f"Invalid dpi: must be in [{MIN_DPI}, {MAX_DPI}] (got {dpi})"
        )
    if max_dim_px < 1 or max_dim_px > MAX_MAX_DIM_PX:
        raise RegionRenderError(
            f"Invalid max_dim_px: must be in [1, {MAX_MAX_DIM_PX}] (got {max_dim_px})"
        )
    if page_index < 0:
        raise RegionRenderError(f"Invalid page_index: must be >= 0 (got {page_index})")
    if output_format not in _FORMAT_TO_PIXMAP_OUTPUT:
        raise RegionRenderError(
            f"Invalid output_format: must be one of {SUPPORTED_FORMATS} (got {output_format!r})"
        )

    try:
        doc = pymupdf.open(stream=pdf_data, filetype="pdf")
    except Exception as e:
        raise MalformedPdfError(f"Failed to parse PDF: {e}") from e

    try:
        n_pages = len(doc)
        if page_index >= n_pages:
            raise RegionRenderError(
                f"page_index {page_index} out of range (document has {n_pages} pages)"
            )

        page = doc[page_index]
        page_rect = page.rect

        requested = pymupdf.Rect(x0, y0, x1, y1)
        clip = requested & page_rect
        clipped_to_page = clip != requested
        if clip.is_empty or not clip.is_valid:
            raise RegionRenderError(
                f"Bbox {bbox} does not intersect page bounds "
                f"({page_rect.x0}, {page_rect.y0}, {page_rect.x1}, {page_rect.y1})"
            )

        # Compute scale factor from DPI; PyMuPDF Matrix scale = dpi/72.
        scale = dpi / 72.0
        clip_w_pts = clip.x1 - clip.x0
        clip_h_pts = clip.y1 - clip.y0
        natural_w = clip_w_pts * scale
        natural_h = clip_h_pts * scale

        downscaled = False
        largest = max(natural_w, natural_h)
        if largest > max_dim_px:
            scale *= max_dim_px / largest
            downscaled = True

        matrix = pymupdf.Matrix(scale, scale)
        try:
            pix = page.get_pixmap(clip=clip, matrix=matrix)
        except Exception as e:
            raise RuntimeError(f"PyMuPDF render failed: {e}") from e

        dpi_used = int(round(scale * 72.0))

        pixmap_output = _FORMAT_TO_PIXMAP_OUTPUT[output_format]
        try:
            image_bytes = pix.tobytes(pixmap_output)
        except Exception as e:
            raise RuntimeError(
                f"PyMuPDF {output_format} encode failed: {e}"
            ) from e

        metadata = RenderMetadata(
            width_px=pix.width,
            height_px=pix.height,
            dpi_used=dpi_used,
            page_index=page_index,
            clipped_to_page=clipped_to_page,
            downscaled=downscaled,
        )
        return image_bytes, metadata
    finally:
        doc.close()

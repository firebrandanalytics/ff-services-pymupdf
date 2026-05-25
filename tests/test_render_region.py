"""Tests for the render-region functionality and HTTP endpoint."""

import io
import struct

import pytest
import pymupdf

from fastapi.testclient import TestClient

from src.http_server import create_app
from src.renderers.region import (
    MalformedPdfError,
    RegionRenderError,
    render_region,
)


def make_test_pdf(num_pages: int = 1, width: float = 612, height: float = 792) -> bytes:
    """Build a small multi-page PDF with visible content per page."""
    doc = pymupdf.open()
    for i in range(num_pages):
        page = doc.new_page(width=width, height=height)
        page.insert_text(
            pymupdf.Point(72, 72),
            f"Page {i+1} heading",
            fontsize=24,
            fontname="helv",
        )
        page.insert_text(
            pymupdf.Point(72, 120),
            "Body text body text body text",
            fontsize=12,
            fontname="helv",
        )
        # Draw a filled rectangle so the rendered pixmap has non-trivial content.
        page.draw_rect(
            pymupdf.Rect(72, 200, 300, 400),
            color=(0, 0, 0),
            fill=(0.2, 0.4, 0.8),
        )
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def png_dimensions(png_bytes: bytes) -> tuple[int, int]:
    """Parse width/height from a PNG IHDR chunk."""
    assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    # IHDR is at bytes 8..; length(4) + 'IHDR'(4) + width(4) + height(4) + ...
    width, height = struct.unpack(">II", png_bytes[16:24])
    return width, height


# -----------------------------
# Unit tests of render_region()
# -----------------------------


class TestRenderRegionUnit:
    def test_happy_path_returns_png(self):
        pdf = make_test_pdf()
        png, meta = render_region(pdf, 0, (50.0, 50.0, 400.0, 450.0), dpi=144, max_dim_px=2048)
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        w, h = png_dimensions(png)
        assert w > 0 and h > 0
        assert meta.dpi_used == 144
        assert meta.page_index == 0
        assert meta.clipped_to_page is False
        assert meta.downscaled is False
        assert meta.width_px == w
        assert meta.height_px == h

    def test_jpg_output(self):
        pdf = make_test_pdf()
        img, meta = render_region(
            pdf, 0, (50.0, 50.0, 400.0, 450.0), dpi=144, output_format="jpg"
        )
        # JPEG SOI marker.
        assert img[:2] == b"\xff\xd8"
        assert meta.width_px > 0 and meta.height_px > 0

    def test_invalid_output_format_rejected(self):
        pdf = make_test_pdf()
        with pytest.raises(RegionRenderError, match="Invalid output_format"):
            render_region(pdf, 0, (50.0, 50.0, 100.0, 100.0), output_format="webp")

    def test_bbox_exceeds_page_is_clipped(self):
        """A bbox that extends past the page bounds should be clipped, not rejected."""
        pdf = make_test_pdf(width=612, height=792)
        # Bbox extends beyond the 612x792 page
        png, meta = render_region(pdf, 0, (0.0, 0.0, 10000.0, 10000.0), dpi=144)
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        assert meta.clipped_to_page is True

    def test_bbox_entirely_outside_page_rejected(self):
        pdf = make_test_pdf(width=612, height=792)
        with pytest.raises(RegionRenderError, match="does not intersect"):
            render_region(pdf, 0, (5000.0, 5000.0, 6000.0, 6000.0))

    def test_invalid_bbox_x0_gte_x1(self):
        pdf = make_test_pdf()
        with pytest.raises(RegionRenderError, match="x0 .* must be < x1"):
            render_region(pdf, 0, (100.0, 50.0, 50.0, 200.0))

    def test_invalid_bbox_y0_gte_y1(self):
        pdf = make_test_pdf()
        with pytest.raises(RegionRenderError, match="y0 .* must be < y1"):
            render_region(pdf, 0, (50.0, 200.0, 200.0, 100.0))

    def test_negative_bbox_rejected(self):
        pdf = make_test_pdf()
        with pytest.raises(RegionRenderError, match="non-negative"):
            render_region(pdf, 0, (-10.0, 50.0, 100.0, 200.0))

    def test_page_out_of_range(self):
        pdf = make_test_pdf(num_pages=2)
        with pytest.raises(RegionRenderError, match="out of range"):
            render_region(pdf, 5, (50.0, 50.0, 200.0, 200.0))

    def test_negative_page_index(self):
        pdf = make_test_pdf()
        with pytest.raises(RegionRenderError, match="page_index"):
            render_region(pdf, -1, (50.0, 50.0, 200.0, 200.0))

    def test_malformed_pdf(self):
        with pytest.raises(MalformedPdfError):
            render_region(b"this is not a pdf", 0, (0.0, 0.0, 100.0, 100.0))

    def test_invalid_dpi_too_low(self):
        pdf = make_test_pdf()
        with pytest.raises(RegionRenderError, match="dpi"):
            render_region(pdf, 0, (50.0, 50.0, 200.0, 200.0), dpi=1)

    def test_invalid_dpi_too_high(self):
        pdf = make_test_pdf()
        with pytest.raises(RegionRenderError, match="dpi"):
            render_region(pdf, 0, (50.0, 50.0, 200.0, 200.0), dpi=10000)

    def test_invalid_max_dim_px(self):
        pdf = make_test_pdf()
        with pytest.raises(RegionRenderError, match="max_dim_px"):
            render_region(pdf, 0, (50.0, 50.0, 200.0, 200.0), max_dim_px=0)

    def test_max_dim_downscale_triggers(self):
        """Rendering a large region at high DPI with small max_dim_px should downscale."""
        pdf = make_test_pdf(width=612, height=792)
        # 612pt @ 144dpi -> 1224 px wide. Cap at 300 -> must downscale.
        png, meta = render_region(
            pdf, 0, (0.0, 0.0, 612.0, 792.0), dpi=144, max_dim_px=300
        )
        w, h = png_dimensions(png)
        assert meta.downscaled is True
        assert meta.dpi_used < 144
        # Image dimension should now be <= max_dim_px (within rounding)
        assert max(w, h) <= 300 + 1
        assert meta.width_px == w and meta.height_px == h

    def test_max_dim_no_downscale_when_under_limit(self):
        pdf = make_test_pdf()
        png, meta = render_region(
            pdf, 0, (50.0, 50.0, 100.0, 100.0), dpi=72, max_dim_px=2048
        )
        assert meta.downscaled is False
        assert meta.dpi_used == 72

    def test_metadata_dimensions_match_png(self):
        pdf = make_test_pdf()
        png, meta = render_region(pdf, 0, (10.0, 20.0, 410.0, 420.0), dpi=144)
        w, h = png_dimensions(png)
        assert (meta.width_px, meta.height_px) == (w, h)


# -----------------------------
# HTTP endpoint integration
# -----------------------------


@pytest.fixture
def client():
    return TestClient(create_app())


def _multipart(pdf: bytes, **fields):
    """Build TestClient args for the multipart render-region contract.

    Mirrors what `DocProcLayoutClient.renderRegion` sends from rag-agent-bundle:
    file + page (1-based) + x_min/y_min/x_max/y_max + dpi + format + max_dim_px.
    """
    defaults = {
        "page": "1",
        "x_min": "50.0",
        "y_min": "50.0",
        "x_max": "400.0",
        "y_max": "450.0",
        "dpi": "144",
        "format": "png",
        "max_dim_px": "2048",
    }
    # Cast every override to str — multipart fields are always sent as strings.
    for k, v in fields.items():
        defaults[k] = str(v)
    return {
        "files": {"file": ("document.pdf", io.BytesIO(pdf), "application/pdf")},
        "data": defaults,
    }


class TestRenderRegionEndpoint:
    def test_happy_path(self, client):
        pdf = make_test_pdf()
        r = client.post("/api/render-region", **_multipart(pdf))
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "image/png"
        assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
        # Bundle-facing headers (DocProcLayoutClient reads these).
        assert int(r.headers["x-width-px"]) > 0
        assert int(r.headers["x-height-px"]) > 0
        assert int(r.headers["x-render-time-ms"]) >= 0
        # Page echoes as 1-based (matches request convention).
        assert r.headers["x-page-number"] == "1"
        assert r.headers["x-clipped-to-page"] == "false"
        assert r.headers["x-downscaled"] == "false"

    def test_jpg_format(self, client):
        pdf = make_test_pdf()
        r = client.post("/api/render-region", **_multipart(pdf, format="jpg"))
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "image/jpeg"
        # JPEG SOI marker.
        assert r.content[:2] == b"\xff\xd8"

    def test_invalid_format_returns_400(self, client):
        pdf = make_test_pdf()
        r = client.post("/api/render-region", **_multipart(pdf, format="webp"))
        assert r.status_code == 400
        assert "format" in r.json()["detail"]["error"].lower()

    def test_bbox_exceeds_page_clipped(self, client):
        pdf = make_test_pdf()
        r = client.post(
            "/api/render-region",
            **_multipart(pdf, x_min=0, y_min=0, x_max=10000, y_max=10000),
        )
        assert r.status_code == 200, r.text
        assert r.headers["x-clipped-to-page"] == "true"
        assert r.content[:8] == b"\x89PNG\r\n\x1a\n"

    def test_bbox_outside_page_returns_400(self, client):
        pdf = make_test_pdf()
        r = client.post(
            "/api/render-region",
            **_multipart(pdf, x_min=5000, y_min=5000, x_max=6000, y_max=6000),
        )
        assert r.status_code == 400
        assert "does not intersect" in r.json()["detail"]["error"]

    def test_invalid_bbox_returns_400(self, client):
        pdf = make_test_pdf()
        # x_min >= x_max
        r = client.post(
            "/api/render-region",
            **_multipart(pdf, x_min=400, y_min=50, x_max=100, y_max=200),
        )
        assert r.status_code == 400
        assert "x0" in r.json()["detail"]["error"]

    def test_page_out_of_range_returns_400(self, client):
        pdf = make_test_pdf(num_pages=2)
        # 1-based page=10 → page_index=9, out of range for a 2-page doc.
        r = client.post("/api/render-region", **_multipart(pdf, page=10))
        assert r.status_code == 400
        assert "out of range" in r.json()["detail"]["error"]

    def test_page_zero_returns_400(self, client):
        """page=0 is invalid (1-based); endpoint rejects before calling renderer."""
        pdf = make_test_pdf()
        r = client.post("/api/render-region", **_multipart(pdf, page=0))
        assert r.status_code == 400
        assert "1-based" in r.json()["detail"]["error"]

    def test_negative_page_returns_400(self, client):
        pdf = make_test_pdf()
        r = client.post("/api/render-region", **_multipart(pdf, page=-1))
        assert r.status_code == 400
        assert "1-based" in r.json()["detail"]["error"]

    def test_dpi_out_of_range_returns_400(self, client):
        """dpi outside [36, 600] reaches the renderer and is rejected with a 400."""
        pdf = make_test_pdf()
        r = client.post("/api/render-region", **_multipart(pdf, dpi=10000))
        assert r.status_code == 400
        assert "dpi" in r.json()["detail"]["error"].lower()

    def test_max_dim_out_of_range_returns_400(self, client):
        pdf = make_test_pdf()
        r = client.post("/api/render-region", **_multipart(pdf, max_dim_px=0))
        assert r.status_code == 400
        assert "max_dim_px" in r.json()["detail"]["error"]

    def test_malformed_pdf_returns_422(self, client):
        bad = b"this is definitely not a pdf"
        r = client.post(
            "/api/render-region",
            **_multipart(bad, x_min=0, y_min=0, x_max=100, y_max=100),
        )
        assert r.status_code == 422
        assert "PDF" in r.json()["detail"]["error"]

    def test_max_dim_downscale_via_endpoint(self, client):
        pdf = make_test_pdf()
        r = client.post(
            "/api/render-region",
            **_multipart(
                pdf,
                x_min=0,
                y_min=0,
                x_max=612,
                y_max=792,
                dpi=144,
                max_dim_px=300,
            ),
        )
        assert r.status_code == 200, r.text
        assert r.headers["x-downscaled"] == "true"
        assert int(r.headers["x-width-px"]) <= 301
        assert int(r.headers["x-height-px"]) <= 301

    def test_defaults_applied(self, client):
        """dpi, format, and max_dim_px have defaults; only the bbox+file+page are required."""
        pdf = make_test_pdf()
        files = {"file": ("document.pdf", io.BytesIO(pdf), "application/pdf")}
        data = {
            "page": "1",
            "x_min": "50",
            "y_min": "50",
            "x_max": "400",
            "y_max": "450",
        }
        r = client.post("/api/render-region", files=files, data=data)
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "image/png"
        assert r.headers["x-dpi-used"] == "144"
        assert r.headers["x-downscaled"] == "false"

    def test_missing_required_field_422(self, client):
        # Missing y_max
        pdf = make_test_pdf()
        files = {"file": ("document.pdf", io.BytesIO(pdf), "application/pdf")}
        data = {
            "page": "1",
            "x_min": "50",
            "y_min": "50",
            "x_max": "400",
        }
        r = client.post("/api/render-region", files=files, data=data)
        assert r.status_code == 422

    def test_missing_file_422(self, client):
        # Multipart with no file part — FastAPI rejects with 422.
        data = {
            "page": "1",
            "x_min": "50",
            "y_min": "50",
            "x_max": "400",
            "y_max": "450",
        }
        r = client.post("/api/render-region", data=data)
        assert r.status_code == 422


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

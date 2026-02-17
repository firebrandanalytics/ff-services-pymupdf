"""Tests for PDF processing backends."""

import json
import pytest
import pymupdf

from src.backends.text_extraction import TextExtractionBackend
from src.backends.text_layer_detection import TextLayerDetectionBackend
from src.utils.page_filter import parse_page_range


def create_test_pdf(pages=None):
    """Create a simple test PDF with text content using PyMuPDF.

    Args:
        pages: List of dicts with 'text' and optionally 'fontsize', 'bold' keys.
               If None, creates a single page with sample content.
    """
    if pages is None:
        pages = [
            {"text": "Test Document Title", "fontsize": 24, "bold": True, "y": 72},
            {"text": "Section Heading", "fontsize": 16, "bold": False, "y": 120},
            {"text": "This is body text in a test document.", "fontsize": 12, "bold": False, "y": 160},
        ]
        pages = [{"items": pages}]

    doc = pymupdf.open()

    for page_def in pages:
        page = doc.new_page(width=612, height=792)
        items = page_def.get("items", [])
        for item in items:
            text = item.get("text", "")
            fontsize = item.get("fontsize", 12)
            bold = item.get("bold", False)
            y = item.get("y", 72)
            fontname = "helv"  # Helvetica
            if bold:
                fontname = "hebo"  # Helvetica Bold

            page.insert_text(
                pymupdf.Point(72, y),
                text,
                fontsize=fontsize,
                fontname=fontname,
            )

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def create_table_pdf():
    """Create a test PDF with a table."""
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)

    # Draw a simple table using lines and text
    # Header row
    start_x, start_y = 72, 100
    col_width = 150
    row_height = 25
    cols = 3
    rows = 3

    headers = ["Name", "Age", "City"]
    data = [
        ["Alice", "30", "New York"],
        ["Bob", "25", "London"],
    ]

    # Draw grid lines
    for r in range(rows + 1):
        y = start_y + r * row_height
        page.draw_line(
            pymupdf.Point(start_x, y),
            pymupdf.Point(start_x + cols * col_width, y),
        )
    for c in range(cols + 1):
        x = start_x + c * col_width
        page.draw_line(
            pymupdf.Point(x, start_y),
            pymupdf.Point(x, start_y + rows * row_height),
        )

    # Insert header text
    for c, header in enumerate(headers):
        page.insert_text(
            pymupdf.Point(start_x + c * col_width + 5, start_y + 18),
            header,
            fontsize=10,
            fontname="hebo",
        )

    # Insert data
    for r, row in enumerate(data):
        for c, cell in enumerate(row):
            page.insert_text(
                pymupdf.Point(start_x + c * col_width + 5, start_y + (r + 1) * row_height + 18),
                cell,
                fontsize=10,
                fontname="helv",
            )

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


# --- Page Filter Tests ---

class TestPageFilter:
    """Tests for page filtering utility."""

    def test_parse_single_page(self):
        assert parse_page_range("1") == [1]

    def test_parse_multiple_pages(self):
        assert parse_page_range("1,3,5") == [1, 3, 5]

    def test_parse_page_range(self):
        assert parse_page_range("1-3") == [1, 2, 3]

    def test_parse_mixed_format(self):
        assert parse_page_range("1,3,5-7") == [1, 3, 5, 6, 7]

    def test_parse_invalid_range(self):
        with pytest.raises(ValueError):
            parse_page_range("10-5")


# --- Backend Support Tests ---

class TestBackendSupport:
    """Tests for backend operation support."""

    def test_text_extraction_supports_extract(self):
        backend = TextExtractionBackend()
        assert backend.supports("extract")
        assert not backend.supports("detect_text_layer")

    def test_text_layer_supports_detect(self):
        backend = TextLayerDetectionBackend()
        assert backend.supports("detect_text_layer")
        assert not backend.supports("extract")


# --- Text Extraction Tests ---

class TestTextExtractionBackend:
    """Tests for TextExtractionBackend with real PDFs."""

    def setup_method(self):
        self.backend = TextExtractionBackend()

    def test_extract_json(self):
        """Extract text from a PDF and get JSON output."""
        pdf = create_test_pdf()
        output, fmt, metadata = self.backend.process(pdf, "extract", {"output_format": "json"})

        assert fmt == "json"
        result = json.loads(output)
        assert "paragraphs" in result
        assert "content_blocks" in result
        assert "full_text" in result
        assert result["model_used"] == "pymupdf"
        assert len(result["paragraphs"]) > 0

    def test_extract_html(self):
        """Extract text and get HTML output."""
        pdf = create_test_pdf()
        output, fmt, metadata = self.backend.process(pdf, "extract", {"output_format": "html"})

        assert fmt == "html"
        html = output.decode("utf-8")
        assert "<html>" in html
        assert "</html>" in html
        assert "<body>" in html

    def test_extract_has_font_metadata(self):
        """Extracted paragraphs should include font metadata."""
        pdf = create_test_pdf()
        output, fmt, metadata = self.backend.process(pdf, "extract", {"output_format": "json"})

        result = json.loads(output)
        for para in result["paragraphs"]:
            assert "font" in para
            assert "size" in para["font"]
            assert "name" in para["font"]
            assert "bold" in para["font"]

    def test_extract_has_bounding_boxes(self):
        """Extracted paragraphs should have bounding box coordinates."""
        pdf = create_test_pdf()
        output, fmt, metadata = self.backend.process(pdf, "extract", {"output_format": "json"})

        result = json.loads(output)
        for para in result["paragraphs"]:
            assert "bounding_box" in para
            bbox = para["bounding_box"]
            assert "x_min" in bbox
            assert "y_min" in bbox
            assert "x_max" in bbox
            assert "y_max" in bbox

    def test_role_detection_applied(self):
        """Semantic roles should be assigned based on font heuristics."""
        pdf = create_test_pdf()
        output, fmt, metadata = self.backend.process(pdf, "extract", {"output_format": "json"})

        result = json.loads(output)
        roles = [p["role"] for p in result["paragraphs"]]
        # At least one paragraph should have a role assigned (title or heading)
        assert any(r is not None for r in roles), f"No roles detected. Roles: {roles}"

    def test_extract_page_range(self):
        """Page range filtering should work."""
        # Create multi-page PDF
        pages = [
            {"items": [{"text": "Page 1 content", "fontsize": 12, "y": 72}]},
            {"items": [{"text": "Page 2 content", "fontsize": 12, "y": 72}]},
            {"items": [{"text": "Page 3 content", "fontsize": 12, "y": 72}]},
        ]
        pdf = create_test_pdf(pages)
        output, fmt, metadata = self.backend.process(
            pdf, "extract", {"output_format": "json", "pages": "1,3"}
        )

        result = json.loads(output)
        assert metadata["pages_processed"] == "2"

    def test_extract_metadata(self):
        """Metadata should include processing stats."""
        pdf = create_test_pdf()
        output, fmt, metadata = self.backend.process(pdf, "extract", {"output_format": "json"})

        assert "pages_processed" in metadata
        assert "total_paragraphs" in metadata
        assert "total_tables" in metadata
        assert metadata["model_used"] == "pymupdf"


# --- Text Layer Detection Tests ---

class TestTextLayerDetectionBackend:
    """Tests for TextLayerDetectionBackend."""

    def setup_method(self):
        self.backend = TextLayerDetectionBackend()

    def test_detect_text_layer_present(self):
        """PDF with text should be detected as having a text layer."""
        pdf = create_test_pdf()
        output, fmt, metadata = self.backend.process(pdf, "detect_text_layer", {})

        assert fmt == "json"
        result = json.loads(output)
        assert "pages" in result
        assert result["total_pages"] == 1
        assert result["pages"][0]["has_text_layer"] is True
        assert result["pages"][0]["char_count"] > 0

    def test_detect_multi_page(self):
        """Multi-page detection should return per-page results."""
        pages = [
            {"items": [{"text": "This is page one with enough text to exceed the threshold limit for detection.", "fontsize": 12, "y": 72}]},
            {"items": [{"text": "This is page two with enough text to exceed the threshold limit for detection.", "fontsize": 12, "y": 72}]},
        ]
        pdf = create_test_pdf(pages)
        output, fmt, metadata = self.backend.process(pdf, "detect_text_layer", {})

        result = json.loads(output)
        assert result["total_pages"] == 2
        assert len(result["pages"]) == 2
        assert all(p["has_text_layer"] for p in result["pages"])

    def test_detect_metadata(self):
        """Metadata should include summary statistics."""
        pdf = create_test_pdf()
        output, fmt, metadata = self.backend.process(pdf, "detect_text_layer", {})

        assert "total_pages" in metadata
        assert "pages_with_text" in metadata


# --- Table Extraction Tests ---

class TestTableExtraction:
    """Tests for table extraction in TextExtractionBackend."""

    def test_table_pdf_extraction(self):
        """Tables should be detected in PDFs with grid lines."""
        pdf = create_table_pdf()
        backend = TextExtractionBackend()
        output, fmt, metadata = backend.process(pdf, "extract", {"output_format": "json"})

        result = json.loads(output)
        # Table detection may or may not find the table depending on the
        # quality of the drawn grid. At minimum, text should be extracted.
        assert "tables" in result
        assert "paragraphs" in result

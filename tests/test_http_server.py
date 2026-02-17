"""Tests for HTTP server endpoints."""

import base64
import json
import pytest
import pymupdf

from fastapi.testclient import TestClient

from src.http_server import create_app


def create_test_pdf_bytes():
    """Create a simple test PDF."""
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text(pymupdf.Point(72, 72), "Test Title", fontsize=24, fontname="hebo")
    page.insert_text(pymupdf.Point(72, 120), "Section One", fontsize=16, fontname="helv")
    page.insert_text(pymupdf.Point(72, 160), "This is paragraph body text in the document.", fontsize=12, fontname="helv")
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


@pytest.fixture
def client():
    """Create test client."""
    app = create_app()
    return TestClient(app)


class TestHealthEndpoint:
    """Tests for GET /health endpoint."""

    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "ok"
        assert "operations" in data
        assert isinstance(data["operations"], list)
        assert "extract" in data["operations"]
        assert "detect_text_layer" in data["operations"]

    def test_ready_check(self, client):
        response = client.get("/ready")
        assert response.status_code == 200
        assert response.json()["status"] == "ready"


class TestExtractEndpoint:
    """Tests for POST /api/extract endpoint."""

    def test_extract_json(self, client):
        """Extract from PDF should return JSON result."""
        pdf = create_test_pdf_bytes()
        response = client.post(
            "/api/extract",
            files={"file": ("test.pdf", pdf, "application/pdf")},
            data={"output_format": "json"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "result" in data
        assert "paragraphs" in data["result"]
        assert "content_blocks" in data["result"]
        assert data["result"]["model_used"] == "pymupdf"

    def test_extract_html(self, client):
        """Extract from PDF should return HTML when requested."""
        pdf = create_test_pdf_bytes()
        response = client.post(
            "/api/extract",
            files={"file": ("test.pdf", pdf, "application/pdf")},
            data={"output_format": "html"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["format"] == "text/html"
        assert "<html>" in data["result"]
        assert "</html>" in data["result"]

    def test_extract_has_roles(self, client):
        """Extracted paragraphs should have semantic roles."""
        pdf = create_test_pdf_bytes()
        response = client.post(
            "/api/extract",
            files={"file": ("test.pdf", pdf, "application/pdf")},
            data={"output_format": "json"},
        )

        data = response.json()
        roles = [p["role"] for p in data["result"]["paragraphs"]]
        assert any(r is not None for r in roles)

    def test_extract_with_page_range(self, client):
        """Page range should limit extraction."""
        # Create multi-page PDF
        doc = pymupdf.open()
        for i in range(3):
            page = doc.new_page()
            page.insert_text(pymupdf.Point(72, 72), f"Page {i+1}", fontsize=12)
        pdf = doc.tobytes()
        doc.close()

        response = client.post(
            "/api/extract",
            files={"file": ("test.pdf", pdf, "application/pdf")},
            data={"output_format": "json", "pages": "1,3"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["metadata"]["pages_processed"] == "2"

    def test_extract_processing_time(self, client):
        """Response should include processing time."""
        pdf = create_test_pdf_bytes()
        response = client.post(
            "/api/extract",
            files={"file": ("test.pdf", pdf, "application/pdf")},
            data={"output_format": "json"},
        )

        data = response.json()
        assert "processing_time_ms" in data
        assert isinstance(data["processing_time_ms"], int)


class TestDetectTextLayerEndpoint:
    """Tests for POST /api/detect-text-layer endpoint."""

    def test_detect_text_layer(self, client):
        """Should detect text layer in a text PDF."""
        pdf = create_test_pdf_bytes()
        response = client.post(
            "/api/detect-text-layer",
            files={"file": ("test.pdf", pdf, "application/pdf")},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["result"]["total_pages"] == 1
        assert data["result"]["pages"][0]["has_text_layer"] is True


class TestProcessEndpoint:
    """Tests for POST /process (base64 mode)."""

    def test_process_extract(self, client):
        """Process endpoint should work with base64 PDF."""
        pdf = create_test_pdf_bytes()
        encoded = base64.b64encode(pdf).decode("utf-8")

        response = client.post("/process", json={
            "operation": "extract",
            "data": encoded,
            "options": {"output_format": "json"},
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "paragraphs" in data["result"]

    def test_process_invalid_base64(self, client):
        """Invalid base64 should return 400."""
        response = client.post("/process", json={
            "operation": "extract",
            "data": "not-valid-base64!!!",
            "options": {},
        })

        assert response.status_code == 400

    def test_process_unsupported_operation(self, client):
        """Unsupported operation should return 400."""
        pdf = create_test_pdf_bytes()
        encoded = base64.b64encode(pdf).decode("utf-8")

        response = client.post("/process", json={
            "operation": "nonexistent_op",
            "data": encoded,
            "options": {},
        })

        assert response.status_code == 400

    def test_process_detect_text_layer(self, client):
        """Process endpoint should work for detect_text_layer operation."""
        pdf = create_test_pdf_bytes()
        encoded = base64.b64encode(pdf).decode("utf-8")

        response = client.post("/process", json={
            "operation": "detect_text_layer",
            "data": encoded,
            "options": {},
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["result"]["total_pages"] == 1


class TestRequestValidation:
    """Tests for request validation."""

    def test_missing_file_extract(self, client):
        """Missing file should return validation error."""
        response = client.post("/api/extract")
        assert response.status_code == 422

    def test_missing_file_detect(self, client):
        """Missing file should return validation error."""
        response = client.post("/api/detect-text-layer")
        assert response.status_code == 422

    def test_missing_operation_process(self, client):
        """Missing operation in /process should return validation error."""
        response = client.post("/process", json={
            "data": "dGVzdA==",
            "options": {},
        })
        assert response.status_code == 422


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

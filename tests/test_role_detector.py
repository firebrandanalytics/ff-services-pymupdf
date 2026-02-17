"""Tests for semantic role detection from font heuristics."""

import pytest
from src.converters.role_detector import RoleDetector


class TestRoleDetector:
    """Tests for RoleDetector."""

    def setup_method(self):
        self.detector = RoleDetector()

    def _make_para(self, content, size=12.0, bold=False, font="Arial"):
        return {
            "id": f"para-{id(content)}",
            "content": content,
            "role": None,
            "page_number": 1,
            "bounding_box": {"x_min": 0, "y_min": 0, "x_max": 100, "y_max": 20},
            "font": {"name": font, "size": size, "bold": bold},
        }

    def test_title_detection_by_size(self):
        """Large font should be classified as title."""
        paragraphs = [
            self._make_para("Document Title", size=24.0, bold=True),
            self._make_para("Body text that is long enough to be the dominant size. " * 5, size=12.0),
        ]
        self.detector.classify(paragraphs)
        assert paragraphs[0]["role"] == "title"
        assert paragraphs[1]["role"] is None

    def test_heading_detection_by_size(self):
        """Medium font should be classified as sectionHeading."""
        paragraphs = [
            self._make_para("Section Heading", size=16.0),
            self._make_para("Body text that is long enough to be dominant. " * 5, size=12.0),
        ]
        self.detector.classify(paragraphs)
        assert paragraphs[0]["role"] == "sectionHeading"
        assert paragraphs[1]["role"] is None

    def test_heading_detection_bold_larger(self):
        """Bold text slightly larger than body should be heading."""
        paragraphs = [
            self._make_para("Bold Heading", size=13.5, bold=True),
            self._make_para("Normal body text repeated many times. " * 10, size=12.0),
        ]
        self.detector.classify(paragraphs)
        assert paragraphs[0]["role"] == "sectionHeading"

    def test_body_text_stays_none(self):
        """Body-sized text should remain None."""
        paragraphs = [
            self._make_para("First paragraph of body text. " * 5, size=12.0),
            self._make_para("Second paragraph of body text. " * 5, size=12.0),
        ]
        self.detector.classify(paragraphs)
        assert paragraphs[0]["role"] is None
        assert paragraphs[1]["role"] is None

    def test_empty_paragraphs(self):
        """Should handle empty list gracefully."""
        paragraphs = []
        self.detector.classify(paragraphs)
        assert paragraphs == []

    def test_custom_thresholds(self):
        """Custom thresholds should be respected."""
        paragraphs = [
            self._make_para("Would-be Title", size=16.0, bold=True),
            self._make_para("Body text that is dominant. " * 10, size=12.0),
        ]
        # With low thresholds, 16pt should be title
        self.detector.classify(paragraphs, title_threshold=15.0, heading_threshold=13.0)
        assert paragraphs[0]["role"] == "title"

    def test_body_font_size_detection(self):
        """Body font size should be the most frequent size weighted by content length."""
        paragraphs = [
            self._make_para("Title", size=24.0),
            self._make_para("Long body paragraph one that has a lot of content. " * 10, size=11.0),
            self._make_para("Long body paragraph two that has a lot of content. " * 10, size=11.0),
        ]
        body_size = self.detector._detect_body_font_size(paragraphs)
        assert body_size == 11.0

    def test_title_by_relative_size_and_bold(self):
        """Text >= 1.5x body size and bold should be title even below absolute threshold."""
        paragraphs = [
            self._make_para("Big Bold Text", size=17.0, bold=True),
            self._make_para("Normal text repeated a lot of times. " * 10, size=11.0),
        ]
        # 17pt / 11pt = 1.54x and bold → title even though 17 < 18 threshold
        self.detector.classify(paragraphs)
        assert paragraphs[0]["role"] == "title"

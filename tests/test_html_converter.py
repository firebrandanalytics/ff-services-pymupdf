"""Tests for HTML converter."""

import pytest
from src.converters.html_converter import HtmlConverter


class TestHtmlConverter:
    """Tests for HtmlConverter."""

    def setup_method(self):
        self.converter = HtmlConverter()

    def test_basic_paragraph(self):
        """Body paragraphs should render as <p> tags."""
        result = {
            "paragraphs": [
                {"id": "para-0", "content": "Hello world", "role": None},
            ],
            "tables": [],
            "images": [],
            "content_blocks": [
                {"type": "paragraph", "page": 1, "y_position": 0, "content_id": "para-0"},
            ],
        }
        html = self.converter.convert(result)
        assert "<p>Hello world</p>" in html

    def test_title_renders_h1(self):
        """Title role should render as <h1>."""
        result = {
            "paragraphs": [
                {"id": "para-0", "content": "My Title", "role": "title"},
            ],
            "tables": [],
            "images": [],
            "content_blocks": [
                {"type": "paragraph", "page": 1, "y_position": 0, "content_id": "para-0"},
            ],
        }
        html = self.converter.convert(result)
        assert "<h1>My Title</h1>" in html

    def test_heading_renders_h2(self):
        """sectionHeading role should render as <h2>."""
        result = {
            "paragraphs": [
                {"id": "para-0", "content": "Section One", "role": "sectionHeading"},
            ],
            "tables": [],
            "images": [],
            "content_blocks": [
                {"type": "paragraph", "page": 1, "y_position": 0, "content_id": "para-0"},
            ],
        }
        html = self.converter.convert(result)
        assert "<h2>Section One</h2>" in html

    def test_table_rendering(self):
        """Tables should render with proper HTML structure."""
        result = {
            "paragraphs": [],
            "tables": [
                {
                    "id": "table-0",
                    "page_number": 1,
                    "rows": 2,
                    "columns": 2,
                    "cells": [
                        {"row_index": 0, "column_index": 0, "content": "Name", "kind": "columnHeader", "row_span": 1, "column_span": 1},
                        {"row_index": 0, "column_index": 1, "content": "Age", "kind": "columnHeader", "row_span": 1, "column_span": 1},
                        {"row_index": 1, "column_index": 0, "content": "Alice", "kind": "content", "row_span": 1, "column_span": 1},
                        {"row_index": 1, "column_index": 1, "content": "30", "kind": "content", "row_span": 1, "column_span": 1},
                    ],
                }
            ],
            "images": [],
            "content_blocks": [
                {"type": "table", "page": 1, "y_position": 0, "content_id": "table-0"},
            ],
        }
        html = self.converter.convert(result)
        assert '<table border="1" id="table-0">' in html
        assert "<th>Name</th>" in html
        assert "<th>Age</th>" in html
        assert "<td>Alice</td>" in html
        assert "<td>30</td>" in html

    def test_html_escaping(self):
        """Special characters should be escaped."""
        result = {
            "paragraphs": [
                {"id": "para-0", "content": "a < b & c > d", "role": None},
            ],
            "tables": [],
            "images": [],
            "content_blocks": [
                {"type": "paragraph", "page": 1, "y_position": 0, "content_id": "para-0"},
            ],
        }
        html = self.converter.convert(result)
        assert "a &lt; b &amp; c &gt; d" in html

    def test_content_block_ordering(self):
        """Content should be rendered in content_blocks order."""
        result = {
            "paragraphs": [
                {"id": "para-0", "content": "First", "role": None},
                {"id": "para-1", "content": "Second", "role": None},
            ],
            "tables": [],
            "images": [],
            "content_blocks": [
                {"type": "paragraph", "page": 1, "y_position": 0, "content_id": "para-0"},
                {"type": "paragraph", "page": 1, "y_position": 100, "content_id": "para-1"},
            ],
        }
        html = self.converter.convert(result)
        first_pos = html.index("First")
        second_pos = html.index("Second")
        assert first_pos < second_pos

    def test_html_wrapper(self):
        """Output should have proper HTML wrapper."""
        result = {
            "paragraphs": [],
            "tables": [],
            "images": [],
            "content_blocks": [],
        }
        html = self.converter.convert(result)
        assert html.startswith('<html><head><meta charset="utf-8"></head><body>')
        assert html.endswith('</body></html>')

    def test_image_rendering(self):
        """Images should render as base64 img tags."""
        result = {
            "paragraphs": [],
            "tables": [],
            "images": [
                {"id": "img-0", "data": "abc123", "mime_type": "image/png"},
            ],
            "content_blocks": [
                {"type": "image", "page": 1, "y_position": 50, "content_id": "img-0"},
            ],
        }
        html = self.converter.convert(result)
        assert '<img src="data:image/png;base64,abc123" />' in html

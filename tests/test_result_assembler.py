"""Tests for result assembler."""

import pytest
from src.converters.result_assembler import ResultAssembler


class TestResultAssembler:
    """Tests for ResultAssembler."""

    def setup_method(self):
        self.assembler = ResultAssembler()

    def test_basic_assembly(self):
        """Assembles paragraphs into proper result format."""
        paragraphs = [
            {
                "id": "para-0",
                "content": "Hello world",
                "role": None,
                "page_number": 1,
                "bounding_box": {"x_min": 0, "y_min": 10, "x_max": 100, "y_max": 30},
                "font": {"name": "Arial", "size": 12.0, "bold": False},
            }
        ]
        result = self.assembler.assemble(paragraphs=paragraphs, tables=[], total_pages=1)

        assert result["model_used"] == "pymupdf"
        assert result["pages"] == 1
        assert len(result["paragraphs"]) == 1
        assert result["full_text"] == "Hello world"
        assert len(result["content_blocks"]) == 1
        assert result["content_blocks"][0]["type"] == "paragraph"

    def test_content_block_ordering(self):
        """Content blocks should be sorted by page then y position."""
        paragraphs = [
            {
                "id": "para-0", "content": "Page 2 text", "role": None,
                "page_number": 2, "bounding_box": {"x_min": 0, "y_min": 10, "x_max": 100, "y_max": 30},
                "font": {"name": "Arial", "size": 12.0, "bold": False},
            },
            {
                "id": "para-1", "content": "Page 1 top", "role": None,
                "page_number": 1, "bounding_box": {"x_min": 0, "y_min": 10, "x_max": 100, "y_max": 30},
                "font": {"name": "Arial", "size": 12.0, "bold": False},
            },
            {
                "id": "para-2", "content": "Page 1 bottom", "role": None,
                "page_number": 1, "bounding_box": {"x_min": 0, "y_min": 100, "x_max": 100, "y_max": 120},
                "font": {"name": "Arial", "size": 12.0, "bold": False},
            },
        ]
        result = self.assembler.assemble(paragraphs=paragraphs, tables=[], total_pages=2)

        block_ids = [b["content_id"] for b in result["content_blocks"]]
        assert block_ids == ["para-1", "para-2", "para-0"]

    def test_table_overlap_filtering(self):
        """Paragraphs overlapping tables should be filtered out."""
        paragraphs = [
            {
                "id": "para-0", "content": "Normal text", "role": None,
                "page_number": 1,
                "bounding_box": {"x_min": 0, "y_min": 0, "x_max": 100, "y_max": 20},
                "font": {"name": "Arial", "size": 12.0, "bold": False},
            },
            {
                "id": "para-1", "content": "Table cell text", "role": None,
                "page_number": 1,
                "bounding_box": {"x_min": 50, "y_min": 100, "x_max": 200, "y_max": 120},
                "font": {"name": "Arial", "size": 12.0, "bold": False},
            },
        ]
        tables = [
            {
                "id": "table-0", "page_number": 1,
                "bounding_box": {"x_min": 40, "y_min": 90, "x_max": 300, "y_max": 200},
                "rows": 2, "columns": 2, "cells": [],
            },
        ]
        result = self.assembler.assemble(paragraphs=paragraphs, tables=tables, total_pages=1)

        # para-1 overlaps with table-0, should be filtered
        para_ids = [p["id"] for p in result["paragraphs"]]
        assert "para-0" in para_ids
        assert "para-1" not in para_ids

    def test_no_overlap_different_pages(self):
        """Paragraphs on different pages from tables should not be filtered."""
        paragraphs = [
            {
                "id": "para-0", "content": "Page 1 text", "role": None,
                "page_number": 1,
                "bounding_box": {"x_min": 50, "y_min": 100, "x_max": 200, "y_max": 120},
                "font": {"name": "Arial", "size": 12.0, "bold": False},
            },
        ]
        tables = [
            {
                "id": "table-0", "page_number": 2,
                "bounding_box": {"x_min": 40, "y_min": 90, "x_max": 300, "y_max": 200},
                "rows": 2, "columns": 2, "cells": [],
            },
        ]
        result = self.assembler.assemble(paragraphs=paragraphs, tables=tables, total_pages=2)

        assert len(result["paragraphs"]) == 1

    def test_empty_input(self):
        """Should handle empty inputs gracefully."""
        result = self.assembler.assemble(paragraphs=[], tables=[], total_pages=0)
        assert result["paragraphs"] == []
        assert result["tables"] == []
        assert result["content_blocks"] == []
        assert result["full_text"] == ""

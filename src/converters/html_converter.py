"""Converts DocumentAnalysisResult to HTML matching Azure DI output format."""

from typing import Dict


class HtmlConverter:
    """Generates HTML from DocumentAnalysisResult, matching Azure Document Intelligence output."""

    def convert(self, result: Dict) -> str:
        """
        Convert a DocumentAnalysisResult dict to HTML.

        Produces the same HTML structure as DocumentIntelligenceClient.convertToHtml()
        in the doc-proc service.
        """
        html = '<html><head><meta charset="utf-8"></head><body>'

        # Create lookup maps
        paragraphs_by_id = {p["id"]: p for p in result.get("paragraphs", [])}
        tables_by_id = {t["id"]: t for t in result.get("tables", [])}
        images_by_id = {i["id"]: i for i in result.get("images", [])}

        # Output content in order using content_blocks
        for block in result.get("content_blocks", []):
            if block["type"] == "paragraph":
                para = paragraphs_by_id.get(block["content_id"])
                if para:
                    tag = self._get_role_tag(para.get("role"))
                    html += f'<{tag}>{self._escape_html(para["content"])}</{tag}>'

            elif block["type"] == "table":
                table = tables_by_id.get(block["content_id"])
                if table:
                    html += self._table_to_html(table)

            elif block["type"] == "image":
                img = images_by_id.get(block["content_id"])
                if img and img.get("data"):
                    mime = img.get("mime_type", "image/png")
                    html += f'<img src="data:{mime};base64,{img["data"]}" />'

        html += '</body></html>'
        return html

    def _get_role_tag(self, role: str = None) -> str:
        """Map paragraph role to HTML tag."""
        if role == "title":
            return "h1"
        elif role == "sectionHeading":
            return "h2"
        return "p"

    def _table_to_html(self, table: Dict) -> str:
        """Convert a table dict to HTML."""
        html = f'<table border="1" id="{table["id"]}"><tbody>'

        # Group cells by row
        rows = []
        for cell in table.get("cells", []):
            while len(rows) <= cell["row_index"]:
                rows.append([None] * table.get("columns", 0))
            if cell["column_index"] < len(rows[cell["row_index"]]):
                rows[cell["row_index"]][cell["column_index"]] = cell

        # Render rows
        for row in rows:
            html += '<tr>'
            for cell in row:
                if cell is None:
                    html += '<td></td>'
                    continue

                tag = 'th' if cell.get("kind") == "columnHeader" else 'td'
                colspan = f' colspan="{cell["column_span"]}"' if cell.get("column_span", 1) > 1 else ''
                rowspan = f' rowspan="{cell["row_span"]}"' if cell.get("row_span", 1) > 1 else ''

                html += f'<{tag}{colspan}{rowspan}>{self._escape_html(cell["content"])}</{tag}>'
            html += '</tr>'

        html += '</tbody></table>'
        return html

    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters."""
        return (
            text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#039;")
        )

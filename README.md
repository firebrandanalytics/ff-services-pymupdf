# ff-services-pymupdf

A fast, lightweight PDF processing microservice powered by [PyMuPDF](https://pymupdf.readthedocs.io/). Part of the [FireFoundry](https://github.com/firebrandanalytics) document processing platform.

## Features

- **Text extraction** with full font metadata (size, name, bold/italic, color)
- **Semantic role detection** — automatically classifies text as titles, headings, or body paragraphs based on font characteristics
- **Table extraction** — detects and extracts table structures with cell spans
- **Image extraction** — extracts embedded images with bounding box positions
- **Text layer detection** — per-page analysis of whether extractable text exists (useful for routing scanned pages to OCR)
- **HTML generation** — produces structured HTML matching the `DocumentAnalysisResult` format used across FireFoundry services

## How It Fits

This service handles text-layer PDFs — documents where text is embedded directly (not scanned images). It pairs with Azure Document Intelligence for OCR on scanned content, giving you the best of both worlds:

- **Text-layer pages** → this service (fast, local, no API costs)
- **Scanned pages** → Azure Document Intelligence (cloud OCR)

Both produce the same output format, so consumers get consistent HTML regardless of which backend processed each page.

```
doc-proc-service
    ├── ff-services-pymupdf  → text-layer pages
    └── Azure Doc Intelligence → scanned/image pages
```

## API

### `POST /api/extract`
Extract structured content from a PDF.

**Request:** multipart/form-data with `file` field, or JSON with base64-encoded PDF.

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `output_format` | `json` \| `html` | `json` | Response format |
| `pages` | string | all | Page range (e.g., `1,3,5-10`) |
| `include_images` | boolean | `false` | Extract embedded images as base64 |

**Response (JSON):**
```json
{
  "pages": 5,
  "paragraphs": [
    {
      "id": "para-0",
      "content": "Document Title",
      "role": "title",
      "page_number": 1,
      "bounding_box": { "x_min": 72, "y_min": 50, "x_max": 540, "y_max": 80 },
      "font": { "name": "Arial-Bold", "size": 24, "bold": true }
    }
  ],
  "tables": [
    {
      "id": "table-0",
      "page_number": 2,
      "rows": 5,
      "columns": 3,
      "cells": [
        { "row_index": 0, "column_index": 0, "content": "Header", "kind": "columnHeader" }
      ]
    }
  ],
  "content_blocks": [
    { "type": "paragraph", "page": 1, "y_position": 50, "content_id": "para-0" }
  ]
}
```

### `POST /api/detect-text-layer`
Check which pages have extractable text.

**Response:**
```json
{
  "total_pages": 10,
  "pages": [
    { "page": 1, "has_text_layer": true, "char_count": 1523 },
    { "page": 2, "has_text_layer": false, "char_count": 0 }
  ]
}
```

### `GET /health` | `GET /ready`
Health and readiness probes.

## Development

### Prerequisites
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### Setup
```bash
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

### Run
```bash
uvicorn app.main:app --reload --port 8089
```

### Test
```bash
pytest
```

### Docker
```bash
docker build -t ff-services-pymupdf .
docker run -p 8089:8089 ff-services-pymupdf
```

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `PORT` | `8089` | Service port |
| `LOG_LEVEL` | `info` | Logging level |
| `MAX_FILE_SIZE_MB` | `100` | Maximum upload size |
| `HEADING_FONT_SIZE_THRESHOLD` | `14` | Min font size for heading classification |
| `TITLE_FONT_SIZE_THRESHOLD` | `18` | Min font size for title classification |

## License

AGPL-3.0 — see [LICENSE](LICENSE).

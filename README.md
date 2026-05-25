# ff-services-pymupdf

A fast, lightweight PDF processing microservice powered by [PyMuPDF](https://pymupdf.readthedocs.io/).

## Features

- **Text extraction** with full font metadata (size, name, bold/italic, color)
- **Semantic role detection** — automatically classifies text as titles, headings, or body paragraphs based on font characteristics
- **Table extraction** — detects and extracts table structures with cell spans
- **Image extraction** — extracts embedded images with bounding box positions
- **Text layer detection** — per-page analysis of whether extractable text exists (useful for routing scanned pages to OCR)
- **HTML generation** — produces structured HTML matching the `DocumentAnalysisResult` format

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

### `POST /api/render-region`
Rasterize a bounding-box region of a single PDF page as a PNG or JPG image.
Used by consumers that need image bytes for a figure or table (e.g. for
attaching to a working-memory record).

**Request:** `multipart/form-data` (mirrors `/api/extract`).

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `file` | file | — | PDF bytes (`application/pdf` part). |
| `page` | int | — | **1-based** page number, matching `/api/extract`'s `page_number` convention. |
| `x_min`, `y_min`, `x_max`, `y_max` | float | — | Bbox in PDF point coordinates (1/72 inch). `x_min<x_max`, `y_min<y_max`, non-negative. Bbox is clipped to the page rect; entirely-outside bboxes return 400. |
| `dpi` | int | `144` | Render DPI. Must be in `[36, 600]`. |
| `format` | `png` \| `jpg` | `png` | Output image format. |
| `max_dim_px` | int | `2048` | If the rendered image's larger dimension exceeds this, the image is rendered at a proportionally lower scale. Must be in `[1, 8192]`. |

**Response:** raw image bytes. `Content-Type` is `image/png` or `image/jpeg`
depending on `format`. Image metadata is in response headers:
- `X-Width-Px`, `X-Height-Px`: pixel dimensions
- `X-DPI-Used`: effective DPI (lower than requested if downscaled)
- `X-Page-Number`: 1-based page rendered (echoes the request)
- `X-Clipped-To-Page`: `true` if the requested bbox extended past page bounds
- `X-Downscaled`: `true` if the image was downscaled to fit `max_dim_px`
- `X-Render-Time-Ms`: server-side processing time in milliseconds

**Errors:**
- `400` invalid bbox / page / dpi / format / max_dim_px / oversized file
- `422` malformed PDF or missing required multipart field
- `5xx` PyMuPDF render failure

**Breaking change in v0.3.0:** the prior JSON+base64 contract (with nested
`bbox` and 0-indexed `page`) was removed. See ff-services-pymupdf#12.

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
uvicorn src.http_server:app --reload --port 8089
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

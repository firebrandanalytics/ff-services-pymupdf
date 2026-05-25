"""HTTP server for the PyMuPDF processing service using FastAPI."""

import asyncio
import base64
import logging
import time
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .backends.base import Backend
from .backends.text_extraction import TextExtractionBackend
from .backends.text_layer_detection import TextLayerDetectionBackend
from .config import get_config
from .renderers.region import (
    MalformedPdfError,
    RegionRenderError,
    render_region,
)

SERVICE_VERSION = "0.3.0"
ALLOWED_RENDER_FORMATS = {"png", "jpg"}
RENDER_FORMAT_CONTENT_TYPES = {"png": "image/png", "jpg": "image/jpeg"}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Pydantic models
class ProcessRequest(BaseModel):
    """Request body for POST /process (base64 mode)."""
    operation: str = Field(..., description="Operation: extract, detect_text_layer")
    data: str = Field(..., description="Base64-encoded PDF data")
    options: Dict[str, str] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    """Response body for GET /health."""
    status: str = "ok"
    operations: List[str]
    version: str = SERVICE_VERSION


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="PyMuPDF Processing Service",
        description="PDF text extraction, table detection, and text layer analysis using PyMuPDF",
        version=SERVICE_VERSION,
    )

    backends: List[Backend] = [
        TextExtractionBackend(),
        TextLayerDetectionBackend(),
    ]

    supported_operations = set()
    for backend in backends:
        if hasattr(backend, "SUPPORTED_OPERATIONS"):
            supported_operations.update(backend.SUPPORTED_OPERATIONS)

    def find_backend(operation: str) -> Optional[Backend]:
        for backend in backends:
            if backend.supports(operation):
                return backend
        return None

    @app.get("/health", response_model=HealthResponse)
    async def health_check() -> HealthResponse:
        return HealthResponse(
            status="ok",
            operations=sorted(list(supported_operations)),
            version=SERVICE_VERSION,
        )

    @app.get("/ready")
    async def readiness_check():
        return {"status": "ready"}

    @app.post("/api/extract")
    async def extract(
        file: UploadFile = File(...),
        output_format: str = Form("json"),
        pages: str = Form(""),
        include_images: str = Form("false"),
    ):
        """Extract structured content from a PDF via multipart upload."""
        start_time = time.time()

        pdf_data = await file.read()
        config = get_config()
        max_bytes = config.extraction.max_file_size_mb * 1024 * 1024
        if len(pdf_data) > max_bytes:
            raise HTTPException(
                status_code=400,
                detail={"success": False, "error": f"File exceeds {config.extraction.max_file_size_mb}MB limit"},
            )

        logger.info(f"Extract request: size={len(pdf_data)} bytes, format={output_format}")

        backend = find_backend("extract")
        if backend is None:
            raise HTTPException(status_code=500, detail="Extract backend not available")

        try:
            options = {"output_format": output_format, "include_images": include_images}
            if pages:
                options["pages"] = pages

            output_data, fmt, metadata = await asyncio.to_thread(
                backend.process, pdf_data, "extract", options
            )
            processing_time_ms = int((time.time() - start_time) * 1000)

            if fmt == "json":
                import json
                return {
                    "success": True,
                    "result": json.loads(output_data.decode("utf-8")),
                    "format": "application/json",
                    "metadata": metadata,
                    "processing_time_ms": processing_time_ms,
                }
            else:
                return {
                    "success": True,
                    "result": output_data.decode("utf-8"),
                    "format": "text/html",
                    "metadata": metadata,
                    "processing_time_ms": processing_time_ms,
                }

        except ValueError as e:
            raise HTTPException(status_code=400, detail={"success": False, "error": str(e)})
        except Exception as e:
            logger.exception(f"Extract failed: {e}")
            raise HTTPException(status_code=500, detail={"success": False, "error": str(e)})

    @app.post("/api/detect-text-layer")
    async def detect_text_layer(file: UploadFile = File(...)):
        """Detect which pages have extractable text layers."""
        start_time = time.time()

        pdf_data = await file.read()
        config = get_config()
        max_bytes = config.extraction.max_file_size_mb * 1024 * 1024
        if len(pdf_data) > max_bytes:
            raise HTTPException(
                status_code=400,
                detail={"success": False, "error": f"File exceeds {config.extraction.max_file_size_mb}MB limit"},
            )

        logger.info(f"Detect text layer request: size={len(pdf_data)} bytes")

        backend = find_backend("detect_text_layer")
        if backend is None:
            raise HTTPException(status_code=500, detail="Detection backend not available")

        try:
            output_data, fmt, metadata = await asyncio.to_thread(
                backend.process, pdf_data, "detect_text_layer", {}
            )
            processing_time_ms = int((time.time() - start_time) * 1000)

            import json
            return {
                "success": True,
                "result": json.loads(output_data.decode("utf-8")),
                "metadata": metadata,
                "processing_time_ms": processing_time_ms,
            }

        except ValueError as e:
            raise HTTPException(status_code=400, detail={"success": False, "error": str(e)})
        except Exception as e:
            logger.exception(f"Detection failed: {e}")
            raise HTTPException(status_code=500, detail={"success": False, "error": str(e)})

    @app.post("/api/render-region")
    async def render_region_endpoint(
        file: UploadFile = File(...),
        page: int = Form(..., description="1-based page number"),
        x_min: float = Form(...),
        y_min: float = Form(...),
        x_max: float = Form(...),
        y_max: float = Form(...),
        dpi: int = Form(144),
        format: str = Form("png"),
        max_dim_px: int = Form(2048),
    ):
        """Render a bbox of a PDF page as a PNG or JPG image.

        Mirrors the multipart contract of /api/extract. The `page` parameter
        is 1-based (matching /api/extract's page_number convention). The
        rendered image bytes are returned in the response body with metadata
        in response headers (see X-Width-Px etc.).
        """
        start_time = time.time()

        pdf_data = await file.read()

        config = get_config()
        max_bytes = config.extraction.max_file_size_mb * 1024 * 1024
        if len(pdf_data) > max_bytes:
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "error": f"File exceeds {config.extraction.max_file_size_mb}MB limit",
                },
            )

        normalized_format = format.lower()
        if normalized_format not in ALLOWED_RENDER_FORMATS:
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "error": (
                        f"Invalid format: must be one of "
                        f"{sorted(ALLOWED_RENDER_FORMATS)} (got {format!r})"
                    ),
                },
            )

        if page < 1:
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "error": f"Invalid page: must be 1-based (>= 1), got {page}",
                },
            )
        page_index = page - 1

        logger.info(
            f"Render region request: size={len(pdf_data)} bytes, "
            f"page={page} (0-indexed {page_index}), "
            f"bbox=({x_min},{y_min},{x_max},{y_max}), dpi={dpi}, "
            f"format={normalized_format}, max_dim_px={max_dim_px}"
        )

        try:
            image_bytes, meta = await asyncio.to_thread(
                render_region,
                pdf_data,
                page_index,
                (x_min, y_min, x_max, y_max),
                dpi,
                max_dim_px,
                normalized_format,
            )
        except MalformedPdfError as e:
            raise HTTPException(
                status_code=422,
                detail={"success": False, "error": str(e)},
            )
        except RegionRenderError as e:
            raise HTTPException(
                status_code=400,
                detail={"success": False, "error": str(e)},
            )
        except Exception as e:
            logger.exception(f"Render failed: {e}")
            raise HTTPException(
                status_code=500,
                detail={"success": False, "error": str(e)},
            )

        processing_time_ms = int((time.time() - start_time) * 1000)
        headers = {
            "X-Width-Px": str(meta.width_px),
            "X-Height-Px": str(meta.height_px),
            "X-DPI-Used": str(meta.dpi_used),
            "X-Page-Number": str(meta.page_index + 1),
            "X-Clipped-To-Page": "true" if meta.clipped_to_page else "false",
            "X-Downscaled": "true" if meta.downscaled else "false",
            "X-Render-Time-Ms": str(processing_time_ms),
        }
        return Response(
            content=image_bytes,
            media_type=RENDER_FORMAT_CONTENT_TYPES[normalized_format],
            headers=headers,
        )

    @app.post("/process")
    async def process_document(request: ProcessRequest) -> Dict[str, Any]:
        """Process a PDF via base64-encoded payload (compatible with pyworker pattern)."""
        start_time = time.time()

        try:
            document_data = base64.b64decode(request.data, validate=True)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail={"success": False, "error": {"code": "INVALID_BASE64", "message": str(e)}}
            )

        config = get_config()
        max_bytes = config.extraction.max_file_size_mb * 1024 * 1024
        if len(document_data) > max_bytes:
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "error": {
                        "code": "FILE_TOO_LARGE",
                        "message": f"File exceeds {config.extraction.max_file_size_mb}MB limit",
                    }
                }
            )

        backend = find_backend(request.operation)
        if backend is None:
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "error": {
                        "code": "INVALID_OPERATION",
                        "message": f"Operation '{request.operation}' is not supported",
                        "details": {"supported_operations": sorted(list(supported_operations))},
                    }
                }
            )

        try:
            output_data, output_format, metadata = await asyncio.to_thread(
                backend.process, document_data, request.operation, request.options
            )

            processing_time_ms = int((time.time() - start_time) * 1000)

            if output_format == "json":
                import json
                return {
                    "success": True,
                    "result": json.loads(output_data.decode("utf-8")),
                    "format": "application/json",
                    "metadata": {str(k): str(v) for k, v in metadata.items()},
                    "processing_time_ms": processing_time_ms,
                }
            else:
                return {
                    "success": True,
                    "result": output_data.decode("utf-8"),
                    "format": f"text/{output_format}",
                    "metadata": {str(k): str(v) for k, v in metadata.items()},
                    "processing_time_ms": processing_time_ms,
                }

        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail={"success": False, "error": {"code": "VALIDATION_ERROR", "message": str(e)}}
            )
        except Exception as e:
            logger.exception(f"Processing error: {e}")
            raise HTTPException(
                status_code=500,
                detail={"success": False, "error": {"code": "PROCESSING_FAILED", "message": str(e)}}
            )

    return app


# Create app instance for uvicorn
app = create_app()


def run_server():
    """Run the HTTP server."""
    import uvicorn
    config = get_config()
    logger.info(f"Starting HTTP server on {config.server.host}:{config.server.port}")
    uvicorn.run(
        "src.http_server:app",
        host=config.server.host,
        port=config.server.port,
        log_level="info",
    )


if __name__ == "__main__":
    run_server()

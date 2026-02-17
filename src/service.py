"""PyMuPDFWorker gRPC service implementation."""

import time
import logging
from typing import List

import grpc
from pymupdf_worker_pb2 import (
    OperationRequest,
    SupportResponse,
    ProcessRequest,
    ProcessResponse,
    Empty,
    HealthResponse
)
from pymupdf_worker_pb2_grpc import PyMuPDFWorkerServicer

from .backends.base import Backend
from .backends.text_extraction import TextExtractionBackend
from .backends.text_layer_detection import TextLayerDetectionBackend

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PyMuPDFWorkerService(PyMuPDFWorkerServicer):
    """Implementation of PyMuPDFWorker gRPC service."""

    VERSION = "0.1.0"

    def __init__(self):
        self.backends: List[Backend] = [
            TextExtractionBackend(),
            TextLayerDetectionBackend(),
        ]

        logger.info(f"PyMuPDFWorker Service v{self.VERSION} initialized")
        logger.info(f"Registered {len(self.backends)} backends")

    def SupportsOperation(
        self,
        request: OperationRequest,
        context: grpc.ServicerContext
    ) -> SupportResponse:
        operation = request.operation
        format_hint = request.format

        for backend in self.backends:
            if backend.supports(operation, format_hint):
                return SupportResponse(
                    supported=True,
                    message=f"Supported by {backend.__class__.__name__}"
                )

        return SupportResponse(
            supported=False,
            message=f"Operation '{operation}' is not supported"
        )

    def ProcessDocument(
        self,
        request: ProcessRequest,
        context: grpc.ServicerContext
    ) -> ProcessResponse:
        operation = request.operation
        document_data = request.document_data
        options = dict(request.options)

        logger.info(
            f"Processing: operation={operation}, size={len(document_data)} bytes"
        )

        start_time = time.time()

        try:
            backend = self._find_backend(operation)
            if backend is None:
                error_msg = f"No backend found for operation '{operation}'"
                logger.error(error_msg)
                return ProcessResponse(
                    success=False,
                    error_message=error_msg,
                    processing_time_ms=int((time.time() - start_time) * 1000)
                )

            output_data, output_format, metadata = backend.process(
                document_data, operation, options
            )

            processing_time_ms = int((time.time() - start_time) * 1000)

            logger.info(
                f"Completed in {processing_time_ms}ms: "
                f"output_size={len(output_data)} bytes, format={output_format}"
            )

            return ProcessResponse(
                output_data=output_data,
                format=output_format,
                metadata=metadata,
                processing_time_ms=processing_time_ms,
                success=True,
                error_message=""
            )

        except Exception as e:
            processing_time_ms = int((time.time() - start_time) * 1000)
            error_msg = f"Processing failed: {str(e)}"
            logger.error(error_msg, exc_info=True)

            return ProcessResponse(
                success=False,
                error_message=error_msg,
                processing_time_ms=processing_time_ms
            )

    def HealthCheck(
        self,
        request: Empty,
        context: grpc.ServicerContext
    ) -> HealthResponse:
        supported_ops = set()
        for backend in self.backends:
            if hasattr(backend, 'SUPPORTED_OPERATIONS'):
                supported_ops.update(backend.SUPPORTED_OPERATIONS)

        return HealthResponse(
            healthy=True,
            version=self.VERSION,
            supported_operations=sorted(list(supported_ops))
        )

    def _find_backend(self, operation: str) -> Backend:
        for backend in self.backends:
            if backend.supports(operation):
                return backend
        return None

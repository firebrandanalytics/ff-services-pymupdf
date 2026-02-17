# PyMuPDF PDF Processing Service - Dockerfile
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies (PyMuPDF ships prebuilt wheels, no gcc/libmupdf-dev needed)
RUN pip install --no-cache-dir -r requirements.txt

# Copy proto files and generate gRPC stubs
COPY proto/ ./proto/
RUN mkdir -p ./src && python -m grpc_tools.protoc \
    -I./proto \
    --python_out=./src \
    --grpc_python_out=./src \
    proto/pymupdf_worker.proto

# Copy application source code
COPY src/ ./src/

# Expose ports
EXPOSE 50052
EXPOSE 8089

# Set environment variables
ENV GRPC_PORT=50052
ENV HTTP_PORT=8089
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import grpc; from src.pymupdf_worker_pb2_grpc import PyMuPDFWorkerStub; from src.pymupdf_worker_pb2 import Empty; channel = grpc.insecure_channel('localhost:50052'); stub = PyMuPDFWorkerStub(channel); stub.HealthCheck(Empty())" || exit 1

# Run the gRPC server
CMD ["python", "-m", "src.server"]

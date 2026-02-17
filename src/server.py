"""gRPC server for the PyMuPDFWorker service."""

import logging
import os
import signal
import sys
import threading
from concurrent import futures

import grpc
from pymupdf_worker_pb2_grpc import add_PyMuPDFWorkerServicer_to_server

from .service import PyMuPDFWorkerService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DEFAULT_PORT = 50052
MAX_WORKERS = 10
MAX_MESSAGE_LENGTH = 100 * 1024 * 1024  # 100MB


def start_http_health_server():
    """Start the HTTP health server in a background thread."""
    import uvicorn
    from .http_server import app

    http_port = int(os.environ.get('HTTP_PORT', '8089'))
    logger.info(f"Starting HTTP health server on port {http_port}")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=http_port,
        log_level="warning",
    )


class GracefulKiller:
    """Handle graceful shutdown on SIGTERM and SIGINT."""

    def __init__(self):
        self.kill_now = False
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self, signum, frame):
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.kill_now = True


def serve(port: int = DEFAULT_PORT):
    """Start the gRPC server."""
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=MAX_WORKERS),
        options=[
            ('grpc.max_send_message_length', MAX_MESSAGE_LENGTH),
            ('grpc.max_receive_message_length', MAX_MESSAGE_LENGTH),
        ]
    )

    add_PyMuPDFWorkerServicer_to_server(PyMuPDFWorkerService(), server)
    server.add_insecure_port(f'[::]:{port}')
    server.start()

    logger.info(f"PyMuPDFWorker gRPC server started on port {port}")
    logger.info(f"Max workers: {MAX_WORKERS}")
    logger.info(f"Max message length: {MAX_MESSAGE_LENGTH / 1024 / 1024}MB")

    killer = GracefulKiller()
    try:
        while not killer.kill_now:
            server.wait_for_termination(timeout=1)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        logger.info("Stopping server...")
        server.stop(grace=5)
        logger.info("Server stopped")


def main():
    """Main entry point."""
    import os
    port = int(os.environ.get('GRPC_PORT', DEFAULT_PORT))

    logger.info("=" * 60)
    logger.info("PyMuPDF PDF Processing Worker")
    logger.info("=" * 60)

    # Start HTTP health server in background thread
    http_thread = threading.Thread(target=start_http_health_server, daemon=True)
    http_thread.start()

    try:
        serve(port)
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()

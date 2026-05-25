export { PyMuPDFProcessorClient } from './client.js';
export type { PyMuPDFProcessorClientOptions } from './client.js';
export {
  ProcessRequest,
  ProcessResponse,
  OperationRequest,
  SupportResponse,
  HealthResponse,
  Empty,
  PyMuPDFWorkerClient,
  PyMuPDFWorkerService,
  protobufPackage,
} from './generated/pymupdf_worker.js';

export {
  PyMuPDFHttpClient,
  PyMuPDFServiceError,
  BBoxSchema,
  RenderRegionRequestSchema,
} from './http-client.js';
export type {
  BBox,
  RenderRegionRequest,
  RenderRegionResult,
  PyMuPDFHttpClientOptions,
} from './http-client.js';

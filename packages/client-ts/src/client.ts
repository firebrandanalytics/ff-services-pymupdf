import * as grpc from '@grpc/grpc-js';
import {
  PyMuPDFWorkerClient,
  ProcessRequest,
  ProcessResponse,
  SupportResponse,
  HealthResponse,
} from './generated/pymupdf_worker.js';

export interface PyMuPDFProcessorClientOptions {
  address: string;
  credentials?: grpc.ChannelCredentials;
  options?: grpc.ClientOptions;
}

/**
 * Convenience wrapper around the generated gRPC client with Promise-based API.
 */
export class PyMuPDFProcessorClient {
  private client: PyMuPDFWorkerClient;

  constructor(opts: PyMuPDFProcessorClientOptions) {
    this.client = new PyMuPDFWorkerClient(
      opts.address,
      opts.credentials ?? grpc.credentials.createInsecure(),
      opts.options
    );
  }

  async processDocument(request: ProcessRequest): Promise<ProcessResponse> {
    return new Promise((resolve, reject) => {
      this.client.processDocument(request, (err, response) => {
        if (err) return reject(err);
        resolve(response!);
      });
    });
  }

  async supportsOperation(operation: string, format = ''): Promise<SupportResponse> {
    return new Promise((resolve, reject) => {
      this.client.supportsOperation({ operation, format }, (err, response) => {
        if (err) return reject(err);
        resolve(response!);
      });
    });
  }

  async healthCheck(): Promise<HealthResponse> {
    return new Promise((resolve, reject) => {
      this.client.healthCheck({}, (err, response) => {
        if (err) return reject(err);
        resolve(response!);
      });
    });
  }

  close(): void {
    this.client.close();
  }
}

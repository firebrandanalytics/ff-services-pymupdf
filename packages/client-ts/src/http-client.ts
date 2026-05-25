import { z } from 'zod';

// ---- Zod schemas ----

export const BBoxSchema = z.object({
  x0: z.number(),
  y0: z.number(),
  x1: z.number(),
  y1: z.number(),
});
export type BBox = z.infer<typeof BBoxSchema>;

export const RenderRegionRequestSchema = z.object({
  pdf_bytes: z.string().describe('Base64-encoded PDF data'),
  page: z.number().int().nonnegative().describe('0-indexed page number'),
  bbox: BBoxSchema,
  dpi: z.number().int().positive().default(144),
  max_dim_px: z.number().int().positive().default(2048),
});
export type RenderRegionRequest = z.input<typeof RenderRegionRequestSchema>;

export interface RenderRegionResult {
  png: Uint8Array;
  widthPx: number;
  heightPx: number;
  dpiUsed: number;
  pageIndex: number;
  clippedToPage: boolean;
  downscaled: boolean;
  processingTimeMs?: number;
}

export interface PyMuPDFHttpClientOptions {
  /** Base URL e.g. `http://doc-proc-pymupdf:8089`. Trailing slash optional. */
  baseUrl: string;
  /** Optional fetch implementation. Defaults to global `fetch`. */
  fetch?: typeof fetch;
  /** Default request headers (e.g. auth). */
  headers?: Record<string, string>;
}

export class PyMuPDFServiceError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly body?: unknown,
  ) {
    super(message);
    this.name = 'PyMuPDFServiceError';
  }
}

/**
 * Thin HTTP client for the ff-services-pymupdf HTTP API.
 *
 * The gRPC client (`PyMuPDFProcessorClient`) covers `extract` and
 * `detect_text_layer`. Binary-bearing endpoints like `render-region`,
 * which return raw `image/png`, live here.
 */
export class PyMuPDFHttpClient {
  private readonly baseUrl: string;
  private readonly fetchImpl: typeof fetch;
  private readonly defaultHeaders: Record<string, string>;

  constructor(opts: PyMuPDFHttpClientOptions) {
    this.baseUrl = opts.baseUrl.replace(/\/+$/, '');
    this.fetchImpl =
      opts.fetch ??
      (typeof fetch !== 'undefined' ? fetch.bind(globalThis) : undefined as any);
    if (!this.fetchImpl) {
      throw new Error(
        'No fetch implementation available; pass `fetch` in options',
      );
    }
    this.defaultHeaders = { ...(opts.headers ?? {}) };
  }

  /**
   * Render a bbox of a single PDF page as a PNG.
   *
   * @param input Either an already-base64 string + bbox, or pdf bytes that
   *   will be base64-encoded for you.
   */
  async renderRegion(
    input:
      | RenderRegionRequest
      | (Omit<RenderRegionRequest, 'pdf_bytes'> & { pdfBytes: Uint8Array }),
  ): Promise<RenderRegionResult> {
    const body =
      'pdfBytes' in input
        ? { ...input, pdf_bytes: encodeBase64(input.pdfBytes), pdfBytes: undefined }
        : input;
    delete (body as Record<string, unknown>).pdfBytes;

    const parsed = RenderRegionRequestSchema.parse(body);

    const res = await this.fetchImpl(`${this.baseUrl}/api/render-region`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'image/png',
        ...this.defaultHeaders,
      },
      body: JSON.stringify(parsed),
    });

    if (!res.ok) {
      let detail: unknown = undefined;
      try {
        detail = await res.json();
      } catch {
        try {
          detail = await res.text();
        } catch {
          // ignore
        }
      }
      throw new PyMuPDFServiceError(
        `render-region failed: HTTP ${res.status}`,
        res.status,
        detail,
      );
    }

    const buf = new Uint8Array(await res.arrayBuffer());
    return {
      png: buf,
      widthPx: parseIntHeader(res.headers, 'x-image-width'),
      heightPx: parseIntHeader(res.headers, 'x-image-height'),
      dpiUsed: parseIntHeader(res.headers, 'x-dpi-used'),
      pageIndex: parseIntHeader(res.headers, 'x-page-index'),
      clippedToPage: res.headers.get('x-clipped-to-page') === 'true',
      downscaled: res.headers.get('x-downscaled') === 'true',
      processingTimeMs: tryParseIntHeader(res.headers, 'x-processing-time-ms'),
    };
  }
}

function parseIntHeader(headers: Headers, name: string): number {
  const v = headers.get(name);
  if (v == null) throw new Error(`Missing response header: ${name}`);
  const n = Number.parseInt(v, 10);
  if (!Number.isFinite(n)) throw new Error(`Invalid integer header ${name}: ${v}`);
  return n;
}

function tryParseIntHeader(headers: Headers, name: string): number | undefined {
  const v = headers.get(name);
  if (v == null) return undefined;
  const n = Number.parseInt(v, 10);
  return Number.isFinite(n) ? n : undefined;
}

function encodeBase64(bytes: Uint8Array): string {
  // Prefer Node's Buffer when available; fall back to btoa.
  const g = globalThis as unknown as {
    Buffer?: { from(b: Uint8Array): { toString(enc: 'base64'): string } };
    btoa?: (s: string) => string;
  };
  if (g.Buffer) {
    return g.Buffer.from(bytes).toString('base64');
  }
  if (g.btoa) {
    let s = '';
    for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
    return g.btoa(s);
  }
  throw new Error('No base64 encoder available (no Buffer, no btoa)');
}

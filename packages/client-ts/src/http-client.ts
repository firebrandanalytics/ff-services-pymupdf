import { z } from 'zod';

// ---- Zod schemas ----

/**
 * Bounding box in PDF point coordinates (1/72 inch).
 *
 * Note: the prior 0.2.0 schema used {x0,y0,x1,y1}. The service now matches
 * the rest of the FireFoundry ecosystem (DocProcLayoutClient, pymupdf
 * extract responses) which use {x_min,y_min,x_max,y_max}.
 */
export const BBoxSchema = z.object({
  x_min: z.number(),
  y_min: z.number(),
  x_max: z.number(),
  y_max: z.number(),
});
export type BBox = z.infer<typeof BBoxSchema>;

export const RenderRegionRequestSchema = z.object({
  /** 1-based page number, matching `/api/extract`'s page_number convention. */
  page: z.number().int().min(1).describe('1-based page number'),
  bbox: BBoxSchema,
  dpi: z.number().int().min(36).max(600).default(144),
  format: z.enum(['png', 'jpg']).default('png'),
  max_dim_px: z.number().int().min(1).max(8192).default(2048),
});
export type RenderRegionRequest = z.input<typeof RenderRegionRequestSchema>;

export interface RenderRegionResult {
  /** Encoded image bytes (PNG or JPEG, per request `format`). */
  image: Uint8Array;
  /** Same bytes as `image`; kept for backwards-compat with 0.2.0 callers. */
  png: Uint8Array;
  format: 'png' | 'jpg';
  widthPx: number;
  heightPx: number;
  dpiUsed: number;
  /** 1-based page number that was rendered. */
  pageNumber: number;
  clippedToPage: boolean;
  downscaled: boolean;
  renderTimeMs?: number;
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
 * which return raw image bytes, live here.
 *
 * As of service v0.3.0, `/api/render-region` accepts multipart/form-data
 * (matching the existing `/api/extract` pattern). The prior JSON+base64
 * contract has been removed.
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
   * Render a bbox of a single PDF page as an image.
   *
   * The PDF bytes are sent as a multipart file part named `file`, alongside
   * the render parameters as separate form fields. This matches the contract
   * implemented by `DocProcLayoutClient.renderRegion` in rag-agent-bundle.
   */
  async renderRegion(
    pdfBytes: Uint8Array,
    params: RenderRegionRequest,
  ): Promise<RenderRegionResult> {
    const parsed = RenderRegionRequestSchema.parse(params);

    const form = new FormData();
    form.append(
      'file',
      new Blob([new Uint8Array(pdfBytes)], { type: 'application/pdf' }),
      'document.pdf',
    );
    form.append('page', String(parsed.page));
    form.append('x_min', String(parsed.bbox.x_min));
    form.append('y_min', String(parsed.bbox.y_min));
    form.append('x_max', String(parsed.bbox.x_max));
    form.append('y_max', String(parsed.bbox.y_max));
    form.append('dpi', String(parsed.dpi));
    form.append('format', parsed.format);
    form.append('max_dim_px', String(parsed.max_dim_px));

    const acceptHeader =
      parsed.format === 'jpg' ? 'image/jpeg' : 'image/png';
    const res = await this.fetchImpl(`${this.baseUrl}/api/render-region`, {
      method: 'POST',
      headers: {
        Accept: acceptHeader,
        ...this.defaultHeaders,
      },
      body: form,
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
      image: buf,
      png: buf,
      format: parsed.format,
      widthPx: parseIntHeader(res.headers, 'x-width-px'),
      heightPx: parseIntHeader(res.headers, 'x-height-px'),
      dpiUsed: parseIntHeader(res.headers, 'x-dpi-used'),
      pageNumber: parseIntHeader(res.headers, 'x-page-number'),
      clippedToPage: res.headers.get('x-clipped-to-page') === 'true',
      downscaled: res.headers.get('x-downscaled') === 'true',
      renderTimeMs: tryParseIntHeader(res.headers, 'x-render-time-ms'),
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

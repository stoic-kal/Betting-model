/**
 * api.ts — Axios base instance
 *
 * Single configured Axios client for all Athena → Flask requests.
 * Interceptors handle: auth headers, error normalisation, timing logs.
 */

import axios, { type AxiosError, type AxiosResponse } from 'axios';

// ── Instance ──────────────────────────────────────────────────────────────────

export const api = axios.create({
  // In dev, Vite proxies /api → http://localhost:3000
  // In production, Flask serves both Athena static files and /api
  baseURL: '/api',
  timeout: 30_000,
  headers: {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  },
});

// ── Request interceptor ───────────────────────────────────────────────────────

api.interceptors.request.use(
  (config) => {
    // Stamp every request with a high-res start time for latency logging
    (config as unknown as Record<string, unknown>)['_t'] = performance.now();
    return config;
  },
  (error) => Promise.reject(error)
);

// ── Response interceptor ──────────────────────────────────────────────────────

api.interceptors.response.use(
  (response: AxiosResponse) => {
    const start = (response.config as unknown as Record<string, unknown>)['_t'] as number | undefined;
    if (start !== undefined && import.meta.env.DEV) {
      const ms = Math.round(performance.now() - start);
      console.debug(`[Athena API] ${response.config.url}  ${ms}ms  ${response.status}`);
    }
    return response;
  },
  (error: AxiosError) => {
    const url    = error.config?.url ?? 'unknown';
    const status = error.response?.status ?? 0;
    const msg    = (error.response?.data as Record<string, unknown>)?.['error']
                ?? error.message
                ?? 'Unknown API error';

    if (import.meta.env.DEV) {
      console.error(`[Athena API] ✗ ${url}  ${status}  ${msg}`);
    }

    // Re-throw a normalised error object — services catch and surface this
    return Promise.reject(
      new AthenaApiError(String(msg), status, url)
    );
  }
);

// ── Normalised error class ────────────────────────────────────────────────────

export class AthenaApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly url: string
  ) {
    super(message);
    this.name = 'AthenaApiError';
  }

  get isNotFound()     { return this.status === 404; }
  get isServerError()  { return this.status >= 500; }
  get isNetworkError() { return this.status === 0; }
}

/**
 * The React side of the Tauri `brain_call` command (front-back-communicate.md
 * F11, back-end-core/docs/desktop-bridge.md): a `Transport` that sends one api.md
 * request envelope to the Rust host and returns the response envelope.
 *
 * It talks to the Tauri 2 global `window.__TAURI_INTERNALS__.invoke` directly.
 * The `@tauri-apps/api` package is NOT installed and `npm install` cannot run in
 * the agent sandbox; once the user installs it, this shim can be replaced by
 * `invoke('brain_call', { request })` from `@tauri-apps/api/core` (the contract
 * below stays the same). In a plain browser (`vite dev`, Playwright) the global
 * does not exist: `createTauriTransport()` returns null and nothing is called.
 *
 * Failure handling (desktop-bridge.md "生命周期与故障"): the host returns schema
 * version 1 error envelopes for its own failures, but an `invoke` can also
 * REJECT (ACL denial, desktop unavailable, a closed window). Every rejection
 * becomes a schema-version-1 error envelope with code `MODEL_UNAVAILABLE` and
 * the request's id, so `RemoteBrainAdapter` maps it like any other error.
 * Nothing is thrown past the adapter and nothing is ever retried: a failed
 * `submit` may or may not have been committed, and there is no idempotency key
 * (a retry could store the same text twice). The user re-checks the input list.
 *
 * UNVERIFIED: written against the Tauri 2 API and the Rust host's tests
 * (MockRuntime). It has NOT been run in the native WebKitGTK build of the
 * desktop app; do not claim the desktop flow works until that acceptance ran.
 *
 * Pure module: no React, DOM or three (the global is read structurally).
 */

import type { RequestEnvelope, ResponseEnvelope, Transport } from './remote';
import { t } from '../i18n/lang';

/** The Tauri command name, as registered in `src-tauri/src/lib.rs`. */
export const BRAIN_COMMAND = 'brain_call';

type Invoke = (command: string, args?: Record<string, unknown>) => Promise<unknown>;

/** Longest rejection text copied into an error message (it can be arbitrary Rust/ACL text). */
const MAX_DETAIL = 200;

/** `window.__TAURI_INTERNALS__.invoke` when it is a function, else null (plain browser, or Node). */
function findInvoke(scope: unknown): Invoke | null {
  const w = (scope as { window?: { __TAURI_INTERNALS__?: { invoke?: unknown } } } | undefined)?.window;
  const invoke = w?.__TAURI_INTERNALS__?.invoke;
  return typeof invoke === 'function' ? (invoke as Invoke).bind(w?.__TAURI_INTERNALS__) : null;
}

/** One line, bounded, for the UI; `undefined`/empty falls back to a generic Chinese text. */
function detailOf(reason: unknown): string {
  let text = '';
  if (typeof reason === 'string') text = reason;
  else if (reason instanceof Error) text = reason.message;
  else if (reason !== null && typeof reason === 'object' && typeof (reason as { message?: unknown }).message === 'string') {
    text = (reason as { message: string }).message;
  }
  text = text.replace(/\s+/g, ' ').trim();
  return text.length > MAX_DETAIL ? `${text.slice(0, MAX_DETAIL)}…` : text;
}

/** A schema-version-1 error envelope, as `core/api.py` and the Rust host produce them. */
export function unavailableEnvelope(id: string, reason?: unknown): ResponseEnvelope {
  const detail = detailOf(reason);
  return {
    schema_version: 1,
    id,
    ok: false,
    error: { code: 'MODEL_UNAVAILABLE', message: detail ? t('be.desktop.detail', { detail }) : t('be.desktop') },
  };
}

/**
 * A Transport over the Tauri `brain_call` command, or null when this page is
 * not running inside the Tauri webview (no `window.__TAURI_INTERNALS__.invoke`).
 * `scope` is for tests (defaults to `globalThis`). Calling it has no side effect.
 */
export function createTauriTransport(scope: unknown = globalThis): Transport | null {
  const invoke = findInvoke(scope);
  if (!invoke) return null;
  return {
    async request(envelope: RequestEnvelope): Promise<ResponseEnvelope> {
      try {
        // Exactly one attempt: no retry, not even for a read.
        return (await invoke(BRAIN_COMMAND, { request: envelope })) as ResponseEnvelope;
      } catch (reason) {
        return unavailableEnvelope(envelope.id, reason);
      }
    },
  };
}

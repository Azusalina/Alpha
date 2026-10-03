/**
 * Which back end the UI talks to (D56). A tiny external store: React reads it
 * with `useBackend()`, plain code with `getAdapter()`.
 *
 *  - `unconnected` (the default of every build): `UnavailableAdapter`, the UI
 *    shows "后端未连接" and a button that calls `enterDemo()`. There is
 *    deliberately no URL flag or storage key that enters demo mode.
 *  - `demo`: a fresh `MockBrainAdapter`, in memory only. `leaveDemo()` drops it
 *    and every input it held. Entering demo mode again starts empty.
 *  - `remote`: a `RemoteBrainAdapter` over a Transport. `connectDesktopBackend()`
 *    is the glue: inside the Tauri webview it probes `health` through
 *    `brain_call` and connects with the probed options; in a browser, or on any
 *    failure, it changes nothing except `lastConnectError`, which the banner can
 *    show. NOTHING calls it at import time: the UI (a "连接本机后端" button, or the
 *    app shell on start) decides when. UNVERIFIED on the native WebKitGTK build.
 *
 * The snapshot is immutable and replaced on every change, so
 * `useSyncExternalStore` re-renders exactly when the adapter changed;
 * `generation` lets a view drop what it fetched from the previous adapter.
 */

import { useSyncExternalStore } from 'react';
import { MockBrainAdapter } from './mock';
import type { MockOptions } from './mock';
import { RemoteBrainAdapter } from './remote';
import type { RemoteOptions, Transport } from './remote';
import { createTauriTransport } from './tauriTransport';
import { UnavailableAdapter } from './unavailable';
import { BackendError } from './types';
import type { BrainAdapter } from './types';
import { t } from '../i18n/lang';

export type BackendMode = 'unconnected' | 'demo' | 'remote';

export interface BackendSnapshot {
  readonly mode: BackendMode;
  readonly adapter: BrainAdapter;
  /** Increases with every change of adapter (including a fresh demo). */
  readonly generation: number;
  /**
   * Why the last `connectDesktopBackend()` did not connect (Chinese, one line),
   * or null. Cleared by any change of adapter. A failed connect does NOT change
   * `generation`: nothing the view holds became stale.
   */
  readonly lastConnectError: string | null;
}

type Listener = () => void;

class BackendStore {
  private snapshot: BackendSnapshot = {
    mode: 'unconnected',
    adapter: new UnavailableAdapter(),
    generation: 0,
    lastConnectError: null,
  };
  private listeners = new Set<Listener>();

  get mode(): BackendMode {
    return this.snapshot.mode;
  }

  get = (): BackendSnapshot => this.snapshot;

  subscribe = (l: Listener): (() => void) => {
    this.listeners.add(l);
    return () => this.listeners.delete(l);
  };

  private swap(mode: BackendMode, adapter: BrainAdapter): void {
    this.snapshot = { mode, adapter, generation: this.snapshot.generation + 1, lastConnectError: null };
    for (const l of this.listeners) l();
  }

  private setConnectError(message: string): void {
    this.snapshot = { ...this.snapshot, lastConnectError: message };
    for (const l of this.listeners) l();
  }

  /** Start demo mode with a FRESH mock; whatever a previous demo held is gone. */
  enterDemo = (options?: MockOptions): void => this.swap('demo', new MockBrainAdapter(options));

  /** Drop the mock and all its data; back to "后端未连接". No effect outside demo mode. */
  leaveDemo = (): void => {
    if (this.snapshot.mode === 'demo') this.swap('unconnected', new UnavailableAdapter());
  };

  /** Use the real back end behind `transport` (tests, or the glue below). Drops any demo data. */
  connectRemote = (transport: Transport, options?: RemoteOptions): void =>
    this.swap('remote', new RemoteBrainAdapter(transport, options));

  /**
   * Connect to the local Python back end through the Tauri `brain_call` command:
   * probe `health` (two judgements, methods), then `connectRemote` with the probed
   * options. Resolves true when connected. Resolves false, leaving the mode and
   * adapter untouched and explaining in `lastConnectError`, when this is not the
   * desktop app, the back end is unreachable, or something else changed the
   * adapter while the probe was running. Never rejects, never retries, never
   * falls back to the mock. UNVERIFIED on the native WebKitGTK build.
   */
  connectDesktopBackend = async (): Promise<boolean> => {
    const transport = createTauriTransport();
    if (!transport) {
      this.setConnectError(t('be.notDesktop'));
      return false;
    }
    const generation = this.snapshot.generation;
    try {
      const probe = await RemoteBrainAdapter.probe(transport);
      // The user entered demo mode (or another connect won) meanwhile: do not override that choice.
      if (this.snapshot.generation !== generation) return false;
      this.connectRemote(transport, probe.options);
      return true;
    } catch (e) {
      if (this.snapshot.generation === generation) {
        this.setConnectError(e instanceof BackendError && e.message ? e.message : t('be.cannotConnect'));
      }
      return false;
    }
  };

  /** The transport went away: back to "后端未连接". */
  disconnectRemote = (): void => {
    if (this.snapshot.mode === 'remote') this.swap('unconnected', new UnavailableAdapter());
  };
}

export const backendStore = new BackendStore();

/** The adapter in use right now. Do not keep it across a mode change; read it again. */
export function getAdapter(): BrainAdapter {
  return backendStore.get().adapter;
}

/** React hook: the current snapshot; the component re-renders when the adapter is replaced. */
export function useBackend(): BackendSnapshot {
  return useSyncExternalStore(backendStore.subscribe, backendStore.get, backendStore.get);
}

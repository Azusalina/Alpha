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
 * Access (F13). A real back end can be password-protected. The snapshot's `access`
 * is `none` (no gate, demo, unconnected), `open` (gate configured and unlocked) or
 * `locked`. Locking, a `LOCKED` answer to any private call, and every unlock attempt
 * install a FRESH adapter (a new `generation`), so every view drops the private text,
 * excerpts, previews, effects and model state it held and every response still on
 * its way is discarded; nothing is retried and the password is never kept.
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
import type { AccessStatus, BrainAdapter } from './types';
import { t } from '../i18n/lang';

export type BackendMode = 'unconnected' | 'demo' | 'remote';

/** `none`: no password gate (or no real back end). `open`: configured and unlocked. `locked`: private methods fail LOCKED. */
export type AccessState = 'none' | 'open' | 'locked';

export function accessStateOf(status: AccessStatus | null): AccessState {
  if (status === null || !status.configured) return 'none';
  return status.locked ? 'locked' : 'open';
}

export interface BackendSnapshot {
  readonly mode: BackendMode;
  readonly adapter: BrainAdapter;
  /** Password-gate state of a remote back end (F13); `none` in every other mode. */
  readonly access: AccessState;
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
    access: 'none',
    generation: 0,
    lastConnectError: null,
  };
  private listeners = new Set<Listener>();
  /** What the current remote adapter was built from, so a lock/unlock can build a fresh one. */
  private remote: { transport: Transport; options: RemoteOptions | undefined } | null = null;

  get mode(): BackendMode {
    return this.snapshot.mode;
  }

  get = (): BackendSnapshot => this.snapshot;

  subscribe = (l: Listener): (() => void) => {
    this.listeners.add(l);
    return () => this.listeners.delete(l);
  };

  private swap(mode: BackendMode, adapter: BrainAdapter, access: AccessState = 'none'): void {
    if (mode !== 'remote') this.remote = null;
    this.snapshot = { mode, adapter, access, generation: this.snapshot.generation + 1, lastConnectError: null };
    for (const l of this.listeners) l();
  }

  /** A fresh remote adapter over the remembered transport; its `LOCKED` answers lock the store, only while it is current. */
  private swapRemote(transport: Transport, options: RemoteOptions | undefined, access: AccessState): void {
    const adapter: RemoteBrainAdapter = new RemoteBrainAdapter(transport, {
      ...options,
      onLocked: () => {
        if (this.snapshot.adapter === adapter) this.markLocked();
      },
    });
    this.swap('remote', adapter, access);
    this.remote = { transport, options };
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
  connectRemote = (transport: Transport, options?: RemoteOptions, access: AccessState = 'none'): void =>
    this.swapRemote(transport, options, access);

  /**
   * Treat the remote back end as locked: a fresh adapter, a new generation, so every private cache and
   * every in-flight response of the old one is dropped. No effect outside remote mode or when already locked.
   */
  markLocked = (): void => {
    if (this.snapshot.mode !== 'remote' || this.snapshot.access === 'locked' || !this.remote) return;
    this.swapRemote(this.remote.transport, this.remote.options, 'locked');
  };

  /**
   * Send the password once (F13). Resolves with the new access state; a wrong password
   * rejects with `LOCKED`, any other failure with its own code. Whatever the outcome, the earlier
   * session is revoked by the back end, so the views are reset first. The password is a parameter only.
   * One attempt, never retried.
   */
  unlockBackend = async (password: string): Promise<AccessState> => {
    if (this.snapshot.mode !== 'remote' || !this.remote) {
      throw new BackendError('UNSUPPORTED', t('be.unsupported'));
    }
    const { transport, options } = this.remote;
    const previous = this.snapshot.adapter;
    // The attempt itself revokes access: show the locked state at once and drop what was held.
    this.swapRemote(transport, options, 'locked');
    const attempt = this.snapshot.adapter;
    let status: AccessStatus;
    try {
      status = await attempt.unlock(password);
    } catch (e) {
      // A wrong password and a failed attempt both leave the back end locked.
      if (previous !== attempt && this.snapshot.adapter === attempt && this.snapshot.access !== 'locked') this.markLocked();
      throw e;
    }
    if (this.snapshot.adapter !== attempt) return this.snapshot.access;
    const state = accessStateOf(status);
    // Open: a fresh adapter again so nothing read while it was locked (health without an epoch) is reused.
    this.swapRemote(transport, options, state);
    return state;
  };

  /** Lock now (F13): ask the back end, then drop every private cache. The store is locked even if the request failed. */
  lockBackend = async (): Promise<void> => {
    if (this.snapshot.mode !== 'remote' || !this.remote) return;
    const adapter = this.snapshot.adapter;
    this.markLocked();
    try {
      await adapter.lock();
    } catch {
      // The store is already locked; a back end that could not be told stays unlocked until its own timeout or the next unlock.
    }
  };

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
      this.connectRemote(transport, probe.options, accessStateOf(probe.access));
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

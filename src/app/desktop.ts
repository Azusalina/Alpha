/**
 * Connecting to the local back end when the app runs inside the Tauri shell
 * (round 3 part 9, D56). In a plain browser nothing is ever connected: the
 * product default stays "后端未连接" and demo mode is entered by hand.
 *
 * UNVERIFIED on the native WebKitGTK build: `connectDesktopBackend` (and the
 * transport it uses) is covered only by a fake `window.__TAURI_INTERNALS__` in
 * Node and by the Rust host's own tests. Nothing here has run against the real
 * window yet.
 */

import { backendStore } from '../backend';

/** Is there a Tauri host to talk to? (The transport itself stays inside src/backend.) */
export function hasDesktopHost(): boolean {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
}

let started = false;

/**
 * Called once when the app starts: connect to the desktop back end, only when
 * there is a Tauri host. A failure leaves the mode alone and sets
 * `lastConnectError`, which the banner shows with a retry button. Never throws.
 */
export function connectDesktopOnStart(): void {
  if (started) return;
  started = true;
  if (!hasDesktopHost()) return;
  void backendStore.connectDesktopBackend();
}

/**
 * The only door from the UI to the model (D56). UI code imports from
 * `src/backend`, never a transport and never a concrete adapter.
 *
 * Node-side tests import the pure modules (`spans`, `text`, `mock`, `remote`,
 * `tauriTransport`, `unavailable`) directly instead of this file. `createTauriTransport` is
 * deliberately not exported here: the UI calls `backendStore.connectDesktopBackend()`, never a transport.
 */

export * from './types';
export * from './spans';
export * from './text';
export { backendStore, getAdapter, useBackend } from './store';
export type { BackendMode, BackendSnapshot } from './store';
export { MockBrainAdapter, MOCK_LABEL } from './mock';
export type { MockOptions } from './mock';
export { RemoteBrainAdapter } from './remote';
export type { HealthReport, ProbeResult, RemoteOptions, RequestEnvelope, ResponseEnvelope, Transport } from './remote';
export { UnavailableAdapter, UNAVAILABLE_LABEL } from './unavailable';

/**
 * The model-state view's data (round 3 part 9, D55): `state()` and the effect
 * log of the ADAPTER, re-read whenever the list of inputs changed, never
 * computed from guesses. The hook lives in RecordsPanel (above both tabs), so a
 * training done on the list tab is already noticed when the user opens the
 * state tab.
 *
 * When is it re-read? The store patches a record from the back end after every
 * judgement, edit, delete and submit, so a signature of the loaded records
 * (id, status, judgements, reviewed / edited stamps) changes exactly when the
 * model may have changed. A no-op repeated judgement changes nothing, so
 * nothing is fetched.
 *
 * "Just changed": the parameters whose value or support differ between the
 * previous read and this one (per partition). Only a non-empty difference
 * replaces the highlight, so a pending submit (no change) does not wipe the
 * mark of the last training. The first read of a back end highlights nothing.
 *
 * "Latest revision": the highest revision among the effect log's entries for a
 * parameter of a partition, reversals included. The log is read whole
 * (`effects()` without an id); a very long log would want a server-side
 * "latest per parameter" call: noted for [back], not needed at today's sizes.
 *
 * Race safety: a read carries a counter; only the newest may write, and a read
 * that outlives a back-end change is dropped (generation check).
 */

import { useEffect, useRef, useState } from 'react';

import { PARAMETER_IDS, PARTITIONS, backendStore, getAdapter, useBackend } from '../../backend';
import type { BackendErrorCode, ModelState, Partition } from '../../backend';
import { BackendError } from '../../backend';
import { useInputs } from '../../app/inputStore';

export interface ModelView {
  state: ModelState | null;
  /** `${partition}|${parameter}` -> latest revision that touched it. */
  revisions: Record<string, number>;
  /** `${partition}|${parameter}` of the parameters that changed in the last change. */
  changed: ReadonlySet<string>;
  loading: boolean;
  error: { code: BackendErrorCode; message: string } | null;
  /** Re-read now (the retry button). */
  reload: () => void;
}

export const paramKey = (p: Partition, id: string): string => `${p}|${id}`;

function diff(prev: ModelState, next: ModelState): Set<string> {
  const out = new Set<string>();
  for (const p of PARTITIONS) {
    for (const id of PARAMETER_IDS) {
      const a = prev[p][id];
      const b = next[p][id];
      if (a.observed !== b.observed || a.value !== b.value || a.support !== b.support) out.add(paramKey(p, id));
    }
  }
  return out;
}

export function useModelState(): ModelView {
  const backend = useBackend();
  const inputs = useInputs();
  const [view, setView] = useState<Omit<ModelView, 'reload'>>({
    state: null,
    revisions: {},
    changed: new Set(),
    loading: false,
    error: null,
  });
  const seq = useRef(0);
  const prev = useRef<{ generation: number; state: ModelState } | null>(null);
  const [nonce, setNonce] = useState(0);

  const signature = inputs.records
    .map((r) => `${r.source_id}|${r.status}|${r.immediate}|${r.confirm}|${r.reviewed_at ?? ''}|${r.edited_at ?? ''}`)
    .join('\n');
  const connected = backend.mode !== 'unconnected';

  // a different back end: nothing shown belongs to it any more
  useEffect(() => {
    seq.current++;
    prev.current = null;
    setView({ state: null, revisions: {}, changed: new Set(), loading: false, error: null });
  }, [backend.generation]);

  useEffect(() => {
    if (!connected) return;
    const mine = ++seq.current;
    const generation = backendStore.get().generation;
    setView((v) => ({ ...v, loading: true }));
    (async () => {
      try {
        const adapter = getAdapter();
        const [state, log] = await Promise.all([adapter.state(), adapter.effects()]);
        if (mine !== seq.current || backendStore.get().generation !== generation) return;
        const revisions: Record<string, number> = {};
        for (const e of log) {
          if (e.revision === undefined) continue;
          const k = paramKey(e.partition, e.parameter);
          if (revisions[k] === undefined || e.revision > revisions[k]) revisions[k] = e.revision;
        }
        const before = prev.current && prev.current.generation === generation ? prev.current.state : null;
        const moved = before ? diff(before, state) : new Set<string>();
        prev.current = { generation, state };
        setView((v) => ({
          state,
          revisions,
          changed: moved.size > 0 ? moved : before ? v.changed : new Set(),
          loading: false,
          error: null,
        }));
      } catch (e) {
        if (mine !== seq.current || backendStore.get().generation !== generation) return;
        const err = e instanceof BackendError ? { code: e.code, message: e.message } : { code: 'INTERNAL_ERROR' as const, message: e instanceof Error ? e.message : String(e) };
        setView((v) => ({ ...v, loading: false, error: err }));
      }
    })();
  }, [signature, connected, backend.generation, nonce]);

  return { ...view, reload: () => setNonce((n) => n + 1) };
}

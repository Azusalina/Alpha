/**
 * The record graph the brain and the tree draw (D65): the main node, the three
 * states and, once the model holds them, the parameters and the inputs that
 * trained it. A tiny external store; the snapshot is immutable and replaced on
 * every change, so `useGraph()` re-renders exactly when the graph changed.
 *
 * `startGraphSync()` (called once by the app shell) keeps it current: it reads
 * the adapter's `state`, `effects` and every agreed input whenever the back end
 * changes (a new generation), the input list changes (a judgement, an edit, a
 * delete, a submit) or the model epoch moves. Reads are coalesced and a stale
 * read never overwrites a newer one. With no back end connected the graph is the
 * skeleton, so an unused install shows the main node and the three states only.
 */

import { useSyncExternalStore } from 'react';

import { backendStore, getAdapter } from '../backend';
import type { InputRecord } from '../backend';
import { BackendError } from '../backend/types';
import type { GraphData } from '../fixtures/graph';
import { inputStore } from '../app/inputStore';
import { baseGraph, buildGraph, isInModel, withExamples } from './build';
import { langStore, t } from '../i18n/lang';

const exampleBase = (): GraphData => withExamples(baseGraph());

type Listener = () => void;

class GraphStore {
  private graph: GraphData = exampleBase();
  private listeners = new Set<Listener>();
  /** Increases with every new graph. */
  version = 0;

  get = (): GraphData => this.graph;

  subscribe = (l: Listener): (() => void) => {
    this.listeners.add(l);
    return () => this.listeners.delete(l);
  };

  set(next: GraphData): void {
    this.graph = next;
    this.version++;
    for (const l of this.listeners) l();
  }
}

export const graphStore = new GraphStore();

/** The graph as it is now (plain code; React uses `useGraph`). */
export const getGraph = (): GraphData => graphStore.get();

export function useGraph(): GraphData {
  return useSyncExternalStore(graphStore.subscribe, graphStore.get, graphStore.get);
}

/** Every agreed input, page by page. A stale cursor restarts the read once. */
async function allAgreed(): Promise<InputRecord[]> {
  const adapter = getAdapter();
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const out: InputRecord[] = [];
      let cursor: string | null = null;
      do {
        const page = await adapter.inputPage({ status: 'agreed', limit: 100, cursor });
        out.push(...page.items);
        cursor = page.next_cursor;
      } while (cursor !== null);
      return out;
    } catch (e) {
      if (!(e instanceof BackendError && e.code === 'STALE_CURSOR')) throw e;
    }
  }
  throw new BackendError('STALE_CURSOR', t('be.listChurn'));
}

let seq = 0;

/** Read the model and rebuild the graph. Resolves when done; a failed read leaves the last graph as it was. */
export async function refreshGraph(): Promise<void> {
  const mine = ++seq;
  const generation = backendStore.get().generation;
  if (backendStore.get().mode === 'unconnected') {
    graphStore.set(exampleBase());
    return;
  }
  try {
    const adapter = getAdapter();
    const [state, effects, inputs] = await Promise.all([adapter.state(), adapter.effects(), allAgreed()]);
    if (mine !== seq || generation !== backendStore.get().generation) return;
    const built = buildGraph(inputs, state, effects);
    // example branches only while the model holds no input and the back end is not a real one
    const real = backendStore.get().mode === 'remote';
    graphStore.set(!real && !built.nodes.some((n) => n.kind === 'input') ? withExamples(built) : built);
  } catch {
    // the tree keeps showing the last graph; the records panel reports the error itself
  }
}

let started = false;

/** Keep the graph current. Idempotent; returns a stop function (tests). */
export function startGraphSync(): () => void {
  if (started) return () => undefined;
  started = true;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let lastKey = '';
  const schedule = () => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      timer = null;
      void refreshGraph();
    }, 120);
  };
  const key = (): string => {
    const s = inputStore.get();
    const rows = s.records.map((r) => `${r.source_id}|${isInModel(r)}|${r.partition}|${r.reviewed_at ?? ''}|${r.edited_at ?? ''}`).join('\n');
    // the language is part of the key: node labels are read from the dictionaries when the graph is built
    return `${langStore.get()}#${backendStore.get().generation}#${s.modelEpoch ?? ''}#${rows}`;
  };
  const check = () => {
    const k = key();
    if (k === lastKey) return;
    lastKey = k;
    schedule();
  };
  const offBackend = backendStore.subscribe(check);
  const offInputs = inputStore.subscribe(check);
  const offLang = langStore.subscribe(check);
  check();
  void refreshGraph();
  return () => {
    started = false;
    if (timer) clearTimeout(timer);
    offBackend();
    offInputs();
    offLang();
  };
}

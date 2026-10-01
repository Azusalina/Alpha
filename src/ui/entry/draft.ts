/**
 * The unsent entry form (D54), kept in MEMORY only.
 *
 * Why a store and not component state: the entry panel unmounts whenever the
 * brain is drilled into (and when the destination is left), and the prototype's
 * input box lost whatever was typed. A draft is the user's own text; it never
 * goes to localStorage or anywhere else (data stays local), so it lives exactly
 * as long as the page. Reloading clears it, like demo data.
 *
 * `immediate` is kept apart from `exclamation` on purpose: ticking the
 * exclamation shows the immediate box as checked and locked, and unticking it
 * must give back what the user had chosen before (see `shownImmediate`).
 */

import { useSyncExternalStore } from 'react';

import type { Kind, Partition } from '../../backend';

export interface EntryDraft {
  /** null until the user chooses: the state is never guessed for them. */
  partition: Partition | null;
  kind: Kind;
  self_speaker: string;
  text: string;
  /** The raw choice of the box "是否为真（当下）"; default false, so nothing trains unless asserted. */
  immediate: boolean;
  /** The box "断言为真". */
  exclamation: boolean;
  /** Display name of the chosen file while the text is still exactly its content. */
  source_ref: string | null;
  /** Code points of that file, for the line under the text. */
  file_chars: number | null;
}

export const EMPTY_DRAFT: EntryDraft = {
  partition: null,
  kind: 'diary',
  self_speaker: '',
  text: '',
  immediate: false,
  exclamation: false,
  source_ref: null,
  file_chars: null,
};

type Listener = () => void;

let draft: EntryDraft = EMPTY_DRAFT;
const listeners = new Set<Listener>();

export const draftStore = {
  get: (): EntryDraft => draft,
  subscribe: (l: Listener): (() => void) => {
    listeners.add(l);
    return () => listeners.delete(l);
  },
  set(patch: Partial<EntryDraft>): void {
    draft = { ...draft, ...patch };
    for (const l of listeners) l();
  },
  /** After a successful write: the text and the judgements go, the user's choice of state, kind and speaker stay. */
  clearContent(): void {
    draftStore.set({ text: '', immediate: false, exclamation: false, source_ref: null, file_chars: null });
  },
};

export function useDraft(): EntryDraft {
  return useSyncExternalStore(draftStore.subscribe, draftStore.get, draftStore.get);
}

/** What the box "是否为真（当下）" shows: an exclamation makes it checked (the back end sets both judgements true). */
export const shownImmediate = (d: Pick<EntryDraft, 'immediate' | 'exclamation'>): boolean =>
  d.exclamation || d.immediate;

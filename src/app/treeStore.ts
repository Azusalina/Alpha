/**
 * UI state of the system destination (the technology tree). Discrete fields
 * for React; the scene reads them each frame.
 */

import { useSyncExternalStore } from 'react';

export interface TreeUi {
  selected: string | null;
  hovered: string | null;
}

class TreeStore {
  private ui: TreeUi = { selected: null, hovered: null };
  private listeners = new Set<() => void>();

  get = (): TreeUi => this.ui;

  set(patch: Partial<TreeUi>): void {
    const next = { ...this.ui, ...patch };
    if (next.selected === this.ui.selected && next.hovered === this.ui.hovered) return;
    this.ui = next;
    for (const l of this.listeners) l();
  }

  subscribe = (l: () => void): (() => void) => {
    this.listeners.add(l);
    return () => this.listeners.delete(l);
  };

  reset(): void {
    this.set({ selected: null, hovered: null });
  }
}

export const treeStore = new TreeStore();

export function useTreeUi(): TreeUi {
  return useSyncExternalStore(treeStore.subscribe, treeStore.get);
}

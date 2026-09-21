import { useEffect, useState } from 'react';

import { stage, type ViewMode } from '../app/stage';

/** The current view mode (docs/CONTRACTS.md §9). Changes are rare, so React state is fine. */
export function useViewMode(): ViewMode {
  const [mode, setMode] = useState<ViewMode>(stage.viewMode);
  useEffect(() => stage.subscribeViewMode(setMode), []);
  return mode;
}

/**
 * The record graph shared by the particle brain and the technology tree (spec 4:
 * one structure, two ways of looking at it; decisions D36, D65).
 *
 * Only the types live here. The graph itself is built from what the model really
 * holds (`src/graph/build.ts`, kept current by `src/graph/graphStore.ts`): a main
 * node, the three states, the parameters that have evidence, and the inputs that
 * trained them. A fresh install therefore shows the main node and the three
 * states only; nothing is a placeholder.
 */

import type { ParameterId, Partition } from '../backend/types';

export type GraphNodeKind = 'root' | 'partition' | 'parameter' | 'input';

export interface GraphNode {
  /** Stable: `root`, `p:<partition>`, `m:<partition>:<parameter>`, `i:<source_id>`. */
  id: string;
  label: string;
  /** Tree depth: 0 is the main node. */
  depth: number;
  parent: string | null;
  /** Index into the brain asset's `regions` (placeholder grouping: one region per state). */
  region: number;
  kind: GraphNodeKind;
  partition?: Partition;
  parameter?: ParameterId;
  /** `input` nodes: the source it stands for. */
  sourceId?: string;
  /** `input` nodes: the change it made to its parameter (its largest effect). */
  delta?: number;
  /**
   * Set when the node forks off the LINE from its parent to the node `forkOn`
   * (that line is then a trunk), instead of growing from a node's end.
   */
  forkOn?: string;
  /** An example branch (D66), not something the model holds. */
  example?: true;
}

export interface GraphEdge {
  from: string;
  to: string;
  /** `tree` edges form the hierarchy. (`link` is kept for the brain's shaders; nothing produces it.) */
  kind: 'tree' | 'link';
  /** A line fork: the edge starts at the middle of the line `from` → `onLine` rather than at `from`. */
  onLine?: string;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

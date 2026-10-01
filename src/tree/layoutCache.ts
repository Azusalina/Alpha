/** The layout of the current graph, computed once per graph snapshot. */

import type { GraphData } from '../fixtures/graph';
import { layoutTree, type TreeLayout } from './layout';

let cachedFor: GraphData | null = null;
let cached: TreeLayout | null = null;

export function treeLayout(graph: GraphData): TreeLayout {
  if (cachedFor !== graph || !cached) {
    cached = layoutTree(graph);
    cachedFor = graph;
  }
  return cached;
}

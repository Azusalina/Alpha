/**
 * Placeholder GraphData shared by the particle brain and (next) the technology
 * tree (spec 4: one structure, two ways of looking at it; decision D36).
 *
 * Labels are neutral numbered records and regions are the reference brain
 * model's region names, marked as placeholders: the real classification of the
 * user's data is not defined yet (IDEA §6). Ids are stable — the brain and the
 * tree must agree on them.
 */

export interface GraphNode {
  id: string;
  label: string;
  /** Tree depth: 0 is the root. */
  depth: number;
  parent: string | null;
  /** Index into the brain asset's `regions` (placeholder grouping). */
  region: number;
}

export interface GraphEdge {
  from: string;
  to: string;
  /** `tree` edges form the hierarchy; `link` edges are cross-associations. */
  kind: 'tree' | 'link';
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

/** Cortex regions of the brain asset that hold records (0–4; see brain.json). */
const RECORD_REGIONS = [0, 1, 2, 3, 4];

function build(): GraphData {
  const nodes: GraphNode[] = [{ id: 'n00', label: '示例根节点', depth: 0, parent: null, region: 0 }];
  // Five branches, one per placeholder region; each has 2–3 children, some with a leaf.
  const shape = [3, 2, 3, 2, 3];
  let k = 1;
  const id = () => `n${String(k).padStart(2, '0')}`;
  shape.forEach((children, b) => {
    const region = RECORD_REGIONS[b];
    const branch = id();
    nodes.push({ id: branch, label: `示例记录 ${String(k).padStart(2, '0')}`, depth: 1, parent: 'n00', region });
    k++;
    for (let c = 0; c < children; c++) {
      const child = id();
      nodes.push({ id: child, label: `示例记录 ${String(k).padStart(2, '0')}`, depth: 2, parent: branch, region });
      k++;
      if ((b + c) % 2 === 0) {
        nodes.push({ id: id(), label: `示例记录 ${String(k).padStart(2, '0')}`, depth: 3, parent: child, region });
        k++;
      }
    }
  });
  const edges: GraphEdge[] = nodes
    .filter((n) => n.parent)
    .map((n) => ({ from: n.parent as string, to: n.id, kind: 'tree' as const }));
  // a few cross-associations between branches
  for (const [a, b] of [
    ['n03', 'n09'],
    ['n07', 'n15'],
    ['n12', 'n20'],
    ['n18', 'n05'],
  ]) {
    if (nodes.some((n) => n.id === a) && nodes.some((n) => n.id === b)) edges.push({ from: a, to: b, kind: 'link' });
  }
  return { nodes, edges };
}

export const GRAPH: GraphData = build();

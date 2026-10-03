/**
 * Builds the record graph from what the back end holds (D65). Pure and
 * deterministic: the same inputs give the same graph, in the same order.
 *
 *   main node
 *   ├─ 理性 / 感性 / 癫狂          (always present, one per state)
 *   │   └─ a parameter             (only with evidence in that state: `observed`)
 *   │       └─ the inputs that trained it (agreed, both judgements true, in the
 *   │          current model), oldest first
 *
 * An input stands under the parameter it moved most (its largest approved
 * effect); one that moved none (vocabulary only) stands directly under its
 * state. Inputs that raised/lowered a parameter in the same direction as the
 * one before extend the branch; one that pulled the other way forks off the
 * LINE leading to the previous input (`forkOn`), which makes that line a trunk.
 */

import { PARAMETER_IDS, PARTITIONS } from '../backend/types';
import type { InputRecord, ModelState, ParameterEffect, ParameterId, Partition } from '../backend/types';
import type { GraphData, GraphEdge, GraphNode } from '../fixtures/graph';
import { parameterLabel, PARTITION_LABELS } from '../ui/shared/labels';
import { t } from '../i18n/lang';

export const ROOT_ID = 'root';

/** Placeholder brain region per state (0–2 of the cortex regions). */
const REGION: Record<Partition, number> = { rational: 0, emotional: 1, crazy: 2 };
const EXCERPT_NODE_CHARS = 14;

export const partitionNodeId = (p: Partition): string => `p:${p}`;
export const parameterNodeId = (p: Partition, id: ParameterId): string => `m:${p}:${id}`;
export const inputNodeId = (sourceId: string): string => `i:${sourceId}`;

/** The skeleton: the main node and the three states. What an install shows before any training. */
export function baseGraph(): GraphData {
  const nodes: GraphNode[] = [{ id: ROOT_ID, label: t('node.kind.root'), depth: 0, parent: null, region: 0, kind: 'root' }];
  const edges: GraphEdge[] = [];
  for (const p of PARTITIONS) {
    nodes.push({ id: partitionNodeId(p), label: PARTITION_LABELS[p], depth: 1, parent: ROOT_ID, region: REGION[p], kind: 'partition', partition: p });
    edges.push({ from: ROOT_ID, to: partitionNodeId(p), kind: 'tree' });
  }
  return { nodes, edges };
}

/** Does this record take part in the current model (agreed, both judgements true, not left behind by a reset)? */
export function isInModel(r: Pick<InputRecord, 'status' | 'immediate' | 'confirm' | 'model_active'>): boolean {
  return r.status === 'agreed' && r.immediate && r.confirm === true && r.model_active !== false;
}

function oneLine(text: string): string {
  const flat = text.replace(/[\u0000-\u001f\u007f\u0085\s]+/gu, ' ').trim();
  const chars = Array.from(flat);
  return chars.length > EXCERPT_NODE_CHARS ? `${chars.slice(0, EXCERPT_NODE_CHARS).join('')}…` : flat || t('rec.empty');
}

/** The effect an input is placed by: its largest approved change; the later revision wins a tie. */
function primaryEffect(effects: readonly ParameterEffect[]): ParameterEffect | null {
  let best: ParameterEffect | null = null;
  for (const e of effects) {
    if (e.action !== 'approve') continue;
    if (!best || Math.abs(e.delta) > Math.abs(best.delta) || (Math.abs(e.delta) === Math.abs(best.delta) && (e.revision ?? 0) > (best.revision ?? 0))) best = e;
  }
  return best;
}

/**
 * Example branches (D66), shown only while no back end holds real inputs (an unused
 * install, or the demo): they let the tree show what it will look like. Labelled
 * 示例, never sent anywhere, never mixed with real inputs.
 */

export function withExamples(graph: GraphData): GraphData {
  const nodes = [...graph.nodes];
  const edges = [...graph.edges];
  const addParam = (p: Partition, id: ParameterId) => {
    const nid = parameterNodeId(p, id);
    nodes.push({ id: nid, label: parameterLabel(id), depth: 2, parent: partitionNodeId(p), region: REGION[p], kind: 'parameter', partition: p, parameter: id, example: true });
    edges.push({ from: partitionNodeId(p), to: nid, kind: 'tree' });
    return nid;
  };
  let k = 0;
  const addInput = (p: Partition, parent: string, label: string, delta: number, forkOn?: string, forkParent?: string) => {
    const nid = `i:example-${++k}`;
    nodes.push({ id: nid, label: t('example.prefix') + label, depth: 3, parent: forkOn ? (forkParent as string) : parent, region: REGION[p], kind: 'input', partition: p, delta, example: true, ...(forkOn ? { forkOn } : {}) });
    edges.push(forkOn ? { from: forkParent as string, to: nid, kind: 'tree', onLine: forkOn } : { from: parent, to: nid, kind: 'tree' });
    return nid;
  };
  const trust = addParam('rational', 'value.truth');
  const t1 = addInput('rational', trust, t('example.1'), 0.2);
  const t2 = addInput('rational', t1, t('example.2'), 0.1);
  addInput('rational', trust, t('example.3'), -0.15, t2, t1);
  const fair = addParam('rational', 'value.fairness');
  addInput('rational', fair, t('example.4'), 0.2);
  const sad = addParam('emotional', 'affect.sadness');
  const s1 = addInput('emotional', sad, t('example.5'), 0.2);
  addInput('emotional', s1, t('example.6'), 0.1);
  const joy = addParam('emotional', 'affect.happiness');
  addInput('emotional', joy, t('example.7'), 0.2);
  const grow = addParam('crazy', 'value.growth');
  const g1 = addInput('crazy', grow, t('example.8'), 0.2);
  addInput('crazy', g1, t('example.9'), 0.1);
  const dep = new Map<string, number>(nodes.map((n) => [n.id, n.depth]));
  for (const n of nodes) {
    if (n.parent !== null) n.depth = (dep.get(n.parent) ?? 0) + 1;
    dep.set(n.id, n.depth);
  }
  return { nodes, edges };
}

export function buildGraph(inputs: readonly InputRecord[], state: ModelState | null, effects: readonly ParameterEffect[]): GraphData {
  const graph = baseGraph();
  const nodes = graph.nodes;
  const edges = graph.edges;
  const have = new Set(nodes.map((n) => n.id));

  // parameters with evidence
  if (state) {
    for (const p of PARTITIONS) {
      for (const id of PARAMETER_IDS) {
        if (!state[p]?.[id]?.observed) continue;
        const nid = parameterNodeId(p, id);
        nodes.push({ id: nid, label: parameterLabel(id), depth: 2, parent: partitionNodeId(p), region: REGION[p], kind: 'parameter', partition: p, parameter: id });
        edges.push({ from: partitionNodeId(p), to: nid, kind: 'tree' });
        have.add(nid);
      }
    }
  }

  const bySource = new Map<string, ParameterEffect[]>();
  for (const e of effects) bySource.set(e.source_id, [...(bySource.get(e.source_id) ?? []), e]);

  // inputs, oldest first (the effect's revision orders them; ties by id)
  const placed = inputs
    .filter(isInModel)
    .map((r) => ({ r, e: primaryEffect(bySource.get(r.source_id) ?? []) }))
    .sort((a, b) => (a.e?.revision ?? 0) - (b.e?.revision ?? 0) || a.r.created_at.localeCompare(b.r.created_at) || a.r.source_id.localeCompare(b.r.source_id));

  const last = new Map<string, GraphNode>(); // the newest input of each parameter / state
  for (const { r, e } of placed) {
    const anchor = e && have.has(parameterNodeId(r.partition, e.parameter)) ? parameterNodeId(r.partition, e.parameter) : partitionNodeId(r.partition);
    const prev = last.get(anchor);
    const node: GraphNode = {
      id: inputNodeId(r.source_id),
      label: oneLine(r.excerpt),
      depth: 0,
      parent: anchor,
      region: REGION[r.partition],
      kind: 'input',
      partition: r.partition,
      sourceId: r.source_id,
      ...(e ? { parameter: e.parameter, delta: e.delta } : {}),
    };
    let edge: GraphEdge;
    if (prev && prev.kind === 'input' && (prev.delta ?? 0) * (node.delta ?? 0) < 0) {
      // pulled the other way: a fork off the line that leads to the previous input
      node.parent = prev.parent;
      node.forkOn = prev.id;
      edge = { from: prev.parent as string, to: node.id, kind: 'tree', onLine: prev.id };
    } else if (prev && prev.kind === 'input') {
      // same direction: the branch is extended
      node.parent = prev.id;
      edge = { from: prev.id, to: node.id, kind: 'tree' };
    } else {
      edge = { from: anchor, to: node.id, kind: 'tree' };
    }
    last.set(anchor, node);
    nodes.push(node);
    edges.push(edge);
  }

  // depths follow the parents (a parent always comes before its children in `nodes`)
  const depth = new Map<string, number>(nodes.map((n) => [n.id, n.depth]));
  for (const n of nodes) {
    if (n.parent !== null) n.depth = (depth.get(n.parent) ?? 0) + 1;
    depth.set(n.id, n.depth);
  }
  return graph;
}

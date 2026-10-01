/**
 * Chinese labels for everything the entry and records panels show (round 3,
 * part 9, D54–D57). One place, so the two panels and the shared pieces never
 * disagree about a word.
 *
 * The parameter names are the plain-language reading of `parameters.md`; the
 * id is always shown next to a label (EffectsTable), so a label is never the
 * only way to tell two parameters apart.
 */

import { MOCK_RULE_PREFIX } from '../../backend';
import type { InputReason, InputStatus, Kind, ParameterEffect, ParameterId, Partition } from '../../backend';

export const PARAMETER_LABELS: Record<ParameterId, string> = {
  'value.autonomy': '自主',
  'value.fairness': '公平',
  'value.care': '关怀',
  'value.truth': '真实',
  'value.security': '安全',
  'value.growth': '成长',
  'value.achievement': '成就',
  'value.connection': '陪伴 / 联结',
  'affect.disappointment': '失望',
  'affect.sadness': '难过',
  'affect.happiness': '开心',
  'affect.anger': '生气',
  'expression.less_initiative': '更少主动联系',
};

/** A label for any id; an unknown id (a newer back end) shows itself, never nothing. */
export const parameterLabel = (id: string): string => (PARAMETER_LABELS as Record<string, string>)[id] ?? id;

export const PARTITION_LABELS: Record<Partition, string> = {
  rational: '理性',
  emotional: '感性',
  crazy: '癫狂',
};

/**
 * 癫狂 is the user's own name for a situational state (IDEA): it is not a
 * diagnosis and nothing here scores a person. Shown wherever the state is chosen.
 */
export const PARTITION_NOTE = '「癫狂」是你给某种处境下的自己起的名字，不是诊断，也不是对你的评价。';

export const PARTITION_HINTS: Record<Partition, string> = {
  rational: '冷静、有条理地想的时候',
  emotional: '情绪很满、被感受带着走的时候',
  crazy: '失控、极端、不像平时的自己的时候',
};

export const KIND_LABELS: Record<Kind, string> = {
  diary: '日记',
  chat: '聊天',
  philosophy: '哲学',
};

export const STATUS_LABELS: Record<InputStatus, string> = {
  pending: '待确认',
  agreed: '已认可',
  disagreed: '不同意',
  revoked: '已撤销',
};

export const REASON_LABELS: Record<InputReason, string> = {
  immediate_false: '当下判断为否',
  confirm_false: '二次确认为否',
  user_revoked: '已撤销',
};

/** One-line explanation of a status, for a tooltip or a small note. */
export const STATUS_HINTS: Record<InputStatus, string> = {
  pending: '录入时判断为真，还没有做二次确认；不参与训练',
  agreed: '两次判断都为真，正在参与训练',
  disagreed: '至少有一次判断为否；不参与训练，可以编辑或删除',
  revoked: '曾经认可、后来被撤销；历史保留，不参与训练',
};

/**
 * The same hints for demo mode (D56): the mock never trains anything, so no
 * word of a demo status may say the model is being trained.
 */
export const DEMO_STATUS_HINTS: Record<InputStatus, string> = {
  ...STATUS_HINTS,
  agreed: '演示：两次判断都为真，只是标记，没有运行模型',
  revoked: '演示：曾经标记为认可、后来被撤销；历史保留',
  pending: '录入时判断为真，还没有做二次确认；演示数据，不会训练',
  disagreed: '至少有一次判断为否；演示数据，可以编辑或删除',
};

/** The hint for a status, in the wording of the current backend mode. */
export const statusHint = (status: InputStatus, demo: boolean): string => (demo ? DEMO_STATUS_HINTS : STATUS_HINTS)[status];

export const CONFIRMED_BY_LABELS = {
  exclamation: '断言为真',
  manual: '手动确认',
  legacy: '旧数据',
} as const;

/** "不同意 · 当下判断为否" style text for a record. */
export function statusText(status: InputStatus, reason: InputReason | null): string {
  const base = STATUS_LABELS[status];
  return reason && (status === 'disagreed' || status === 'revoked') && REASON_LABELS[reason] !== base
    ? `${base} · ${REASON_LABELS[reason]}`
    : base;
}

export const ACTION_LABELS: Record<ParameterEffect['action'], string> = {
  preview: '预览',
  approve: '已应用',
  revoke: '已撤销',
};

/** The raw id always stays visible; a mock id is additionally tagged. */
export function ruleDisplay(ruleId: string): { id: string; isDemo: boolean; tag: string | null } {
  const isDemo = ruleId.startsWith(MOCK_RULE_PREFIX);
  return { id: ruleId, isDemo, tag: isDemo ? '演示' : null };
}

/**
 * Small accent marks per state (D57). Used ONLY as a dot or a thin rule, never
 * as a fill behind text. The values live in shared.css (`--alpha-state-*`, one
 * set per theme; they follow STATE_PALETTE in config/theme.ts for rational).
 */
export const partitionColor = (p: Partition): string => `var(--alpha-state-${p})`;

export const DEMO_TAG = '演示';
export const UNVERIFIED_NOTE = '未在原生构建上验证';

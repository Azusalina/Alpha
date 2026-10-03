/**
 * Labels for everything the entry and records panels show (round 3,
 * part 9, D54–D57). One place, so the two panels and the shared pieces never
 * disagree about a word.
 *
 * The parameter names are the plain-language reading of `parameters.md`; the
 * id is always shown next to a label (EffectsTable), so a label is never the
 * only way to tell two parameters apart.
 */

import { MOCK_RULE_PREFIX } from '../../backend';
import { KINDS, PARAMETER_IDS, PARTITIONS } from '../../backend';
import type { InputReason, InputStatus, Kind, ParameterEffect, ParameterId, Partition } from '../../backend';
import { lazyLabels, t } from '../../i18n/lang';

export const PARAMETER_LABELS: Record<ParameterId, string> = lazyLabels(PARAMETER_IDS, 'param.');

/** A label for any id; an unknown id (a newer back end) shows itself, never nothing. */
export const parameterLabel = (id: string): string => (PARAMETER_LABELS as Record<string, string>)[id] ?? id;

export const PARTITION_LABELS: Record<Partition, string> = lazyLabels(PARTITIONS, 'partition.');

/**
 * 癫狂 / "crazy" is the user's own name for a situational state (IDEA): it is not a
 * diagnosis and nothing here scores a person. Shown wherever the state is chosen.
 */
export const partitionNote = (): string => t('partition.note');

export const PARTITION_HINTS: Record<Partition, string> = lazyLabels(PARTITIONS, 'partition.hint.');

export const KIND_LABELS: Record<Kind, string> = lazyLabels(KINDS, 'kind.');

const STATUSES = ['pending', 'agreed', 'disagreed', 'revoked'] as const;
const REASONS = ['immediate_false', 'confirm_false', 'user_revoked'] as const;

export const STATUS_LABELS: Record<InputStatus, string> = lazyLabels(STATUSES, 'status.');

export const REASON_LABELS: Record<InputReason, string> = lazyLabels(REASONS, 'reason.');

/** One-line explanation of a status, for a tooltip or a small note. */
export const STATUS_HINTS: Record<InputStatus, string> = lazyLabels(STATUSES, 'status.hint.');

/**
 * The same hints for demo mode (D56): the mock never trains anything, so no
 * word of a demo status may say the model is being trained.
 */
export const DEMO_STATUS_HINTS: Record<InputStatus, string> = lazyLabels(STATUSES, 'status.demohint.');

/** The hint for a status, in the wording of the current backend mode. */
export const statusHint = (status: InputStatus, demo: boolean): string => (demo ? DEMO_STATUS_HINTS : STATUS_HINTS)[status];

export const CONFIRMED_BY_LABELS = lazyLabels(['exclamation', 'manual', 'legacy'] as const, 'confirmedby.');

/** "Disagreed · judged false at entry" style text for a record. */
export function statusText(status: InputStatus, reason: InputReason | null): string {
  const base = STATUS_LABELS[status];
  return reason && (status === 'disagreed' || status === 'revoked') && REASON_LABELS[reason] !== base
    ? `${base} · ${REASON_LABELS[reason]}`
    : base;
}

export const ACTION_LABELS: Record<ParameterEffect['action'], string> = lazyLabels(['preview', 'approve', 'revoke'] as const, 'action.');

/** The raw id always stays visible; a mock id is additionally tagged. */
export function ruleDisplay(ruleId: string): { id: string; isDemo: boolean; tag: string | null } {
  const isDemo = ruleId.startsWith(MOCK_RULE_PREFIX);
  return { id: ruleId, isDemo, tag: isDemo ? t('demo.tag') : null };
}

/**
 * Small accent marks per state (D57). Used ONLY as a dot or a thin rule, never
 * as a fill behind text. The values live in shared.css (`--alpha-state-*`, one
 * set per theme; they follow STATE_PALETTE in config/theme.ts for rational).
 */
export const partitionColor = (p: Partition): string => `var(--alpha-state-${p})`;

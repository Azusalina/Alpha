/**
 * Small display helpers of the records panel (round 3 part 9, D55).
 */

import { codePointLength } from '../../backend';

/** "10-01 14:32" in the viewer's zone; an unparsable stamp is shown as it came. */
export function formatTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const p = (n: number) => String(n).padStart(2, '0');
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** The full stamp for a tooltip. */
export function formatFull(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

/**
 * The raw excerpt of api.md is the first 80 code points of the original: it may
 * hold line breaks, NULs and other controls. Shown as ONE line of plain text
 * (CSS clamps it to two): runs of whitespace and controls become a single
 * space; an ellipsis is added when the text is longer than the excerpt.
 */
export function displayExcerpt(excerpt: string, charCount: number): string {
  // eslint-disable-next-line no-control-regex
  const flat = excerpt.replace(/[\u0000-\u001f\u007f\u0085\s]+/gu, ' ').trim();
  const shown = flat === '' ? '（空白）' : flat;
  return charCount > codePointLength(excerpt) ? `${shown}…` : shown;
}

/** T / F / — for a judgement (null = not made). */
export const tf = (v: boolean | null | undefined): 'T' | 'F' | '—' => (v === null || v === undefined ? '—' : v ? 'T' : 'F');

/**
 * Shown wherever a greyed action explains itself. User-facing wording only; the
 * developer pointer is here: edit and delete are request F6 in
 * front-back-communicate.md ([back] has not implemented it).
 */
export const UNSUPPORTED_NOTE = '后端暂不支持编辑和删除';

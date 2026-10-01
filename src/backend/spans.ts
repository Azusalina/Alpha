/**
 * Text spans of the back end, and how to use them in JavaScript (D54–D56).
 *
 * A span is `[start, end)` in Unicode CODE POINTS of the exact submitted
 * string (Python `str` offsets). JavaScript strings are UTF-16: an emoji or a
 * rare CJK character (U+20000 and up) is two code units but ONE code point, so
 * `text.slice(start, end)` is wrong as soon as such a character precedes the
 * evidence. Everything in the UI that slices, highlights or checks evidence
 * goes through this file.
 *
 * Lone surrogates (which a `.txt` cannot contain but a pasted string can) count
 * as one code point each, the way `Array.from` and Python count them; `submit`
 * refuses them (front-back-communicate.md F8), so this only keeps the helpers
 * total, never throwing.
 *
 * Pure module: no React, DOM or three, so Playwright imports it in plain Node.
 */

import type { Span } from './types';

const SURROGATE = /[\ud800-\udfff]/;
const LONE_SURROGATE = /[\ud800-\udbff](?![\udc00-\udfff])|(?<![\ud800-\udbff])[\udc00-\udfff]/;

/** Number of code points in `text`, without allocating an array. */
export function codePointLength(text: string): number {
  if (!SURROGATE.test(text)) return text.length;
  let n = 0;
  for (let i = 0; i < text.length; i++) {
    const c = text.charCodeAt(i);
    if (c >= 0xd800 && c <= 0xdbff && i + 1 < text.length) {
      const d = text.charCodeAt(i + 1);
      if (d >= 0xdc00 && d <= 0xdfff) i++;
    }
    n++;
  }
  return n;
}

/** True when `text` holds a surrogate that is not half of a valid pair. */
export function hasLoneSurrogate(text: string): boolean {
  return LONE_SURROGATE.test(text);
}

/**
 * Maps between code point offsets and UTF-16 indices of ONE string. Built once
 * (O(n)), then `toUtf16` is O(1) and `fromUtf16` O(log n). A text without any
 * surrogate needs no table: both directions are the identity.
 */
export class CodePointIndex {
  /** Code points in the text. */
  readonly length: number;
  /** UTF-16 length of the text. */
  readonly utf16Length: number;
  /** `starts[k]` = UTF-16 index of code point k; `starts[length]` = utf16Length. Null = identity. */
  private readonly starts: Uint32Array | null;

  constructor(text: string) {
    this.utf16Length = text.length;
    if (!SURROGATE.test(text)) {
      this.length = text.length;
      this.starts = null;
      return;
    }
    const starts = new Uint32Array(text.length + 1);
    let n = 0;
    for (let i = 0; i < text.length; i++) {
      starts[n++] = i;
      const c = text.charCodeAt(i);
      if (c >= 0xd800 && c <= 0xdbff && i + 1 < text.length) {
        const d = text.charCodeAt(i + 1);
        if (d >= 0xdc00 && d <= 0xdfff) i++;
      }
    }
    starts[n] = text.length;
    this.length = n;
    this.starts = starts.slice(0, n + 1);
  }

  /** UTF-16 index of code point offset `cp`; clamped to `[0, length]`. */
  toUtf16(cp: number): number {
    const k = cp < 0 ? 0 : cp > this.length ? this.length : cp;
    return this.starts ? this.starts[k] : k;
  }

  /**
   * Code point offset of UTF-16 index `i`: the code point that contains unit
   * `i` (an index between the two halves of a pair belongs to that pair), and
   * `length` for `i >= utf16Length`.
   */
  fromUtf16(i: number): number {
    if (i <= 0) return 0;
    if (i >= this.utf16Length) return this.length;
    const s = this.starts;
    if (!s) return i;
    let lo = 0;
    let hi = this.length; // starts[hi] > i
    while (lo + 1 < hi) {
      const mid = (lo + hi) >>> 1;
      if (s[mid] <= i) lo = mid;
      else hi = mid;
    }
    return lo;
  }
}

// A one-entry cache: a card that checks many spans against the same text
// builds the table once without threading it through every call.
let lastText: string | null = null;
let lastIndex: CodePointIndex | null = null;

/** The `CodePointIndex` of `text`, reusing the previous one when the text is the same string. */
export function indexFor(text: string): CodePointIndex {
  if (lastIndex && lastText === text) return lastIndex;
  const index = new CodePointIndex(text);
  lastText = text;
  lastIndex = index;
  return index;
}

/** Code point offset of UTF-16 index `i` in `text` (e.g. a textarea selection). */
export function codePointOffsetOfUtf16(text: string, i: number): number {
  return indexFor(text).fromUtf16(i);
}

/** UTF-16 index of code point offset `cp` in `text`. */
export function utf16OffsetOfCodePoint(text: string, cp: number): number {
  return indexFor(text).toUtf16(cp);
}

/** A span the text can honour: two integers, `0 <= start < end <= length`. */
export function isValidSpan(span: readonly number[] | null | undefined, length: number): boolean {
  if (!span || span.length !== 2) return false;
  const [s, e] = span;
  return Number.isInteger(s) && Number.isInteger(e) && s >= 0 && s < e && e <= length;
}

/** `text` between the code point offsets of `span`; '' when the span is invalid. */
export function codePointSlice(text: string, span: Span | readonly number[], index?: CodePointIndex): string {
  const ix = index ?? indexFor(text);
  if (!isValidSpan(span, ix.length)) return '';
  return text.slice(ix.toUtf16(span[0]), ix.toUtf16(span[1]));
}

/**
 * Does the back end's claim hold: the text at `span` is exactly `evidence`?
 * The UI shows a warning where it does not (a stale preview, an edited text,
 * a back-end bug) instead of highlighting the wrong characters.
 */
export function evidenceMatches(
  text: string,
  claim: { span: Span | readonly number[]; evidence: string },
  index?: CodePointIndex,
): boolean {
  const ix = index ?? indexFor(text);
  return isValidSpan(claim.span, ix.length) && codePointSlice(text, claim.span, ix) === claim.evidence;
}

export type SpanId = string | number;

/** A span to mark, optionally named (default name: its position in the input array). */
export type HighlightInput = Span | readonly number[] | { span: Span | readonly number[]; id?: SpanId };

export interface Segment {
  text: string;
  marked: boolean;
  /** Names of the input spans that cover this segment (empty when not marked), in input order. */
  spanIds: SpanId[];
  /** Code point offsets `[start, end)` of this segment in the whole text. */
  start: number;
  end: number;
}

/**
 * Cuts `text` into consecutive segments, marking every span. Overlapping and
 * touching spans merge into one marked segment (its `spanIds` lists all of
 * them). A span is clamped to the text; one that is empty, inverted, not made
 * of integers or wholly outside the text is dropped. Never throws.
 */
export function highlight(text: string, spans: readonly HighlightInput[], index?: CodePointIndex): Segment[] {
  const ix = index ?? indexFor(text);
  const total = ix.length;
  if (total === 0) return [];

  interface Range {
    s: number;
    e: number;
    id: SpanId;
    order: number;
  }
  const ranges: Range[] = [];
  spans.forEach((item, order) => {
    const isPair = Array.isArray(item);
    const span = (isPair ? item : (item as { span: readonly number[] }).span) as readonly number[] | undefined;
    if (!span || span.length !== 2) return;
    const [rs, re] = span;
    if (!Number.isInteger(rs) || !Number.isInteger(re) || rs >= re) return;
    const s = Math.max(0, rs);
    const e = Math.min(total, re);
    if (s >= e) return;
    const id = isPair ? order : ((item as { id?: SpanId }).id ?? order);
    ranges.push({ s, e, id, order });
  });
  ranges.sort((a, b) => a.s - b.s || a.e - b.e || a.order - b.order);

  // Merge overlapping or touching ranges.
  const merged: { s: number; e: number; members: Range[] }[] = [];
  for (const r of ranges) {
    const last = merged[merged.length - 1];
    if (last && r.s <= last.e) {
      last.e = Math.max(last.e, r.e);
      last.members.push(r);
    } else merged.push({ s: r.s, e: r.e, members: [r] });
  }

  const out: Segment[] = [];
  const cut = (s: number, e: number, marked: boolean, spanIds: SpanId[]): void => {
    if (s >= e) return;
    out.push({ text: text.slice(ix.toUtf16(s), ix.toUtf16(e)), marked, spanIds, start: s, end: e });
  };
  let cursor = 0;
  for (const m of merged) {
    cut(cursor, m.s, false, []);
    const seen = new Set<SpanId>();
    const ids: SpanId[] = [];
    for (const r of [...m.members].sort((a, b) => a.order - b.order)) {
      if (!seen.has(r.id)) {
        seen.add(r.id);
        ids.push(r.id);
      }
    }
    cut(m.s, m.e, true, ids);
    cursor = m.e;
  }
  cut(cursor, total, false, []);
  return out;
}

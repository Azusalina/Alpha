/**
 * Getting text into an input, and checking it before `submit` (D54).
 *
 *  - `readTextFile`: a local `.txt` / `.md`, decoded as STRICT UTF-8. Invalid
 *    bytes are refused, never replaced by U+FFFD: a replaced character would
 *    silently shift every span the back end reports (front-back-communicate.md F8).
 *  - `normalizeForSubmit`: what the front end does to a string just before it is
 *    sent — drop one leading BOM, keep everything else (CRLF included) byte for
 *    byte, refuse lone surrogates.
 *  - `validateEntry`: blocking errors and non-blocking warnings, in Chinese, for
 *    the entry form. The chat rules mirror `translator.pipeline` exactly, so the
 *    warning "no line for speaker X" predicts what the back end will do.
 *
 * The Python-compatible helpers at the top (`pyStrip`, `splitLines`,
 * `parseChatLine`) exist because the back end's offsets are those of Python
 * `str`; the mock extractor uses them to reproduce the same spans.
 *
 * Pure module: no React, DOM or three (`File` is used structurally).
 */

import { codePointLength, hasLoneSurrogate } from './spans';
import { BackendError, KINDS, MAX_INPUT_CHARS, PARTITIONS } from './types';
import type { Kind, Partition } from './types';
import { t } from '../i18n/lang';

/** Largest file the entry form reads: 1,000,000 code points need at most 4,000,000 UTF-8 bytes. */
export const MAX_FILE_BYTES = 4_000_000;
const BOM_BYTES = 3;

// ---- Python str compatibility ------------------------------------------------------

/**
 * The characters for which Python `str.isspace()` is true. It is what `\s` and
 * `str.strip()` use in the back end, and it differs from JavaScript's `\s`
 * (Python adds U+001C..U+001F and U+0085, JavaScript adds U+FEFF).
 */
export const PY_WS = '\\t\\n\\x0b\\x0c\\r\\x1c-\\x1f \\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000';

/**
 * The same 29 code points as `PY_WS`, as a lookup. Trimming scans from each end
 * with this instead of running `/[ws]+$/`: a regex with an end anchor retries from
 * every start of a whitespace run, which is quadratic in the length of a run that
 * is followed by a non-space (a pasted 40,000-space gap froze the page for
 * seconds, and `validateEntry` runs on every keystroke). Python's `str.strip()`
 * is linear, and so is this.
 */
export function isPyWhitespace(code: number): boolean {
  return (
    (code >= 0x09 && code <= 0x0d) ||
    (code >= 0x1c && code <= 0x20) ||
    code === 0x85 ||
    code === 0xa0 ||
    code === 0x1680 ||
    (code >= 0x2000 && code <= 0x200a) ||
    code === 0x2028 ||
    code === 0x2029 ||
    code === 0x202f ||
    code === 0x205f ||
    code === 0x3000
  );
}

/** Index of the first non-whitespace UTF-16 unit (`s.length` when blank). All whitespace is BMP, so units are code points. */
function firstNonWs(s: string): number {
  let i = 0;
  while (i < s.length && isPyWhitespace(s.charCodeAt(i))) i++;
  return i;
}

/** Python `str.strip()`. */
export function pyStrip(s: string): string {
  const start = firstNonWs(s);
  if (start === s.length) return '';
  let end = s.length;
  while (end > start && isPyWhitespace(s.charCodeAt(end - 1))) end--;
  return s.slice(start, end);
}

/** Python `str.lstrip()`. */
export function pyLstrip(s: string): string {
  const start = firstNonWs(s);
  return start === 0 ? s : s.slice(start);
}

/** True when Python `s.strip()` would be empty. Linear, allocation free. */
export function isBlank(s: string): boolean {
  return firstNonWs(s) === s.length;
}

export interface Line {
  /** The line including its terminator (`str.splitlines(keepends=True)`). */
  raw: string;
  /** `raw.rstrip("\r\n")`. */
  bare: string;
  /** UTF-16 index of the line in the whole text. */
  start: number;
}

const LINE_BREAK = /\r\n|[\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029]/g;

/** Python `str.splitlines(keepends=True)`: no trailing empty line. */
export function splitLines(text: string): Line[] {
  const lines: Line[] = [];
  let start = 0;
  const push = (end: number): void => {
    const raw = text.slice(start, end);
    lines.push({ raw, bare: raw.replace(/[\r\n]+$/, ''), start });
    start = end;
  };
  for (const m of text.matchAll(LINE_BREAK)) push((m.index as number) + m[0].length);
  if (start < text.length) push(text.length);
  return lines;
}

/** `translator.pipeline._CHAT_LINE`: `^\s*([^:：\s]{1,32})\s*[:：]\s*(.*)$`. */
const CHAT_LINE = new RegExp(`^[${PY_WS}]*([^:：${PY_WS}]{1,32})[${PY_WS}]*[:：][${PY_WS}]*(.*)$`, 'sud');

export interface ChatLine {
  speaker: string;
  content: string;
  /** UTF-16 index of `content` inside the bare line. */
  contentStart: number;
}

/** One `name: text` / `name：text` line, or null. `bare` has no line terminator. */
export function parseChatLine(bare: string): ChatLine | null {
  const m = CHAT_LINE.exec(bare);
  if (!m || !m.indices) return null;
  return { speaker: m[1], content: m[2], contentStart: m.indices[2][0] };
}

// ---- files -------------------------------------------------------------------------

export type TextFileErrorCode = 'EXTENSION' | 'TOO_LARGE' | 'INVALID_UTF8' | 'READ_FAILED';

export class TextFileError extends Error {
  readonly code: TextFileErrorCode;
  constructor(code: TextFileErrorCode, message: string) {
    super(message);
    this.name = 'TextFileError';
    this.code = code;
  }
}

/** The part of a `File` that `readTextFile` uses (a real `File` satisfies it). */
export interface FileLike {
  readonly name: string;
  readonly size: number;
  arrayBuffer(): Promise<ArrayBuffer>;
}

export interface TextFile {
  text: string;
  /** The file name only, never a path. */
  source_ref: string;
}

function baseName(name: string): string {
  return name.split(/[\\/]/).pop() ?? name;
}

/**
 * Reads a `.txt` / `.md` (any case) as strict UTF-8. One leading U+FEFF is
 * removed; CRLF is kept as it is. Rejects with `TextFileError`.
 */
export async function readTextFile(file: FileLike): Promise<TextFile> {
  const name = baseName(file.name);
  if (!/\.(txt|md)$/i.test(name)) {
    throw new TextFileError('EXTENSION', t('text.ext'));
  }
  // A BOM is 3 bytes that never reach the back end, so a file of exactly
  // 1,000,000 code points plus a BOM is valid. The byte limit is only a memory
  // guard; the code point limit itself is checked by `validateEntry`.
  if (file.size > MAX_FILE_BYTES + BOM_BYTES) {
    throw new TextFileError('TOO_LARGE', t('text.tooLarge', { mb: MAX_FILE_BYTES / 1_000_000 }));
  }
  let bytes: ArrayBuffer;
  try {
    bytes = await file.arrayBuffer();
  } catch {
    throw new TextFileError('READ_FAILED', t('entry.file.failed'));
  }
  if (bytes.byteLength > MAX_FILE_BYTES) {
    const head = new Uint8Array(bytes, 0, Math.min(3, bytes.byteLength));
    const hasBom = head.length === 3 && head[0] === 0xef && head[1] === 0xbb && head[2] === 0xbf;
    if (!hasBom || bytes.byteLength > MAX_FILE_BYTES + BOM_BYTES) {
      throw new TextFileError('TOO_LARGE', t('text.tooLarge', { mb: MAX_FILE_BYTES / 1_000_000 }));
    }
  }
  let decoded: string;
  try {
    // ignoreBOM: keep the BOM in the output so that stripping it is our explicit,
    // single step rather than a decoder default.
    decoded = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(bytes);
  } catch {
    throw new TextFileError('INVALID_UTF8', t('text.utf8'));
  }
  // A text file has no U+0000. UTF-16 without a BOM (every other byte is 00) decodes
  // as "valid" UTF-8 full of NULs and would otherwise be read as garbage text; the
  // back end also refuses a text with one anywhere (see `hasNul`).
  if (decoded.includes('\u0000')) {
    throw new TextFileError('INVALID_UTF8', t('text.nulFile'));
  }
  if (decoded.charCodeAt(0) === 0xfeff) decoded = decoded.slice(1);
  return { text: decoded, source_ref: name };
}

/**
 * The string that is actually sent. Drops one leading U+FEFF; nothing else is
 * touched (no trimming, no newline normalisation), so `input_get` returns what
 * was typed. Throws `BackendError('INVALID_ARGUMENT')` for a lone surrogate.
 */
export function normalizeForSubmit(text: string): string {
  const body = text.charCodeAt(0) === 0xfeff ? text.slice(1) : text;
  if (hasLoneSurrogate(body)) {
    throw new BackendError('INVALID_ARGUMENT', t('text.surrogate'));
  }
  if (hasNul(body)) throw new BackendError('INVALID_ARGUMENT', leadingNulMessage());
  return body;
}

// ---- validation --------------------------------------------------------------------

export const leadingNulMessage = (): string => t('text.nul');

/**
 * True when the text holds U+0000 anywhere. The back end refuses a new submit or
 * edit text with one (INVALID_ARGUMENT, nothing is stripped); legacy stored text
 * that has one stays readable.
 */
export function hasNul(text: string): boolean {
  return text.includes('\u0000');
}

export interface EntryDraft {
  text: string;
  partition: Partition;
  kind: Kind;
  self_speaker?: string | null;
}

export interface ChatCounts {
  /** Lines of the self speaker (analysed). */
  selfLines: number;
  /** Lines of other speakers (ignored, not an error). */
  otherLines: number;
  /** Non-blank lines without a `name: text` shape (skipped). */
  unlabeledLines: number;
}

export interface EntryValidation {
  /** Blocking. */
  errors: string[];
  /** Shown, not blocking. */
  warnings: string[];
  /** Present for chat with a speaker. */
  chat?: ChatCounts;
}

/** Counts chat lines the way the back end reads them. */
export function chatCounts(text: string, selfSpeaker: string): ChatCounts {
  const counts: ChatCounts = { selfLines: 0, otherLines: 0, unlabeledLines: 0 };
  for (const line of splitLines(text)) {
    if (isBlank(line.bare)) continue;
    const parsed = parseChatLine(line.bare);
    if (!parsed) counts.unlabeledLines++;
    else if (parsed.speaker === selfSpeaker) counts.selfLines++;
    else counts.otherLines++;
  }
  return counts;
}

/**
 * Blocking errors and warnings for an entry, in Chinese. It judges the TEXT only:
 * the two judgements are never an error. `exclamation` does not need `immediate`
 * (the back end sets both true itself; see `effectiveJudgement` in types.ts).
 */
export function validateEntry(draft: EntryDraft): EntryValidation {
  const errors: string[] = [];
  const warnings: string[] = [];
  const { kind } = draft;
  // What is sent has one leading BOM removed (`normalizeForSubmit`): judge that string.
  const text = draft.text.charCodeAt(0) === 0xfeff ? draft.text.slice(1) : draft.text;

  if (!PARTITIONS.includes(draft.partition)) errors.push(t('text.pickState'));
  if (!KINDS.includes(kind)) errors.push(t('text.pickKind'));

  if (isBlank(text)) errors.push(t('text.empty'));
  else if (codePointLength(text) > MAX_INPUT_CHARS) {
    errors.push(t('text.over', { n: MAX_INPUT_CHARS.toLocaleString('en-US') }));
  }
  if (hasLoneSurrogate(text)) errors.push(t('text.surrogate'));
  if (hasNul(text)) errors.push(leadingNulMessage());

  if (kind !== 'chat') return { errors, warnings };

  const speaker = draft.self_speaker ?? '';
  if (isBlank(speaker)) {
    errors.push(t('text.speaker.need'));
    return { errors, warnings };
  }
  if (splitLines(speaker).length > 1) {
    errors.push(t('text.speaker.line'));
    return { errors, warnings };
  }
  if (speaker !== pyStrip(speaker)) {
    errors.push(t('text.speaker.trim'));
    return { errors, warnings };
  }
  if (isBlank(text)) return { errors, warnings };

  const counts = chatCounts(text, speaker);
  if (counts.selfLines === 0) {
    const unmatchable = new RegExp(`[:：${PY_WS}]`, 'u').test(speaker) || codePointLength(speaker) > 32;
    warnings.push(
      unmatchable
        ? t('text.speaker.unmatchable', { name: speaker })
        : t('text.speaker.none', { name: speaker }),
    );
  }
  if (counts.unlabeledLines > 0) {
    warnings.push(t('text.unlabeled', { n: counts.unlabeledLines }));
  }
  return { errors, warnings, chat: counts };
}

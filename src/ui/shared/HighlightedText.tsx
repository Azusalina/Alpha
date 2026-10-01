/**
 * The ORIGINAL text of an input with its evidence spans marked (D54–D56).
 *
 * Why this is not `text.slice(start, end)`: a span is a zero-based Unicode CODE
 * POINT offset, end exclusive, into the exact submitted string; JavaScript
 * indexes UTF-16 units, so a direct slice lands inside an emoji or a rare CJK
 * character. Everything goes through `src/backend/spans.ts`.
 *
 * Long texts (the limit is 1,000,000 code points) must not freeze the page, so
 * above FOLD_LIMIT code points only a window is rendered: around the first mark
 * when there is one, else the first characters. The window is sliced by code
 * point and the spans are shifted into it, so every mark that is shown is still
 * exactly the back end's span. The controls say how much is folded and grow the
 * window stepwise (STEP code points), so the page never has to lay out a whole
 * megabyte at once.
 *
 * A mark whose evidence is not what the text holds at that span (a stale
 * preview, an edited text, a back-end bug) is NOT drawn: the warning "证据位置与原文不符"
 * is shown instead of a highlight on the wrong characters.
 *
 * Hover or focus of an effect row sets `activeId`; the marks that belong to it
 * get `is-active`. Each mark carries `data-span="start,end"` (code points of the
 * whole text) and `data-mark-ids`.
 */

import './shared.css';
import { useMemo, useState } from 'react';

import { CodePointIndex, evidenceMatches, highlight } from '../../backend';
import type { Span } from '../../backend';

export interface HighlightMark {
  /** Names the mark; an effect row with the same id lights it up. */
  id: string;
  span: Span;
  /** When given, the mark is drawn only if the text at `span` is exactly this. */
  evidence?: string;
}

/** The marks of an effects list; ids are the row indices, the same ones EffectsTable uses. */
export function marksFromEffects(effects: readonly { span: Span; evidence: string }[]): HighlightMark[] {
  return effects.map((e, i) => ({ id: String(i), span: e.span, evidence: e.evidence }));
}

/** Above this many code points the text is folded. */
export const FOLD_LIMIT = 6000;
/** How many code points each "展开" adds. */
export const STEP = 20000;
/** Context kept before the first mark when a window opens on it. */
const LEAD = 240;

interface Props {
  text: string;
  marks?: readonly HighlightMark[];
  activeId?: string | null;
  className?: string;
  'data-testid'?: string;
  /** Override FOLD_LIMIT (tests). */
  foldLimit?: number;
}

export function HighlightedText({ text, marks = [], activeId = null, className, foldLimit = FOLD_LIMIT, ...rest }: Props) {
  const index = useMemo(() => new CodePointIndex(text), [text]);
  const total = index.length;

  // marks that hold vs marks the text contradicts
  const { good, bad } = useMemo(() => {
    const good: HighlightMark[] = [];
    const bad: HighlightMark[] = [];
    for (const m of marks) {
      if (m.evidence !== undefined && !evidenceMatches(text, { span: m.span, evidence: m.evidence }, index)) bad.push(m);
      else good.push(m);
    }
    return { good, bad };
  }, [marks, text, index]);

  const firstStart = useMemo(() => {
    let s = Infinity;
    for (const m of good) if (Number.isInteger(m.span[0]) && m.span[0] >= 0 && m.span[0] < total && m.span[0] < m.span[1]) s = Math.min(s, m.span[0]);
    return Number.isFinite(s) ? s : -1;
  }, [good, total]);

  const folded = total > foldLimit;
  const initial = useMemo<[number, number]>(() => {
    if (!folded) return [0, total];
    if (firstStart < 0) return [0, foldLimit];
    const from = Math.max(0, firstStart - LEAD);
    return [from, Math.min(total, from + foldLimit)];
  }, [folded, total, firstStart, foldLimit]);

  // the window the user has grown, reset whenever the text or the first mark changes
  const [grown, setGrown] = useState<{ key: string; win: [number, number] } | null>(null);
  const key = `${text.length}:${total}:${initial[0]}:${initial[1]}`;
  const [from, to] = !folded ? [0, total] : grown && grown.key === key ? grown.win : initial;

  const segments = useMemo(() => {
    if (total === 0) return [];
    const a = index.toUtf16(from);
    const b = index.toUtf16(to);
    const piece = text.slice(a, b);
    const shifted = good.map((m) => ({ span: [m.span[0] - from, m.span[1] - from] as const, id: m.id }));
    return highlight(piece, shifted, new CodePointIndex(piece));
  }, [text, index, good, from, to, total]);

  const grow = (dir: -1 | 1) =>
    setGrown({
      key,
      win: dir < 0 ? [Math.max(0, from - STEP), to] : [from, Math.min(total, to + STEP)],
    });

  return (
    <div className={`hl${className ? ` ${className}` : ''}`} {...rest}>
      {folded && from > 0 && (
        <p className="hl__fold" data-testid="hl-fold-before">
          <span>已折叠前面 {from.toLocaleString('zh-CN')} 个字符 …</span>{' '}
          <button type="button" onClick={() => grow(-1)}>
            展开
          </button>
        </p>
      )}
      <p className="hl__text" data-testid="hl-text">
        {segments.map((s, i) =>
          s.marked ? (
            <mark
              key={i}
              className={`hl__mark${activeId !== null && s.spanIds.includes(activeId) ? ' is-active' : ''}`}
              data-testid="hl-mark"
              data-span={`${s.start + from},${s.end + from}`}
              data-mark-ids={s.spanIds.join(' ')}
            >
              {s.text}
            </mark>
          ) : (
            <span key={i}>{s.text}</span>
          ),
        )}
      </p>
      {folded && to < total && (
        <p className="hl__fold" data-testid="hl-fold-after">
          <span>… 已折叠后面 {(total - to).toLocaleString('zh-CN')} 个字符</span>{' '}
          <button type="button" onClick={() => grow(1)}>
            展开
          </button>
        </p>
      )}
      {folded && (from !== initial[0] || to !== initial[1]) && (
        <p className="hl__fold">
          <button type="button" onClick={() => setGrown(null)}>
            收起
          </button>
        </p>
      )}
      {bad.length > 0 && (
        <p className="hl__warn" role="note" data-testid="hl-mismatch">
          证据位置与原文不符（{bad.length} 处）：原文可能已被修改，这些证据不作高亮。
        </p>
      )}
    </div>
  );
}

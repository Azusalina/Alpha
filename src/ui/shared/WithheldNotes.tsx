/**
 * What the back end's basic value rules did NOT take from the text, and why
 * (`interpretation.withheld_values`, back-end-core/docs/evidence-policy.md).
 *
 * This is a diagnostic about the automatic extraction, not a result: it is not
 * the final effects, not an abstain and not a verdict on the writer. A user's
 * explicit correction can still override a withheld rule, so the list must
 * never be used to delete or hide an effect. The reason enum can grow (the
 * schema already holds v1 and v2): an unknown reason shows its raw id.
 * Old frozen contexts carry none of these fields: then nothing is shown.
 */

import './shared.css';
import type { Interpretation } from '../../backend';
import { parameterLabel } from './labels';

export const WITHHELD_REASON_LABELS: Record<string, string> = {
  quoted_text: '引号里的话',
  code_text: '代码片段',
  markdown_quote: 'Markdown 引述',
  question: '疑问句',
  reported_speech: '转述别人的话',
  hypothetical: '假设',
  other_subject_value: '是别人的看法',
  hedged_value: '带「可能」的不确定表述',
  ambiguous_negation: '否定含义不明确',
  ambiguous_opposition: '对立含义不明确',
  ambiguous_normative_negation: '规范性否定含义不明确',
  ambiguous_comparison: '比较含义不明确',
};

export const withheldReasonLabel = (reason: string): string => WITHHELD_REASON_LABELS[reason] ?? reason;

interface Props {
  interpretation?: Interpretation | null;
  /** Hover / focus of an item can highlight its span in the original (same ids as the caller's marks, optional). */
  onActiveChange?: (id: string | null) => void;
}

export function WithheldNotes({ interpretation, onActiveChange }: Props) {
  const items = interpretation?.withheld_values ?? [];
  const count = interpretation?.withheld_count ?? items.length;
  if (!interpretation || !interpretation.evidence_policy || count === 0) return null;
  return (
    <section className="withheld" data-testid="withheld-notes" aria-label="自动提取暂不采纳的片段">
      <h4 className="withheld__h">自动提取暂不采纳</h4>
      <p className="withheld__lead">
        基础规则没有把下面这些话当作你自己的价值表述。这只是说明规则为什么没用它们，不是最终结果；你的显式纠正可以覆盖。
      </p>
      <ul className="withheld__list">
        {items.map((w, i) => (
          <li
            key={`${w.span[0]}-${w.span[1]}-${i}`}
            className="withheld__item"
            data-testid="withheld-item"
            data-reason={w.reason}
            tabIndex={0}
            onMouseEnter={() => onActiveChange?.(`withheld-${i}`)}
            onMouseLeave={() => onActiveChange?.(null)}
            onFocus={() => onActiveChange?.(`withheld-${i}`)}
            onBlur={() => onActiveChange?.(null)}
          >
            <span className="withheld__reason" data-testid="withheld-reason">
              {withheldReasonLabel(w.reason)}
            </span>
            <span className="withheld__evidence" data-testid="withheld-evidence">
              {w.evidence}
            </span>
            <span className="withheld__meta">
              {w.parameters.map(parameterLabel).join('、')} · 位置 [{w.span[0]}, {w.span[1]})
            </span>
          </li>
        ))}
      </ul>
      {interpretation.withheld_truncated && (
        <p className="withheld__lead" data-testid="withheld-truncated">
          只列出了前 {items.length} 条，共 {count} 条；这只是缩短了这份说明，并不表示只分析了前面的内容。
        </p>
      )}
      <p className="withheld__policy">规则版本 {interpretation.evidence_policy}</p>
    </section>
  );
}

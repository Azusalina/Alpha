/**
 * The effects of a preview, a submit, a review or a revoke, one ruled row per
 * effect (D54–D56). Rows are stacked rather than a wide table: the panels are
 * narrow columns.
 *
 * Shown per effect: 参数 (label + id), 前 → 后 with the delta, 支持 before →
 * after, 证据 (the evidence text, which the caller's HighlightedText shows in
 * place in the original), 位置 [start, end) in code points, 规则 (the raw rule
 * id; a `mock.*` id is tagged 演示), 修订 (a preview has none: "预览 · 无修订号")
 * and an action tag (预览 / 已应用 / 已撤销).
 *
 * An empty list says "未提取到可拟合的证据". That is not an abstain, and it
 * does not mean nothing was learned: vocabulary may still have changed
 * (F10), so the wording makes no claim beyond "no parameter evidence".
 *
 * Hover or focus of a row calls `onActiveChange(id)`; the ids are row indices,
 * the same ones `marksFromEffects` gives the HighlightedText.
 *
 * An effect whose `model_epoch` is older than `health.model_epoch` is tagged
 * 旧模型轮次: history that predates a model reset, never the current state.
 *
 * A preview is hypothetical and may be stale: after a review the caller shows
 * the review's own effects instead (this component just shows what it is given).
 */

import './shared.css';
import type { ParameterEffect } from '../../backend';
import { useInputs } from '../../app/inputStore';
import { fmt } from './EvidenceValue';
import { ACTION_LABELS, parameterLabel, ruleDisplay } from './labels';
import { t } from '../../i18n/lang';

interface Props {
  effects: readonly ParameterEffect[];
  /** Replaces the default empty wording (kept for unusual callers; normally leave it). */
  emptyText?: string;
  activeId?: string | null;
  onActiveChange?: (id: string | null) => void;
  /** Extra class on the list. */
  className?: string;
}

const signed = (n: number): string => (n > 0 ? `+${fmt(n)}` : fmt(n));

export function EffectsTable({ effects, emptyText = t('effects.empty'), activeId = null, onActiveChange, className }: Props) {
  // An effect written in an earlier model epoch is history; it never describes the current state.
  const currentEpoch = useInputs().modelEpoch;
  if (effects.length === 0) {
    return (
      <p className="effects-empty" data-testid="effects-empty" role="note">
        {emptyText}
      </p>
    );
  }
  return (
    <ol className={`effects${className ? ` ${className}` : ''}`} data-testid="effects-table" aria-label={t('effects.aria')}>
      {effects.map((e, i) => {
        const id = String(i);
        const rule = ruleDisplay(e.rule_id);
        const dir = e.delta > 0 ? 'up' : e.delta < 0 ? 'down' : 'flat';
        return (
          <li
            key={`${e.revision ?? 'p'}:${e.parameter}:${e.span[0]}:${e.span[1]}:${i}`}
            className={`effect${activeId === id ? ' is-active' : ''}`}
            data-testid="effect-row"
            data-parameter={e.parameter}
            data-rule-id={e.rule_id}
            data-action={e.action}
            data-demo={rule.isDemo ? 'true' : 'false'}
            tabIndex={0}
            onMouseEnter={() => onActiveChange?.(id)}
            onMouseLeave={() => onActiveChange?.(null)}
            onFocus={() => onActiveChange?.(id)}
            onBlur={() => onActiveChange?.(null)}
          >
            <div className="effect__head">
              <span className="effect__param" data-testid="effect-param">
                {parameterLabel(e.parameter)}
                <code>{e.parameter}</code>
              </span>
              <span className={`effect__action effect__action--${e.action}`} data-testid="effect-action">
                {ACTION_LABELS[e.action]}
              </span>
            </div>
            <div className="effect__nums">
              <span data-testid="effect-value">
                <b>{t('effects.value')}</b> {fmt(e.before)} → {fmt(e.after)}
                <em className={`effect__delta effect__delta--${dir}`} data-testid="effect-delta">
                  {signed(e.delta)}
                </em>
              </span>
              <span data-testid="effect-support">
                <b>{t('effects.support')}</b> {e.support_before} → {e.support_after}
              </span>
            </div>
            <blockquote className="effect__evidence" data-testid="effect-evidence">
              {e.evidence}
            </blockquote>
            <div className="effect__meta">
              <span data-testid="effect-span">
                {t('effects.span', { a: e.span[0], b: e.span[1] })}
              </span>
              <span data-testid="effect-rule">
                {t('effects.rule')} <code>{rule.id}</code>
                {rule.tag && <span className="effect__demo">{rule.tag}</span>}
              </span>
              <span data-testid="effect-revision">
                {t('effects.revision')} {e.revision === undefined ? t('effects.revision.none') : `#${e.revision}`}
              </span>
              {currentEpoch !== null && e.model_epoch !== undefined && e.model_epoch < currentEpoch && (
                <span className="effect__demo" data-testid="effect-old-epoch">
                  {t('effects.oldEpoch')}
                </span>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

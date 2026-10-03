/**
 * One parameter's state (D54–D56): a value with its support, or "尚无证据".
 *
 * `observed=false` means the model has seen nothing for this parameter. It must
 * never be drawn as a zero bar, which would read as a measured neutral: there is
 * no bar, only the words. An observed value is a thin bar centred on 0 over
 * [-1, 1] (scores are `net / (support + 4)`), plus the number and the support.
 */

import './shared.css';
import type { ParameterState } from '../../backend';
import { t } from '../../i18n/lang';

export const fmt = (n: number): string => {
  if (!Number.isFinite(n)) return '—';
  const s = n.toFixed(3).replace(/\.?0+$/, '');
  return s === '-0' ? '0' : s;
};

interface Props {
  state: ParameterState;
  /** Shown before the value, e.g. the parameter's label. */
  label?: string;
}

export function EvidenceValue({ state, label }: Props) {
  if (!state.observed) {
    return (
      <span className="ev ev--none" data-testid="evidence-none">
        {label && <span className="ev__label">{label}</span>}
        <span className="ev__none">{t('ev.none')}</span>
      </span>
    );
  }
  const v = Math.max(-1, Math.min(1, state.value));
  return (
    <span className="ev" data-testid="evidence-value">
      {label && <span className="ev__label">{label}</span>}
      <span className="ev__bar" aria-hidden="true">
        <i style={{ left: v < 0 ? `${50 + v * 50}%` : '50%', width: `${Math.abs(v) * 50}%` }} />
      </span>
      <span className="ev__num">{fmt(state.value)}</span>
      <span className="ev__support">{t('ev.support', { n: state.support })}</span>
    </span>
  );
}

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
import { t, tOr } from '../../i18n/lang';

/** Why a fragment was set aside; a reason this build does not know shows itself. */
export const withheldReasonLabel = (reason: string): string => tOr(`withheld.reason.${reason}`, reason);

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
    <section className="withheld" data-testid="withheld-notes" aria-label={t('withheld.aria')}>
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
              {w.parameters.map(parameterLabel).join(t('list.sep'))} · {t('effects.span', { a: w.span[0], b: w.span[1] })}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

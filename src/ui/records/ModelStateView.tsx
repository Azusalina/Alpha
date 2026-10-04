/**
 * "模型状态": what the back end's model holds now, per partition (D55). Three
 * small blocks, one per state (accent mark and name); each lists the 13
 * parameters of `parameters.md`. A parameter that has evidence shows a thin bar
 * centred on 0 over [-1, 1], the number and its support; one that has none
 * shows "尚无证据" and NO bar (EvidenceValue: a zero bar would read as a
 * measured neutral). A small tag carries the latest revision that touched the
 * parameter (reversals included), and the parameters changed by the last
 * training are marked 刚变化.
 *
 * Everything here comes from the adapter (`useModelState`), nothing from the
 * rows' own effects. In demo mode the numbers are the mock's and the banner
 * above says so permanently.
 *
 * NOT here yet: a ranking view. `rank` and its `abstain` answer ("资料不足",
 * AbstainNote) belong to the later choice-feedback version of the UI (a
 * question with options); there is nothing to rank in this panel, and a probe
 * with invented options would be misleading. AbstainNote is built and tested
 * (tests/records.spec.ts) for that version.
 */

import { PARAMETER_IDS, PARTITIONS } from '../../backend';
import type { Partition } from '../../backend';
import { EvidenceValue } from '../shared/EvidenceValue';
import { PARTITION_LABELS, parameterLabel, partitionColor } from '../shared/labels';
import { paramKey } from './useModelState';
import type { ModelView } from './useModelState';
import { t } from '../../i18n/lang';

interface Props {
  view: ModelView;
  connected: boolean;
}

export function ModelStateView({ view, connected }: Props) {
  const { state, revisions, changed, loading, error } = view;

  if (!connected) return null;

  return (
    <div className="mstate" data-testid="model-state" aria-busy={loading}>
      {error && (
        <p className="rec__error" role="alert" data-testid="state-error">
          <code>{error.code}</code> {error.message}{' '}
          <button type="button" onClick={view.reload}>
            {t('common.retry')}
          </button>
        </p>
      )}
      {!state && !error && <p className="rec__quiet">{t('mstate.loading')}</p>}
      {state &&
        PARTITIONS.map((p: Partition) => {
          const observed = PARAMETER_IDS.filter((id) => state[p][id].observed).length;
          return (
            <section
              key={p}
              className="mstate__block"
              data-testid="state-block"
              data-partition={p}
              aria-label={PARTITION_LABELS[p]}
              style={{ ['--rec-accent' as string]: partitionColor(p) }}
            >
              <h3 className="mstate__title">
                <span className="mstate__mark" aria-hidden="true" />
                {PARTITION_LABELS[p]}
                <small data-testid="state-observed-count">
                  {observed === 0 ? t('ev.none') : t('mstate.observed', { n: observed, total: PARAMETER_IDS.length })}
                </small>
              </h3>
              <ul className="mstate__list">
                {PARAMETER_IDS.map((id) => {
                  const k = paramKey(p, id);
                  const st = state[p][id];
                  const rev = revisions[k];
                  const isChanged = changed.has(k);
                  return (
                    <li
                      key={id}
                      className={`mp${isChanged ? ' is-changed' : ''}`}
                      data-testid="state-param"
                      data-partition={p}
                      data-parameter={id}
                      data-observed={String(st.observed)}
                      data-changed={String(isChanged)}
                    >
                      <EvidenceValue state={st} label={parameterLabel(id)} />
                      <span className="mp__tags">
                        {isChanged && (
                          <span className="mp__changed" data-testid="state-changed">
                            {t('mstate.justChanged')}
                          </span>
                        )}
                        {rev !== undefined && (
                          <span className="mp__rev" data-testid="state-revision">
                            #{rev}
                          </span>
                        )}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </section>
          );
        })}
    </div>
  );
}

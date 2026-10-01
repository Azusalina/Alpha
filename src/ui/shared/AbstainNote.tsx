/**
 * A rank result the back end declined to give (`status: 'abstain'`, D54–D56):
 * "资料不足", with the back end's own reason in small type. It is not a score of
 * zero and not an error. Renders nothing for a provisional result.
 */

import './shared.css';
import type { RankResult } from '../../backend';

interface Props {
  result: RankResult | null | undefined;
}

export function AbstainNote({ result }: Props) {
  if (!result || result.status !== 'abstain') return null;
  return (
    <p className="abstain" role="note" data-testid="abstain-note">
      <span className="abstain__title">资料不足</span>
      {result.reason && (
        <small className="abstain__reason" data-testid="abstain-reason">
          {result.reason}
        </small>
      )}
    </p>
  );
}

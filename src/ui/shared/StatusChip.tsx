/**
 * A record's status as a small mark and a word (D55): 待确认 / 已认可 / 不同意 /
 * 已撤销, with the reason when there is one (当下判断为否 / 二次确认为否 / 已撤销).
 * No filled badge: a dot in the status's weight and the word in ink, in paper
 * and ink's ruled manner. The status of the RECORD is shown, never that of a
 * preview (a preview of a disagreed input still says disagreed).
 */

import './shared.css';
import type { InputReason, InputStatus } from '../../backend';
import { useBackend } from '../../backend';
import { statusHint, statusText } from './labels';

interface Props {
  status: InputStatus;
  reason?: InputReason | null;
  /** Show the judgement path too: "当下 T · 二次 —". */
  className?: string;
}

export function StatusChip({ status, reason = null, className }: Props) {
  const demo = useBackend().mode === 'demo'; // D56: a demo tooltip never says "training"
  return (
    <span
      className={`status-chip status-chip--${status}${className ? ` ${className}` : ''}`}
      data-testid="status-chip"
      data-status={status}
      data-reason={reason ?? ''}
      title={statusHint(status, demo)}
    >
      <i className="status-chip__dot" aria-hidden="true" />
      {statusText(status, reason)}
    </span>
  );
}

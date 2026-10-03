/**
 * An error of the entry's own actions, inline, with its code (the store puts
 * every `BackendError` into `state.error`; nothing is swallowed). Only errors
 * of the listed actions are shown here: a failed list refresh belongs to the
 * records panel. `id` narrows it to one input (a preview of the open result).
 */

import { inputStore, useInputs } from '../../app/inputStore';
import type { InputError } from '../../app/inputStore';
import { t } from '../../i18n/lang';

interface Props {
  actions: InputError['action'][];
  id?: string;
}

export function EntryError({ actions, id }: Props) {
  const { error } = useInputs();
  if (!error || !actions.includes(error.action) || (id !== undefined && error.id !== id)) return null;
  return (
    <div className="entry-error" role="alert" data-testid="entry-error" data-code={error.code}>
      <p>
        <b>{error.action === 'preview' ? t('entry.error.preview') : t('entry.error.submit')}</b>
        <code data-testid="entry-error-code">{error.code}</code>
      </p>
      <p className="entry-error__msg">{error.message}</p>
      <button type="button" className="entry-link" onClick={inputStore.dismissError}>
        {t('entry.error.close')}
      </button>
    </div>
  );
}

/**
 * Which back end the panels are talking to (D56), always visible in both panels.
 *
 *  - unconnected (the product default): "后端未连接", what that means, and a
 *    button that enters demo mode BY HAND (`backendStore.enterDemo`). When a
 *    connection to the desktop back end was tried and failed, the reason and a
 *    retry button are shown as well.
 *  - demo: a permanent slim strip, "演示数据 · 未运行模型 · 刷新即清空", with
 *    "退出演示". Nothing entered in demo mode trains anything, and the strip
 *    must never be hidden or shortened: the mock must not be presentable as
 *    real training. Leaving drops every demo record (the input store resets on
 *    the backend change); with records present it asks once more first.
 *  - remote: a quiet "本机后端已连接", plus which actions this back end does not
 *    offer (edit / delete: F6) and, if the last connect failed, why.
 *
 * Connecting is UNVERIFIED on the native build (see app/desktop.ts).
 */

import './shared.css';
import { useEffect, useState } from 'react';

import { backendStore, useBackend } from '../../backend';
import { hasDesktopHost } from '../../app/desktop';
import { inputStore, useInputs } from '../../app/inputStore';
import { t } from '../../i18n/lang';



interface Props {
  className?: string;
}

export function BackendBanner({ className }: Props) {
  const backend = useBackend();
  const inputs = useInputs();
  const [confirmLeave, setConfirmLeave] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const cls = `backend-banner backend-banner--${backend.mode}${className ? ` ${className}` : ''}`;

  // the methods this back end offers (for the "not offered" line)
  useEffect(() => {
    if (backend.mode === 'remote') void inputStore.ensureLoaded();
  }, [backend.mode, backend.generation]);
  useEffect(() => setConfirmLeave(false), [backend.mode, backend.generation]);

  if (backend.mode === 'demo') {
    const hasData = inputs.total > 0 || inputs.records.length > 0;
    return (
      <div className={cls} data-testid="backend-banner" data-mode="demo" role="status">
        <span className="backend-banner__demo" data-testid="backend-demo-label">
          {t('banner.demo')}
        </span>
        <button
          type="button"
          className="backend-banner__btn"
          data-testid="backend-leave-demo"
          onClick={() => {
            if (hasData && !confirmLeave) setConfirmLeave(true);
            else backendStore.leaveDemo();
          }}
          onBlur={() => setConfirmLeave(false)}
        >
          {confirmLeave ? t('banner.leave.confirm') : t('banner.leave')}
        </button>
      </div>
    );
  }

  if (backend.mode === 'remote') {
    // nothing to say while connected (no "connected" line); the element stays, hidden, as the mode marker
    return (
      <div className={cls} data-testid="backend-banner" data-mode="remote" role="status" hidden={!backend.lastConnectError}>
        {backend.lastConnectError && (
          <span className="backend-banner__error" data-testid="backend-connect-error">
            {backend.lastConnectError}
          </span>
        )}
      </div>
    );
  }

  const canRetry = backend.lastConnectError !== null && hasDesktopHost();
  return (
    <div className={cls} data-testid="backend-banner" data-mode="unconnected" role="status">
      <p className="backend-banner__title" data-testid="backend-status">
        {t('banner.off')}
      </p>
      {backend.lastConnectError && (
        <p className="backend-banner__error" data-testid="backend-connect-error">
          {backend.lastConnectError}
        </p>
      )}
      <div className="backend-banner__actions">
        <button type="button" className="backend-banner__btn" data-testid="backend-enter-demo" onClick={() => backendStore.enterDemo()}>
          {t('banner.enterDemo')}
        </button>
        {canRetry && (
          <button
            type="button"
            className="backend-banner__btn"
            data-testid="backend-retry"
            disabled={retrying}
            onClick={() => {
              setRetrying(true);
              void backendStore.connectDesktopBackend().finally(() => setRetrying(false));
            }}
          >
            {t('banner.retry')}
          </button>
        )}
      </div>
    </div>
  );
}

/**
 * English / 中文 switch (D67): a small mark left of the theme switch, faint
 * until hovered, on every page. Same visibility rules as the theme switch.
 */

import { captureClean } from '../config/theme';
import { langStore, useLang, useT } from '../i18n/lang';
import { useViewMode } from '../scene/useViewMode';

export function LangToggle() {
  const lang = useLang();
  const t = useT();
  const viewMode = useViewMode();
  if (viewMode !== 'full' || captureClean) return null;
  return (
    <button
      type="button"
      className="lang-toggle"
      data-testid="lang-toggle"
      lang={lang === 'en' ? 'zh' : 'en'}
      aria-label={t('lang.switch')}
      onClick={() => langStore.toggle()}
    >
      <span className={lang === 'en' ? 'is-on' : ''}>EN</span>
      <span className={lang === 'zh' ? 'is-on' : ''}>中</span>
    </button>
  );
}

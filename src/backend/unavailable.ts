/**
 * The adapter of a product build with no back end connected (D56 default).
 * Every call rejects `UNAVAILABLE`; the UI shows "后端未连接" with a button to
 * enter demo mode by hand. It holds no data and never pretends to.
 *
 * Pure module: no React, DOM or three.
 */

import { BackendError } from './types';
import type { AdapterInfo, AdapterMethod, BrainAdapter } from './types';
import { t } from '../i18n/lang';

export const UNAVAILABLE_LABEL = (): string => t('banner.off');

export class UnavailableAdapter implements BrainAdapter {
  readonly info: AdapterInfo = { kind: 'unavailable', label: UNAVAILABLE_LABEL(), trains: false };

  private fail(): Promise<never> {
    return Promise.reject(new BackendError('UNAVAILABLE', UNAVAILABLE_LABEL()));
  }

  capabilities(): Promise<ReadonlySet<AdapterMethod>> {
    return Promise.resolve(new Set<AdapterMethod>());
  }
  modelEpoch(): Promise<number | null> {
    return Promise.resolve(null);
  }
  accessStatus: BrainAdapter['accessStatus'] = () => this.fail();
  unlock: BrainAdapter['unlock'] = () => this.fail();
  lock: BrainAdapter['lock'] = () => this.fail();
  submit: BrainAdapter['submit'] = () => this.fail();
  preview: BrainAdapter['preview'] = () => this.fail();
  confirm: BrainAdapter['confirm'] = () => this.fail();
  revoke: BrainAdapter['revoke'] = () => this.fail();
  inputList: BrainAdapter['inputList'] = () => this.fail();
  inputPage: BrainAdapter['inputPage'] = () => this.fail();
  inputGet: BrainAdapter['inputGet'] = () => this.fail();
  inputEdit: BrainAdapter['inputEdit'] = () => this.fail();
  inputDelete: BrainAdapter['inputDelete'] = () => this.fail();
  modelReset: BrainAdapter['modelReset'] = () => this.fail();
  state: BrainAdapter['state'] = () => this.fail();
  effects: BrainAdapter['effects'] = () => this.fail();
  rank: BrainAdapter['rank'] = () => this.fail();
}

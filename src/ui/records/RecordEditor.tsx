/**
 * The inline editor of a record that is not agreed (D55). DEMO ONLY: editing
 * is F6, which the back end has not implemented; the button that opens this is
 * greyed out against a real back end (`can('inputEdit')`), so this is only
 * reachable through the labelled mock.
 *
 * What saving does (mock, mirroring the proposal): the text is replaced, the
 * second judgement is reset, every old span and effect no longer applies, and
 * the record returns to 待确认 (当下 T) or 不同意 (当下 F). The box
 * "是否为真（当下）" therefore has to be re-declared with every edit; it starts
 * from the record's current value. The user's text is held only in this
 * component's state until saved: no storage.
 *
 * Escape closes the editor first (inputStore.closeTopLayer), then the row.
 */

import { useEffect, useRef, useState } from 'react';

import { inputStore, useInputs } from '../../app/inputStore';
import { validateEntry } from '../../backend';
import type { InputRecord } from '../../backend';

interface Props {
  rec: InputRecord;
  /** The original text the editor starts from. */
  original: string;
  demoTag: string | null;
}

export function RecordEditor({ rec, original, demoTag }: Props) {
  const s = useInputs();
  const [text, setText] = useState(original);
  const [immediate, setImmediate] = useState(rec.immediate);
  const area = useRef<HTMLTextAreaElement>(null);
  const id = rec.source_id;
  const saving = s.busy.records[id]?.includes('edit') ?? false;
  const error = s.error && s.error.id === id && s.error.action === 'edit' ? s.error : null;

  useEffect(() => {
    area.current?.focus();
  }, []);

  const check = validateEntry({ text, partition: rec.partition, kind: rec.kind, self_speaker: rec.self_speaker ?? undefined });
  const changed = text !== original || immediate !== rec.immediate;
  const next = immediate ? '待确认' : '不同意';

  return (
    <form
      className="rec__editor"
      data-testid="record-editor"
      onSubmit={(e) => {
        e.preventDefault();
        if (check.errors.length > 0 || saving) return;
        void inputStore.edit(id, { text, immediate });
      }}
    >
      <h4 className="rec__h">
        编辑原文{demoTag && <span className="rec__tag">{demoTag}</span>}
      </h4>
      <textarea
        ref={area}
        className="rec__textarea"
        data-testid="editor-text"
        aria-label="原文"
        value={text}
        rows={6}
        onChange={(e) => setText(e.target.value)}
        disabled={saving}
      />
      <label className="rec__check">
        <input type="checkbox" data-testid="editor-immediate" checked={immediate} onChange={(e) => setImmediate(e.target.checked)} disabled={saving} />
        是否为真（当下）
      </label>
      <p className="rec__quiet" data-testid="editor-next">
        保存后二次判断重置，旧证据位置全部失效；记录回到「{next}」。
      </p>
      {check.errors.map((m) => (
        <p key={m} className="rec__error" role="alert" data-testid="editor-error">
          {m}
        </p>
      ))}
      {check.warnings.map((m) => (
        <p key={m} className="rec__quiet" data-testid="editor-warning">
          {m}
        </p>
      ))}
      {error && (
        <p className="rec__error" role="alert" data-testid="record-error">
          <code>{error.code}</code> {error.message}
        </p>
      )}
      <div className="rec__acts">
        <button type="submit" className="rec__act rec__act--primary" data-testid="editor-save" disabled={saving || check.errors.length > 0 || !changed}>
          {saving ? '保存中…' : '保存'}
        </button>
        <button type="button" className="rec__act rec__act--plain" data-testid="editor-cancel" disabled={saving} onClick={() => inputStore.openEditor(null)}>
          取消
        </button>
      </div>
    </form>
  );
}

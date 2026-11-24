import { useEffect, useState } from 'react';
import { message } from 'antd';
import { POLICY_FIELDS } from './mtefLayout';
import { mtefError, usePolicy, useSavePolicy, type PolicyValues } from './useMtef';

const inRange = (text: string) => text.trim() !== '' && Number.isFinite(Number(text)) && Number(text) >= 0 && Number(text) <= 100;

/**
 * The limits the framework is held to. The defaults are a starting point: each government sets its own, and a change takes
 * effect on the next view of the framework.
 */
export default function MtefPolicy() {
  const policy = usePolicy();
  const save = useSavePolicy();
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [golden, setGolden] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!policy.data) return;
    setDraft(Object.fromEntries(POLICY_FIELDS.map((f) => [f.key, String(policy.data![f.key])])));
    setGolden(policy.data.enforce_golden_rule);
  }, [policy.data]);

  const allValid = POLICY_FIELDS.every((f) => inRange(draft[f.key] ?? ''));

  const submit = async () => {
    setError(null);
    try {
      await save.mutateAsync({ ...Object.fromEntries(POLICY_FIELDS.map((f) => [f.key, draft[f.key]])), enforce_golden_rule: golden } as Partial<PolicyValues>);
      message.success('Fiscal rule limits saved');
    } catch (e) { setError(mtefError(e)); }
  };

  if (policy.isLoading) return <p className="mtef-sub">Loading…</p>;

  return (
    <div data-testid="mtef-policy">
      <p className="mtef-sub">These are the government&rsquo;s own limits, not a statute: set them to your fiscal policy.</p>
      <div className="mtef-grid3" style={{ margin: '12px 0' }}>
        {POLICY_FIELDS.map((f) => (
          <div className="mtef-field" key={f.key}>
            <label htmlFor={`policy-${f.key}`}>{f.label}</label>
            <input id={`policy-${f.key}`} data-testid={`policy-${f.key}`} inputMode="decimal" value={draft[f.key] ?? ''}
              aria-invalid={!inRange(draft[f.key] ?? '') || undefined} onChange={(e) => setDraft((d) => ({ ...d, [f.key]: e.target.value }))} />
            <p className="mtef-sub" style={{ fontSize: 12, marginTop: 4 }}>{f.hint}</p>
          </div>
        ))}
      </div>
      <label className="mtef-switch">
        <input type="checkbox" data-testid="policy-golden" checked={golden} onChange={(e) => setGolden(e.target.checked)} style={{ width: 18, height: 18 }} />
        Enforce the golden rule: recurrent spending must fit within recurrent revenue
      </label>
      {error && <div className="mtef-error" role="alert" style={{ marginTop: 12 }}>{error}</div>}
      <div style={{ marginTop: 14 }}>
        <button type="button" className="ef-btn ef-btn-primary" data-testid="policy-save" disabled={!allValid || save.isPending} onClick={submit}>
          {save.isPending ? 'Saving…' : 'Save limits'}
        </button>
        {!allValid && <span className="mtef-sub" style={{ marginLeft: 12 }}>Each limit is a percentage from 0 to 100.</span>}
      </div>
    </div>
  );
}

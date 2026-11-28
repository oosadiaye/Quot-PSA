import { useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { Alert, DatePicker, Table } from 'antd';
import { useDimensionReport, useDimensionTypes, type ReportRow } from './api';

const naira = (v: string | number) => `₦${Number(v).toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

/** Spend by one custom dimension (a Ward report, a Zone report), with a drill-down from a value into its children. */
export default function DimensionReportPage() {
  const { code = '' } = useParams<{ code: string }>();
  const [params, setParams] = useSearchParams();
  const parentValue = params.get('parent');
  const [range, setRange] = useState<{ from?: string; to?: string }>({});
  const types = useDimensionTypes();
  const report = useDimensionReport(code, parentValue, range);
  const child = (types.data ?? []).find((t) => t.parent_type_code === code && t.is_active);
  const total = (report.data?.rows ?? []).reduce((s, r) => s + Number(r.net), 0);

  return (
    <div style={{ padding: '1.25rem', maxWidth: 1000, margin: '0 auto' }} data-testid="dimension-report">
      <p style={{ margin: 0 }}><Link to="/settings/dimensions">Custom dimensions</Link></p>
      <h1 style={{ margin: '4px 0 12px' }}>
        Spend by {report.data?.name ?? code}{parentValue ? ` — under ${parentValue}` : ''}
      </h1>
      <div style={{ display: 'flex', gap: 12, marginBottom: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <DatePicker.RangePicker format="DD/MM/YYYY" onChange={(_, s) => {
          const [from, to] = s as [string, string];
          const iso = (d: string) => (d ? d.split('/').reverse().join('-') : undefined);
          setRange({ from: iso(from), to: iso(to) });
        }} />
        {parentValue && <button type="button" className="btn btn-outline" onClick={() => setParams({})}>Show all</button>}
      </div>
      {report.isError && <Alert type="error" showIcon message="This report could not be loaded." />}
      <Table<ReportRow> rowKey="code" size="middle" loading={report.isLoading} dataSource={report.data?.rows ?? []} pagination={false}
        summary={() => (
          <Table.Summary.Row>
            <Table.Summary.Cell index={0} colSpan={3}><strong>Total</strong></Table.Summary.Cell>
            <Table.Summary.Cell index={1} align="right"><strong data-testid="dim-report-total">{naira(total)}</strong></Table.Summary.Cell>
            <Table.Summary.Cell index={2} />
          </Table.Summary.Row>)}
        columns={[
          { title: report.data?.name ?? 'Value', dataIndex: 'name', render: (n: string, r) => (
            <span data-testid={`dim-report-row-${r.code}`}>
              {r.code === '(untagged)' ? <em>{n}</em> : <strong>{r.code}</strong>}{r.code !== '(untagged)' && ` — ${n}`}
            </span>) },
          { title: 'Debit', dataIndex: 'debit', align: 'right', render: (v: string) => naira(v) },
          { title: 'Credit', dataIndex: 'credit', align: 'right', render: (v: string) => naira(v) },
          { title: 'Net spend', dataIndex: 'net', align: 'right', render: (v: string) => naira(v) },
          { title: '', key: 'drill', width: 150, render: (_, r) => (child && r.code !== '(untagged)'
            ? <Link to={`/accounting/reports/dimension/${child.code}?parent=${encodeURIComponent(r.code)}`}>By {child.name}</Link> : null) },
        ]} />
    </div>
  );
}

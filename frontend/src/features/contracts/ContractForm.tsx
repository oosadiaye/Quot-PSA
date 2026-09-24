import { useEffect, useMemo } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Form, Input, InputNumber, DatePicker, Select, Button, Card,
  Row, Col, App as AntApp, Alert, Tag, Modal,
} from 'antd';
import dayjs from 'dayjs';
import PageHeader from '../../components/PageHeader';
import apiClient from '../../api/client';
import { useContract, useCreateContract, useUpdateContract } from './hooks/useContracts';
import { useVendors } from '../procurement/hooks/useProcurement';
import { useFiscalYears } from '../../hooks/useGovForms';
import { useCurrency } from '../../context/CurrencyContext';
import { formatServiceError } from './utils/errors';
import { retentionAmountFromRate, retentionRateFromAmount } from './utils/retention';
import { ListPageShell } from '../../components/layout';

/** One possible duplicate, as ``contracts/check-duplicate/`` returns it. */
interface DuplicateMatch {
  contract_id: number;
  contract_number: string;
  vendor_name: string;
  similarity: number;
  shared_terms: string[];
  value_difference: string;
  days_apart: number;
}

// ── NCoA segment types — used by the per-segment dropdowns ───────────
interface NCoASegmentRow {
  id: number;
  code: string;
  name?: string;
  full_code?: string;
  description?: string;
  // The economic position is served by /accounting/accounts/, so these
  // rows are GL accounts. Only id / code / name are consumed here; the
  // posting-level and control-account narrowing happens server-side via
  // is_postable / is_reconciliation.
}

// ── Budget appropriation row (subset we render) ──────────────────────
interface AppropriationRow {
  id: number;
  amount_approved: string | number;
  cached_total_committed?: string | number;
  cached_total_expended?: string | number;
  available_balance?: string | number;
  status?: string;
}

// ── Enum choices (frozen on the backend in contracts/models/contract.py) ──
const CONTRACT_TYPE_OPTIONS = [
  { value: 'WORKS',           label: 'Works (Civil / Construction)' },
  { value: 'GOODS',           label: 'Goods / Supply' },
  { value: 'CONSULTANCY',     label: 'Consultancy Services' },
  { value: 'NON_CONSULTANCY', label: 'Non-Consultancy Services' },
];

const PROCUREMENT_METHOD_OPTIONS = [
  { value: 'OPEN_TENDER',   label: 'Open Competitive Tender' },
  { value: 'RESTRICTED',    label: 'Restricted Tender' },
  { value: 'SELECTIVE',     label: 'Selective Tender' },
  { value: 'DIRECT_LABOUR', label: 'Direct Labour' },
  { value: 'DIRECT_AWARD',  label: 'Direct Award (Emergency)' },
];

const ContractForm = () => {
  const { id } = useParams<{ id: string }>();
  const isEdit = !!id && id !== 'new';
  const navigate = useNavigate();
  const { message } = AntApp.useApp();
  const [form] = Form.useForm();

  // Live retention ₦↔% sync. Watch the amount + rate so the ₦ helper input
  // and the reserve/ceiling readout stay in step. Only retention_rate (%) is
  // ever submitted; the ₦ field back-computes it (rate = ₦/amount×100, capped
  // 0–20 in the input's onChange). Reserve = amount × rate / 100.
  const watchedOriginalSum = Form.useWatch('original_sum', form);
  const watchedRetentionRate = Form.useWatch('retention_rate', form);
  const retentionAmount = useMemo(
    () => retentionAmountFromRate(Number(watchedOriginalSum), Number(watchedRetentionRate)),
    [watchedOriginalSum, watchedRetentionRate],
  );
  const contractCeiling = useMemo(() => {
    const amt = Number(watchedOriginalSum) || 0;
    return Math.max(0, amt - retentionAmount);
  }, [watchedOriginalSum, retentionAmount]);
  const fmtNaira = (n: number) =>
    `₦${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  const { data: existing } = useContract(isEdit ? Number(id) : null);

  const { data: vendorsData, isLoading: loadingVendors } = useVendors({ is_active: true, page_size: 500 });
  const vendors = Array.isArray(vendorsData) ? vendorsData : vendorsData?.results ?? [];

  const { data: fiscalYears, isLoading: loadingFys } = useFiscalYears();
  const { formatCurrency } = useCurrency();

  // ── Per-segment NCoA fetches ──────────────────────────────────────
  // Each segment has its own active-only listing. They're independent
  // queries (not chained) because the backend resolves them as a set
  // at submit time via /accounting/ncoa/codes/resolve/. Loading these
  // in parallel keeps the form responsive even on slow connections.
  const fetchSegment = async (path: string): Promise<NCoASegmentRow[]> => {
    const { data } = await apiClient.get(path, {
      params: { is_active: true, page_size: 1000 },
    });
    return Array.isArray(data) ? data : data?.results ?? [];
  };

  // MDA list — fetched from the NCoA AdministrativeSegment endpoint
  // (NOT the legacy ``/accounting/mdas/``) because:
  //   • Contract.mda FK     -> accounting.AdministrativeSegment
  //   • Appropriation.administrative FK -> accounting.AdministrativeSegment
  // The legacy MDA model has different primary keys (linked via
  // AdministrativeSegment.legacy_mda_id). Using the legacy endpoint
  // makes the Appropriation filter ``administrative=<legacy_id>``
  // match nothing, which is what produced the spurious "no
  // appropriation found" warning users were seeing.
  const { data: mdas, isLoading: loadingMdas } = useQuery<NCoASegmentRow[]>({
    queryKey: ['ncoa-administrative-segments'],
    queryFn: () => fetchSegment('/accounting/ncoa/administrative/'),
    staleTime: 5 * 60 * 1000,
  });

  // Economic = "GL Account" in the user's vocabulary, and in
  // public-sector accounting the two really are one list: the NCoA
  // economic segment IS the chart of accounts. The mirror table this
  // used to read has been retired, so it reads the GL directly.
  //
  // The server does the narrowing, which is both cheaper and harder to
  // get wrong than filtering a full chart client-side:
  //   account_type=Expense      NCoA family 2 — expenditure
  //   is_postable=true          leaf accounts only, no headers
  //   is_reconciliation=false   keeps GR/IR and AP control accounts out
  //                             of a contract's expense line
  // The 2-series check below is belt-and-braces for a tenant whose
  // account_type disagrees with its code; ``resolve_code`` rejects the
  // rest server-side at submit.
  const { data: economicAll, isLoading: loadingEconomic } = useQuery<NCoASegmentRow[]>({
    queryKey: ['gl-expenditure-accounts'],
    queryFn: async () => {
      const { data } = await apiClient.get('/accounting/accounts/', {
        params: {
          account_type: 'Expense',
          is_postable: true,
          is_reconciliation: false,
          is_active: true,
          page_size: 1000,
          ordering: 'code',
        },
      });
      return Array.isArray(data) ? data : data?.results ?? [];
    },
    staleTime: 5 * 60 * 1000,
  });
  const economicSegments = useMemo<NCoASegmentRow[]>(
    () => (economicAll ?? []).filter((acct) => acct.code?.startsWith('2')),
    [economicAll],
  );

  const { data: fundSegments, isLoading: loadingFunds } = useQuery<NCoASegmentRow[]>({
    queryKey: ['ncoa-fund-segments'],
    queryFn: () => fetchSegment('/accounting/ncoa/fund/'),
    staleTime: 5 * 60 * 1000,
  });

  const { data: programmeSegments, isLoading: loadingProgrammes } = useQuery<NCoASegmentRow[]>({
    queryKey: ['ncoa-programme-segments'],
    queryFn: () => fetchSegment('/accounting/ncoa/programme/'),
    staleTime: 5 * 60 * 1000,
  });

  const { data: functionalSegments, isLoading: loadingFunctional } = useQuery<NCoASegmentRow[]>({
    queryKey: ['ncoa-functional-segments'],
    queryFn: () => fetchSegment('/accounting/ncoa/functional/'),
    staleTime: 5 * 60 * 1000,
  });

  const { data: geoSegments, isLoading: loadingGeo } = useQuery<NCoASegmentRow[]>({
    queryKey: ['ncoa-geographic-segments'],
    queryFn: () => fetchSegment('/accounting/ncoa/geographic/'),
    staleTime: 5 * 60 * 1000,
  });

  const createMut = useCreateContract();
  const updateMut = useUpdateContract();

  useEffect(() => {
    if (existing) {
      form.setFieldsValue({
        ...existing,
        // Map the existing ncoa_code's segments back into the new
        // per-segment fields when editing — so the form prefill
        // reflects the same combination the contract was created with.
        economic:   existing.ncoa_code_economic_id,
        fund:       existing.ncoa_code_fund_id,
        programme:  existing.ncoa_code_programme_id,
        functional: existing.ncoa_code_functional_id,
        geographic: existing.ncoa_code_geographic_id,
        signed_date: existing.signed_date ? dayjs(existing.signed_date) : null,
        commencement_date: existing.commencement_date ? dayjs(existing.commencement_date) : null,
        contract_start_date: existing.contract_start_date ? dayjs(existing.contract_start_date) : null,
        contract_end_date: existing.contract_end_date ? dayjs(existing.contract_end_date) : null,
      });
    }
  }, [existing, form]);

  // ── Watch the budget-relevant segments + amount for live availability ───
  // Form.useWatch returns the current value of a field on every render
  // — perfect for driving a dependent React Query. We watch MDA, fund,
  // economic, fiscal year, and original_sum because those four
  // dimensions uniquely identify the appropriation line + the amount
  // we're trying to encumber against it.
  const watchedMda    = Form.useWatch('mda', form);
  const watchedFund   = Form.useWatch('fund', form);
  const watchedEcon   = Form.useWatch('economic', form);
  const watchedFy     = Form.useWatch('fiscal_year', form);
  const watchedAmount = Form.useWatch('original_sum', form);

  const canQueryAppropriation =
    !!watchedMda && !!watchedFund && !!watchedEcon && !!watchedFy;

  const { data: appropriations } = useQuery<AppropriationRow[]>({
    queryKey: ['contract-appropriation-lookup', watchedMda, watchedFund, watchedEcon, watchedFy],
    queryFn: async () => {
      const { data } = await apiClient.get('/budget/appropriations/', {
        params: {
          administrative: watchedMda,
          fund:           watchedFund,
          economic:       watchedEcon,
          fiscal_year:    watchedFy,
          status:         'ACTIVE',
          page_size:      10,
        },
      });
      return Array.isArray(data) ? data : data?.results ?? [];
    },
    enabled: canQueryAppropriation,
    staleTime: 30 * 1000,
  });

  const matchedAppropriation: AppropriationRow | null =
    (appropriations && appropriations.length > 0) ? appropriations[0] : null;
  const availableBalance: number = parseFloat(
    String(matchedAppropriation?.available_balance ?? 0),
  ) || 0;
  const requestedAmount: number = parseFloat(String(watchedAmount ?? 0)) || 0;
  const overBudget: boolean =
    !!matchedAppropriation && requestedAmount > availableBalance && requestedAmount > 0;

  /**
   * Ask the server whether this contract already exists, and if so make
   * the clerk say why they are saving it anyway.
   *
   * Runs before the NCoA resolution below because that is a round trip
   * and a write-ish operation (``resolve_code`` creates the composite
   * code on first use) — there is no sense minting one for a contract
   * that is about to be abandoned.
   *
   * Returns the acknowledgement to attach, or null to abort the save.
   * Soft by design, matching the over-budget gate a few lines down: a
   * clerk may know this is a re-award after a termination. A hard block
   * would be worked around by rewording the title, which is exactly the
   * behaviour that makes duplicates invisible.
   */
  const confirmNotDuplicate = async (
    values: {
      vendor?: number;
      title?: string;
      original_sum?: number | string;
      signed_date?: { format: (f: string) => string } | null;
    },
  ): Promise<{ duplicate_ack_ids: number[]; duplicate_ack_reason: string } | null> => {
    let matches: DuplicateMatch[] = [];
    try {
      const { data } = await apiClient.post('/contracts/contracts/check-duplicate/', {
        id: isEdit ? Number(id) : 0,
        vendor: values.vendor,
        title: values.title,
        original_sum: values.original_sum,
        signed_date: values.signed_date?.format('YYYY-MM-DD') ?? null,
      });
      matches = data?.matches ?? [];
    } catch {
      // A duplicate check that cannot run must not stop a legitimate
      // contract being captured. It is a warning, not a control.
      return { duplicate_ack_ids: [], duplicate_ack_reason: '' };
    }

    if (!matches.length) return { duplicate_ack_ids: [], duplicate_ack_reason: '' };

    return new Promise((resolve) => {
      let reason = '';
      Modal.confirm({
        title: matches.length === 1
          ? 'This looks like a contract already on the register'
          : `This looks like ${matches.length} contracts already on the register`,
        width: 640,
        okText: 'Save anyway',
        okButtonProps: { danger: true },
        cancelText: 'Go back and check',
        content: (
          <div>
            <p style={{ marginTop: 8, color: '#475569' }}>
              Same contractor, a similar value, and a title that reads as the
              same requirement. Saving a second time creates a second contract
              number and a second payment stream.
            </p>
            {matches.map((m) => (
              <div key={m.contract_id} style={{
                border: '1px solid #fca5a5', background: '#fef2f2',
                borderRadius: 8, padding: '10px 12px', marginBottom: 8, fontSize: 13,
              }}>
                <div style={{ fontWeight: 700 }}>
                  {m.contract_number || `Contract #${m.contract_id}`}
                  <span style={{ float: 'right', fontWeight: 600 }}>
                    {Math.round(m.similarity * 100)}% title match
                  </span>
                </div>
                <div style={{ color: '#7f1d1d', marginTop: 4 }}>
                  Shared wording: {m.shared_terms.join(', ') || '—'}
                </div>
                <div style={{ color: '#7f1d1d' }}>
                  Value differs by {formatCurrency(Number(m.value_difference))}
                  {' · '}signed {m.days_apart} day{m.days_apart === 1 ? '' : 's'} apart
                </div>
              </div>
            ))}
            <label style={{ fontSize: 12.5, fontWeight: 600, color: '#334155' }}>
              Why is this a different contract?
            </label>
            <Input.TextArea
              rows={2}
              placeholder="e.g. re-award after termination of DSG/WORKS/2026/003"
              onChange={(e) => { reason = e.target.value; }}
              style={{ marginTop: 4 }}
            />
            <div style={{ fontSize: 11.5, color: '#64748b', marginTop: 6 }}>
              Recorded on the contract against your name, so an auditor asking
              later finds the answer here rather than in somebody&rsquo;s memory.
            </div>
          </div>
        ),
        onOk: () => resolve({
          duplicate_ack_ids: matches.map((m) => m.contract_id),
          duplicate_ack_reason: reason.trim(),
        }),
        onCancel: () => resolve(null),
      });
    });
  };

  const onFinish = async (values: any) => {
    const ack = await confirmNotDuplicate(values);
    if (ack === null) return;                 // clerk chose to go back

    // ── Step 1: Resolve the 5 segment IDs the user picked into a
    // single ncoa_code id. The backend's ``resolve_code`` action
    // accepts CODE strings (not IDs) and returns the composite
    // NCoACode (creating it on first use). We therefore look up the
    // code strings from our cached segment lists.
    const codeOf = (rows: NCoASegmentRow[] | undefined, id: number | undefined): string | null => {
      if (!id || !rows) return null;
      const row = rows.find((r) => r.id === id);
      return row?.code ?? null;
    };
    const adminCode      = codeOf(mdas, values.mda);
    const economicCode   = codeOf(economicSegments, values.economic);
    const functionalCode = codeOf(functionalSegments, values.functional);
    const programmeCode  = codeOf(programmeSegments, values.programme);
    const fundCode       = codeOf(fundSegments, values.fund);
    const geoCode        = codeOf(geoSegments, values.geographic);
    if (!adminCode || !economicCode || !functionalCode || !programmeCode || !fundCode || !geoCode) {
      message.error('Could not resolve the selected segments. Please re-pick the missing field.');
      return;
    }

    let resolvedNcoaCodeId: number;
    try {
      const { data } = await apiClient.post('/accounting/ncoa/codes/resolve/', {
        admin_code:      adminCode,
        economic_code:   economicCode,
        functional_code: functionalCode,
        programme_code:  programmeCode,
        fund_code:       fundCode,
        geo_code:        geoCode,
      });
      resolvedNcoaCodeId = data.id;
    } catch (e) {
      message.error(formatServiceError(e, 'NCoA resolution failed — check your segment selections'));
      return;
    }

    // ── Step 2: Soft budget gate. We only WARN on over-budget; the
    // backend's commitment-creation pipeline does the hard check
    // again at IPC payment time. This matches IPSAS practice: a
    // signed contract can exceed the current appropriation if a
    // supplementary appropriation is expected.
    if (overBudget && !values._budget_overridden) {
      const proceed = window.confirm(
        `Contract amount ${formatCurrency(requestedAmount)} exceeds the available `
        + `balance ${formatCurrency(availableBalance)} on this appropriation.\n\n`
        + `Click OK to proceed (a supplementary appropriation or virement may be required), `
        + `or Cancel to revise the amount.`,
      );
      if (!proceed) return;
    }

    const payload = {
      ...values,
      ...ack,
      ncoa_code: resolvedNcoaCodeId,
      // Note: ``Contract.appropriation`` FK points at the LEGACY
      // ``accounting.BudgetEncumbrance`` model (not the modern
      // ``budget.Appropriation`` that the live-balance panel above
      // queries). Setting it here would crash with "Invalid pk —
      // object does not exist" because the IDs are from different
      // tables. We deliberately leave it null: the contract is still
      // tied to the appropriation via ``ncoa_code`` (MDA × Economic
      // × Fund × FY uniquely identifies one Appropriation row), and
      // the IPC commitment pipeline runs ``find_matching_appropriation``
      // to resolve the right budget line at each payment time.
      signed_date: values.signed_date?.format('YYYY-MM-DD') ?? null,
      commencement_date: values.commencement_date?.format('YYYY-MM-DD') ?? null,
      contract_start_date: values.contract_start_date?.format('YYYY-MM-DD') ?? null,
      contract_end_date: values.contract_end_date?.format('YYYY-MM-DD') ?? null,
    };
    // Strip the segment-level fields — backend doesn't recognise them.
    delete payload.economic;
    delete payload.functional;
    delete payload.programme;
    delete payload.geographic;
    delete payload._budget_overridden;

    try {
      if (isEdit) {
        await updateMut.mutateAsync({ id: Number(id), payload });
        message.success('Contract updated');
      } else {
        const created = await createMut.mutateAsync(payload);
        message.success('Contract created');
        navigate(`/contracts/${created.id}`);
        return;
      }
      navigate('/contracts');
    } catch (e) {
      message.error(formatServiceError(e, 'Save failed'));
    }
  };

  // ── Generic fuzzy-match filter for all searchable selects ───────────
  const filterByLabelOrSearchText = (input: string, option: any) => {
    const needle = input.trim().toLowerCase();
    if (!needle) return true;
    const haystack = [option?.label, option?.searchText]
      .filter(Boolean)
      .join(' ')
      .toLowerCase();
    return haystack.includes(needle);
  };

  return (
    <ListPageShell>
        <PageHeader title={isEdit ? 'Edit Contract' : 'New Contract'} />
        <div style={{ maxWidth: '880px' }}>
          <Card>
            <Form
              form={form}
              layout="vertical"
              onFinish={onFinish}
              initialValues={{
                contract_type: 'WORKS',
                procurement_method: 'OPEN_TENDER',
                // Retention is no longer pre-filled. Many contracts
                // (consultancy, supply, service) carry no retention;
                // pre-filling 5% trained operators to think it's
                // automatic. Leave blank — operator opts in by typing
                // a rate, omission is saved as 0%.
                mobilization_rate: 0,
                defects_liability_period_days: 365,
              }}
            >
              {/* ── Identity ─────────────────────────────────────── */}
              <Row gutter={24}>
                <Col xs={24} md={12}>
                  <Form.Item
                    label="Reference / File Number"
                    name="reference"
                    tooltip="Internal reference (does not replace the auto-assigned contract number)"
                  >
                    <Input placeholder="e.g. DTS/WKS/2026/0001" />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item
                    label="Contract Type"
                    name="contract_type"
                    rules={[{ required: true, message: 'Contract type required' }]}
                  >
                    <Select options={CONTRACT_TYPE_OPTIONS} />
                  </Form.Item>
                </Col>
              </Row>

              <Form.Item
                label="Title"
                name="title"
                rules={[{ required: true, message: 'Title required' }]}
              >
                <Input placeholder="e.g. Warri–Sapele Road (Section A) Rehabilitation" />
              </Form.Item>

              <Form.Item label="Description" name="description">
                <Input.TextArea rows={3} placeholder="Scope summary (optional)" />
              </Form.Item>

              {/* ── Counterparties ──────────────────────────────── */}
              <Row gutter={24}>
                <Col xs={24} md={12}>
                  <Form.Item
                    label="Vendor"
                    name="vendor"
                    rules={[{ required: true, message: 'Vendor required' }]}
                  >
                    <Select
                      showSearch
                      placeholder={loadingVendors ? 'Loading vendors…' : 'Search by vendor name or code…'}
                      loading={loadingVendors}
                      optionFilterProp="label"
                      filterOption={filterByLabelOrSearchText}
                      notFoundContent={loadingVendors ? 'Loading…' : 'No active vendors.'}
                      options={vendors.map((v: any) => {
                        const code = v.code ?? '';
                        const name = v.name ?? `Vendor #${v.id}`;
                        return {
                          value: v.id,
                          label: code ? `${code} · ${name}` : name,
                          searchText: [code, name, v.tax_id, v.registration_number].filter(Boolean).join(' '),
                        };
                      })}
                    />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item
                    label="MDA (Administrative Segment)"
                    name="mda"
                    rules={[{ required: true, message: 'MDA required' }]}
                    tooltip="Implementing / procuring MDA — must match the appropriation's MDA"
                  >
                    <Select
                      showSearch
                      placeholder={loadingMdas ? 'Loading MDAs…' : 'Search by MDA code or name…'}
                      loading={loadingMdas}
                      optionFilterProp="label"
                      filterOption={filterByLabelOrSearchText}
                      options={(mdas ?? []).map((m) => ({
                        value: m.id,
                        label: `${m.code} · ${m.name ?? ''}`,
                        searchText: [m.code, m.name].filter(Boolean).join(' '),
                      }))}
                    />
                  </Form.Item>
                </Col>
              </Row>

              {/* ── Budget classification (per-segment) ─────────── */}
              {/* Each NCoA segment is picked individually so the user can
                  see — and the form can validate — exactly which slice
                  of the budget the contract draws against. The 5
                  segments below + the MDA above are resolved into a
                  single NCoACode at submit time via /accounting/ncoa/
                  codes/resolve/, which auto-creates the composite if
                  needed (NCoACode is a unique tuple of all 6 segments). */}
              <Row gutter={24}>
                <Col xs={24} md={12}>
                  <Form.Item
                    label="GL Account (Economic Segment)"
                    name="economic"
                    rules={[{ required: true, message: 'GL account required' }]}
                    tooltip="The expenditure GL account this contract is charged to"
                  >
                    <Select
                      showSearch
                      placeholder={loadingEconomic ? 'Loading GL accounts…' : 'Search by code or name…'}
                      loading={loadingEconomic}
                      optionFilterProp="label"
                      filterOption={filterByLabelOrSearchText}
                      options={economicSegments.map((s) => ({
                        value: s.id,
                        label: `${s.code} · ${s.name ?? ''}`,
                        searchText: [s.code, s.name, s.description].filter(Boolean).join(' '),
                      }))}
                    />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item
                    label="Fund"
                    name="fund"
                    rules={[{ required: true, message: 'Fund required' }]}
                    tooltip="Source of funds — Consolidated Revenue, Capital Development, etc."
                  >
                    <Select
                      showSearch
                      placeholder={loadingFunds ? 'Loading funds…' : 'Search by fund code or name…'}
                      loading={loadingFunds}
                      optionFilterProp="label"
                      filterOption={filterByLabelOrSearchText}
                      options={(fundSegments ?? []).map((s) => ({
                        value: s.id,
                        label: `${s.code} · ${s.name ?? ''}`,
                        searchText: [s.code, s.name].filter(Boolean).join(' '),
                      }))}
                    />
                  </Form.Item>
                </Col>
              </Row>

              <Row gutter={24}>
                <Col xs={24} md={12}>
                  <Form.Item
                    label="Funded Programme"
                    name="programme"
                    rules={[{ required: true, message: 'Programme required' }]}
                    tooltip="Government programme funding this expenditure"
                  >
                    <Select
                      showSearch
                      placeholder={loadingProgrammes ? 'Loading programmes…' : 'Search…'}
                      loading={loadingProgrammes}
                      optionFilterProp="label"
                      filterOption={filterByLabelOrSearchText}
                      options={(programmeSegments ?? []).map((s) => ({
                        value: s.id,
                        label: `${s.code} · ${s.name ?? ''}`,
                        searchText: [s.code, s.name].filter(Boolean).join(' '),
                      }))}
                    />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item
                    label="Function (COFOG)"
                    name="functional"
                    rules={[{ required: true, message: 'Function required' }]}
                    tooltip="UN COFOG functional classification"
                  >
                    <Select
                      showSearch
                      placeholder={loadingFunctional ? 'Loading functions…' : 'Search…'}
                      loading={loadingFunctional}
                      optionFilterProp="label"
                      filterOption={filterByLabelOrSearchText}
                      options={(functionalSegments ?? []).map((s) => ({
                        value: s.id,
                        label: `${s.code} · ${s.name ?? ''}`,
                        searchText: [s.code, s.name].filter(Boolean).join(' '),
                      }))}
                    />
                  </Form.Item>
                </Col>
              </Row>

              <Row gutter={24}>
                <Col xs={24} md={12}>
                  <Form.Item
                    label="Geographic Location"
                    name="geographic"
                    rules={[{ required: true, message: 'Geographic location required' }]}
                    tooltip="LGA / district / facility this contract serves"
                  >
                    <Select
                      showSearch
                      placeholder={loadingGeo ? 'Loading locations…' : 'Search…'}
                      loading={loadingGeo}
                      optionFilterProp="label"
                      filterOption={filterByLabelOrSearchText}
                      options={(geoSegments ?? []).map((s) => ({
                        value: s.id,
                        label: `${s.code} · ${s.name ?? ''}`,
                        searchText: [s.code, s.name].filter(Boolean).join(' '),
                      }))}
                    />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item
                    label="Fiscal Year"
                    name="fiscal_year"
                    rules={[{ required: true, message: 'Fiscal year required' }]}
                  >
                    <Select
                      showSearch
                      placeholder={loadingFys ? 'Loading…' : 'Select fiscal year'}
                      loading={loadingFys}
                      optionFilterProp="label"
                      filterOption={filterByLabelOrSearchText}
                      options={(fiscalYears ?? []).map((f: any) => ({
                        value: f.id,
                        label: f.year ?? f.name ?? `FY #${f.id}`,
                      }))}
                    />
                  </Form.Item>
                </Col>
              </Row>

              {/* ── Live budget availability panel ──────────────── */}
              {/* Once MDA + GL + Fund + FY are all picked, we surface
                  the matching appropriation's balance so the operator
                  knows whether the contract amount they're typing
                  fits inside the line. Soft warning only — backend
                  enforces the hard ceiling at IPC commitment time. */}
              {canQueryAppropriation && (
                <div style={{ marginBottom: 16 }}>
                  {matchedAppropriation ? (
                    <Alert
                      type={overBudget ? 'error' : 'info'}
                      showIcon
                      message={
                        <span>
                          Budget Appropriation matched
                          {' '}<Tag color={overBudget ? 'error' : 'success'}>
                            {matchedAppropriation.status ?? 'ACTIVE'}
                          </Tag>
                        </span>
                      }
                      description={
                        <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginTop: 4 }}>
                          <span>
                            <strong>Approved:</strong> {formatCurrency(parseFloat(String(matchedAppropriation.amount_approved ?? 0)))}
                          </span>
                          <span>
                            <strong>Committed:</strong> {formatCurrency(parseFloat(String(matchedAppropriation.cached_total_committed ?? 0)))}
                          </span>
                          <span>
                            <strong>Expended:</strong> {formatCurrency(parseFloat(String(matchedAppropriation.cached_total_expended ?? 0)))}
                          </span>
                          <span style={{ color: overBudget ? '#cf1322' : '#389e0d', fontWeight: 600 }}>
                            <strong>Available:</strong> {formatCurrency(availableBalance)}
                          </span>
                          {overBudget && (
                            <span style={{ color: '#cf1322', fontWeight: 600 }}>
                              ⚠ Contract amount exceeds available by {formatCurrency(requestedAmount - availableBalance)}
                            </span>
                          )}
                        </div>
                      }
                    />
                  ) : (
                    <Alert
                      type="warning"
                      showIcon
                      message="No matching active appropriation found"
                      description={
                        'No ACTIVE Appropriation exists for this MDA × GL × Fund × Fiscal Year combination. '
                        + 'You can still save the contract, but no budget will be encumbered until an appropriation is approved.'
                      }
                    />
                  )}
                </div>
              )}

              {/* ── Money ────────────────────────────────────────── */}
              <Row gutter={24}>
                <Col xs={24} md={12}>
                  <Form.Item
                    label="Original Sum"
                    name="original_sum"
                    rules={[{ required: true, message: 'Original sum required' }]}
                    tooltip="Award value. Ceiling = original_sum + approved write-ups."
                  >
                    <InputNumber
                      min={0.01}
                      style={{ width: '100%' }}
                      step={1000}
                      formatter={(v) => (v !== undefined && v !== null ? `₦ ${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',') : '')}
                      parser={(v) => (v ? v.replace(/[^\d.]/g, '') : '') as unknown as 0.01}
                    />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item
                    label="Procurement Method"
                    name="procurement_method"
                    rules={[{ required: true }]}
                  >
                    <Select options={PROCUREMENT_METHOD_OPTIONS} />
                  </Form.Item>
                </Col>
              </Row>

              <Row gutter={24}>
                <Col xs={24} md={12}>
                  <Form.Item
                    label="Retention Rate (%)"
                    name="retention_rate"
                    tooltip="Optional. Leave blank for contracts without retention (consultancy, supply, service). DB-enforced 0–20%. Works contracts typically use 5%."
                    style={{ marginBottom: 8 }}
                  >
                    <InputNumber min={0} max={20} style={{ width: '100%' }} step={0.5} placeholder="Blank = no retention" />
                  </Form.Item>
                  {/* …or enter retention as a ₦ value — synced to the % above.
                      Only retention_rate is submitted; this back-computes it.
                      Needs an Original Sum first (to convert ₦→%). */}
                  <Form.Item
                    label="…or Retention Amount (₦)"
                    tooltip="Enter retention as a naira value; it converts to the % above (rate = amount ÷ original sum, capped 20%). Requires an Original Sum."
                    style={{ marginBottom: 4 }}
                  >
                    <InputNumber
                      min={0}
                      style={{ width: '100%' }}
                      step={1000}
                      value={retentionAmount || undefined}
                      disabled={!(Number(watchedOriginalSum) > 0)}
                      placeholder={Number(watchedOriginalSum) > 0 ? '0.00' : 'Set Original Sum first'}
                      formatter={(v) => (v !== undefined && v !== null ? `₦ ${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',') : '')}
                      parser={(v) => (v ? v.replace(/[^\d.]/g, '') : '') as unknown as number}
                      onChange={(val) => {
                        const amt = Number(watchedOriginalSum) || 0;
                        if (amt <= 0) return;
                        form.setFieldsValue({
                          retention_rate: retentionRateFromAmount(amt, Number(val)),
                        });
                      }}
                    />
                  </Form.Item>
                  {(Number(watchedOriginalSum) > 0) && (
                    <div style={{ fontSize: 12, color: '#64748b', marginBottom: 8 }}>
                      Reserve {fmtNaira(retentionAmount)} · Ceiling {fmtNaira(contractCeiling)}
                    </div>
                  )}
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item
                    label="Mobilization Rate (%)"
                    name="mobilization_rate"
                    tooltip="DB-enforced 0–30%. Set 0 if no advance."
                  >
                    <InputNumber min={0} max={30} style={{ width: '100%' }} step={0.5} />
                  </Form.Item>
                </Col>
              </Row>

              {/* ── Dates ────────────────────────────────────────── */}
              <Row gutter={24}>
                <Col xs={24} md={12}>
                  <Form.Item label="Signed Date" name="signed_date">
                    <DatePicker style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item label="Commencement Date" name="commencement_date">
                    <DatePicker style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
              </Row>

              <Row gutter={24}>
                <Col xs={24} md={12}>
                  <Form.Item label="Contract Start Date" name="contract_start_date">
                    <DatePicker style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item label="Contract End Date" name="contract_end_date">
                    <DatePicker style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
              </Row>

              {/* ── Compliance ───────────────────────────────────── */}
              <Row gutter={24}>
                <Col xs={24} md={12}>
                  <Form.Item
                    label="BPP No Objection Ref"
                    name="bpp_no_objection_ref"
                    tooltip="BPP Certificate of No Objection reference"
                  >
                    <Input placeholder="BPP/CNO/..." />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item
                    label="Defects Liability Period (days)"
                    name="defects_liability_period_days"
                  >
                    <InputNumber min={0} style={{ width: '100%' }} step={30} />
                  </Form.Item>
                </Col>
              </Row>

              <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end', marginTop: '16px' }}>
                <Button onClick={() => navigate('/contracts')}>Cancel</Button>
                <Button
                  type="primary"
                  htmlType="submit"
                  loading={createMut.isPending || updateMut.isPending}
                >
                  {isEdit ? 'Save' : 'Create'}
                </Button>
              </div>
            </Form>
          </Card>
        </div>
    </ListPageShell>
  );
};

export default ContractForm;

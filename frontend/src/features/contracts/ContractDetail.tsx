/**
 * Contract Detail — redesigned per Stitch reference (Project Intelligence
 * Dashboard, Delta State). Visual language: indigo hero gradient, soft
 * neutral canvas, white cards with thin borders, two-column main +
 * right sidebar layout with budget pulse / stakeholders / activity log.
 *
 * Preserves existing data wiring (useContract, useContractBalance,
 * useIPCs, useVariations) and existing business actions (activate /
 * close / edit / new IPC / new variation). Status mapping compresses
 * the 7-state backend lifecycle into a 5-step visual stepper:
 *   Draft → Activated → In Progress → Completion → Closed
 * where Completion encompasses PRACTICAL_COMPLETION / DEFECTS_LIABILITY
 * / FINAL_COMPLETION. The full status name is still shown as a tag in
 * the hero so auditors don't lose granularity.
 */
import { useNavigate, useParams } from 'react-router-dom';
import {
  Popconfirm, Button, App as AntApp,
  Modal, Form, Input, InputNumber, DatePicker,
} from 'antd';
import { useQuery } from '@tanstack/react-query';
import dayjs from 'dayjs';
import apiClient from '../../api/client';
import {
  ArrowLeft, ChevronRight, Tag as TagIcon, Hash, Check,
  Plus, Edit2, MessageCircle, Info, UserPlus,
} from 'lucide-react';
import { ListPageShell } from '../../components/layout';
import LoadingScreen from '../../components/common/LoadingScreen';
import {
  useContract, useContractBalance,
  useActivateContract, useCloseContract,
  useCreateMilestone, useStartMilestone, useApproveMilestone,
  useConvertMilestoneToIPC,
  useContractMobilization, useIssueMobilization,
  useContractRetentionReleases, useCreateRetentionRelease,
} from './hooks/useContracts';
import { useIPCs } from './hooks/useIPCs';
import { useVariations } from './hooks/useVariations';
import UnclearedAdvanceWarning from '../accounting/vendor-advance/UnclearedAdvanceWarning';
import { useCurrency } from '../../context/CurrencyContext';
import { formatServiceError } from './utils/errors';
import { useMemo, useState } from 'react';

// ── Status mapping ──────────────────────────────────────────────────
// 7 backend statuses → 5 visual phases for the compact stepper.
// The granular status is still shown as a coloured tag in the hero.
type ContractStatus =
  | 'DRAFT' | 'ACTIVATED' | 'IN_PROGRESS'
  | 'PRACTICAL_COMPLETION' | 'DEFECTS_LIABILITY' | 'FINAL_COMPLETION'
  | 'CLOSED';

interface PhaseSpec {
  key: string;
  label: string;
  /** Lower-bound index into ALL backend statuses that triggers
   *  this visual phase. The current phase is the highest index
   *  whose threshold is satisfied. */
  reachedAt: ContractStatus[];
}

const PHASES: PhaseSpec[] = [
  { key: 'draft',      label: 'Draft',       reachedAt: ['DRAFT'] },
  { key: 'activated',  label: 'Activated',   reachedAt: ['ACTIVATED'] },
  { key: 'inProgress', label: 'In Progress', reachedAt: ['IN_PROGRESS'] },
  { key: 'completion', label: 'Completion',  reachedAt: ['PRACTICAL_COMPLETION', 'DEFECTS_LIABILITY', 'FINAL_COMPLETION'] },
  { key: 'closed',     label: 'Closed',      reachedAt: ['CLOSED'] },
];

const STATUS_TAG_COLOR: Record<ContractStatus, { bg: string; fg: string }> = {
  DRAFT:                { bg: 'rgba(148,163,184,0.20)', fg: '#cbd5e1' },
  ACTIVATED:            { bg: 'rgba(99,102,241,0.20)',  fg: '#a5b4fc' },
  IN_PROGRESS:          { bg: 'rgba(34,211,238,0.20)',  fg: '#67e8f9' },
  PRACTICAL_COMPLETION: { bg: 'rgba(251,191,36,0.20)',  fg: '#fcd34d' },
  DEFECTS_LIABILITY:    { bg: 'rgba(167,139,250,0.20)', fg: '#c4b5fd' },
  FINAL_COMPLETION:     { bg: 'rgba(52,211,153,0.20)',  fg: '#6ee7b7' },
  CLOSED:               { bg: 'rgba(52,211,153,0.30)',  fg: '#34d399' },
};

const ALL_STATUSES_ORDER: ContractStatus[] = [
  'DRAFT', 'ACTIVATED', 'IN_PROGRESS',
  'PRACTICAL_COMPLETION', 'DEFECTS_LIABILITY', 'FINAL_COMPLETION',
  'CLOSED',
];

function currentPhaseIndex(status: ContractStatus): number {
  // Walk PHASES top-down — the last phase whose ``reachedAt`` includes
  // the current status (or any earlier status in the linear order)
  // wins. CLOSED is treated as its own terminal phase.
  if (status === 'CLOSED') return 4;
  const statusIdx = ALL_STATUSES_ORDER.indexOf(status);
  for (let i = PHASES.length - 1; i >= 0; i--) {
    const reachedAtThreshold = Math.min(
      ...PHASES[i].reachedAt.map((s) => ALL_STATUSES_ORDER.indexOf(s)),
    );
    if (statusIdx >= reachedAtThreshold) return i;
  }
  return 0;
}


// ── Tab type ─────────────────────────────────────────────────────────
type TabKey = 'milestones' | 'ipcs' | 'variations';


// ──────────────────────────────────────────────────────────────────────
// Component
// ──────────────────────────────────────────────────────────────────────
const ContractDetail = () => {
  const { id } = useParams<{ id: string }>();
  const cid = Number(id);
  const navigate = useNavigate();
  const { formatCurrency } = useCurrency();
  const { message } = AntApp.useApp();
  const [activeTab, setActiveTab] = useState<TabKey>('milestones');

  const { data: contract, isLoading: loadingC } = useContract(cid);
  const { data: balance } = useContractBalance(cid);
  const { data: ipcs } = useIPCs({ contract: cid });
  const { data: variations } = useVariations({ contract: cid });

  // ── Original budget from the matching Appropriation ──────────────
  // Fires when MDA + economic + fund + fiscal year are all present
  // on the loaded contract. Returns the single ACTIVE Appropriation
  // row whose tuple matches — same lookup the New Contract form uses
  // for its live-balance panel. Keeping this as a dependent query
  // (not denormalised on the contract serializer) means the card
  // refreshes when supplementary appropriations or virements adjust
  // the line, without a contract-level cache invalidation.
  const apprAdminId = contract?.mda;
  const apprEconId  = contract?.ncoa_code_economic_id;
  const apprFundId  = contract?.ncoa_code_fund_id;
  const apprFyId    = contract?.fiscal_year;
  const canQueryAppr = !!apprAdminId && !!apprEconId && !!apprFundId && !!apprFyId;
  const { data: appropriationMatches } = useQuery({
    queryKey: [
      'contract-appropriation', cid,
      apprAdminId, apprEconId, apprFundId, apprFyId,
    ],
    queryFn: async () => {
      const { data } = await apiClient.get('/budget/appropriations/', {
        params: {
          administrative: apprAdminId,
          fund:           apprFundId,
          economic:       apprEconId,
          fiscal_year:    apprFyId,
          status:         'ACTIVE',
          page_size:      5,
        },
      });
      return Array.isArray(data) ? data : (data?.results ?? []);
    },
    enabled: canQueryAppr,
    staleTime: 30 * 1000,
  });
  const matchedAppropriation = (appropriationMatches && appropriationMatches[0]) || null;
  const apprApproved = parseFloat(String(matchedAppropriation?.amount_approved ?? 0)) || 0;
  const apprAvailable = parseFloat(String(matchedAppropriation?.available_balance ?? 0)) || 0;

  const activateMut = useActivateContract();
  const closeMut = useCloseContract();
  const createMilestoneMut = useCreateMilestone();
  const startMilestoneMut = useStartMilestone();
  const approveMilestoneMut = useApproveMilestone();

  const handleStartMilestone = async (milestoneId: number) => {
    try {
      await startMilestoneMut.mutateAsync({ id: milestoneId, contractId: cid });
      message.success('Milestone marked as in progress.');
    } catch (e) {
      message.error(formatServiceError(e, 'Failed to start milestone'));
    }
  };

  const handleApproveMilestone = async (milestoneId: number) => {
    try {
      await approveMilestoneMut.mutateAsync({ id: milestoneId, contractId: cid });
      message.success('Milestone approved — IPC can now be raised against it.');
    } catch (e) {
      message.error(formatServiceError(e, 'Failed to approve milestone'));
    }
  };

  const convertMilestoneMut = useConvertMilestoneToIPC();
  const { data: mobilizationPayment } = useContractMobilization(cid);
  const issueMobilizationMut = useIssueMobilization();

  const handleIssueMobilization = async () => {
    try {
      await issueMobilizationMut.mutateAsync(cid);
      message.success(
        'Mobilization advance issued. Now create a Payment Voucher in Treasury to disburse.',
      );
    } catch (e) {
      message.error(formatServiceError(e, 'Failed to issue mobilization advance'));
    }
  };

  // Derived early so retention-release wiring below can read it.
  const status = (contract?.status ?? 'DRAFT') as ContractStatus;

  // ── Retention release wiring ───────────────────────────────────────
  // The backend gates this on contract.status — only PRACTICAL_COMPLETION
  // (releases 50%) or FINAL_COMPLETION (releases remaining 50%) qualify.
  // The button below maps to whichever release_type is currently
  // available; the gate is checked again server-side.
  const { data: retentionReleases } = useContractRetentionReleases(cid);
  const createReleaseMut = useCreateRetentionRelease();
  const releasedTypes = new Set(
    ((retentionReleases ?? []) as any[]).map((r) => r.release_type),
  );
  const retentionHeld = Number(balance?.retention_held ?? 0);
  const retentionReleased = Number(balance?.retention_released ?? 0);
  const retentionRemaining = Math.max(0, retentionHeld - retentionReleased);
  // Decide which release type the button should attempt next.
  const nextReleaseType: 'PRACTICAL_COMPLETION' | 'FINAL_COMPLETION' | null = (() => {
    if (status === 'PRACTICAL_COMPLETION' && !releasedTypes.has('PRACTICAL_COMPLETION')) {
      return 'PRACTICAL_COMPLETION';
    }
    if (status === 'FINAL_COMPLETION' && !releasedTypes.has('FINAL_COMPLETION')) {
      return 'FINAL_COMPLETION';
    }
    return null;
  })();
  const canReleaseRetention = !!nextReleaseType && retentionRemaining > 0;

  const handleReleaseRetention = async () => {
    if (!nextReleaseType) return;
    try {
      const result = await createReleaseMut.mutateAsync({
        contractId: cid, release_type: nextReleaseType,
      });
      const release = result.data;
      const releasedAmount = parseFloat(String(release.amount || 0)) || 0;
      message.success(
        `Retention release of ${formatCurrency(releasedAmount)} created. `
        + `Now raise a Payment Voucher in Treasury to disburse to the contractor.`,
      );
    } catch (e) {
      message.error(formatServiceError(e, 'Failed to create retention release'));
    }
  };
  const handleConvertToIPC = async (milestoneId: number) => {
    try {
      const result = await convertMilestoneMut.mutateAsync({
        milestoneId, contractId: cid,
      });
      const ipc = result.data;
      message.success(
        `IPC ${ipc.ipc_number} created — opening it now.`,
      );
      // Move the user straight to the IPC detail so they can progress
      // it through certification → approval → voucher.
      navigate(`/contracts/ipcs/${ipc.id}`);
    } catch (e) {
      message.error(formatServiceError(e, 'Failed to convert milestone to IPC'));
    }
  };

  // Inline "New Milestone" modal — keeps the user in the contract
  // detail context (no navigation away). Matches SAP's "schedule
  // line" pattern where child rows are added via a slide-over panel
  // rather than a separate page.
  const [milestoneModalOpen, setMilestoneModalOpen] = useState(false);
  const [milestoneForm] = Form.useForm();

  // ── Derived values (safe with undefined contract during loading) ──
  // Computed BEFORE early returns so the hooks below can depend on
  // them without violating the Rules of Hooks (hook count must be
  // stable across renders).
  const ceiling = Number(contract?.contract_ceiling || 0);

  // Aggregate caps — derived from the loaded contract + milestones.
  // Used by both the table footer and the create-modal live preview
  // so what we show always matches what the backend will accept.
  const milestoneTotals = useMemo(() => {
    const list = (contract?.milestones ?? []) as any[];
    const totalValue = list.reduce(
      (s, m) => s + (parseFloat(String(m.scheduled_value || 0)) || 0), 0,
    );
    const totalWeight = list.reduce(
      (s, m) => s + (parseFloat(String(m.percentage_weight || 0)) || 0), 0,
    );
    return {
      totalValue,
      totalWeight,
      remainingValue: Math.max(0, ceiling - totalValue),
      remainingWeight: Math.max(0, 100 - totalWeight),
    };
  }, [contract?.milestones, ceiling]);

  // Live-watch the modal form so the preview banner updates as the
  // user types. ``Form.useWatch`` re-renders whenever the watched
  // field changes, so the comparisons below always reflect what's
  // currently in the inputs. Hoisted above early-returns to keep
  // hook order stable.
  const liveValue = Form.useWatch('scheduled_value', milestoneForm) || 0;
  const liveWeight = Form.useWatch('percentage_weight', milestoneForm) || 0;

  if (loadingC) return <LoadingScreen />;
  if (!contract) {
    return (
      <ListPageShell>
        <div style={{ padding: '3rem', textAlign: 'center', color: '#64748b' }}>
          Contract not found.
        </div>
      </ListPageShell>
    );
  }

  // ── Derived values (post-load) ────────────────────────────────────
  const certified = Number(
    balance?.cumulative_gross_certified ?? contract.cumulative_gross_certified ?? 0,
  );
  const utilPct = ceiling > 0 ? (certified / ceiling) * 100 : 0;
  const remaining = Math.max(0, ceiling - certified);
  const committed = Number(balance?.pending_voucher_amount ?? 0);
  const retentionPct = Number(contract.retention_rate ?? contract.retention_pct ?? 0);
  const mobilizationPct = Number(contract.mobilization_rate ?? contract.mobilization_pct ?? 0);
  const phaseIdx = currentPhaseIndex(status);
  const tagColor = STATUS_TAG_COLOR[status] ?? STATUS_TAG_COLOR.DRAFT;

  // ── Action handlers ───────────────────────────────────────────────
  const handleActivate = async () => {
    try {
      await activateMut.mutateAsync({ id: cid, notes: '' });
      message.success('Contract activated — number assigned and balance initialised');
    } catch (e) {
      message.error(formatServiceError(e, 'Activation failed'));
    }
  };

  const handleClose = async () => {
    try {
      await closeMut.mutateAsync({ id: cid, notes: '' });
      message.success('Contract closed');
    } catch (e) {
      message.error(formatServiceError(e, 'Close failed'));
    }
  };

  const projectedValue = milestoneTotals.totalValue + Number(liveValue || 0);
  const projectedWeight = milestoneTotals.totalWeight + Number(liveWeight || 0);
  const valueOverflow = projectedValue > ceiling;
  const weightOverflow = projectedWeight > 100;

  const handleSubmitMilestone = async () => {
    try {
      const values = await milestoneForm.validateFields();
      // Client-side aggregate check — backend's
      // ``MilestoneSchedule.clean`` enforces the same rule (defence
      // in depth), but failing fast in the UI saves a round-trip
      // and gives a more contextual error.
      const v = Number(values.scheduled_value || 0);
      const w = Number(values.percentage_weight || 0);
      if (milestoneTotals.totalValue + v > ceiling && ceiling > 0) {
        message.error(
          `Total milestone value would be ${formatCurrency(milestoneTotals.totalValue + v)}, `
          + `which exceeds the contract sum of ${formatCurrency(ceiling)}. `
          + `Reduce the value or raise a contract variation first.`,
        );
        return;
      }
      if (milestoneTotals.totalWeight + w > 100) {
        message.error(
          `Total milestone weight would be ${(milestoneTotals.totalWeight + w).toFixed(2)}% — `
          + `over the 100% cap.`,
        );
        return;
      }

      const nextNumber = (contract.milestones?.length ?? 0) + 1;
      await createMilestoneMut.mutateAsync({
        contract: cid,
        milestone_number: nextNumber,
        description:       values.description,
        scheduled_value:   values.scheduled_value,
        percentage_weight: values.percentage_weight,
        target_date:       values.target_date.format('YYYY-MM-DD'),
        notes:             values.notes ?? '',
      });
      message.success(`Milestone #${nextNumber} added.`);
      milestoneForm.resetFields();
      setMilestoneModalOpen(false);
    } catch (e) {
      // ``validateFields`` rejects with an errorFields object — that's
      // not a service error, it's just "fix the form". Service errors
      // are real failures from the API call.
      if ((e as { errorFields?: unknown })?.errorFields) return;
      message.error(formatServiceError(e, 'Failed to add milestone'));
    }
  };

  const canRaiseIPC = status !== 'DRAFT' && status !== 'CLOSED';
  const canRaiseVariation = canRaiseIPC;

  // Mobilization can only be issued once per contract, only after
  // activation, and only when ``mobilization_rate > 0``. Once a
  // ``MobilizationPayment`` exists, the action collapses to status
  // display + a "Generate PV" link.
  const canIssueMobilization =
    canRaiseIPC
    && mobilizationPct > 0
    && !mobilizationPayment;
  const mobilizationStatusLabel = mobilizationPayment
    ? mobilizationPayment.status
    : null;

  return (
    <ListPageShell>
      <div style={pageGrid}>
        {/* ── LEFT / MAIN COLUMN ──────────────────────────────── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {/* Hero */}
          <section style={heroSection}>
            <div style={{ position: 'relative', zIndex: 1 }}>
              <div style={heroTopRow}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                  <button onClick={() => navigate('/contracts')} style={heroBackBtn}>
                    <ArrowLeft size={14} /> BACK
                  </button>
                  <div style={heroDivider} />
                  <nav style={heroBreadcrumb}>
                    <span style={{ color: 'rgba(255,255,255,0.65)' }}>Contracts</span>
                    <ChevronRight size={12} color="rgba(255,255,255,0.5)" />
                    <span style={{ color: '#ffffff', fontWeight: 700 }}>{contract.contract_type ?? 'Contract'}</span>
                  </nav>
                </div>
                <div style={liveStatus}>
                  <span style={livePulse} />
                  <span style={{ color: '#34d399' }}>Live Status</span>
                </div>
              </div>

              <div style={heroBodyRow}>
                <div>
                  <h1 style={heroTitle}>{contract.title}</h1>
                  <div style={{ display: 'flex', gap: '1.25rem', marginTop: '0.5rem', flexWrap: 'wrap' }}>
                    {contract.contract_number && (
                      <p style={heroMeta}>
                        <TagIcon size={12} style={{ opacity: 0.6 }} /> {contract.contract_number}
                      </p>
                    )}
                    {contract.reference && (
                      <p style={heroMeta}>
                        <Hash size={12} style={{ opacity: 0.6 }} /> {contract.reference}
                      </p>
                    )}
                    <p style={{ ...heroMeta, ...statusPill(tagColor) }}>
                      {status.replace(/_/g, ' ')}
                    </p>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                  {status === 'DRAFT' && (
                    <Popconfirm
                      title="Activate this contract?"
                      description="A contract number will be assigned and the balance ledger initialised."
                      okText="Yes, activate"
                      cancelText="Cancel"
                      onConfirm={handleActivate}
                    >
                      <Button
                        type="primary"
                        size="middle"
                        loading={activateMut.isPending}
                        style={primaryHeroBtn}
                      >
                        ▶ Activate
                      </Button>
                    </Popconfirm>
                  )}
                  {status === 'FINAL_COMPLETION' && (
                    <Popconfirm
                      title="Close this contract?"
                      description="Closing is terminal. No further IPCs or variations may be raised."
                      okText="Yes, close"
                      okButtonProps={{ danger: true }}
                      cancelText="Cancel"
                      onConfirm={handleClose}
                    >
                      <Button danger size="middle" loading={closeMut.isPending}>
                        Close Contract
                      </Button>
                    </Popconfirm>
                  )}
                  {canReleaseRetention && (
                    <Popconfirm
                      title={
                        nextReleaseType === 'PRACTICAL_COMPLETION'
                          ? `Release 50% retention (${formatCurrency(retentionHeld * 0.5)})?`
                          : `Release remaining retention (${formatCurrency(retentionRemaining)})?`
                      }
                      description={
                        <span>
                          {nextReleaseType === 'PRACTICAL_COMPLETION' ? (
                            <>
                              At <strong>Practical Completion</strong>, half of the
                              held retention is returned to the contractor. The
                              remainder is released at Final Completion (after
                              the defects-liability period).
                            </>
                          ) : (
                            <>
                              At <strong>Final Completion</strong>, the remaining
                              retention is returned to the contractor.
                            </>
                          )}
                          <br /><br />
                          A PENDING RetentionRelease record will be created.
                          Treasury then raises a Payment Voucher to disburse
                          the cash. The retention liability GL is debited
                          automatically when the PV posts.
                        </span>
                      }
                      okText="Yes, release"
                      cancelText="Cancel"
                      onConfirm={handleReleaseRetention}
                    >
                      <button
                        style={releaseRetentionBtn}
                        disabled={createReleaseMut.isPending}
                      >
                        {createReleaseMut.isPending ? 'Releasing…' : '↩ Release Retention'}
                      </button>
                    </Popconfirm>
                  )}
                  {canIssueMobilization && (
                    <Popconfirm
                      title={`Issue mobilization advance of ${formatCurrency(
                        ceiling * mobilizationPct / 100,
                      )}?`}
                      description={
                        <span>
                          This raises a mobilization invoice for{' '}
                          <strong>{formatCurrency(ceiling * mobilizationPct / 100)}</strong>
                          {' '}({mobilizationPct.toFixed(2)}% of the contract sum).
                          The system runs a strict appropriation check before
                          issuing — if the budget line lacks balance, you'll
                          get a clear error.
                          <br /><br />
                          After issuance, create a Payment Voucher in Treasury
                          to disburse the advance to the vendor.
                        </span>
                      }
                      okText="Yes, issue advance"
                      cancelText="Cancel"
                      onConfirm={handleIssueMobilization}
                    >
                      <button
                        style={mobilizeBtn}
                        disabled={issueMobilizationMut.isPending}
                      >
                        {issueMobilizationMut.isPending ? 'Issuing…' : '+ Issue Mobilization'}
                      </button>
                    </Popconfirm>
                  )}
                  <button
                    onClick={() => navigate(`/contracts/${cid}/edit`)}
                    style={editProjectBtn}
                  >
                    <Edit2 size={13} /> EDIT CONTRACT
                  </button>
                </div>
              </div>
            </div>
            {/* Decorative blurs */}
            <div style={heroBlurTopRight} />
            <div style={heroBlurBottomLeft} />
          </section>

          {/* Compact Stepper */}
          <div style={card()}>
            <div style={stepperHeaderRow}>
              <span style={stepperHeaderLabel}>Project Lifecycle</span>
              <span style={{ ...stepperHeaderLabel, color: '#4f46e5' }}>
                Current Phase: {PHASES[phaseIdx]?.label ?? 'Draft'}
              </span>
            </div>
            <div style={stepperRow}>
              {PHASES.map((phase, idx) => {
                const completed = idx < phaseIdx;
                const current = idx === phaseIdx;
                const future = idx > phaseIdx;
                return (
                  <div key={phase.key} style={stepperCell}>
                    <div style={stepperCircle({ completed, current })}>
                      {completed ? (
                        <Check size={14} color="#fff" />
                      ) : current ? (
                        <div style={currentDot} />
                      ) : (
                        <span style={stepperFutureNum}>{String(idx + 1).padStart(2, '0')}</span>
                      )}
                    </div>
                    <span style={stepperLabel({ current, future })}>{phase.label}</span>
                    {/* Connector line to next step */}
                    {idx < PHASES.length - 1 && (
                      <div style={stepperConnector({ filled: idx < phaseIdx })} />
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Stats Grid */}
          {/* Order chosen for narrative flow:
              ① ORIGINAL BUDGET (the appropriation that funds this
                contract — the upstream constraint).
              ② CONTRACT SUM (what was committed against that budget).
              ③ CERTIFIED so far.
              ④ RETENTION terms.
              ⑤ MOBILISATION terms.
              The reader scans left-to-right: how much was authorised →
              how much was committed → how much was actually used. */}
          <div style={statsGrid}>
            <StatCard
              label="Original Budget"
              value={canQueryAppr
                ? (matchedAppropriation ? formatCurrency(apprApproved) : '—')
                : '—'}
              footer={
                canQueryAppr
                  ? (matchedAppropriation
                      ? <span style={statSubtle}>
                          Available: <strong style={{ color: '#059669' }}>
                            {formatCurrency(apprAvailable)}
                          </strong>
                        </span>
                      : <span style={pill({ accent: 'neutral' })}>No matching appropriation</span>)
                  : <span style={statSubtle}>Awaiting NCoA segments…</span>
              }
              accent="indigo"
            />
            <StatCard
              label="Contract Sum"
              value={formatCurrency(ceiling)}
              footer={
                // Show what fraction of the original budget this
                // contract committed — gives the reader instant
                // context ("75 % of the line") instead of just a
                // big number. Falls back to the contract type when
                // the appropriation lookup hasn't resolved yet.
                matchedAppropriation && apprApproved > 0
                  ? <span style={statSubtle}>
                      <strong style={{ color: '#0f172a' }}>
                        {((ceiling / apprApproved) * 100).toFixed(1)}%
                      </strong>
                      {' '}of original budget
                    </span>
                  : <span style={pill({ accent: 'success' })}>
                      {contract.contract_type ?? 'Awarded'}
                    </span>
              }
            />
            <StatCard
              label="Certified Amount"
              value={formatCurrency(certified)}
              footer={<span style={pill({ accent: 'neutral' })}>{utilPct.toFixed(0)}% Utilized</span>}
            />
            <StatCard
              label="Retention"
              value={`${retentionPct.toFixed(2)}%`}
              footer={<span style={statSubtle}>Standard retention policy</span>}
            />
            <StatCard
              label="Mobilization"
              value={`${mobilizationPct.toFixed(2)}%`}
              footer={
                mobilizationPayment ? (
                  <span style={pill({
                    accent: mobilizationPayment.status === 'PAID' ? 'success' : 'neutral',
                  })}>
                    {mobilizationPayment.status.replace(/_/g, ' ')}
                    {' · '}
                    {formatCurrency(Number(mobilizationPayment.amount || 0))}
                  </span>
                ) : Number(balance?.mobilization_paid ?? 0) > 0 ? (
                  <span style={statSubtle}>
                    {formatCurrency(Number(balance?.mobilization_paid ?? 0))} paid
                  </span>
                ) : mobilizationPct > 0 ? (
                  <span style={statSubtle}>
                    Available — click <strong>+ Issue Mobilization</strong> in the hero
                  </span>
                ) : (
                  <span style={statSubtle}>No mobilization paid</span>
                )
              }
            />
          </div>

          {/* Uncleared advance banner — Special-GL Phase 1.
              Renders ONLY when this contract's vendor has open
              MOBILIZATION / DPR / AP advance rows. The "Clear
              Advance" button posts the F-54 contra journal
              (DR Real-AP / CR Vendor-Advance recon) so the next
              IPC payment cycle nets the recovery automatically. */}
          {contract.vendor && (
            <UnclearedAdvanceWarning
              vendorId={contract.vendor}
              context={{
                type: 'CONTRACT',
                id: cid,
                reference: contract.contract_number ?? `CONTRACT-${cid}`,
              }}
              variant="inline"
            />
          )}

          {/* Tabs */}
          <section style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div style={tabsHeader}>
              <div style={{ display: 'flex', gap: '2rem' }}>
                <TabButton
                  active={activeTab === 'milestones'}
                  onClick={() => setActiveTab('milestones')}
                  label={`Milestones (${contract.milestones?.length ?? 0})`}
                />
                <TabButton
                  active={activeTab === 'ipcs'}
                  onClick={() => setActiveTab('ipcs')}
                  label={`IPCs (${ipcs?.count ?? 0})`}
                />
                <TabButton
                  active={activeTab === 'variations'}
                  onClick={() => setActiveTab('variations')}
                  label={`Variations (${variations?.count ?? 0})`}
                />
              </div>
              <div style={{ display: 'flex', gap: '0.5rem', paddingBottom: '0.5rem' }}>
                {activeTab === 'milestones' && (
                  <button
                    onClick={() => setMilestoneModalOpen(true)}
                    style={primaryDarkBtn}
                  >
                    <Plus size={14} /> NEW MILESTONE
                  </button>
                )}
                {activeTab === 'ipcs' && (
                  // IPCs are now exclusively raised from approved
                  // milestones — see ``MilestoneScheduleViewSet.convert_to_ipc``.
                  // The button below stays as a label so the user
                  // understands the new workflow at a glance.
                  <span
                    style={ipcOriginNote}
                    title="IPCs are created from the Milestones tab — approve a milestone, then click Convert to IPC."
                  >
                    IPCs are raised from approved milestones
                  </span>
                )}
                {activeTab === 'variations' && (
                  <button
                    onClick={() => navigate(`/contracts/${cid}/variations/new`)}
                    style={canRaiseVariation ? primaryDarkBtn : primaryDarkBtnDisabled}
                    disabled={!canRaiseVariation}
                    title={
                      !canRaiseVariation
                        ? 'Activate the contract first to raise variations'
                        : 'Submit a new variation / change order'
                    }
                  >
                    <Plus size={14} /> NEW VARIATION
                  </button>
                )}
              </div>
            </div>

            {activeTab === 'milestones' && (
              <MilestonesTab
                milestones={contract.milestones ?? []}
                contractCeiling={ceiling}
                formatCurrency={formatCurrency}
                onStart={handleStartMilestone}
                onApprove={handleApproveMilestone}
                onConvertToIPC={handleConvertToIPC}
                actionLoading={
                  startMilestoneMut.isPending
                  || approveMilestoneMut.isPending
                  || convertMilestoneMut.isPending
                }
              />
            )}
            {activeTab === 'ipcs' && (
              <IPCsTab
                ipcs={ipcs?.results ?? []}
                onOpen={(ipcId) => navigate(`/contracts/ipcs/${ipcId}`)}
                formatCurrency={formatCurrency}
              />
            )}
            {activeTab === 'variations' && (
              <VariationsTab
                variations={variations?.results ?? []}
                onOpen={(vId) => navigate(`/contracts/variations/${vId}`)}
                formatCurrency={formatCurrency}
              />
            )}
          </section>
        </div>

        {/* ── RIGHT INFO SIDEBAR ──────────────────────────────── */}
        <aside style={rightSidebar}>
          {/* Budget Pulse */}
          <section>
            <h4 style={sidebarSectionTitle}>Budget Pulse</h4>
            <div style={pulseCard}>
              <div>
                <div style={pulseHeaderRow}>
                  <span>Ceiling Utilization</span>
                  <span>{utilPct.toFixed(0)}%</span>
                </div>
                <div style={pulseBar}>
                  <div
                    style={{
                      ...pulseBarFill,
                      width: `${Math.min(utilPct, 100)}%`,
                      background: utilPct >= 100 ? '#ef4444' : utilPct > 85 ? '#f59e0b' : '#4f46e5',
                    }}
                  />
                </div>
              </div>
              <div style={pulseSplit}>
                <div>
                  <p style={pulseSplitLabel}>Remaining</p>
                  <p style={pulseSplitValue}>{formatCurrency(remaining)}</p>
                </div>
                <div>
                  <p style={pulseSplitLabel}>Committed</p>
                  <p style={pulseSplitValue}>{formatCurrency(committed)}</p>
                </div>
              </div>
            </div>
          </section>

          {/* Stakeholders */}
          <section>
            <div style={sidebarSectionRow}>
              <h4 style={sidebarSectionTitle}>Stakeholders</h4>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <StakeholderRow
                initials={initials(contract.vendor_name ?? 'Vendor')}
                name={contract.vendor_name ?? 'Vendor'}
                role="Lead Contractor"
                online
              />
              <StakeholderRow
                initials="UA"
                name="Unassigned"
                role="Sub-Contractor"
                muted
                rightSlot={<UserPlus size={14} color="#94a3b8" />}
              />
            </div>
          </section>

          {/* Recent Activity */}
          <section>
            <h4 style={sidebarSectionTitle}>Recent Activity</h4>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', paddingLeft: '0.5rem' }}>
              <ActivityItem
                accent
                title={status === 'DRAFT' ? 'Contract Drafted' : 'Contract Activated'}
                meta={`Status: ${status.replace(/_/g, ' ')}`}
              />
              {contract.signed_date && (
                <ActivityItem
                  title="Contract Signed"
                  meta={new Date(contract.signed_date).toLocaleDateString('en-GB')}
                />
              )}
              {contract.created_at && (
                <ActivityItem
                  title="Initial Setup"
                  meta={new Date(contract.created_at).toLocaleDateString('en-GB')}
                />
              )}
            </div>
            <button
              onClick={() => navigate(`/contracts/${cid}/audit`)}
              style={viewAuditBtn}
            >
              View All Audit Logs
            </button>
          </section>
        </aside>
      </div>

      {/* DRAFT helper banner — kept inside the page so first-time users
          have an obvious nudge, but visually subtle so it doesn't fight
          the redesign. Shown only when there's something to nudge. */}
      {status === 'DRAFT' && (
        <div style={draftBanner}>
          <Info size={14} color="#4f46e5" />
          <div style={{ flex: 1 }}>
            <strong>This contract is a DRAFT.</strong> Click <em>Activate</em> in the
            hero to assign the official contract number, materialise the balance
            ledger, and unlock IPC + variation submission.
          </div>
        </div>
      )}

      {/* New Milestone modal — defined inline so the form state lives
          beside the contract context. The next milestone_number is
          computed at submit time from the current count, so the user
          never has to think about numbering. */}
      <Modal
        title={`New Milestone — Contract ${contract.contract_number ?? `#${cid}`}`}
        open={milestoneModalOpen}
        onCancel={() => setMilestoneModalOpen(false)}
        onOk={handleSubmitMilestone}
        okText={`Add Milestone #${(contract.milestones?.length ?? 0) + 1}`}
        okButtonProps={{ disabled: valueOverflow || weightOverflow }}
        confirmLoading={createMilestoneMut.isPending}
        destroyOnHidden
        width={560}
      >
        <p style={{ color: '#64748b', fontSize: 12, marginBottom: 12 }}>
          Milestones are physical contractual checkpoints (e.g. "Foundation laid",
          "Roof complete"). When achieved, they trigger an IPC for payment.
        </p>

        {/* Live aggregate preview — refreshes as the user types so they
            never bump up against the backend's cap unexpectedly. */}
        <div style={{
          background: valueOverflow || weightOverflow ? '#fef2f2' : '#f0f9ff',
          border: `1px solid ${valueOverflow || weightOverflow ? '#fecaca' : '#bae6fd'}`,
          borderRadius: 8,
          padding: '0.75rem 1rem',
          marginBottom: 16,
          fontSize: 12,
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, marginBottom: 6 }}>
            <span>
              <strong>Existing milestones:</strong>{' '}
              {formatCurrency(milestoneTotals.totalValue)} · {milestoneTotals.totalWeight.toFixed(1)}%
            </span>
            <span>
              <strong>Remaining:</strong>{' '}
              {formatCurrency(milestoneTotals.remainingValue)} · {milestoneTotals.remainingWeight.toFixed(1)}%
            </span>
          </div>
          {(liveValue > 0 || liveWeight > 0) && (
            <div style={{
              paddingTop: 6, borderTop: `1px solid ${valueOverflow || weightOverflow ? '#fecaca' : '#bae6fd'}`,
              color: valueOverflow || weightOverflow ? '#b91c1c' : '#0369a1',
              fontWeight: 600,
            }}>
              <strong>After adding this milestone:</strong>{' '}
              {formatCurrency(projectedValue)} ({((projectedValue / Math.max(ceiling, 1)) * 100).toFixed(1)}%)
              {' · '}
              Weight {projectedWeight.toFixed(1)}%
              {valueOverflow && (
                <div style={{ marginTop: 4, fontSize: 11 }}>
                  ⚠ Exceeds contract sum {formatCurrency(ceiling)} by{' '}
                  {formatCurrency(projectedValue - ceiling)}
                </div>
              )}
              {weightOverflow && (
                <div style={{ marginTop: 4, fontSize: 11 }}>
                  ⚠ Exceeds 100% weight cap by {(projectedWeight - 100).toFixed(2)}%
                </div>
              )}
            </div>
          )}
        </div>

        <Form form={milestoneForm} layout="vertical" preserve={false}>
          <Form.Item
            label="Description"
            name="description"
            rules={[{ required: true, message: 'Describe the milestone' }]}
          >
            <Input placeholder="e.g. Foundation work complete" />
          </Form.Item>
          <Form.Item
            label="Scheduled Value (NGN)"
            name="scheduled_value"
            rules={[
              { required: true, message: 'Scheduled value required' },
              {
                validator: (_, v) =>
                  v && Number(v) > 0 ? Promise.resolve() : Promise.reject('Must be > 0'),
              },
            ]}
            tooltip={`Of the ${formatCurrency(ceiling)} contract ceiling.`}
          >
            <InputNumber
              min={0.01}
              style={{ width: '100%' }}
              step={1000}
              formatter={(v) => (v != null && v !== '' ? `₦ ${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',') : '')}
              parser={(v) => (v ? v.replace(/[^\d.]/g, '') : '') as unknown as number}
            />
          </Form.Item>
          <Form.Item
            label="Percentage Weight"
            name="percentage_weight"
            rules={[
              { required: true, message: 'Weight required' },
              { type: 'number', min: 0, max: 100, message: '0–100%' },
            ]}
            tooltip="What share of the total project this milestone represents."
          >
            <InputNumber
              min={0}
              max={100}
              style={{ width: '100%' }}
              step={1}
              addonAfter="%"
            />
          </Form.Item>
          <Form.Item
            label="Target Date"
            name="target_date"
            rules={[{ required: true, message: 'Target date required' }]}
          >
            <DatePicker
              style={{ width: '100%' }}
              format="DD/MM/YYYY"
              disabledDate={(d) => {
                if (!d) return false;
                const start = contract.contract_start_date
                  ? dayjs(contract.contract_start_date)
                  : null;
                const end = contract.contract_end_date
                  ? dayjs(contract.contract_end_date)
                  : null;
                if (start && d.isBefore(start, 'day')) return true;
                if (end && d.isAfter(end, 'day')) return true;
                return false;
              }}
            />
          </Form.Item>
          <Form.Item label="Notes (optional)" name="notes">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </ListPageShell>
  );
};

export default ContractDetail;


// ──────────────────────────────────────────────────────────────────────
// Sub-components
// ──────────────────────────────────────────────────────────────────────

interface StatCardProps {
  label: string;
  value: string;
  footer: React.ReactNode;
  /** ``indigo`` swaps in a tinted background + value colour to
   *  visually anchor the card as the upstream/source-of-truth tile.
   *  Used for the "Original Budget" card so it's immediately
   *  distinguishable from contract / certified figures. */
  accent?: 'indigo';
}
function StatCard({ label, value, footer, accent }: StatCardProps) {
  const isIndigo = accent === 'indigo';
  return (
    <div
      style={{
        ...card({ pad: '1.25rem' }),
        ...(isIndigo ? statCardIndigo : null),
      }}
    >
      <div style={statTopRow}>
        <p style={{ ...statLabel, ...(isIndigo ? { color: '#4f46e5' } : null) }}>
          {label}
        </p>
        <Info size={14} color="#a5b4fc" style={{ opacity: 0.4 }} />
      </div>
      <p style={{ ...statValue, ...(isIndigo ? { color: '#312e81' } : null) }}>
        {value}
      </p>
      <div style={{ marginTop: '0.75rem' }}>{footer}</div>
    </div>
  );
}

const statCardIndigo: React.CSSProperties = {
  background: 'linear-gradient(135deg, rgba(238, 242, 255, 0.55) 0%, rgba(255, 255, 255, 1) 60%)',
  borderColor: '#c7d2fe',
};


interface TabButtonProps { active: boolean; onClick: () => void; label: string; }
function TabButton({ active, onClick, label }: TabButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        padding: '0.6rem 0.25rem',
        borderBottom: active ? '2px solid #4f46e5' : '2px solid transparent',
        color: active ? '#4f46e5' : '#64748b',
        background: 'none', border: 'none',
        fontWeight: 700, fontSize: '0.7rem',
        textTransform: 'uppercase', letterSpacing: '0.1em',
        cursor: 'pointer',
        marginBottom: '-1px',
      }}
    >
      {label}
    </button>
  );
}


interface MilestonesTabProps {
  milestones: any[];
  contractCeiling: number;
  formatCurrency: (n: number) => string;
  onStart: (id: number) => void;
  onApprove: (id: number) => void;
  onConvertToIPC: (id: number) => void;
  actionLoading: boolean;
}
function MilestonesTab({
  milestones, contractCeiling, formatCurrency, onStart, onApprove, onConvertToIPC, actionLoading,
}: MilestonesTabProps) {
  // Aggregate totals — surfaced in the table footer so the user
  // always sees how much of the contract sum + 100% weight pool
  // they've allocated. The same numbers drive the model-level
  // ``MilestoneSchedule.clean()`` aggregate cap, so what the UI
  // shows here matches what the backend will accept.
  const totalScheduled = milestones.reduce(
    (s, m) => s + (parseFloat(String(m.scheduled_value || 0)) || 0),
    0,
  );
  const totalWeight = milestones.reduce(
    (s, m) => s + (parseFloat(String(m.percentage_weight || 0)) || 0),
    0,
  );
  const remainingValue = Math.max(0, contractCeiling - totalScheduled);
  const remainingWeight = Math.max(0, 100 - totalWeight);
  const overValue = totalScheduled > contractCeiling && contractCeiling > 0;
  const overWeight = totalWeight > 100;

  if (!milestones.length) {
    return (
      <EmptyState
        title="No Milestones Defined Yet"
        description="Define your project milestones to track construction progress and trigger payment certificates automatically."
        iconKey="kanban"
      />
    );
  }
  return (
    <div style={card({ pad: 0 })}>
      <table style={dataTable}>
        <thead>
          <tr style={tableHeadRow}>
            <th style={th}>#</th>
            <th style={th}>Description</th>
            <th style={{ ...th, textAlign: 'right' }}>Scheduled Value</th>
            <th style={{ ...th, textAlign: 'right' }}>Weight</th>
            <th style={th}>Target</th>
            <th style={th}>Completed</th>
            <th style={{ ...th, textAlign: 'center' }}>Status</th>
            <th style={{ ...th, textAlign: 'right' }}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {milestones.map((m: any) => (
            <tr key={m.id} style={tableRow}>
              <td style={{ ...td, fontFamily: 'monospace', fontWeight: 700 }}>
                {m.milestone_number}
              </td>
              <td style={td}>{m.description}</td>
              <td style={{ ...td, textAlign: 'right', fontFamily: 'monospace' }}>
                {formatCurrency(Number(m.scheduled_value || 0))}
              </td>
              <td style={{ ...td, textAlign: 'right' }}>{Number(m.percentage_weight || 0).toFixed(1)}%</td>
              <td style={td}>
                {m.target_date
                  ? new Date(m.target_date).toLocaleDateString('en-GB')
                  : '—'}
              </td>
              <td style={{ ...td, color: m.actual_completion_date ? '#0f172a' : '#94a3b8' }}>
                {m.actual_completion_date
                  ? new Date(m.actual_completion_date).toLocaleDateString('en-GB')
                  : '—'}
              </td>
              <td style={{ ...td, textAlign: 'center' }}>
                <span style={statusBadge(m.status)}>{m.status}</span>
              </td>
              <td style={{ ...td, textAlign: 'right' }}>
                <div style={milestoneActionsCell}>
                  {m.status === 'PENDING' && (
                    <Popconfirm
                      title="Mark this milestone as in progress?"
                      description="This signals that site work has begun. The milestone still needs to be approved before an IPC can be raised."
                      okText="Mark in progress"
                      onConfirm={() => onStart(m.id)}
                    >
                      <button style={milestoneStartBtn} disabled={actionLoading}>
                        Start
                      </button>
                    </Popconfirm>
                  )}
                  {(m.status === 'PENDING' || m.status === 'IN_PROGRESS') && (
                    <Popconfirm
                      title="Approve this milestone as complete?"
                      description={
                        <span>
                          This certifies the work as physically complete and unlocks
                          IPC submission against this milestone. Today's date will be
                          recorded as the completion date.
                          <br /><br />
                          <strong>This is the milestone "approval" step.</strong>
                        </span>
                      }
                      okText="Yes, approve"
                      cancelText="Cancel"
                      onConfirm={() => onApprove(m.id)}
                    >
                      <button style={milestoneApproveBtn} disabled={actionLoading}>
                        ✓ Approve
                      </button>
                    </Popconfirm>
                  )}
                  {m.status === 'COMPLETED' && !m.ipc && (
                    <Popconfirm
                      title="Convert this milestone to an IPC?"
                      description={
                        <span>
                          An Interim Payment Certificate (IPC) of
                          <strong> {formatCurrency(Number(m.scheduled_value || 0))}</strong>
                          {' '}will be raised against this milestone. The IPC follows
                          the standard certification → approval → payment-voucher
                          flow. Tax + Withholding Tax default from the vendor master.
                          <br /><br />
                          <strong>IPCs cannot be created manually — they always
                          originate from an approved milestone.</strong>
                        </span>
                      }
                      okText="Yes, create IPC"
                      cancelText="Cancel"
                      onConfirm={() => onConvertToIPC(m.id)}
                    >
                      <button style={milestoneConvertBtn} disabled={actionLoading}>
                        Convert to IPC
                      </button>
                    </Popconfirm>
                  )}
                  {m.status === 'COMPLETED' && m.ipc && (
                    <span style={milestoneIPCLink} title="View the IPC raised against this milestone">
                      IPC raised
                    </span>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr style={milestoneFootRow}>
            <td style={{ ...td, fontWeight: 800, color: '#0f172a' }} colSpan={2}>
              Total ({milestones.length} milestone{milestones.length === 1 ? '' : 's'})
            </td>
            <td style={{
              ...td, textAlign: 'right',
              fontFamily: 'monospace', fontWeight: 800,
              color: overValue ? '#b91c1c' : '#0f172a',
            }}>
              {formatCurrency(totalScheduled)}
            </td>
            <td style={{
              ...td, textAlign: 'right', fontWeight: 800,
              color: overWeight ? '#b91c1c' : '#0f172a',
            }}>
              {totalWeight.toFixed(1)}%
            </td>
            <td style={{ ...td, fontSize: 10, color: '#64748b' }} colSpan={4}>
              {overValue ? (
                <span style={{ color: '#b91c1c', fontWeight: 700 }}>
                  ⚠ Exceeds contract sum by {formatCurrency(totalScheduled - contractCeiling)}
                </span>
              ) : overWeight ? (
                <span style={{ color: '#b91c1c', fontWeight: 700 }}>
                  ⚠ Weights total {totalWeight.toFixed(1)}% — over the 100% cap
                </span>
              ) : (
                <span>
                  Remaining value: <strong style={{ color: '#0f172a' }}>{formatCurrency(remainingValue)}</strong>
                  {' · '}
                  Remaining weight: <strong style={{ color: '#0f172a' }}>{remainingWeight.toFixed(1)}%</strong>
                </span>
              )}
            </td>
            <td style={td}></td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

const milestoneFootRow: React.CSSProperties = {
  borderTop: '2px solid #e2e8f0',
  background: 'rgba(248, 250, 252, 0.5)',
};

const milestoneActionsCell: React.CSSProperties = {
  display: 'inline-flex', gap: 6, justifyContent: 'flex-end',
};
const milestoneStartBtn: React.CSSProperties = {
  padding: '4px 10px',
  fontSize: 11, fontWeight: 700,
  background: '#fff', color: '#4f46e5',
  border: '1px solid #c7d2fe', borderRadius: 6,
  cursor: 'pointer',
};
const milestoneApproveBtn: React.CSSProperties = {
  padding: '4px 12px',
  fontSize: 11, fontWeight: 700,
  background: '#10b981', color: '#fff',
  border: 'none', borderRadius: 6,
  cursor: 'pointer',
  boxShadow: '0 2px 6px rgba(16, 185, 129, 0.25)',
};
const milestoneApprovedTag: React.CSSProperties = {
  display: 'inline-block',
  padding: '2px 10px',
  fontSize: 10, fontWeight: 700,
  background: '#dcfce7', color: '#15803d',
  borderRadius: 999,
  textTransform: 'uppercase', letterSpacing: '0.05em',
};
const milestoneConvertBtn: React.CSSProperties = {
  padding: '4px 12px',
  fontSize: 11, fontWeight: 700,
  background: '#4f46e5', color: '#fff',
  border: 'none', borderRadius: 6,
  cursor: 'pointer',
  boxShadow: '0 2px 6px rgba(79, 70, 229, 0.25)',
};
const milestoneIPCLink: React.CSSProperties = {
  display: 'inline-block',
  padding: '2px 10px',
  fontSize: 10, fontWeight: 700,
  background: '#dbeafe', color: '#1d4ed8',
  borderRadius: 999,
  textTransform: 'uppercase', letterSpacing: '0.05em',
};


interface IPCsTabProps {
  ipcs: any[];
  onOpen: (id: number) => void;
  formatCurrency: (n: number) => string;
}
function IPCsTab({ ipcs, onOpen, formatCurrency }: IPCsTabProps) {
  if (!ipcs.length) {
    return (
      <EmptyState
        title="No IPCs Raised Yet"
        description="Interim Payment Certificates capture each progress payment. Raise the first one once site work begins."
        iconKey="receipt"
      />
    );
  }
  return (
    <div style={card({ pad: 0 })}>
      <table style={dataTable}>
        <thead>
          <tr style={tableHeadRow}>
            <th style={th}>IPC #</th>
            <th style={{ ...th, textAlign: 'right' }}>Gross</th>
            <th style={{ ...th, textAlign: 'center' }}>Status</th>
            <th style={{ ...th, textAlign: 'right' }}>Open</th>
          </tr>
        </thead>
        <tbody>
          {ipcs.map((i: any) => (
            <tr key={i.id} style={{ ...tableRow, cursor: 'pointer' }} onClick={() => onOpen(i.id)}>
              <td style={{ ...td, fontFamily: 'monospace', color: '#4f46e5', fontWeight: 700 }}>
                {i.ipc_number}
              </td>
              <td style={{ ...td, textAlign: 'right', fontFamily: 'monospace' }}>
                {formatCurrency(Number(i.this_certificate_gross))}
              </td>
              <td style={{ ...td, textAlign: 'center' }}>
                <span style={statusBadge(i.status)}>{i.status}</span>
              </td>
              <td style={{ ...td, textAlign: 'right', color: '#4f46e5' }}>›</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}


interface VariationsTabProps {
  variations: any[];
  onOpen: (id: number) => void;
  formatCurrency: (n: number) => string;
}
function VariationsTab({ variations, onOpen, formatCurrency }: VariationsTabProps) {
  if (!variations.length) {
    return (
      <EmptyState
        title="No Variations Yet"
        description="Variations / change orders adjust the contract ceiling. Raise one when scope changes after activation."
        iconKey="edit"
      />
    );
  }
  return (
    <div style={card({ pad: 0 })}>
      <table style={dataTable}>
        <thead>
          <tr style={tableHeadRow}>
            <th style={th}>Variation #</th>
            <th style={{ ...th, textAlign: 'right' }}>Delta Amount</th>
            <th style={{ ...th, textAlign: 'right' }}>Cumulative %</th>
            <th style={{ ...th, textAlign: 'center' }}>Approval Tier</th>
            <th style={{ ...th, textAlign: 'center' }}>Status</th>
          </tr>
        </thead>
        <tbody>
          {variations.map((v: any) => (
            <tr key={v.id} style={{ ...tableRow, cursor: 'pointer' }} onClick={() => onOpen(v.id)}>
              <td style={{ ...td, fontFamily: 'monospace', color: '#4f46e5', fontWeight: 700 }}>
                {v.variation_number}
              </td>
              <td style={{ ...td, textAlign: 'right', fontFamily: 'monospace' }}>
                {formatCurrency(Number(v.delta_amount ?? v.amount ?? 0))}
              </td>
              <td style={{ ...td, textAlign: 'right' }}>
                {Number(v.cumulative_pct ?? 0).toFixed(1)}%
              </td>
              <td style={{ ...td, textAlign: 'center' }}>
                <span style={tierBadge(v.approval_tier)}>{v.approval_tier}</span>
              </td>
              <td style={{ ...td, textAlign: 'center' }}>
                <span style={statusBadge(v.status)}>{v.status}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}


interface EmptyStateProps {
  title: string;
  description: string;
  iconKey?: 'kanban' | 'receipt' | 'edit';
}
function EmptyState({ title, description }: EmptyStateProps) {
  return (
    <div style={emptyState}>
      <div style={emptyIconBox}>
        <Plus size={28} color="#a5b4fc" />
      </div>
      <h3 style={{ color: '#0f172a', fontWeight: 700, marginBottom: '0.5rem', fontSize: '0.95rem' }}>
        {title}
      </h3>
      <p style={{ color: '#94a3b8', fontSize: '0.75rem', maxWidth: 320, lineHeight: 1.6, margin: 0 }}>
        {description}
      </p>
    </div>
  );
}


interface StakeholderRowProps {
  initials: string;
  name: string;
  role: string;
  online?: boolean;
  muted?: boolean;
  rightSlot?: React.ReactNode;
}
function StakeholderRow({ initials, name, role, online, muted, rightSlot }: StakeholderRowProps) {
  return (
    <div
      style={{
        ...stakeholderRow,
        opacity: muted ? 0.6 : 1,
      }}
    >
      <div style={muted ? stakeholderAvatarMuted : stakeholderAvatar}>
        {initials.slice(0, 2).toUpperCase()}
      </div>
      <div style={{ flex: 1, overflow: 'hidden' }}>
        <p style={stakeholderName}>{name}</p>
        <p style={stakeholderRole}>{role}</p>
      </div>
      {online && <div style={onlineDot} />}
      {rightSlot}
    </div>
  );
}


interface ActivityItemProps { title: string; meta: string; accent?: boolean; }
function ActivityItem({ title, meta, accent }: ActivityItemProps) {
  return (
    <div style={activityItem}>
      <div style={accent ? activityDotActive : activityDot} />
      <p style={accent ? activityTitleActive : activityTitle}>{title}</p>
      <p style={activityMeta}>{meta}</p>
    </div>
  );
}


// ──────────────────────────────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────────────────────────────
function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return 'NA';
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[words.length - 1][0]).toUpperCase();
}


// ──────────────────────────────────────────────────────────────────────
// Styles — kept in this file to match the project's existing inline-
// styles convention (see InvoiceMatchingView, AppropriationDetail etc.)
// ──────────────────────────────────────────────────────────────────────
const pageGrid: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'minmax(0, 1fr) 320px',
  gap: '1.5rem',
  alignItems: 'start',
};

// Note: the 320px right column collapses on small screens via parent
// ListPageShell which already has responsive padding; for a true 1-col
// fallback the container query would need a media-query — keeping the
// 2-col grid is fine for the typical desktop viewport this page targets.

function card(opts?: { pad?: string | number }): React.CSSProperties {
  return {
    background: '#fff',
    border: '1px solid #e2e8f0',
    borderRadius: 16,
    boxShadow: '0 1px 2px rgba(15, 23, 42, 0.04)',
    padding: opts?.pad ?? '1.25rem',
  };
}

const heroSection: React.CSSProperties = {
  position: 'relative',
  // Solid Quot brand navy. The gradient was muddying the title — a
  // single tone keeps the heading punchy and prevents the awkward
  // dark-blue fade at the bottom-left.
  background: '#1c206d',
  borderRadius: 16,
  padding: '1.75rem',
  color: '#fff',
  overflow: 'hidden',
  boxShadow: '0 10px 30px -12px rgba(28, 32, 109, 0.35)',
};
// Decorative blurs disabled now that we're on a flat solid colour —
// they'd just look like dark spots on a uniform background.
const heroBlurTopRight: React.CSSProperties = { display: 'none' };
const heroBlurBottomLeft: React.CSSProperties = { display: 'none' };
const heroTopRow: React.CSSProperties = {
  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
  marginBottom: '1.5rem',
};
const heroBackBtn: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: '0.35rem',
  padding: '0.4rem 0.75rem',
  background: 'rgba(255,255,255,0.10)',
  border: '1px solid rgba(255,255,255,0.10)',
  color: '#fff',
  borderRadius: 8,
  fontSize: 11, fontWeight: 700, letterSpacing: '0.05em',
  cursor: 'pointer',
};
const heroDivider: React.CSSProperties = {
  width: 1, height: 16, background: 'rgba(255,255,255,0.20)',
};
const heroBreadcrumb: React.CSSProperties = {
  display: 'flex', alignItems: 'center', gap: '0.4rem',
  fontSize: 11, fontWeight: 500,
};
const liveStatus: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
  fontSize: 10, fontWeight: 700,
  textTransform: 'uppercase', letterSpacing: '0.15em',
};
const livePulse: React.CSSProperties = {
  display: 'inline-block',
  width: 8, height: 8, borderRadius: '50%',
  background: '#34d399',
  animation: 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
};
const heroBodyRow: React.CSSProperties = {
  display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between',
  flexWrap: 'wrap', gap: '1rem',
};
const heroTitle: React.CSSProperties = {
  fontSize: '2.25rem', fontWeight: 800, letterSpacing: '-0.025em',
  margin: 0, lineHeight: 1.1,
  color: '#ffffff',
};
const heroMeta: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: '0.3rem',
  color: 'rgba(255, 255, 255, 0.85)',
  fontSize: 12, fontWeight: 500, margin: 0,
};
const statusPill = ({ bg, fg }: { bg: string; fg: string }): React.CSSProperties => ({
  background: bg, color: fg,
  padding: '2px 10px', borderRadius: 999,
  fontWeight: 700, fontSize: 10, letterSpacing: '0.05em',
});
const editProjectBtn: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
  padding: '0.5rem 1.25rem',
  background: '#6366f1', color: '#fff',
  border: 'none', borderRadius: 8,
  fontSize: 11, fontWeight: 700, letterSpacing: '0.05em',
  cursor: 'pointer',
  boxShadow: '0 8px 16px -8px rgba(79, 70, 229, 0.5)',
};
const mobilizeBtn: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
  padding: '0.5rem 1.1rem',
  background: '#f59e0b', color: '#fff',
  border: 'none', borderRadius: 8,
  fontSize: 11, fontWeight: 700, letterSpacing: '0.05em',
  cursor: 'pointer',
  boxShadow: '0 6px 14px -6px rgba(245, 158, 11, 0.55)',
};
const releaseRetentionBtn: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
  padding: '0.5rem 1.1rem',
  background: '#10b981', color: '#fff',
  border: 'none', borderRadius: 8,
  fontSize: 11, fontWeight: 700, letterSpacing: '0.05em',
  cursor: 'pointer',
  boxShadow: '0 6px 14px -6px rgba(16, 185, 129, 0.45)',
};
const primaryHeroBtn: React.CSSProperties = {
  background: '#22c55e', borderColor: '#22c55e',
  fontWeight: 700,
};

// Stepper styles
const stepperHeaderRow: React.CSSProperties = {
  display: 'flex', justifyContent: 'space-between',
  fontSize: 11, fontWeight: 700,
  color: '#94a3b8',
  textTransform: 'uppercase', letterSpacing: '0.15em',
  marginBottom: '1rem', padding: '0 0.5rem',
};
const stepperHeaderLabel: React.CSSProperties = { fontSize: 11, fontWeight: 700 };
const stepperRow: React.CSSProperties = {
  display: 'flex', alignItems: 'flex-start', padding: '0 0.5rem',
};
const stepperCell: React.CSSProperties = {
  display: 'flex', flexDirection: 'column', alignItems: 'center',
  flex: 1, position: 'relative',
};
const stepperCircle = (
  { completed, current }: { completed: boolean; current: boolean },
): React.CSSProperties => ({
  width: 28, height: 28, borderRadius: '50%',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  zIndex: 1,
  background: completed ? '#10b981' : current ? '#fff' : '#f8fafc',
  border: completed ? 'none' : current ? '2px solid #4f46e5' : '2px solid #e2e8f0',
  boxShadow: completed
    ? '0 0 0 4px #fff, 0 4px 12px -2px rgba(16, 185, 129, 0.4)'
    : current
    ? '0 0 0 4px #fff, 0 4px 12px -2px rgba(79, 70, 229, 0.4)'
    : '0 0 0 4px #fff',
});
const currentDot: React.CSSProperties = {
  width: 8, height: 8, borderRadius: '50%', background: '#4f46e5',
  animation: 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
};
const stepperFutureNum: React.CSSProperties = {
  fontSize: 11, fontWeight: 700, color: '#94a3b8',
};
const stepperLabel = (
  { current, future }: { current: boolean; future: boolean },
): React.CSSProperties => ({
  marginTop: 8,
  fontSize: 10, fontWeight: 700,
  textTransform: 'uppercase', letterSpacing: '0.05em',
  color: current ? '#4f46e5' : future ? '#94a3b8' : '#0f172a',
});
const stepperConnector = ({ filled }: { filled: boolean }): React.CSSProperties => ({
  position: 'absolute', top: 13, left: '50%', width: '100%', height: 2,
  zIndex: 0,
  background: filled
    ? '#10b981'
    : 'repeating-linear-gradient(90deg, #e2e8f0, #e2e8f0 4px, transparent 4px, transparent 8px)',
  opacity: filled ? 1 : 0.7,
});

// Stats grid
const statsGrid: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
  gap: '1rem',
};
const statTopRow: React.CSSProperties = {
  display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
  marginBottom: '0.75rem',
};
const statLabel: React.CSSProperties = {
  fontSize: 10, fontWeight: 700, color: '#94a3b8',
  textTransform: 'uppercase', letterSpacing: '0.15em',
  margin: 0,
};
const statValue: React.CSSProperties = {
  fontSize: '1.6rem', fontWeight: 900, color: '#0f172a',
  letterSpacing: '-0.025em', margin: 0,
};
const statSubtle: React.CSSProperties = {
  fontSize: 10, fontWeight: 500, color: '#94a3b8',
};
const pill = ({ accent }: { accent: 'success' | 'neutral' }): React.CSSProperties => ({
  display: 'inline-block',
  fontSize: 10, fontWeight: 700,
  padding: '2px 8px', borderRadius: 4,
  textTransform: 'uppercase', letterSpacing: '0.04em',
  background: accent === 'success' ? '#ecfdf5' : '#f1f5f9',
  color: accent === 'success' ? '#059669' : '#94a3b8',
});

// Tabs
const tabsHeader: React.CSSProperties = {
  display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end',
  borderBottom: '1px solid #e2e8f0',
  flexWrap: 'wrap', gap: '0.5rem',
};
const primaryDarkBtn: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
  padding: '0.45rem 1rem',
  background: '#0f172a', color: '#fff',
  border: 'none', borderRadius: 8,
  fontSize: 11, fontWeight: 700, letterSpacing: '0.05em',
  cursor: 'pointer',
  boxShadow: '0 4px 12px -4px rgba(15, 23, 42, 0.2)',
};
const primaryDarkBtnDisabled: React.CSSProperties = {
  ...primaryDarkBtn,
  background: '#cbd5e1', cursor: 'not-allowed', boxShadow: 'none',
};
const ipcOriginNote: React.CSSProperties = {
  fontSize: 11, fontWeight: 600,
  color: '#475569', fontStyle: 'italic',
  padding: '0.4rem 0.8rem',
  background: '#f1f5f9', borderRadius: 6,
};

// Tables
const dataTable: React.CSSProperties = {
  width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem',
};
const tableHeadRow: React.CSSProperties = {
  background: 'rgba(148, 163, 184, 0.06)',
  borderBottom: '1px solid #e2e8f0',
};
const th: React.CSSProperties = {
  padding: '0.75rem 1rem', textAlign: 'left',
  fontSize: 10, fontWeight: 700, color: '#64748b',
  textTransform: 'uppercase', letterSpacing: '0.05em',
};
const tableRow: React.CSSProperties = {
  borderBottom: '1px solid #f1f5f9',
};
const td: React.CSSProperties = { padding: '0.75rem 1rem', verticalAlign: 'middle' };

const statusBadge = (s: string): React.CSSProperties => {
  const map: Record<string, { bg: string; color: string }> = {
    DRAFT:        { bg: '#f1f5f9', color: '#475569' },
    PENDING:      { bg: '#fef3c7', color: '#a16207' },
    APPROVED:     { bg: '#dbeafe', color: '#1d4ed8' },
    POSTED:       { bg: '#dcfce7', color: '#15803d' },
    PAID:         { bg: '#dcfce7', color: '#15803d' },
    COMPLETED:    { bg: '#dcfce7', color: '#15803d' },
    IN_PROGRESS:  { bg: '#dbeafe', color: '#1d4ed8' },
    REJECTED:     { bg: '#fee2e2', color: '#b91c1c' },
    CANCELLED:    { bg: '#fee2e2', color: '#b91c1c' },
  };
  const cfg = map[s] ?? { bg: '#f1f5f9', color: '#64748b' };
  return {
    display: 'inline-block',
    padding: '2px 10px', borderRadius: 999,
    fontSize: 10, fontWeight: 700,
    textTransform: 'uppercase', letterSpacing: '0.04em',
    background: cfg.bg, color: cfg.color,
  };
};

const tierBadge = (t: string): React.CSSProperties => {
  const map: Record<string, string> = {
    BPP_REQUIRED: '#ef4444',
    BOARD:        '#f59e0b',
    AG:           '#4f46e5',
    HOD:          '#0ea5e9',
  };
  const color = map[t] ?? '#64748b';
  return {
    display: 'inline-block',
    padding: '2px 10px', borderRadius: 999,
    fontSize: 10, fontWeight: 700,
    textTransform: 'uppercase', letterSpacing: '0.04em',
    background: color + '20', color,
  };
};

// Empty state
const emptyState: React.CSSProperties = {
  ...card({ pad: '3rem' }),
  display: 'flex', flexDirection: 'column', alignItems: 'center',
  justifyContent: 'center', textAlign: 'center', minHeight: 320,
};
const emptyIconBox: React.CSSProperties = {
  width: 80, height: 80, borderRadius: 24,
  background: '#eef2ff', border: '1px solid #e0e7ff',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  marginBottom: '1.5rem',
  boxShadow: 'inset 0 2px 4px rgba(15, 23, 42, 0.04)',
};

// Right sidebar
const rightSidebar: React.CSSProperties = {
  display: 'flex', flexDirection: 'column', gap: '2rem',
  background: '#fff', border: '1px solid #e2e8f0',
  borderRadius: 16, padding: '1.5rem',
  position: 'sticky', top: 16,
};
const sidebarSectionTitle: React.CSSProperties = {
  fontSize: 10, fontWeight: 700, color: '#94a3b8',
  textTransform: 'uppercase', letterSpacing: '0.20em',
  marginBottom: '1rem',
};
const sidebarSectionRow: React.CSSProperties = {
  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
};
const pulseCard: React.CSSProperties = {
  background: '#f8fafc',
  border: '1px solid #f1f5f9',
  borderRadius: 16,
  padding: '1rem',
  display: 'flex', flexDirection: 'column', gap: '1rem',
};
const pulseHeaderRow: React.CSSProperties = {
  display: 'flex', justifyContent: 'space-between',
  fontSize: 11, fontWeight: 700, color: '#475569',
  textTransform: 'uppercase',
  marginBottom: 6,
};
const pulseBar: React.CSSProperties = {
  height: 8, width: '100%',
  background: '#e2e8f0', borderRadius: 999,
  overflow: 'hidden',
};
const pulseBarFill: React.CSSProperties = {
  height: '100%',
  background: '#4f46e5',
  transition: 'width 0.5s ease',
};
const pulseSplit: React.CSSProperties = {
  paddingTop: '1rem',
  borderTop: '1px solid #e2e8f0',
  display: 'grid',
  gridTemplateColumns: '1fr 1fr',
  gap: '1rem',
};
const pulseSplitLabel: React.CSSProperties = {
  fontSize: 10, color: '#94a3b8', fontWeight: 700,
  textTransform: 'uppercase', margin: '0 0 2px',
};
const pulseSplitValue: React.CSSProperties = {
  fontSize: 13, fontWeight: 700, color: '#0f172a', margin: 0,
};

// Stakeholders
const stakeholderRow: React.CSSProperties = {
  display: 'flex', alignItems: 'center', gap: '0.75rem',
  padding: '0.75rem',
  background: '#fff',
  border: '1px solid #f1f5f9',
  borderRadius: 12,
  boxShadow: '0 1px 2px rgba(15, 23, 42, 0.04)',
};
const stakeholderAvatar: React.CSSProperties = {
  width: 32, height: 32, borderRadius: '50%',
  background: '#e0e7ff', color: '#4338ca',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  fontSize: 11, fontWeight: 700,
  border: '2px solid #fff',
};
const stakeholderAvatarMuted: React.CSSProperties = {
  ...stakeholderAvatar,
  background: '#f1f5f9', color: '#475569',
};
const stakeholderName: React.CSSProperties = {
  fontSize: 11, fontWeight: 700, color: '#0f172a',
  textTransform: 'uppercase', margin: 0,
  whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
};
const stakeholderRole: React.CSSProperties = {
  fontSize: 10, color: '#64748b', fontWeight: 500, margin: 0,
};
const onlineDot: React.CSSProperties = {
  width: 8, height: 8, borderRadius: '50%', background: '#34d399',
};

// Activity
const activityItem: React.CSSProperties = {
  position: 'relative', paddingLeft: '1.25rem',
  borderLeft: '1px solid #f1f5f9', paddingBottom: '0.25rem',
};
const activityDot: React.CSSProperties = {
  position: 'absolute', left: -4, top: 0,
  width: 8, height: 8, borderRadius: '50%', background: '#e2e8f0',
};
const activityDotActive: React.CSSProperties = {
  ...activityDot, background: '#4f46e5',
  boxShadow: '0 0 0 4px rgba(79, 70, 229, 0.10)',
};
const activityTitle: React.CSSProperties = {
  fontSize: 11, fontWeight: 700, color: '#334155',
  margin: '0 0 2px', lineHeight: 1.3,
};
const activityTitleActive: React.CSSProperties = {
  ...activityTitle, color: '#0f172a',
};
const activityMeta: React.CSSProperties = {
  fontSize: 10, color: '#94a3b8', fontWeight: 500, margin: 0,
};

const viewAuditBtn: React.CSSProperties = {
  width: '100%', marginTop: '1.5rem', padding: '0.6rem',
  fontSize: 10, fontWeight: 700, color: '#94a3b8',
  background: 'transparent', border: '1px solid #f1f5f9',
  borderRadius: 8,
  textTransform: 'uppercase', letterSpacing: '0.15em',
  cursor: 'pointer',
};

// Draft banner
const draftBanner: React.CSSProperties = {
  marginTop: '1rem',
  padding: '0.75rem 1rem',
  background: '#eef2ff', border: '1px solid #c7d2fe',
  borderRadius: 12,
  display: 'flex', alignItems: 'center', gap: '0.75rem',
  fontSize: 13, color: '#3730a3',
};

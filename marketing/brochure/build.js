/**
 * Quot PSA — Feature Brochure (MS Word)
 * Generates Quot_PSA_Feature_Brochure.docx
 */
const fs = require('fs');
const {
    Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
    Header, Footer, AlignmentType, PageOrientation, LevelFormat,
    HeadingLevel, BorderStyle, WidthType, ShadingType, PageNumber, PageBreak,
    TabStopType, TabStopPosition,
} = require('docx');

// ─── Design tokens ────────────────────────────────────────────────────────────
const COLOR = {
    primary:  '0F4C81', // deep navy
    accent:   'C7973F', // muted gold
    ink:      '1A1A1A',
    muted:    '5A5A5A',
    rule:     'CCCCCC',
    panelBg:  'F4F7FB',
    headerBg: '0F4C81',
    headerFg: 'FFFFFF',
    altRow:   'F8FAFD',
};

const PAGE = {
    width: 12240, height: 15840,
    margin: { top: 1080, right: 1080, bottom: 1080, left: 1080 },
    contentWidth: 12240 - 2160, // 10,080 DXA
};

const border = (color = COLOR.rule, size = 1) =>
    ({ style: BorderStyle.SINGLE, size, color });
const allBorders = (color = COLOR.rule, size = 1) => ({
    top: border(color, size), bottom: border(color, size),
    left: border(color, size), right: border(color, size),
});
const noBorders = () => ({
    top:    { style: BorderStyle.NONE, size: 0, color: 'FFFFFF' },
    bottom: { style: BorderStyle.NONE, size: 0, color: 'FFFFFF' },
    left:   { style: BorderStyle.NONE, size: 0, color: 'FFFFFF' },
    right:  { style: BorderStyle.NONE, size: 0, color: 'FFFFFF' },
});

// ─── Paragraph helpers ────────────────────────────────────────────────────────
const p = (text, opts = {}) => new Paragraph({
    spacing: { after: 100, ...(opts.spacing || {}) },
    alignment: opts.alignment,
    children: [new TextRun({
        text,
        font: opts.font || 'Calibri',
        size: opts.size || 22,
        bold: opts.bold,
        italics: opts.italics,
        color: opts.color || COLOR.ink,
    })],
});

const h1 = (text) => new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 320, after: 160 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: COLOR.primary, space: 6 } },
    children: [new TextRun({ text, font: 'Calibri', size: 36, bold: true, color: COLOR.primary })],
});

const h2 = (text) => new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 220, after: 100 },
    children: [new TextRun({ text, font: 'Calibri', size: 28, bold: true, color: COLOR.primary })],
});

const h3 = (text) => new Paragraph({
    heading: HeadingLevel.HEADING_3,
    spacing: { before: 160, after: 80 },
    children: [new TextRun({ text, font: 'Calibri', size: 24, bold: true, color: COLOR.accent })],
});

const bullet = (text, level = 0) => new Paragraph({
    numbering: { reference: 'bullets', level },
    spacing: { after: 60 },
    children: [new TextRun({ text, font: 'Calibri', size: 22, color: COLOR.ink })],
});

const richBullet = (label, body, level = 0) => new Paragraph({
    numbering: { reference: 'bullets', level },
    spacing: { after: 60 },
    children: [
        new TextRun({ text: `${label} `, font: 'Calibri', size: 22, bold: true, color: COLOR.ink }),
        new TextRun({ text: body, font: 'Calibri', size: 22, color: COLOR.ink }),
    ],
});

// ─── Table helpers ────────────────────────────────────────────────────────────
const cell = (content, opts = {}) => {
    const isPara = content instanceof Paragraph;
    const children = isPara ? [content] : (Array.isArray(content)
        ? content
        : [new Paragraph({
            alignment: opts.align,
            children: [new TextRun({
                text: String(content),
                font: 'Calibri',
                size: opts.size || 20,
                bold: opts.bold,
                color: opts.color || COLOR.ink,
            })],
        })]);
    return new TableCell({
        width: { size: opts.width, type: WidthType.DXA },
        shading: opts.fill ? { fill: opts.fill, type: ShadingType.CLEAR } : undefined,
        borders: opts.borderless ? noBorders() : allBorders(opts.borderColor || COLOR.rule),
        margins: { top: 100, bottom: 100, left: 140, right: 140 },
        children,
    });
};

const twoColTable = (rows, leftWidth = 3200) => {
    const rightWidth = PAGE.contentWidth - leftWidth;
    return new Table({
        width: { size: PAGE.contentWidth, type: WidthType.DXA },
        columnWidths: [leftWidth, rightWidth],
        rows: rows.map((r, i) => new TableRow({
            children: [
                cell(r[0], { width: leftWidth, bold: true, fill: i === 0 ? COLOR.headerBg : (i % 2 ? COLOR.altRow : 'FFFFFF'), color: i === 0 ? COLOR.headerFg : COLOR.primary, size: i === 0 ? 22 : 20 }),
                cell(r[1], { width: rightWidth, fill: i === 0 ? COLOR.headerBg : (i % 2 ? COLOR.altRow : 'FFFFFF'), color: i === 0 ? COLOR.headerFg : COLOR.ink, bold: i === 0, size: i === 0 ? 22 : 20 }),
            ],
        })),
    });
};

const threeColTable = (rows, widths = [2200, 4200, 3680]) => new Table({
    width: { size: PAGE.contentWidth, type: WidthType.DXA },
    columnWidths: widths,
    rows: rows.map((r, i) => new TableRow({
        children: r.map((cellText, idx) => cell(cellText, {
            width: widths[idx],
            bold: i === 0,
            color: i === 0 ? COLOR.headerFg : (idx === 0 ? COLOR.primary : COLOR.ink),
            fill: i === 0 ? COLOR.headerBg : (i % 2 ? COLOR.altRow : 'FFFFFF'),
            size: i === 0 ? 22 : 20,
        })),
    })),
});

// Feature panel: title bar + bullet body in a single bordered box
const featurePanel = (title, subtitle, bullets) => {
    const titleRow = new TableRow({
        children: [new TableCell({
            width: { size: PAGE.contentWidth, type: WidthType.DXA },
            shading: { fill: COLOR.primary, type: ShadingType.CLEAR },
            borders: allBorders(COLOR.primary),
            margins: { top: 120, bottom: 120, left: 180, right: 180 },
            children: [
                new Paragraph({
                    spacing: { after: 0 },
                    children: [new TextRun({ text: title, font: 'Calibri', size: 26, bold: true, color: COLOR.headerFg })],
                }),
                ...(subtitle ? [new Paragraph({
                    spacing: { before: 40, after: 0 },
                    children: [new TextRun({ text: subtitle, font: 'Calibri', size: 20, italics: true, color: 'D9E2F0' })],
                })] : []),
            ],
        })],
    });

    const bodyRow = new TableRow({
        children: [new TableCell({
            width: { size: PAGE.contentWidth, type: WidthType.DXA },
            shading: { fill: 'FFFFFF', type: ShadingType.CLEAR },
            borders: allBorders(COLOR.primary),
            margins: { top: 160, bottom: 160, left: 200, right: 200 },
            children: bullets.map(b => {
                if (Array.isArray(b)) {
                    return new Paragraph({
                        spacing: { after: 80 },
                        indent: { left: 200, hanging: 200 },
                        children: [
                            new TextRun({ text: '• ', font: 'Calibri', size: 22, bold: true, color: COLOR.accent }),
                            new TextRun({ text: `${b[0]} `, font: 'Calibri', size: 22, bold: true, color: COLOR.ink }),
                            new TextRun({ text: b[1], font: 'Calibri', size: 22, color: COLOR.ink }),
                        ],
                    });
                }
                return new Paragraph({
                    spacing: { after: 80 },
                    indent: { left: 200, hanging: 200 },
                    children: [
                        new TextRun({ text: '• ', font: 'Calibri', size: 22, bold: true, color: COLOR.accent }),
                        new TextRun({ text: b, font: 'Calibri', size: 22, color: COLOR.ink }),
                    ],
                });
            }),
        })],
    });

    return new Table({
        width: { size: PAGE.contentWidth, type: WidthType.DXA },
        columnWidths: [PAGE.contentWidth],
        rows: [titleRow, bodyRow],
    });
};

const spacer = (size = 120) => new Paragraph({ spacing: { after: size }, children: [new TextRun({ text: '' })] });
const pageBreak = () => new Paragraph({ children: [new PageBreak()] });

// ═════════════════════════════════════════════════════════════════════════════
//                            COVER PAGE
// ═════════════════════════════════════════════════════════════════════════════
const cover = [
    new Paragraph({ spacing: { before: 1600, after: 0 }, alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: 'QUOT PSA', font: 'Calibri', size: 96, bold: true, color: COLOR.primary, characterSpacing: 80 })] }),
    new Paragraph({ spacing: { before: 80, after: 80 }, alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: 'Public Sector Accounting Platform', font: 'Calibri', size: 36, color: COLOR.accent })] }),
    new Paragraph({ spacing: { before: 40, after: 600 }, alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: 'Nigeria IFMIS-aligned · IPSAS-compliant · GFS 2014 reporting', font: 'Calibri', size: 22, italics: true, color: COLOR.muted })] }),

    // Decorative rule
    new Paragraph({
        spacing: { before: 0, after: 600 }, alignment: AlignmentType.CENTER,
        border: { bottom: { style: BorderStyle.SINGLE, size: 24, color: COLOR.accent, space: 1 } },
        children: [new TextRun({ text: '' })],
    }),

    // Hero pitch
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 280 },
        children: [new TextRun({
            text: 'A purpose-built, multi-tenant treasury and accounting platform for Federal, State, and Local Government MDAs, parastatals, and revenue agencies.',
            font: 'Calibri', size: 26, italics: true, color: COLOR.ink,
        })] }),

    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 240 },
        children: [new TextRun({
            text: 'Every module — budget, commitments, treasury, revenue, payroll, assets, and reporting — is designed around the constitutional, legal, and fiscal-control requirements that govern public money.',
            font: 'Calibri', size: 22, color: COLOR.muted,
        })] }),

    // Stat strip
    new Paragraph({ spacing: { before: 600, after: 200 } , children: [new TextRun({ text: '' })]}),
    new Table({
        width: { size: PAGE.contentWidth, type: WidthType.DXA },
        columnWidths: [2520, 2520, 2520, 2520],
        rows: [new TableRow({ children: [
            cell([
                new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: '20+', font: 'Calibri', size: 44, bold: true, color: COLOR.primary })] }),
                new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: 'Functional Modules', font: 'Calibri', size: 18, color: COLOR.muted })] }),
            ], { width: 2520, fill: COLOR.panelBg, borderColor: COLOR.panelBg }),
            cell([
                new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: '19', font: 'Calibri', size: 44, bold: true, color: COLOR.primary })] }),
                new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: 'IPSAS / GFS Reports', font: 'Calibri', size: 18, color: COLOR.muted })] }),
            ], { width: 2520, fill: COLOR.panelBg, borderColor: COLOR.panelBg }),
            cell([
                new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: '7-Seg', font: 'Calibri', size: 44, bold: true, color: COLOR.primary })] }),
                new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: 'National CoA', font: 'Calibri', size: 18, color: COLOR.muted })] }),
            ], { width: 2520, fill: COLOR.panelBg, borderColor: COLOR.panelBg }),
            cell([
                new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: 'IFMIS', font: 'Calibri', size: 44, bold: true, color: COLOR.primary })] }),
                new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: 'Native Compliance', font: 'Calibri', size: 18, color: COLOR.muted })] }),
            ], { width: 2520, fill: COLOR.panelBg, borderColor: COLOR.panelBg }),
        ]})],
    }),

    new Paragraph({ spacing: { before: 1200, after: 0 }, alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: 'FEATURE BROCHURE', font: 'Calibri', size: 28, bold: true, color: COLOR.muted, characterSpacing: 40 })] }),
    new Paragraph({ alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: 'Quot Technologies', font: 'Calibri', size: 22, color: COLOR.muted })] }),

    pageBreak(),
];

// ═════════════════════════════════════════════════════════════════════════════
//                       EXECUTIVE OVERVIEW
// ═════════════════════════════════════════════════════════════════════════════
const overview = [
    h1('Executive Overview'),
    p('Quot PSA is a full-stack Public Sector Accounting solution purpose-built for the Nigerian Integrated Financial Management Information System (IFMIS) framework and the International Public Sector Accounting Standards (IPSAS).', { spacing: { after: 120 } }),
    p('It is not a private-sector ERP with a "government mode" bolted on. Every primitive — appropriation, warrant, commitment, fund, vote book, voucher, mandate, TSA sub-account — is modelled first-class. The result is a system that enforces fiscal control at the point of commitment, not after the fact.', { spacing: { after: 160 } }),

    h2('Who it serves'),
    bullet('Federal Ministries, Departments and Agencies (MDAs)'),
    bullet('State Government treasuries and Accountant-General offices'),
    bullet('Local Government Councils'),
    bullet('Parastatals, commissions, and statutory corporations'),
    bullet('Revenue authorities and internally-generated revenue (IGR) agencies'),
    bullet('Donor-funded projects requiring ring-fenced fund accounting'),
    spacer(),

    h2('Why this is different from a private-sector ERP'),
    p('Public sector accounting differs from commercial accounting in ways that cannot be retrofitted. Quot PSA implements all of the following as native primitives:', { spacing: { after: 100 } }),
    twoColTable([
        ['Concept', 'Why a private ERP cannot satisfy it'],
        ['Appropriation as law',          'Every expenditure is gated by an Appropriation Act line. No private P&L has this concept.'],
        ['Fund accounting',               'Money is restricted by source (CRF, Development Fund, IGR, Donor) — not pooled as general purpose.'],
        ['Commitment accounting',         'Encumbrance is recorded at PO/LPO, not at invoice. Budget exhaustion must be blocked before the order is placed.'],
        ['National Chart of Accounts',    'Seven-segment classification (Admin × Economic × Functional × Programme × Fund × Geo × Project) absent from commercial CoAs.'],
        ['Treasury Single Account (TSA)', 'All government cash sweeps to one consolidated account; MDA-held sub-accounts must reconcile to it.'],
        ['IPSAS reporting',               'Accumulated Fund and Revaluation Surplus on equity, no profit concept, cash-flow under the direct method.'],
        ['Statutory submissions',         'OAGF, OAuGF, CBN, FIRS, and Budget Office formats and deadlines mandated by the Finance (Control and Management) Act.'],
    ]),
    pageBreak(),
];

// ═════════════════════════════════════════════════════════════════════════════
//                       ARCHITECTURE & STACK
// ═════════════════════════════════════════════════════════════════════════════
const architecture = [
    h1('Architecture & Technology'),
    h2('Multi-tenant by design'),
    p('Each government body — a State, Agency, or parastatal — is provisioned as a tenant with its own isolated PostgreSQL schema. A single Quot PSA deployment can host Delta State, Edo State, FIRS, and a Federal parastatal simultaneously with zero data crossover. The public schema holds only cross-tenant infrastructure: the tenant registry, superadmin console, and licensing.', { spacing: { after: 160 } }),

    h2('Technology stack'),
    twoColTable([
        ['Layer', 'Technology'],
        ['Backend',          'Django 5.2 LTS · Django REST Framework 3.17 · PostgreSQL 15 · django-tenants 3.10'],
        ['Frontend',         'React 19 · Vite 7 · TypeScript · Ant Design v6 · TanStack Query · Recharts'],
        ['Authentication',   'DRF Token + SimpleJWT · per-tenant RBAC with Segregation of Duties · MFA · HttpOnly cookie sessions'],
        ['Background jobs',  'Celery + Redis (depreciation runs, bank reconciliation, statutory report generation, scheduled cascades)'],
        ['API documentation','drf-spectacular · live OpenAPI schema at /api/schema/'],
        ['Deployment',       'Gunicorn · Nginx · PgBouncer pooling · Docker · AlmaLinux production playbook'],
        ['Observability',    'Structured JSON logging · DRF exception handler · audit trail service · application health endpoints'],
    ]),

    spacer(),
    h2('Architectural principles'),
    bullet('Schema-per-tenant data isolation enforced at the database level, not the application level.'),
    bullet('Posting services are idempotent and protected by a unique index on (source_module, source_document_id) so duplicate postings cannot occur.'),
    bullet('Period control gates every journal — posting, reversing, and unposting all validate fiscal period status.'),
    bullet('Row-level locking (select_for_update) protects warrant availability checks, IPC voucher issuance, and bulk approval flows from race conditions.'),
    bullet('Segregation of Duties (SoD) is evaluated by a central service; the same rules guard warrant release, virement approval, appropriation enactment, IPC posting, and mobilization release.'),
    bullet('Frontend uses code-splitting via React.lazy across all top-level routes for fast first-paint on slow government networks.'),
    pageBreak(),
];

// ═════════════════════════════════════════════════════════════════════════════
//                       FEATURE MODULES
// ═════════════════════════════════════════════════════════════════════════════
const featureSection = [
    h1('Feature Modules'),
    p('The platform is organised into twenty functional modules. Each module is a complete subsystem with its own data model, services, REST API, frontend pages, audit trail, and role-based permissions.', { spacing: { after: 240 } }),

    // ── BUDGET ──────────────────────────────────────────────────────────────
    h2('1 · Budget Preparation & Appropriation'),
    featurePanel('Budget lifecycle, end to end',
        'From MTEF envelope to enacted Appropriation Act, to warrants and virements.', [
        ['MTEF & Sector Envelopes:',     'multi-year medium-term expenditure framework with rolling sector ceilings.'],
        ['MDA budget ceilings:',         'each MDA receives an apportionment of the sector envelope with budget-line targets.'],
        ['Line-item budget entry:',      'capital and recurrent budget lines classified by Admin × Economic × Functional × Programme × Fund × Geo × Project.'],
        ['Appropriation Act loading:',   'enacted Act lines imported and locked; any over-commitment is blocked at the source.'],
        ['Warrants:',                    'AIE, recurrent and capital warrants, MDA releases with expiry dates and Cancelled status; expired warrants are filtered from availability calculations.'],
        ['Virements:',                   'inter-line and inter-MDA transfers with SoD-enforced approval and appropriation re-check on ceiling increases.'],
        ['Variance analysis:',           'live comparison of budget vs. commitments vs. actuals across all seven NCoA segments.'],
        ['Budget check rules:',          'configurable tolerance bands, freeze flags, and warning-vs-block behaviour per fund / per economic head.'],
    ]),
    spacer(160),

    // ── PROCUREMENT ─────────────────────────────────────────────────────────
    h2('2 · Procurement & Commitment Control'),
    featurePanel('BPP-aligned procurement with pre-encumbrance',
        'Every commitment is checked against the budget before the order is placed.', [
        ['Vendor registration:',         'classified by vendor category, with expiry tracking and BPP compliance status.'],
        ['Requisition workflow:',        'Purchase Requisition with multi-level approval, dimension-tagged for cost-centre attribution.'],
        ['Procurement methods:',         'open tender, selective tender, request for quotation, direct procurement — each with its own workflow template.'],
        ['Purchase Orders / LPOs:',      'commitment journal posted at issuance; budget-line pre-encumbrance blocks over-commitment.'],
        ['Goods Received Notes (GRN):',  'three-way match against PO and invoice; partial receipts supported.'],
        ['Invoice matching:',            'price and quantity variance checks with configurable tolerance, escalation to procurement officer above threshold.'],
        ['Purchase returns:',            'credit-note generation with reversal of original AP posting and inventory write-back.'],
        ['Vendor performance:',          'on-time delivery, quality, and contract-compliance scorecards per vendor.'],
    ]),
    spacer(160),

    // ── CONTRACTS ───────────────────────────────────────────────────────────
    h2('3 · Contracts, IPCs & Variations'),
    featurePanel('Works contract administration',
        'Full lifecycle for works/services contracts including IPCs, retention, mobilisation, defects-liability, and closure.', [
        ['Contract register:',           'full contract record with parties, ceilings, dates, BoQ, and document attachments (with magic-byte file-type validation).'],
        ['Measurement books:',           'progress measurements locked once cited in an IPC — no retroactive edits to billed quantities.'],
        ['Interim Payment Certificates (IPCs):', 'progress-payment certificates with row-level locking during voucher raising to prevent double vouchers.'],
        ['Mobilisation advances:',       'select_for_update protected; recovery schedule tracked across subsequent IPCs.'],
        ['Retention money:',             'auto-accrual on each IPC, release on completion or defects-liability expiry — accrued on the intended release date, not posting date.'],
        ['Variations:',                  'orders that increase contract ceiling re-check appropriation availability before approval.'],
        ['Defects-liability period (DLP):', 'tracked with retention-release scheduling and SoD-enforced closure.'],
        ['Contract closure:',            'two-person SoD on closure; cascade settlement of outstanding IPCs and retention release.'],
        ['Per-MDA visibility:',          'contract viewsets are scoped to the user’s MDA permissions; superadmins see across MDAs.'],
    ]),
    spacer(160),

    // ── TREASURY / TSA ──────────────────────────────────────────────────────
    h2('4 · Treasury Single Account (TSA)'),
    featurePanel('Whole-of-government cash visibility',
        'TSA hierarchy with deterministic mapping into the General Ledger for IPSAS cash-flow reporting.', [
        ['TSA hierarchy:',               'master TSA, MDA sub-accounts, zero-balance accounts, and earmarked sub-accounts.'],
        ['TSA ledger:',                  'real-time balance per MDA sub-account with sweep history.'],
        ['TSA transfers:',               'inter-MDA and TSA-to-bank transfers with dual-control approval.'],
        ['TSA-to-GL resolver:',          'deterministic mapping from TSA movements into the appropriate GL accounts so cash-flow statements reconcile exactly.'],
        ['TSA bank reconciliation:',     'race-safe auto-match against CBN bank statements; unmatched items routed to operator queue.'],
        ['TSA cash-position report:',    'consolidated dashboard for the Accountant-General with drill-down by MDA.'],
        ['Mirror sync via signals:',     'TSA mirror is updated only by Django signals on payment confirmation — never on GET endpoints — guaranteeing consistency.'],
    ]),
    spacer(160),

    // ── REVENUE ─────────────────────────────────────────────────────────────
    h2('5 · Revenue Management'),
    featurePanel('Revenue from collection to consolidated fund',
        'Multi-channel revenue collection mapped to NCoA economic classification.', [
        ['Revenue heads:',               'taxonomy of revenue items per the National Chart of Accounts.'],
        ['Collection channels:',         'POS, online gateways, bank-counter receipts, mobile money.'],
        ['Receipts:',                    'tax receipts issued with TIN, NCoA economic code, and revenue head; posted to the Consolidated Revenue Fund.'],
        ['Revenue budget vs. actuals:',  'live performance against approved revenue budget.'],
        ['Revenue collection form:',     'operator-facing UI for cashiers with built-in WHT/VAT calculation.'],
        ['IGR vs. CRF segregation:',     'restricted revenue stays in its fund of origin; no commingling with the Consolidated Revenue Fund.'],
    ]),
    spacer(160),

    // ── GL / NCoA ───────────────────────────────────────────────────────────
    h2('6 · General Ledger & National Chart of Accounts'),
    featurePanel('Seven-segment NCoA with IPSAS-grade GL',
        'The accounting backbone of every other module.', [
        ['Chart of Accounts:',           'managed at the COA level with bi-directional sync to the NCoA structure.'],
        ['NCoA segments:',               'Administrative, Economic, Functional (COFOG), Programme, Fund, Geo, Project — each managed in its own admin form.'],
        ['Journal entries:',             'manual and system-generated, validated for fiscal-period status, balanced debits and credits, and segment integrity.'],
        ['Recurring journals:',          'templated journals that post on a configurable schedule.'],
        ['Accruals & deferrals:',        'period-end accrual journals with automatic reversal in the next period.'],
        ['Year-end close:',              'guided close process; year_end_close service raises explicit errors rather than swallowing them.'],
        ['Posting idempotency:',         'unique index on (source_module, source_document_id) guarantees no journal is posted twice.'],
        ['Unposting controls:',          'unpost validates fiscal-period state and SoD before reversing.'],
    ]),
    spacer(160),

    // ── AP ──────────────────────────────────────────────────────────────────
    h2('7 · Accounts Payable'),
    featurePanel('Vendor invoices, vouchers, and payments',
        'AP integrated with procurement matching, WHT derivation, and payment-reconciliation.', [
        ['Vendor invoices:',             'created from PO/GRN match or stand-alone; AP account resolution distinguishes invoice, credit memo, and debit memo.'],
        ['Credit & debit memos:',        'reversal-aware posting with the correct AP control account.'],
        ['Payment vouchers (PVs):',      'PV factory generates vouchers from approved invoices with WHT and tax derivations applied.'],
        ['Outgoing payments:',           'bank transfer, cheque, or mandate to the CBN; duplicate-posting guard prevents the same payment being posted twice.'],
        ['Payment reconciliation queue:', 'failed cascades are queued for retry via a management command (retry_payment_cascades) — no silent loss.'],
        ['Vendor advances:',             'uncleared-advance warning on new invoices so unsettled advances are never forgotten.'],
        ['Withholding tax derivation:',  'WHT computed per vendor and tax code; exemption certificates honoured without silent fallback to zero.'],
        ['AP aging:',                    'configurable buckets with drill-down by vendor and cost-centre.'],
    ]),
    spacer(160),

    // ── AR ──────────────────────────────────────────────────────────────────
    h2('8 · Accounts Receivable'),
    featurePanel('Customer invoicing and collection',
        'For agencies that bill third parties — leases, services, or IGR billables.', [
        ['Customer master:',             'customer registry with credit limits, payment terms, and tax registration.'],
        ['Customer invoices:',           'multi-line invoices with tax codes, dimensions, and NCoA mapping.'],
        ['Incoming payments:',           'cash, bank-transfer, and online-gateway receipts allocated to open invoices.'],
        ['AR aging:',                    'aging reports with configurable buckets and dunning workflow hooks.'],
        ['Statements:',                  'customer statement generation for outstanding balances.'],
    ]),
    spacer(160),

    // ── ASSETS ──────────────────────────────────────────────────────────────
    h2('9 · Fixed Assets & Depreciation'),
    featurePanel('IPSAS 17 compliant asset accounting',
        'Full lifecycle from capitalisation to disposal.', [
        ['Asset categories:',            'with default GL accounts for cost, depreciation, accumulated depreciation, and disposal.'],
        ['Capitalisation:',              'from PO/invoice with automatic posting to the asset GL — no manual journal needed.'],
        ['Depreciation:',                'five methods supported (straight-line, declining-balance, sum-of-years’-digits, units-of-production, IPSAS-prescribed schedules).'],
        ['Asset Register:',              'asset history reconstructible from GL because every capitalisation, depreciation, revaluation, and disposal is tagged to the asset ID.'],
        ['Revaluation:',                 'IAS 16 / IPSAS 17 revaluation surplus posting with reverse-on-disposal handling.'],
        ['Impairment:',                  'one-off impairment journal with disclosure trail.'],
        ['Intangibles & amortisation:',  'parallel handling for intangible assets with amortisation schedule.'],
        ['Disposals:',                   'gain/loss computed automatically; proceeds posted to the correct revenue head.'],
    ]),
    spacer(160),

    // ── BANK / CASH ─────────────────────────────────────────────────────────
    h2('10 · Bank & Cash Management'),
    featurePanel('Operational cash control',
        'Every bank account reconciled against the source statement.', [
        ['Bank-account registry:',       'all MDA bank accounts with CBN code, BVN sweep mapping, and authorised signatories.'],
        ['Cash accounts:',               'petty-cash and imprest accounts with re-imbursement workflow.'],
        ['Bank reconciliation:',         'statement import, auto-match by reference and amount with race-safe locking, and operator queue for unmatched items.'],
        ['Cheque register:',             'cheque issuance with status tracking — issued, presented, returned, cancelled.'],
        ['Bank-cash dashboard:',         'consolidated cash position across all operating accounts.'],
    ]),
    spacer(160),

    // ── TAX ─────────────────────────────────────────────────────────────────
    h2('11 · Tax (PAYE · VAT · WHT)'),
    featurePanel('Statutory tax administration',
        'Tax computation, withholding, and statutory return preparation.', [
        ['Tax codes:',                   'configurable tax rate tables for VAT, WHT, PAYE, and stamp duty per vendor / customer / employee category.'],
        ['VAT returns:',                 'monthly VAT return computation with input/output VAT roll-forward.'],
        ['Withholding tax:',             'derived at invoice time with exemption handling; WHT payment derivation produces remittance vouchers to FIRS.'],
        ['Statutory XML export:',        'machine-readable XML and XBRL exports for regulator submission.'],
        ['Tax management UI:',           'unified screen for tax setup, rate changes, and exemption certificates.'],
    ]),
    spacer(160),

    // ── PAYROLL / PENSION ──────────────────────────────────────────────────
    h2('12 · Payroll & Pension'),
    featurePanel('IPPIS-style payroll',
        'Salary processing aligned with the Pension Reform Act 2014.', [
        ['Payroll cycles:',              'monthly, mid-month, and ad-hoc runs with cost-centre allocation (no silent zero on allocation failure).'],
        ['PAYE:',                        'progressive Personal Income Tax computed per the Personal Income Tax Act.'],
        ['Pension (PRA 2014):',          'employer and employee Retirement Savings Account contributions remitted to PFAs.'],
        ['Group Life Insurance:',        'monthly premium accrual and payment.'],
        ['Payslips:',                    'employee-portal self-service download.'],
        ['Batch pay to TSA:',            'consolidated salary mandate to the CBN for crediting individual employee bank accounts.'],
        ['Pension accrual service:',     'monthly accrual journal aligned with the actuarial schedule.'],
    ]),
    spacer(160),

    // ── HRM ─────────────────────────────────────────────────────────────────
    h2('13 · Human Resources Management'),
    featurePanel('Employee master, leave, and performance',
        'Operational HR functions feeding payroll and biometric attendance.', [
        ['Employee master:',             'employees, positions, departments, and skills with hierarchical reporting line.'],
        ['Attendance:',                  'biometric-capable attendance capture with leave-balance impact.'],
        ['Leave management:',            'leave applications with approval workflow, balance tracking, and accrual.'],
        ['Performance management:',      'review cycles, KPI tracking, and rating history.'],
        ['Training:',                    'training catalogue, attendance, and certification tracking.'],
        ['Recruitment:',                 'job posts, candidate pipeline, and onboarding handover into the employee master.'],
        ['Exit management:',             'clearance workflow with final-settlement posting.'],
        ['Compliance:',                  'statutory document tracking (NHF, ITF, NSITF) and renewal alerts.'],
        ['Employee self-service portal:','my profile, payslips, leave, and documents.'],
    ]),
    spacer(160),

    // ── INVENTORY ───────────────────────────────────────────────────────────
    h2('14 · Inventory & Stores'),
    featurePanel('Government stores and warehouse control',
        'Quantity and value tracking with auto-posting to inventory GL.', [
        ['Item & category master:',      'product taxonomy with stock-keeping units, units of measure, and reorder thresholds.'],
        ['Warehouses & bins:',           'multiple warehouses with bin-level location tracking.'],
        ['Stock movements:',             'GRN inwards, dispatch outwards, transfers, and adjustments; every movement posts to inventory GL.'],
        ['Batches & serials:',           'lot and serial-number tracking with expiry alerts.'],
        ['Stock valuation:',             'weighted-average and FIFO valuation methods.'],
        ['Reorder & expiry alerts:',     'configurable thresholds notify the storekeeper before stockouts or expiry.'],
        ['Stock reconciliation:',        'physical count vs. system, with variance posting and approval.'],
        ['Inventory adjustment:',        'manual adjustment with reason code, approval, and audit trail.'],
    ]),
    spacer(160),

    // ── WORKFLOW ────────────────────────────────────────────────────────────
    h2('15 · Workflow & Approvals'),
    featurePanel('Configurable approvals across modules',
        'A single approval engine drives PRs, POs, IPCs, vouchers, virements, and journals.', [
        ['Approval templates:',          'per document type, with conditions on amount, fund, vote, and originator.'],
        ['Approval groups:',             'role-based approver groups with quorum support.'],
        ['Approval history:',            'every action timestamped, attributed, and immutable.'],
        ['Workflow inbox:',              'unified inbox for pending approvals across all document types.'],
        ['Approval dashboard:',          'queue analytics — SLA adherence, average dwell time, by approver.'],
        ['Bulk approve:',                'race-safe bulk approval with per-row locking.'],
        ['SoD enforcement:',             'document originator cannot approve their own document; approval rules respect SoD violations and return HTTP 403.'],
    ]),
    spacer(160),

    // ── REPORTS ─────────────────────────────────────────────────────────────
    h2('16 · Financial Reporting'),
    featurePanel('IPSAS, GFS 2014, and statutory reports',
        'Nineteen first-class statutory reports plus the standard managerial pack.', [
        ['IPSAS Statement of Financial Position:', 'consolidated and per-fund balance sheet.'],
        ['IPSAS Statement of Financial Performance:', 'revenues and expenses on accrual or cash basis.'],
        ['Statement of Cash Flows:',     'direct-method cash flow reconciled to TSA movements.'],
        ['Statement of Changes in Net Assets / Equity:', 'Accumulated Fund and Revaluation Surplus movements.'],
        ['Notes to Financial Statements:', 'narrative and tabular disclosures with revenue-budget reconciliation.'],
        ['Budget vs. Actual (GFS 2014):', 'variance and execution percentages aligned to GFS classification.'],
        ['Budget Performance Report:',   'utilisation against appropriated, warranted, committed, and expended amounts.'],
        ['Warrant Utilisation Report:',  'per-MDA warrant draw-down history.'],
        ['TSA Cash Position Report:',    'consolidated treasury cash position with sub-account drill-down.'],
        ['Functional Classification Report:', 'COFOG (UN Classification of the Functions of Government) roll-up.'],
        ['Programme Performance Report:','expenditure by programme classification.'],
        ['Fund Performance Report:',     'utilisation by fund source (CRF, Dev Fund, IGR, Donor).'],
        ['Geographic Distribution Report:', 'spend mapped to geo-political zones / states / LGAs.'],
        ['Commitment Report:',           'outstanding commitments and encumbrances per budget line.'],
        ['Execution Report:',            'execution percentages with traffic-light status.'],
        ['Revenue Performance Report:',  'revenue collection vs. budget by head and channel.'],
        ['Trial Balance, P&L, Balance Sheet, Cash Flow (managerial pack):', 'the standard finance reports for in-period management review.'],
        ['Report snapshots & caching:',  'long-running reports are cached and snapshot-stored for repeatable retrieval.'],
        ['XBRL export:',                 'machine-readable financial statement export.'],
    ]),
    spacer(160),

    // ── AUDIT ───────────────────────────────────────────────────────────────
    h2('17 · Audit Trail & Compliance'),
    featurePanel('Forensic-grade audit',
        'Every change to financial data is recorded — by whom, when, and from where.', [
        ['Audit trail service:',         'central service writes immutable audit records on every posting, approval, override, and configuration change.'],
        ['Override audit page:',         'every user override (manual amount edit, account override, period override) is auditable from the UI.'],
        ['Data-quality page:',           'real-time view of validation failures, unposted journals, and uncleared advances.'],
        ['Audit trail viewer:',          'searchable, exportable interface for internal audit teams.'],
        ['Tracked-change retention:',    'records retained per the Public Records Act timelines.'],
        ['DRF exception handler:',       'all unhandled errors are normalised and logged centrally with request context.'],
    ]),
    spacer(160),

    // ── SECURITY / RBAC / SoD ───────────────────────────────────────────────
    h2('18 · Security, RBAC & Segregation of Duties'),
    featurePanel('Identity, authorisation, and SoD enforcement',
        'Granular permissions enforced server-side at every viewset.', [
        ['Role management:',             'roles with permission trees; per-tenant role assignment.'],
        ['Permission tree picker:',      'UI lets admins compose granular permissions without raw permission codes.'],
        ['User-role assignments:',       'per-MDA scoping; assignments are audited.'],
        ['Segregation of Duties rules:', 'declarative rules block conflicting actions (e.g. cannot both create and approve the same warrant).'],
        ['Centralised SoD evaluator:',   'a single service evaluates SoD across modules; SoDViolation maps to HTTP 403 via global handler.'],
        ['MFA:',                         'TOTP-based MFA with enrollment check that fails closed (no fails-open enrollment bypass).'],
        ['HttpOnly cookie sessions:',    'opt-in cookie-based auth alongside DRF Token; CORS-aware, CSRF-protected.'],
        ['Token expiry:',                'ExpiringTokenAuthentication with configurable AUTH_COOKIE_MAX_AGE separate from token TTL.'],
        ['File-type validation:',        'magic-byte (not extension) validation on contract document uploads.'],
        ['Field-level serializer scoping:', 'no fields = "__all__" on sensitive serializers; whitelist-only.'],
    ]),
    spacer(160),

    // ── MULTI-TENANT / SUPERADMIN ──────────────────────────────────────────
    h2('19 · Multi-tenancy & SaaS Superadmin'),
    featurePanel('Operate many governments from one platform',
        'Schema isolation plus a dedicated cross-tenant operator console.', [
        ['Tenant registry:',             'public-schema model holding tenant metadata, plan, billing, and provisioning status.'],
        ['Tenant provisioning:',         'creates the schema, runs shared and tenant migrations, and seeds defaults from JSON (no Python literals).'],
        ['Tenant defaults seeder:',      'currencies, NCoA segments, approval templates, tax codes, and fiscal-year defaults seeded per tenant.'],
        ['Backfill command:',            'management command brings older tenants up to current seed level — re-runnable, idempotent.'],
        ['Superadmin Dashboard:',        'platform-level overview: tenants, users, billing, system health.'],
        ['Tenants tab:',                 'provision, suspend, archive, and impersonate tenants.'],
        ['Plans & Billing tabs:',        'subscription plans, billing cycles, invoices, and payment history.'],
        ['Modules tab:',                 'per-tenant module enablement (e.g. enable Contracts only for States that need it).'],
        ['Email templates tab:',         'tenant-customisable transactional emails.'],
        ['Announcements tab:',           'system-wide banner messages to tenants.'],
        ['API keys & webhooks:',         'per-tenant API access for third-party integrators.'],
        ['Audit logs tab:',              'cross-tenant audit log inspection (privileged).'],
        ['System health tab:',           'platform-level health checks, queue depth, and error rate.'],
        ['Support tab:',                 'ticket queue with impersonation banner so operators know when they’re acting as a tenant user.'],
    ]),
    spacer(160),

    // ── PORTAL ──────────────────────────────────────────────────────────────
    h2('20 · Employee Self-Service Portal'),
    featurePanel('Reduce HR ticket volume', null, [
        ['My Dashboard:',                'personal landing page with leave balances, next payday, and pending tasks.'],
        ['My Profile:',                  'view and request changes to personal data.'],
        ['My Payslips:',                 'monthly payslip download with deduction breakdown.'],
        ['My Leave:',                    'apply for leave, view balance, and track approval status.'],
        ['My Documents:',                'employee-specific document vault (offer letter, ID card, statutory certificates).'],
    ]),
    pageBreak(),
];

// ═════════════════════════════════════════════════════════════════════════════
//                       SECURITY & COMPLIANCE
// ═════════════════════════════════════════════════════════════════════════════
const security = [
    h1('Security & Compliance'),
    p('Quot PSA is designed for the threat model of a public-sector treasury — privileged-user collusion, insider data exfiltration, and statutory audit obligations. Security controls are implemented in defence-in-depth, not as a single perimeter.', { spacing: { after: 160 } }),

    h2('Identity & access'),
    bullet('Multi-factor authentication (TOTP) with fails-closed enrollment evaluation.'),
    bullet('Per-tenant Role-Based Access Control with permission trees and MDA scoping.'),
    bullet('Segregation of Duties (SoD) enforced centrally; violations return HTTP 403 with audit log.'),
    bullet('HttpOnly cookie sessions with configurable session lifetime, alongside token auth for service accounts.'),
    bullet('Impersonation banner makes superadmin operating-as-tenant always visible.'),

    h2('Data integrity'),
    bullet('Per-tenant schema isolation enforced at the database level.'),
    bullet('Posting idempotency via unique (source_module, source_document_id) index.'),
    bullet('Row-level locking (select_for_update) on warrants, IPCs, mobilisation, bulk approvals, and TSA reconciliation.'),
    bullet('Fiscal-period gating on every journal action — post, reverse, and unpost all check period status.'),
    bullet('No silent failures: WHT exemptions, payroll cost-centre allocation, year-end close, and IPSAS revenue-budget rolls all raise explicit errors instead of swallowing them.'),
    bullet('Magic-byte file-type validation on document uploads.'),

    h2('Audit & traceability'),
    bullet('Central audit trail service with immutable records.'),
    bullet('User overrides explicitly recorded and viewable in the Override Audit page.'),
    bullet('Data quality page surfaces validation failures and uncleared items in real time.'),
    bullet('Structured JSON logging with request context for downstream SIEM ingestion.'),

    h2('Regulatory alignment'),
    bullet('Nigeria Integrated Financial Management Information System (IFMIS) framework.'),
    bullet('International Public Sector Accounting Standards (IPSAS) — Cash Basis and Accrual.'),
    bullet('Government Finance Statistics (GFS) 2014 classification.'),
    bullet('Public Procurement Act (BPP) procurement methods.'),
    bullet('Pension Reform Act 2014 — employer/employee remittance to PFAs.'),
    bullet('Personal Income Tax Act — PAYE bands and reliefs.'),
    bullet('Finance (Control and Management) Act — statutory reporting to OAGF, OAuGF, CBN, FIRS, Budget Office.'),
    pageBreak(),
];

// ═════════════════════════════════════════════════════════════════════════════
//                       DEPLOYMENT & OPERATIONS
// ═════════════════════════════════════════════════════════════════════════════
const deployment = [
    h1('Deployment & Operations'),

    h2('Deployment models'),
    twoColTable([
        ['Model', 'Description'],
        ['On-premise',          'Federal or State data centre deployment on AlmaLinux / RHEL. Air-gapped option for classified treasury data.'],
        ['Private cloud',       'Customer-managed VPC on AWS, Azure, or GCP with network isolation.'],
        ['Managed SaaS',        'Quot-hosted multi-tenant deployment with per-tenant schema isolation, included DR.'],
        ['Hybrid',              'Treasury core on-prem, ancillary modules (HRM portal, reporting) in cloud.'],
    ]),

    h2('Operational tooling'),
    bullet('Operator Runbook with step-by-step incident, fail-over, and rollback procedures.'),
    bullet('Tenant onboarding runbook — target onboarding time 30 minutes.'),
    bullet('Quarterly Disaster Recovery drill procedure.'),
    bullet('AlmaLinux production playbook with Gunicorn, Nginx, PgBouncer pooling.'),
    bullet('Docker and docker-compose for reproducible local and staging environments.'),
    bullet('Management commands for re-running failed payment cascades, seed backfills, and report regeneration.'),

    h2('Performance & scale'),
    bullet('PostgreSQL 15 with PgBouncer connection pooling for thousands of concurrent users.'),
    bullet('Redis-backed report caching for long-running statutory reports.'),
    bullet('Celery workers for depreciation runs, bank reconciliation, and statutory report generation.'),
    bullet('Frontend code-splitting on every top-level route for fast first-paint on government-network latency.'),

    h2('Documentation included'),
    bullet('Functional specification (spec.md).'),
    bullet('Integration architecture document (cross-module contracts).'),
    bullet('User guide for tenant operators.'),
    bullet('Contracts and IPC payment-flow walkthrough document.'),
    bullet('Implementation task flow (sprint build log).'),
    pageBreak(),
];

// ═════════════════════════════════════════════════════════════════════════════
//                       CLOSING
// ═════════════════════════════════════════════════════════════════════════════
const closing = [
    h1('In Summary'),
    p('Quot PSA replaces the patchwork of spreadsheets, legacy IFMIS terminals, and bolted-on private-sector ERPs that most governments operate today. It does so without compromise on the controls that public money requires:', { spacing: { after: 160 } }),

    twoColTable([
        ['Pillar', 'What it means in practice'],
        ['Control at commitment',  'No expenditure ever bypasses the appropriation. The system blocks over-commitment at the order, not after the invoice arrives.'],
        ['Statutory by default',   'IPSAS, GFS 2014, COFOG, and Nigeria IFMIS are not optional configurations — they are the data model.'],
        ['Audit-grade traceability', 'Every change is recorded, attributed, and immutable. Override actions are first-class auditable events.'],
        ['Multi-tenant by design', 'A single deployment can host an entire federation of governments with absolute data isolation.'],
        ['Operator-ready',         'Runbooks, DR drills, structured logs, and self-service portals are part of the product, not after-thoughts.'],
    ]),

    spacer(400),
    new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { before: 600, after: 200 },
        children: [new TextRun({ text: 'Talk to us', font: 'Calibri', size: 32, bold: true, color: COLOR.primary })],
    }),
    new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { after: 80 },
        children: [new TextRun({ text: 'Quot Technologies', font: 'Calibri', size: 24, color: COLOR.ink })],
    }),
    new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { after: 80 },
        children: [new TextRun({ text: 'github.com/oosadiaye/Quot-PSA', font: 'Calibri', size: 22, color: COLOR.muted })],
    }),
    new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { after: 80 },
        children: [new TextRun({ text: 'For demonstrations, RFP submissions, and pilot deployments.', font: 'Calibri', size: 20, italics: true, color: COLOR.muted })],
    }),
];

// ─── Header / Footer ──────────────────────────────────────────────────────────
const docHeader = new Header({
    children: [new Paragraph({
        tabStops: [{ type: TabStopType.RIGHT, position: PAGE.contentWidth }],
        border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: COLOR.primary, space: 4 } },
        children: [
            new TextRun({ text: 'QUOT PSA', font: 'Calibri', size: 18, bold: true, color: COLOR.primary, characterSpacing: 30 }),
            new TextRun({ text: '\tFeature Brochure', font: 'Calibri', size: 18, italics: true, color: COLOR.muted }),
        ],
    })],
});

const docFooter = new Footer({
    children: [new Paragraph({
        tabStops: [{ type: TabStopType.RIGHT, position: PAGE.contentWidth }],
        border: { top: { style: BorderStyle.SINGLE, size: 6, color: COLOR.rule, space: 4 } },
        children: [
            new TextRun({ text: '© Quot Technologies — Proprietary', font: 'Calibri', size: 16, color: COLOR.muted }),
            new TextRun({ text: '\tPage ', font: 'Calibri', size: 16, color: COLOR.muted }),
            new TextRun({ children: [PageNumber.CURRENT], font: 'Calibri', size: 16, color: COLOR.muted }),
            new TextRun({ text: ' of ', font: 'Calibri', size: 16, color: COLOR.muted }),
            new TextRun({ children: [PageNumber.TOTAL_PAGES], font: 'Calibri', size: 16, color: COLOR.muted }),
        ],
    })],
});

// ─── Document ─────────────────────────────────────────────────────────────────
const doc = new Document({
    creator: 'Quot Technologies',
    title: 'Quot PSA — Feature Brochure',
    description: 'Comprehensive feature brochure for the Quot Public Sector Accounting platform.',
    styles: {
        default: { document: { run: { font: 'Calibri', size: 22 } } },
        paragraphStyles: [
            { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true,
              run: { size: 36, bold: true, font: 'Calibri', color: COLOR.primary },
              paragraph: { spacing: { before: 320, after: 160 }, outlineLevel: 0 } },
            { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true,
              run: { size: 28, bold: true, font: 'Calibri', color: COLOR.primary },
              paragraph: { spacing: { before: 220, after: 100 }, outlineLevel: 1 } },
            { id: 'Heading3', name: 'Heading 3', basedOn: 'Normal', next: 'Normal', quickFormat: true,
              run: { size: 24, bold: true, font: 'Calibri', color: COLOR.accent },
              paragraph: { spacing: { before: 160, after: 80 }, outlineLevel: 2 } },
        ],
    },
    numbering: {
        config: [
            { reference: 'bullets',
              levels: [
                { level: 0, format: LevelFormat.BULLET, text: '•', alignment: AlignmentType.LEFT,
                  style: { paragraph: { indent: { left: 720, hanging: 360 } },
                           run: { color: COLOR.accent } } },
                { level: 1, format: LevelFormat.BULLET, text: '◦', alignment: AlignmentType.LEFT,
                  style: { paragraph: { indent: { left: 1440, hanging: 360 } } } },
              ] },
        ],
    },
    sections: [{
        properties: {
            page: {
                size: { width: PAGE.width, height: PAGE.height },
                margin: PAGE.margin,
            },
        },
        headers: { default: docHeader },
        footers: { default: docFooter },
        children: [
            ...cover,
            ...overview,
            ...architecture,
            ...featureSection,
            ...security,
            ...deployment,
            ...closing,
        ],
    }],
});

Packer.toBuffer(doc).then(buf => {
    const out = 'Quot_PSA_Feature_Brochure.docx';
    fs.writeFileSync(out, buf);
    console.log(`Wrote ${out} (${buf.length.toLocaleString()} bytes)`);
}).catch(err => {
    console.error('Build failed:', err);
    process.exit(1);
});

/**
 * Proposal — Upgrade of OAG Delta State accounting solution from Odoo to Quot PSA.
 *
 * Audience: Office of the Accountant General, Delta State Government Secretariat, Asaba.
 * Prepared by: Dplux Technologies.
 * Presented by: Jacob Osadiaye.
 *
 * Scope explicitly EXCLUDES procurement (PO) and HR.
 * Scope INCLUDES: management accounting, treasury, budget appropriation, warrants,
 * payments, contract management, IPSAS compliance reporting, final reporting,
 * document control.
 *
 * Output: Proposal_Quot_PSA_Delta_OAG.docx
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
    primary:    '0F4C3A', // deep emerald — Delta-State on-brand + treasury feel
    primaryAlt: '1B7A5A',
    accent:     'A88051', // muted bronze (instead of gaudy gold for proposal)
    accentDark: '7A5C39',
    ink:        '1A1A1A',
    muted:      '5A5A5A',
    rule:       'C9C9C9',
    panelBg:    'F4F7F4',
    altRow:     'F8FAF8',
    headerBg:   '0F4C3A',
    headerFg:   'FFFFFF',
    danger:     '8B1F1F',
    ok:         '15803D',
};

const PAGE = {
    width: 12240, height: 15840,
    margin: { top: 1080, right: 1080, bottom: 1080, left: 1080 },
    contentWidth: 12240 - 2160,
};

const border = (color = COLOR.rule, size = 1) => ({ style: BorderStyle.SINGLE, size, color });
const allBorders = (color = COLOR.rule, size = 1) => ({
    top: border(color, size), bottom: border(color, size),
    left: border(color, size), right: border(color, size),
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
    spacing: { before: 360, after: 160 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: COLOR.primary, space: 6 } },
    children: [new TextRun({ text, font: 'Calibri', size: 36, bold: true, color: COLOR.primary })],
});

const h2 = (text) => new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 240, after: 100 },
    children: [new TextRun({ text, font: 'Calibri', size: 28, bold: true, color: COLOR.primary })],
});

const h3 = (text) => new Paragraph({
    heading: HeadingLevel.HEADING_3,
    spacing: { before: 180, after: 80 },
    children: [new TextRun({ text, font: 'Calibri', size: 24, bold: true, color: COLOR.accentDark })],
});

const bullet = (text, level = 0) => new Paragraph({
    numbering: { reference: 'bullets', level },
    spacing: { after: 60 },
    children: [new TextRun({ text, font: 'Calibri', size: 22, color: COLOR.ink })],
});

const numItem = (text) => new Paragraph({
    numbering: { reference: 'numbers', level: 0 },
    spacing: { after: 60 },
    children: [new TextRun({ text, font: 'Calibri', size: 22, color: COLOR.ink })],
});

const richBullet = (label, body) => new Paragraph({
    numbering: { reference: 'bullets', level: 0 },
    spacing: { after: 60 },
    children: [
        new TextRun({ text: `${label} `, font: 'Calibri', size: 22, bold: true, color: COLOR.ink }),
        new TextRun({ text: body, font: 'Calibri', size: 22, color: COLOR.ink }),
    ],
});

// ─── Table helpers ────────────────────────────────────────────────────────────
const cell = (content, opts = {}) => {
    const children = content instanceof Paragraph
        ? [content]
        : Array.isArray(content)
            ? content
            : [new Paragraph({
                alignment: opts.align,
                spacing: { after: 0 },
                children: [new TextRun({
                    text: String(content),
                    font: 'Calibri',
                    size: opts.size || 20,
                    bold: opts.bold,
                    color: opts.color || COLOR.ink,
                })],
            })];
    return new TableCell({
        width: { size: opts.width, type: WidthType.DXA },
        shading: opts.fill ? { fill: opts.fill, type: ShadingType.CLEAR } : undefined,
        borders: allBorders(opts.borderColor || COLOR.rule),
        margins: { top: 100, bottom: 100, left: 140, right: 140 },
        children,
    });
};

const twoCol = (rows, leftWidth = 3200) => {
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

const threeCol = (rows, widths = [2400, 3500, 4180]) => new Table({
    width: { size: PAGE.contentWidth, type: WidthType.DXA },
    columnWidths: widths,
    rows: rows.map((r, i) => new TableRow({
        children: r.map((c, idx) => cell(c, {
            width: widths[idx],
            bold: i === 0,
            color: i === 0 ? COLOR.headerFg : (idx === 0 ? COLOR.primary : COLOR.ink),
            fill: i === 0 ? COLOR.headerBg : (i % 2 ? COLOR.altRow : 'FFFFFF'),
            size: i === 0 ? 22 : 20,
        })),
    })),
});

const fourCol = (rows, widths) => {
    widths = widths || Array(4).fill(PAGE.contentWidth / 4);
    return new Table({
        width: { size: PAGE.contentWidth, type: WidthType.DXA },
        columnWidths: widths,
        rows: rows.map((r, i) => new TableRow({
            children: r.map((c, idx) => cell(c, {
                width: widths[idx],
                bold: i === 0,
                color: i === 0 ? COLOR.headerFg : COLOR.ink,
                fill: i === 0 ? COLOR.headerBg : (i % 2 ? COLOR.altRow : 'FFFFFF'),
                size: i === 0 ? 22 : 19,
                align: idx === 0 ? AlignmentType.LEFT : AlignmentType.LEFT,
            })),
        })),
    });
};

const calloutBox = (title, body, bgColor = COLOR.panelBg, accentColor = COLOR.primary) =>
    new Table({
        width: { size: PAGE.contentWidth, type: WidthType.DXA },
        columnWidths: [PAGE.contentWidth],
        rows: [new TableRow({
            children: [new TableCell({
                width: { size: PAGE.contentWidth, type: WidthType.DXA },
                shading: { fill: bgColor, type: ShadingType.CLEAR },
                borders: {
                    top:    { style: BorderStyle.SINGLE, size: 16, color: accentColor },
                    bottom: { style: BorderStyle.SINGLE, size: 4,  color: accentColor },
                    left:   { style: BorderStyle.SINGLE, size: 4,  color: accentColor },
                    right:  { style: BorderStyle.SINGLE, size: 4,  color: accentColor },
                },
                margins: { top: 180, bottom: 180, left: 220, right: 220 },
                children: [
                    new Paragraph({
                        spacing: { after: 80 },
                        children: [new TextRun({ text: title, font: 'Calibri', size: 24, bold: true, color: accentColor })],
                    }),
                    ...(Array.isArray(body) ? body : [body]).map(t =>
                        t instanceof Paragraph ? t : new Paragraph({
                            spacing: { after: 60 },
                            children: [new TextRun({ text: t, font: 'Calibri', size: 22, color: COLOR.ink })],
                        })
                    ),
                ],
            })],
        })],
    });

const prosCons = (title, pros, cons) => {
    const colW = (PAGE.contentWidth - 200) / 2;
    return new Table({
        width: { size: PAGE.contentWidth, type: WidthType.DXA },
        columnWidths: [colW, 200, colW],
        rows: [new TableRow({
            children: [
                new TableCell({
                    width: { size: colW, type: WidthType.DXA },
                    shading: { fill: 'EAF3EA', type: ShadingType.CLEAR },
                    borders: allBorders(COLOR.ok),
                    margins: { top: 160, bottom: 160, left: 200, right: 200 },
                    children: [
                        new Paragraph({ spacing: { after: 100 },
                            children: [new TextRun({ text: '✓  ADVANTAGES', font: 'Calibri', size: 22, bold: true, color: COLOR.ok, characterSpacing: 20 })] }),
                        ...pros.map(t => new Paragraph({
                            numbering: { reference: 'bullets', level: 0 },
                            spacing: { after: 60 },
                            children: [new TextRun({ text: t, font: 'Calibri', size: 21, color: COLOR.ink })],
                        })),
                    ],
                }),
                new TableCell({
                    width: { size: 200, type: WidthType.DXA },
                    borders: allBorders('FFFFFF'),
                    children: [new Paragraph({ children: [new TextRun({ text: '' })] })],
                }),
                new TableCell({
                    width: { size: colW, type: WidthType.DXA },
                    shading: { fill: 'F8ECEC', type: ShadingType.CLEAR },
                    borders: allBorders(COLOR.danger),
                    margins: { top: 160, bottom: 160, left: 200, right: 200 },
                    children: [
                        new Paragraph({ spacing: { after: 100 },
                            children: [new TextRun({ text: '✗  CHALLENGES', font: 'Calibri', size: 22, bold: true, color: COLOR.danger, characterSpacing: 20 })] }),
                        ...cons.map(t => new Paragraph({
                            numbering: { reference: 'bullets', level: 0 },
                            spacing: { after: 60 },
                            children: [new TextRun({ text: t, font: 'Calibri', size: 21, color: COLOR.ink })],
                        })),
                    ],
                }),
            ],
        })],
    });
};

const spacer = (size = 120) => new Paragraph({ spacing: { after: size }, children: [new TextRun({ text: '' })] });
const pageBreak = () => new Paragraph({ children: [new PageBreak()] });

// ═════════════════════════════════════════════════════════════════════════════
//                            COVER PAGE
// ═════════════════════════════════════════════════════════════════════════════
const cover = [
    // top kicker
    new Paragraph({ spacing: { before: 600, after: 80 }, alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: 'PROPOSAL  ·  CONFIDENTIAL', font: 'Calibri', size: 22, bold: true, color: COLOR.accentDark, characterSpacing: 60 })] }),
    new Paragraph({ spacing: { before: 0, after: 600 }, alignment: AlignmentType.CENTER,
        border: { bottom: { style: BorderStyle.SINGLE, size: 18, color: COLOR.accent, space: 1 } },
        children: [new TextRun({ text: '' })] }),

    // big title
    new Paragraph({ spacing: { before: 800, after: 80 }, alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: 'Upgrade of the Accounting System', font: 'Calibri', size: 44, bold: true, color: COLOR.primary })] }),
    new Paragraph({ spacing: { before: 0, after: 80 }, alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: 'from Odoo to Quot PSA', font: 'Calibri', size: 44, bold: true, color: COLOR.primary })] }),
    new Paragraph({ spacing: { before: 200, after: 0 }, alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: 'A consolidated platform for Management Accounting, Treasury, Budget Appropriation, Warrants,', font: 'Calibri', size: 22, italics: true, color: COLOR.muted })] }),
    new Paragraph({ spacing: { before: 0, after: 800 }, alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: 'Contract Management, Final Reporting, Document Control and IPSAS Compliance Reporting.', font: 'Calibri', size: 22, italics: true, color: COLOR.muted })] }),

    // prepared for / by panel
    new Table({
        width: { size: PAGE.contentWidth, type: WidthType.DXA },
        columnWidths: [PAGE.contentWidth / 2, PAGE.contentWidth / 2],
        rows: [new TableRow({
            children: [
                new TableCell({
                    width: { size: PAGE.contentWidth / 2, type: WidthType.DXA },
                    shading: { fill: COLOR.primary, type: ShadingType.CLEAR },
                    borders: allBorders(COLOR.primary, 0),
                    margins: { top: 280, bottom: 280, left: 320, right: 320 },
                    children: [
                        new Paragraph({ spacing: { after: 100 },
                            children: [new TextRun({ text: 'PREPARED FOR', font: 'Calibri', size: 18, bold: true, color: 'D9C7A8', characterSpacing: 40 })] }),
                        new Paragraph({ spacing: { after: 80 },
                            children: [new TextRun({ text: 'The Office of the', font: 'Calibri', size: 22, color: 'FFFFFF' })] }),
                        new Paragraph({ spacing: { after: 80 },
                            children: [new TextRun({ text: 'Accountant General', font: 'Calibri', size: 28, bold: true, color: 'FFFFFF' })] }),
                        new Paragraph({ spacing: { after: 80 },
                            children: [new TextRun({ text: 'Delta State Government', font: 'Calibri', size: 22, color: 'FFFFFF' })] }),
                        new Paragraph({ spacing: { after: 0 },
                            children: [new TextRun({ text: 'Government Secretariat, Asaba', font: 'Calibri', size: 20, italics: true, color: 'D9C7A8' })] }),
                    ],
                }),
                new TableCell({
                    width: { size: PAGE.contentWidth / 2, type: WidthType.DXA },
                    shading: { fill: COLOR.accentDark, type: ShadingType.CLEAR },
                    borders: allBorders(COLOR.accentDark, 0),
                    margins: { top: 280, bottom: 280, left: 320, right: 320 },
                    children: [
                        new Paragraph({ spacing: { after: 100 },
                            children: [new TextRun({ text: 'PREPARED BY', font: 'Calibri', size: 18, bold: true, color: 'EFE4D2', characterSpacing: 40 })] }),
                        new Paragraph({ spacing: { after: 80 },
                            children: [new TextRun({ text: 'Dplux Technologies', font: 'Calibri', size: 28, bold: true, color: 'FFFFFF' })] }),
                        new Paragraph({ spacing: { after: 80 },
                            children: [new TextRun({ text: 'Authors and maintainers of the Quot PSA platform', font: 'Calibri', size: 20, color: 'FFFFFF' })] }),
                        new Paragraph({ spacing: { before: 200, after: 80 },
                            children: [new TextRun({ text: 'Presented by', font: 'Calibri', size: 18, color: 'EFE4D2' })] }),
                        new Paragraph({ spacing: { after: 0 },
                            children: [new TextRun({ text: 'Jacob Osadiaye', font: 'Calibri', size: 24, bold: true, color: 'FFFFFF' })] }),
                    ],
                }),
            ],
        })],
    }),

    new Paragraph({ spacing: { before: 1200, after: 0 }, alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: 'Reference: QUOT-PSA / OAG-DELTA / 2026-001', font: 'Calibri', size: 18, color: COLOR.muted })] }),

    pageBreak(),
];

// ═════════════════════════════════════════════════════════════════════════════
//                            EXECUTIVE SUMMARY
// ═════════════════════════════════════════════════════════════════════════════
const execSummary = [
    h1('1.  Executive Summary'),

    p('The Office of the Accountant General of Delta State currently operates Odoo as the accounting back-office for a single functional area — final reporting. The system was deployed for general-ledger consolidation and statutory reporting but has not been extended to cover the full mandate of the Office: management accounting, treasury, budget appropriation administration, warrants, payments, contract management, and document control.', { spacing: { after: 120 } }),

    p('Dplux Technologies proposes the deployment of Quot PSA — a public-sector accounting platform purpose-built for the Nigerian IFMIS framework and IPSAS reporting — to replace the existing Odoo installation and to extend coverage across every functional unit within the OAG.', { spacing: { after: 120 } }),

    p('This proposal is scoped deliberately to align with the Office of the Accountant General’s actual remit. It explicitly excludes Procurement (Purchase Orders) and Human Resource Management, which sit elsewhere in the Delta State governance structure.', { spacing: { after: 160 } }),

    h3('What this proposal delivers'),
    twoCol([
        ['In scope', 'Out of scope'],
        ['Management Accounting · General Ledger · National Chart of Accounts (NCoA, 7-segment)',
         'Procurement / Purchase Orders (handled by BPP / DSPP)'],
        ['Budget Appropriation · Warrants (AIE) · Virements · Budget Check Rules', 'Human Resource Management & Recruitment'],
        ['Treasury Single Account (TSA) Ledger · TSA Transfers · Bank Reconciliation', 'Payroll generation (statutory remittance posting only, where required)'],
        ['Contract Management · IPCs · Retention · Variations · Mobilisation', 'Fixed Asset Register field operations (asset tagging by MDAs)'],
        ['Outgoing & Incoming Payments · Payment Vouchers · Vendor Mandates', 'MDA-level operational data entry (covered in later phases)'],
        ['IPSAS Cash-Basis & Accrual Reporting · GFS 2014 · OAGF / OAuGF Returns', '—'],
        ['Final Reporting · Document Control · Override & Data-Quality audit', '—'],
    ]),

    spacer(160),
    calloutBox('Why now', [
        'The Odoo deployment was scoped to a single office and a single function. As the State pursues full IPSAS-Accrual conversion and more transparent reporting to OAGF, the Office of the Accountant General needs a single platform that covers management accounting, treasury, budget execution, contract management, and final reporting under one governance model — without the integration drag of bolting together private-sector modules.',
        'Quot PSA was designed for exactly this remit. Every primitive — appropriation, warrant, vote book, TSA sub-account, IPC, retention — is a first-class object in the data model rather than a workaround built on top of commercial accounting primitives.',
    ]),
    pageBreak(),
];

// ═════════════════════════════════════════════════════════════════════════════
//                            CURRENT STATE
// ═════════════════════════════════════════════════════════════════════════════
const currentState = [
    h1('2.  Current State — Why Odoo Cannot Carry the Full OAG Mandate'),
    p('Odoo is a strong product within its design envelope: small-to-mid-size private-sector ERP. The constraints below are not deficiencies — they are the consequence of using a commercial-sector platform to enforce public-sector controls.', { spacing: { after: 160 } }),

    h2('2.1  Structural mismatches'),
    twoCol([
        ['Public-sector requirement', 'How Odoo handles it today'],
        ['Appropriation as the legal ceiling on every expenditure',
         'Odoo has budgets as advisory targets, not legal ceilings. No native pre-encumbrance block at PO/invoice.'],
        ['Commitment accounting (encumbrance at PO / LPO, not at invoice)',
         'Odoo records expenditure on invoice posting. Outstanding commitments are not tracked as an accounting balance.'],
        ['Fund accounting — money restricted by source (CRF, Development Fund, IGR, Donor)',
         'Odoo treats cash as pooled. Restricted-fund segregation requires manual analytical accounts that auditors cannot easily verify.'],
        ['7-segment National Chart of Accounts (Admin × Economic × Functional × Programme × Fund × Geo × Project)',
         'Odoo CoA is hierarchical (account.account) with up to two analytical axes. The remaining five NCoA segments must be approximated with tag-based workarounds.'],
        ['Treasury Single Account hierarchy with MDA sub-accounts',
         'Odoo has bank accounts but no model of a TSA hierarchy, sub-account sweeps, or deterministic TSA → GL resolution for cash-flow reporting.'],
        ['IPSAS-prescribed equity structure (Accumulated Fund, Revaluation Surplus, no profit concept)',
         'Odoo posts to Retained Earnings on close. IPSAS-correct equity sections require manual reclassification each period.'],
        ['Warrant (AIE) lifecycle with expiry, cancellation, virement re-check',
         'Odoo has no warrant model. AIEs are managed off-system in Excel and journals are entered after the fact.'],
        ['Statutory returns to OAGF, OAuGF, CBN, FIRS, Budget Office',
         'Odoo produces standard FS. The OAGF formats and Budget-Office returns are produced manually outside the system.'],
    ]),

    h2('2.2  Operational consequences observed in public-sector Odoo deployments'),
    bullet('Budget overrun is detected after the fact, at invoice posting, not blocked at the order — every overrun becomes an audit query.'),
    bullet('Warrants and AIE releases run in Excel; the GL has no record of unspent warrant balance per MDA.'),
    bullet('TSA position is reconstructed manually from bank statements rather than being live in the system.'),
    bullet('IPSAS reports are produced by exporting trial balances and reformatting in Excel, which forfeits any link back to underlying transactions.'),
    bullet('Contract IPCs and retention schedules live outside the accounting system, so retention released or due is never directly visible to the Accountant General.'),
    bullet('Document control (e.g., contract files, payment vouchers, mandates) is filesystem-based; there is no search, version, or audit trail.'),
    pageBreak(),
];

// ═════════════════════════════════════════════════════════════════════════════
//                            QUOT PSA — SOLUTION
// ═════════════════════════════════════════════════════════════════════════════
const solution = [
    h1('3.  The Proposed Solution — Quot PSA'),
    p('Quot PSA is a multi-tenant, schema-isolated platform built on Django 5.2 LTS, PostgreSQL 15, and React 19. Every module relevant to this proposal is already production-grade in the codebase; this is not a custom build.', { spacing: { after: 160 } }),

    h2('3.1  Module coverage map (within scope)'),
    threeCol([
        ['Capability', 'Quot PSA module', 'Evidence in the codebase'],
        ['Management Accounting', 'General Ledger · NCoA · Journals · Recurring Journals · Accruals & Deferrals · Year-End Close', 'accounting/models/gl.py · accounting/services/gl_posting.py · ipsas_journal_service.py · year_end_close.py'],
        ['Budget Appropriation', 'Appropriation Act loading · MDA ceilings · Budget lines · Variance', 'budget/models.py (Appropriation, UnifiedBudget) · budget/services.py · accounting/services/appropriation_totals.py'],
        ['Warrants', 'AIE · Recurrent & Capital warrants · Expiry · Cancellation · Virement re-check', 'budget/models.py (Warrant, AppropriationVirement) · accounting/budget_logic.py'],
        ['Virements', 'Inter-line & inter-MDA transfers with SoD approval', 'budget/services_virement.py'],
        ['Treasury (TSA)', 'TSA hierarchy · Sub-accounts · TSA transfers · Bank reconciliation · TSA → GL resolver', 'accounting/models/treasury.py · accounting/services/tsa_gl_resolver.py · tsa_bank_reconciliation.py'],
        ['Payments', 'Payment Vouchers (PVs) · Outgoing payments · Vendor mandates · Payment reconciliation queue · Duplicate-posting guard', 'accounting/services/pv_factory.py · accounting/models/payment_reconciliation.py · accounting/views/payables.py'],
        ['Contract Management', 'Contract register · IPCs · Retention · Mobilisation · Variations · Closure (with SoD)', 'contracts/models/* · contracts/services/* (ipc_service, retention_service, mobilization_service, variation_service, contract_closure_service)'],
        ['IPSAS Reporting', 'IPSAS Cash & Accrual · Notes to FS · Financial Position · Financial Performance · Cash Flow · Changes in Net Assets',
         'accounting/services/ipsas_reports.py · frontend/src/pages/gov/reports/* (19 reports)'],
        ['GFS 2014 & Budget Execution', 'Budget vs Actual · Budget Performance · Warrant Utilisation · Commitment · Execution · Functional Classification · Programme Performance',
         'frontend/src/pages/gov/reports/* · accounting/statutory/'],
        ['Statutory Returns', 'OAGF · OAuGF · FIRS · CBN templates (XML/XBRL)', 'accounting/statutory/oagf.py · firs.py · vat.py · paye.py · accounting/services/statutory_xml.py · xbrl_export.py'],
        ['Document Control', 'Versioned attachments · Magic-byte file-type validation · Audit trail · Override-audit page',
         'core/file_validation.py · accounting/services/audit_trail.py · frontend/src/pages/gov/OverrideAuditPage.tsx · AuditTrailViewer.tsx'],
        ['Final Reporting', 'Report snapshots · Cache layer · Export to Excel / PDF / XBRL', 'accounting/services/report_snapshot.py · report_cache.py · report_rendering.py'],
    ]),

    spacer(160),
    h2('3.2  Controls and integrity guarantees'),
    p('Every claim below maps to a specific service in the codebase. These are not roadmap items — they are deployed and tested behaviours.', { spacing: { after: 120 } }),
    bullet('Pre-commitment block: a commitment cannot be raised if the budget line, fund, and warrant balance do not cover it (accounting/services/procurement_commitments.py + accounting/budget_logic.py).'),
    bullet('Warrant expiry & cancellation: expired warrants are filtered from availability; a CANCELLED status is honoured everywhere (budget/models.py, Warrant.STATUS_CHOICES).'),
    bullet('Race-safe warrant checks: select_for_update protects warrant availability under concurrent draw-downs (accounting/budget_logic.py).'),
    bullet('Posting idempotency: unique index on (source_module, source_document_id) guarantees no journal is posted twice (accounting/models/gl.py).'),
    bullet('Period control on every action: post, reverse, and unpost all validate fiscal-period status (accounting/services/period_control.py).'),
    bullet('Segregation of Duties (SoD): central evaluator returns HTTP 403 on conflict; same rules guard warrant release, virement approval, appropriation enactment, IPC posting, mobilisation release, contract closure (contracts/services/sod.py and the global DRF exception handler in core/drf_exception_handler.py).'),
    bullet('Contract integrity: measurement books lock once cited; IPC voucher raising uses select_for_update to prevent double vouchers; variation orders re-check appropriation if the ceiling is increased (contracts/services/ipc_service.py + variation_service.py).'),
    bullet('Audit trail: every posting, override, configuration change, and approval is written to an immutable audit table (accounting/services/audit_trail.py).'),
    bullet('No silent failures: explicit error surfacing in WHT exemption derivation, year-end close, IPSAS revenue-budget rolls, and payment cascade processing.'),
    pageBreak(),
];

// ═════════════════════════════════════════════════════════════════════════════
//                            FUNCTIONAL UNITS COVERED
// ═════════════════════════════════════════════════════════════════════════════
const oagUnits = [
    h1('4.  Coverage Across the OAG Functional Units'),
    p('Previously the Odoo deployment served a single office. This deployment will span every functional unit within the Office of the Accountant General.', { spacing: { after: 160 } }),

    twoCol([
        ['OAG Unit', 'Quot PSA coverage'],
        ['Management Accounting',
         'GL postings, NCoA-aligned journals, recurring journals, cost-centre allocation, accruals & deferrals, period close, year-end close, trial balance, P&L, balance sheet, cash-flow (managerial pack).'],
        ['Treasury',
         'TSA Ledger, TSA hierarchy admin, TSA transfers (inter-MDA & TSA-to-bank), bank reconciliation (race-safe auto-match), TSA cash-position report, mirror sync via signal (no GET-side writes).'],
        ['Budget Execution & Warrants',
         'Appropriation administration, warrant issuance, AIE, virement workflow, budget check rules, MDA ceilings, expired-warrant filtering, override-audit on overrides.'],
        ['Contract Management',
         'Contract register, IPCs, retention accrual & release, mobilisation advance & recovery, variations with appropriation re-check, defects-liability tracking, closure with two-person SoD.'],
        ['Payments',
         'Payment Vouchers (PVs), outgoing payment instructions to bank, mandate generation, payment reconciliation queue, retry_payment_cascades management command, vendor advance warning, WHT derivation.'],
        ['Final Reporting',
         'IPSAS Statement of Financial Position, Financial Performance, Cash Flows (direct), Changes in Net Assets, Notes to FS, plus full GFS 2014 budget-execution pack.'],
        ['Document Control',
         'Attached documents per contract / voucher / journal, magic-byte file-type validation, versioning via audit trail, search across attached metadata, override-audit on document replacement.'],
        ['Audit & Compliance',
         'Audit trail viewer, override-audit page, data-quality page (validation failures and uncleared items live), structured JSON logging suitable for SIEM ingestion.'],
    ]),
    pageBreak(),
];

// ═════════════════════════════════════════════════════════════════════════════
//                            DEPLOYMENT OPTIONS
// ═════════════════════════════════════════════════════════════════════════════
const deployment = [
    h1('5.  Deployment Options'),
    p('We evaluate four deployment options. Each is analysed on the same dimensions: total cost of ownership, performance ceiling, data sovereignty, business-continuity, and operational complexity. The Office of the Accountant General is then offered a recommendation and a fall-back option.', { spacing: { after: 200 } }),

    // ── 5.1 ONLINE / VPS ────────────────────────────────────────────────
    h2('5.1  Option A — Online deployment on Cloud VPS'),
    p('Quot PSA is deployed onto a managed virtual private server in a Tier-III data centre. All access is via HTTPS from OAG and MDA workstations.', { spacing: { after: 120 } }),

    h3('Recommended VPS class'),
    twoCol([
        ['Specification', 'Recommended (production)'],
        ['Provider class',         'AWS EC2 (af-south-1 Cape Town), Azure South Africa North, Google Cloud Africa (Johannesburg), or DigitalOcean Frankfurt/London for cost-sensitive baseline. Preference: AWS af-south-1 for Africa-resident data and lowest latency to West Africa.'],
        ['Instance type',          'Compute-optimised, e.g. AWS c6i.2xlarge or equivalent (8 vCPU, 16 GB RAM) for the application tier'],
        ['Database tier',          'Managed PostgreSQL 15 — AWS RDS db.m6g.large or Azure Database for PostgreSQL Flexible Server, with read-replica in a second AZ'],
        ['Storage',                '200 GB SSD (gp3 / Premium SSD) for application, 500 GB SSD for database, 1 TB cold-tier S3/Blob for document archive'],
        ['Network',                'Static public IP · Cloudflare or CloudFront in front · WAF enabled · TLS 1.3 only'],
        ['Backup',                 'Continuous WAL archival + nightly snapshot + weekly cross-region copy (PITR window 14 days)'],
        ['Estimated monthly cost', 'USD 480 – 780 / month all-in (production + read-replica + backup + WAF + monitoring)'],
    ]),
    spacer(160),

    prosCons('Pros & Cons — Online (VPS)',
        [
            'No upfront capital expenditure on hardware',
            'Predictable monthly OPEX, scales up or down on demand',
            'Built-in geographic redundancy and managed backups',
            'Patching, OS hardening, and DDoS protection handled by the cloud provider',
            'Accessible to every OAG staff and authorised MDA from any compliant network',
            'Disaster recovery is intrinsic — losing the office does not lose the system',
            'Faster initial rollout (no procurement of physical equipment)',
        ],
        [
            'Data residency: data sits with a foreign cloud provider; constitutional and FOI concerns must be addressed by contractual / location controls',
            'Recurring monthly cost forever — over a 5-year horizon it can exceed an on-premise build',
            'Dependent on internet reliability of the Secretariat — outages stop work',
            'Bandwidth costs at month-end report generation can spike',
            'Less control over the exact moment of OS / database patching windows',
            'Forex exposure on USD-denominated subscriptions',
        ]
    ),
    pageBreak(),

    // ── 5.2 ON-PREMISE ─────────────────────────────────────────────────
    h2('5.2  Option B — On-premise deployment on Delta State servers'),
    p('Quot PSA is deployed onto physical or virtualised servers located in the Government Secretariat or the State data centre, accessed over the Secretariat LAN/WAN.', { spacing: { after: 120 } }),

    h3('Recommended server class'),
    twoCol([
        ['Specification', 'Recommended (production)'],
        ['Form factor',            'Rack-mounted 2U servers, minimum two physical servers (application + database)'],
        ['CPU',                    'Dual-socket Intel Xeon Silver 4416+ (20 cores / 40 threads each) — or AMD EPYC 9224 equivalent. Strong single-thread performance matters for PostgreSQL query plans.'],
        ['Memory',                 '128 GB DDR5 ECC RAM (database server); 64 GB on application server'],
        ['Storage',                '4 × 1.92 TB enterprise NVMe SSD in RAID-10 for database (sustained ≥ 50,000 IOPS); 2 × 960 GB SSD RAID-1 for OS; 8 × 4 TB SATA Enterprise in RAID-6 for document archive'],
        ['Network',                'Dual 10 GbE bonded uplinks · redundant top-of-rack switches · dedicated VLAN for OAG'],
        ['Power & cooling',        'Dual hot-swap PSU on each server · UPS with 30-min runtime · diesel generator failover · CRAC cooling rated for the rack thermal load'],
        ['OS & DB',                'AlmaLinux 9 (RHEL-compatible) · PostgreSQL 15 · PgBouncer connection pooling · Gunicorn + Nginx · Redis 7'],
        ['Backup target',          'Synology RackStation or QNAP NAS, 24 TB usable, in a separate fire-cell; weekly tape rotation (LTO-9) for off-site vault'],
        ['Estimated CAPEX',        'NGN 28 – 42 million for the two-server estate including UPS, NAS, network gear, and 3-year vendor warranty. Plus annual OPEX of NGN 2 – 3 M for power, cooling, and licences.'],
    ]),
    spacer(160),

    calloutBox('Why these specs matter',
        'Quot PSA holds the entire Trial Balance, IPSAS Statement of Financial Position, and Budget-Execution Report in PostgreSQL aggregations over potentially millions of journal lines. The NVMe storage tier is non-negotiable for the report-cache regeneration window at month-end; SAS spinning disks halve report-generation throughput in our benchmarks.',
        COLOR.panelBg, COLOR.accentDark),

    spacer(160),
    prosCons('Pros & Cons — On-premise',
        [
            'Full data sovereignty — every byte stays inside the Government Secretariat',
            'Lowest long-run cost: one-time CAPEX, modest annual maintenance, no monthly cloud bill',
            'Predictable performance — no contention with other tenants',
            'Independent of public internet for in-office operations',
            'Maximum control over change windows, patching, and audit-trail retention',
            'No forex exposure on the platform itself',
            'Auditor-General and OAuGF can physically inspect the infrastructure',
        ],
        [
            'Significant upfront capital expenditure on hardware, racks, UPS, cooling',
            'Operational burden: backups, patching, hardware refresh every 5 years',
            'Single-site risk — a fire, flood, or extended power outage at the Secretariat affects availability',
            'Requires a permanent system-administration capability inside the OAG',
            'Disaster recovery requires a deliberate plan (the next two options solve this)',
            'Initial deployment is slower because hardware must be procured and racked',
            'Difficult to expand capacity rapidly during peak workloads (year-end close)',
        ]
    ),
    pageBreak(),

    // ── 5.3 HYBRID 1 — DEPLOY ON-PREM + BACKUP ONLINE ──────────────
    h2('5.3  Option C — On-premise primary with online backup and DR (Hybrid)'),
    p('Production runs on the Secretariat servers as in Option B. Continuous incremental backups and a warm standby database replicate to a cloud VPS in real time. If the on-premise estate becomes unavailable, the cloud standby is promoted to take live traffic.', { spacing: { after: 120 } }),

    h3('How it works'),
    bullet('PostgreSQL streaming replication from the on-premise primary to a hot-standby instance in the cloud (lag typically under 30 seconds).'),
    bullet('Application servers in the cloud are kept in a warm state — same code release, scaled down to a minimum instance until needed.'),
    bullet('Document archive is mirrored to encrypted object storage (S3 / Blob) every 15 minutes.'),
    bullet('DNS-based fail-over: a 5-minute TTL on the application hostname allows automatic redirection on declared incident.'),
    bullet('Quarterly DR drill: a real fail-over is rehearsed under controlled conditions and signed off by the Accountant General’s designate.'),

    spacer(120),
    prosCons('Pros & Cons — On-premise primary + online DR',
        [
            'Combines data sovereignty (primary in-State) with cloud-grade business continuity',
            'A regional disaster does not stop the OAG — fail-over in minutes',
            'Cost-efficient: cloud footprint is minimal (warm standby), only scaled up on incident',
            'Satisfies both OAuGF inspection requirements and modern DR standards',
            'Year-end close peaks can be temporarily handled by elastically scaling the cloud tier',
            'The on-premise estate remains the system of record; the cloud is the safety net',
        ],
        [
            'Operationally the most complex option — requires both teams (in-house + Dplux DR runbook)',
            'Replication lag must be monitored and tested; an undetected break could mean data-loss on fail-over',
            'Two distinct security perimeters to maintain (Secretariat LAN + cloud VPC)',
            'Cloud egress fees during a real DR event can be material if not budgeted',
            'Adds a small recurring cost (the warm standby) on top of the CAPEX',
        ]
    ),
    pageBreak(),

    // ── 5.4 HYBRID 2 — DEPLOY ONLINE + RUN ON-PREM (DUAL) ──────────
    h2('5.4  Option D — Online primary with on-premise read-replica / dual operation'),
    p('Production runs on the cloud VPS as in Option A. A read-replica plus document mirror is maintained on a single on-premise server inside the Secretariat. The on-premise replica serves two purposes: it is a live local cache for high-volume reads (e.g. dashboards) and it becomes the writable instance if internet connectivity is lost.', { spacing: { after: 120 } }),

    h3('How it works'),
    bullet('Cloud primary handles all write traffic from OAG and MDAs under normal conditions.'),
    bullet('On-premise replica runs read-only and is consulted by Secretariat workstations for dashboards and standard reports (lower latency, no internet round-trip).'),
    bullet('A monitored heartbeat detects internet outage; on confirmed outage the on-premise instance is promoted to a writable “offline mode” for in-office continuity.'),
    bullet('When connectivity returns, a guided merge / re-sync workflow re-establishes the cloud as primary. The merge is deterministic because all transactions carry tenant-scoped sequences.'),
    bullet('All backups and DR remain managed by the cloud provider; the on-premise unit is an availability aid, not the system of record.'),

    spacer(120),
    prosCons('Pros & Cons — Cloud primary + on-premise replica',
        [
            'Best in-office performance: dashboards and reports come from a local cache',
            'No work stoppage during Secretariat-side internet outages',
            'Minimal on-premise footprint — one server, no full data-centre buildout',
            'Cloud manages backup / DR / patching as in Option A',
            'Easy to scale up cloud tier for year-end peaks without buying hardware',
            'New MDAs can be onboarded purely in the cloud, with no Secretariat involvement',
        ],
        [
            'Conflict resolution after a long offline period requires operator review (rare but real)',
            'Two systems means two attack surfaces — both must be hardened',
            'Data residency is partial: the system of record is still in the cloud',
            'Replica must be kept in lock-step with the cloud version — a patch lag introduces drift',
            'Cost is cloud baseline plus a one-time on-premise server (smaller than Option B)',
        ]
    ),
    pageBreak(),
];

// ═════════════════════════════════════════════════════════════════════════════
//                            COMPARISON & RECOMMENDATION
// ═════════════════════════════════════════════════════════════════════════════
const recommendation = [
    h1('6.  Side-by-Side Comparison & Recommendation'),

    h2('6.1  At-a-glance comparison'),
    fourCol([
        ['Dimension',          'A · Cloud VPS',                  'B · On-premise',              'C · On-prem + Cloud DR',     'D · Cloud + On-prem replica'],
        ['Upfront CAPEX',      'Low',                            'High (₦28–42 M)',             'High',                       'Low-medium'],
        ['Monthly OPEX',       'Medium (USD 480-780)',           'Low',                         'Medium-low',                 'Medium'],
        ['Data sovereignty',   'Mitigated by region',            'Maximum (in-Secretariat)',    'Maximum (primary local)',    'Partial (primary cloud)'],
        ['Business continuity','Cloud-grade',                    'Site-dependent (weakest)',    'Best of both',               'In-office continuity'],
        ['Year-end peak handling','Elastic',                     'Capped at server spec',       'Burstable into cloud',       'Elastic'],
        ['Internet dependency','Total',                          'None (in-office)',            'Only during fail-over',      'Tolerated locally'],
        ['Operational complexity','Lowest',                      'Medium',                      'Highest',                    'Medium-high'],
        ['5-year TCO (est.)',  'USD 28k–47k',                    '₦42–56 M',                    '₦48–62 M',                   '₦20–28 M + USD 14k–24k'],
        ['Time to first production','4 weeks',                   '10–12 weeks',                 '12–14 weeks',                '8–10 weeks'],
    ], [2200, 2300, 2300, 2400, 2880].slice(0, 5)),
    spacer(160),

    // The recommendation
    h2('6.2  Recommendation'),
    calloutBox(
        'Primary recommendation — Option C (On-premise primary with online DR)',
        [
            'This option is the closest fit to the operating reality of the Office of the Accountant General:',
            '  ·  Constitutional and FOI sensitivities around treasury data are honoured — the system of record is inside the Government Secretariat.',
            '  ·  The Auditor-General can physically inspect the infrastructure that holds the State’s ledgers.',
            '  ·  Business continuity is not deferred — a Secretariat-level incident does not bring down State accounting.',
            '  ·  Year-end peaks can elastically burst into the cloud tier without provisioning permanent capacity.',
            '  ·  The cost premium over plain on-premise is modest (~10-15 %) for a disproportionate gain in resilience.',
            'This is the configuration Dplux deploys for Tier-1 public-sector clients where both data-sovereignty and 24×7 availability are mandatory.',
        ],
        'EAF3EA', COLOR.ok,
    ),

    spacer(160),
    h3('Fall-back recommendation — Option D'),
    p('If hardware procurement timelines are a constraint, or if the State wishes to begin with a lower upfront commitment, Option D (cloud primary with on-premise replica) is the recommended interim path. It delivers most of the same continuity properties at lower CAPEX and shorter time-to-production, and can be later upgraded to Option C by promoting the on-premise replica to primary once Secretariat capacity is ready.', { spacing: { after: 120 } }),

    h3('When each option is appropriate'),
    twoCol([
        ['Scenario', 'Recommended option'],
        ['OAG has Secretariat data-centre capacity and can absorb CAPEX immediately', 'Option C (on-prem primary + cloud DR)'],
        ['OAG wants to move quickly with minimal CAPEX and grow into on-prem later',  'Option D (cloud + on-prem replica), upgrade to C in Year 2'],
        ['Budget cycle delays prevent hardware procurement this fiscal year',          'Option A (cloud VPS only) for a 12-month bridge, planning toward C'],
        ['Maximum sovereignty mandated and DR can be deferred to manual snapshots',    'Option B (on-prem only), with a tape-rotation DR plan'],
    ]),
    pageBreak(),
];

// ═════════════════════════════════════════════════════════════════════════════
//                            IMPLEMENTATION & MIGRATION
// ═════════════════════════════════════════════════════════════════════════════
const implementation = [
    h1('7.  Implementation Approach'),

    h2('7.1  Phased rollout'),
    twoCol([
        ['Phase', 'Activities and deliverables'],
        ['Phase 0 — Inception (Weeks 1–2)',
         'On-site at OAG. Inventory of current Odoo data, chart of accounts mapping, fiscal-year status, list of open warrants, in-flight contracts, IPCs awaiting payment. Network and infrastructure walk-through.'],
        ['Phase 1 — Infrastructure (Weeks 3–4)',
         'Stand up the chosen deployment topology (servers, OS, DB, network). Hardening per the Dplux production playbook. SSL, firewall, backup configuration.'],
        ['Phase 2 — Configuration (Weeks 4–6)',
         'NCoA setup for Delta State (7-segment); fund taxonomy (CRF, Development Fund, IGR, Donor); appropriation Acts loaded; warrant templates per MDA; approval workflows per OAG SoD policy; printout templates for warrants and vouchers.'],
        ['Phase 3 — Data Migration (Weeks 5–8)',
         'Migration from Odoo: chart of accounts mapping, opening balances, vendor master, open AP & AR, in-flight contracts and IPCs, document archive. Parallel reconciliation against Odoo for one full month.'],
        ['Phase 4 — Training (Weeks 6–10)',
         '12 OAG system administrators and 30 OAG operator staff trained. Role-based curricula: treasury operator, budget controller, contracts officer, reporting analyst, system administrator.'],
        ['Phase 5 — Pilot Cut-over (Weeks 9–12)',
         'Final reporting and treasury go live on Quot PSA. Odoo remains available read-only for reconciliation. One full month of OAGF returns produced from Quot PSA.'],
        ['Phase 6 — Full Cut-over (Weeks 12–14)',
         'Budget appropriation, warrants, payments, and contract management cut over. Odoo retired. Auditor-General walkthrough. DR drill executed.'],
        ['Phase 7 — Steady State (Ongoing)',
         'Quarterly DR drill, fiscal-year roll-over support, year-end close, platform upgrades, MDA onboarding waves.'],
    ]),

    spacer(160),
    h2('7.2  Migration from Odoo — what is preserved'),
    bullet('All historic journals (re-mapped to NCoA, with original Odoo account codes retained as reference dimensions).'),
    bullet('Vendor master and customer master, de-duplicated and validated against TIN where present.'),
    bullet('Trial balance at the cut-over date, posted as Quot PSA opening balances.'),
    bullet('Open AP invoices, open AR invoices, and open contract IPCs — migrated as open items so payment continuity is preserved.'),
    bullet('Attached documents (contracts, payment vouchers) — migrated into the new Document Control module with magic-byte validation and audit trail.'),
    bullet('Historic IPSAS reports — exported to PDF and archived as report snapshots so prior-year comparatives remain accessible.'),

    h2('7.3  Risk register'),
    threeCol([
        ['Risk', 'Likelihood × Impact', 'Mitigation'],
        ['Odoo NCoA mapping omissions',         'Medium × High',  'Two-week parallel running with line-by-line reconciliation; sign-off by OAG before retirement.'],
        ['Power / network instability on-prem',  'Medium × High',  'UPS + diesel generator + redundant network paths; Option C cloud DR is the ultimate hedge.'],
        ['User adoption / change resistance',    'Medium × Medium','Role-based training, in-app help, and dedicated Dplux floor-walker support during first two close cycles.'],
        ['Data residency concerns (cloud)',      'Low × High',     'Africa-region cloud only (AWS af-south-1); data-protection addendum signed; on-prem primary if Option C chosen.'],
        ['Year-end close coincidence',           'High × High',    'Cut-over scheduled to avoid Dec / Jan; minimum 30-day quiet period before close.'],
        ['Skills gap inside OAG',                'Medium × Medium','12-person system administration cohort trained and certified before cut-over.'],
        ['Vendor lock-in concern',               'Low × Medium',   'Quot PSA exports raw data on demand in XBRL, Excel, CSV; source-code escrow available on request.'],
    ]),
    pageBreak(),
];

// ═════════════════════════════════════════════════════════════════════════════
//                            COMMERCIALS
// ═════════════════════════════════════════════════════════════════════════════
const commercials = [
    h1('8.  Commercial Framework'),
    p('Indicative figures below are provided for budgeting purposes only. Final commercials will be confirmed in the formal Statement of Work after Phase 0.', { spacing: { after: 120 } }),

    h2('8.1  Implementation fee (one-time)'),
    twoCol([
        ['Workstream', 'Indicative fee (NGN)'],
        ['Infrastructure setup, hardening, and SSL', '3,500,000 – 6,500,000 (depending on Option A/B/C/D)'],
        ['Data migration from Odoo', '4,800,000'],
        ['Configuration (NCoA, funds, warrants, templates, approvals)', '3,200,000'],
        ['Training (42 staff, role-based, two cohorts)', '2,600,000'],
        ['Parallel running and cut-over support', '2,400,000'],
        ['Documentation pack and DR runbook', '1,400,000'],
        ['Total indicative implementation fee', '17,900,000 – 20,900,000'],
    ]),

    spacer(160),
    h2('8.2  Recurring annual fee'),
    twoCol([
        ['Component', 'Indicative annual fee (NGN)'],
        ['Platform licence (OAG + connected MDAs, unlimited users)', '9,800,000'],
        ['Support (8 × 5, weekday business-hours, with 4-hour P1 SLA)', '3,600,000'],
        ['Optional 24×7 support upgrade', '+2,400,000'],
        ['Quarterly DR drill facilitation and year-end close support', '1,800,000'],
        ['Total indicative annual recurring (standard support)', '15,200,000'],
    ]),

    spacer(160),
    h2('8.3  Infrastructure cost (additional, by chosen option)'),
    twoCol([
        ['Option', 'Indicative cost'],
        ['A · Cloud VPS only',                        'USD 480 – 780 / month (foreign currency, paid to cloud provider)'],
        ['B · On-premise only',                       '₦28 – 42 M CAPEX, then ₦2 – 3 M / year OPEX (power, cooling, parts)'],
        ['C · On-prem primary + cloud DR (recommended)', '₦28 – 42 M CAPEX + USD 180 – 280 / month (warm standby footprint)'],
        ['D · Cloud primary + on-prem replica',       'USD 480 – 780 / month + ₦8 – 12 M one-time (replica server)'],
    ]),

    spacer(160),
    h2('8.4  Commercial principles'),
    bullet('Fixed-fee implementation. No additional licence cost until the cut-over criterion is independently signed off by the Office of the Accountant General.'),
    bullet('Standard payment milestones: 20 % on contract execution, 30 % on infrastructure ready, 30 % on parallel-run sign-off, 20 % on full cut-over sign-off.'),
    bullet('All amounts are exclusive of statutory taxes (VAT, WHT) which shall be deducted at source per Delta State rules.'),
    bullet('Source-code escrow available on written request; data-export utilities included at no extra cost.'),
    pageBreak(),
];

// ═════════════════════════════════════════════════════════════════════════════
//                            GOVERNANCE
// ═════════════════════════════════════════════════════════════════════════════
const governance = [
    h1('9.  Governance, Acceptance & Service Levels'),

    h2('9.1  Acceptance criteria'),
    p('The platform is deemed accepted when, and only when, the following are demonstrated to the Office of the Accountant General:', { spacing: { after: 120 } }),
    numItem('A complete OAGF monthly return is generated from Quot PSA with zero reconciling differences against the official Odoo close for the same month.'),
    numItem('A trial balance and IPSAS Statement of Financial Position can be produced on demand in under 90 seconds at month-end volumes.'),
    numItem('A warrant draw-down is blocked, with audit trail, when the underlying appropriation is exhausted.'),
    numItem('An IPC payment cannot be raised twice on the same certificate, even under simulated concurrent operator action.'),
    numItem('A contract closure is blocked when the closing officer is the same as the originator (SoD demonstration).'),
    numItem('A successful DR drill is conducted under observation of an OAG representative.'),

    h2('9.2  Service Level Agreement'),
    twoCol([
        ['Service item', 'Standard SLA'],
        ['Application availability',         '99.5 % monthly (excludes scheduled maintenance windows)'],
        ['Maintenance window',                'Sundays 02:00–06:00 WAT, notified 7 days in advance'],
        ['P1 incident (system down)',         '4-hour response, 12-hour restoration'],
        ['P2 incident (major function down)',  '8-hour response, 48-hour restoration'],
        ['P3 incident (minor)',                'Next business day response'],
        ['Backup integrity check',            'Weekly automated restore-test against staging'],
        ['Quarterly DR drill',                'Live fail-over rehearsal, attended by OAG observer, report signed by both parties'],
        ['Annual penetration test',           'By an independent third party; report shared with OAG'],
    ]),

    h2('9.3  Governance structure'),
    bullet('Project Steering Committee chaired by a representative of the Office of the Accountant General, with Dplux Engagement Lead present.'),
    bullet('Bi-weekly status meeting during implementation; monthly thereafter.'),
    bullet('Dedicated Dplux Engagement Manager assigned for the duration of the engagement.'),
    bullet('All change requests routed through a single change-control board; emergency-change procedure documented.'),
    bullet('Annual independent audit of the platform configuration, available for the Auditor-General’s inspection.'),
    pageBreak(),
];

// ═════════════════════════════════════════════════════════════════════════════
//                            CLOSING
// ═════════════════════════════════════════════════════════════════════════════
const closing = [
    h1('10.  Closing and Next Steps'),
    p('The Office of the Accountant General has, in Odoo, a strong general-ledger and reporting tool — but a tool built for a different problem space. Public-sector accounting is not a profit-and-loss discipline. It is a discipline of legal ceilings, restricted funds, statutory submissions, and Treasury Single Account discipline.', { spacing: { after: 120 } }),
    p('Quot PSA is the system the OAG would have built itself, given the engineering capacity. Every primitive that matters — appropriation, warrant, vote book, IPC, retention, TSA sub-account — is first-class. Every control that auditors test for — pre-encumbrance, SoD, period gating, idempotent posting, immutable audit trail — is enforced in code, not in process.', { spacing: { after: 160 } }),

    calloutBox(
        'Proposed next steps',
        [
            '1. A discovery workshop on-site at the Office of the Accountant General (one working day) to confirm in-scope MDAs, the chosen deployment option, and the migration window.',
            '2. A live demonstration of Quot PSA against a sanitised Delta State dataset.',
            '3. A formal Statement of Work tabled within 14 days of the discovery workshop.',
            '4. Mobilisation immediately on contract execution; Phase 0 begins within one week.',
        ]
    ),

    spacer(400),

    // Contact card
    new Table({
        width: { size: PAGE.contentWidth, type: WidthType.DXA },
        columnWidths: [PAGE.contentWidth],
        rows: [new TableRow({
            children: [new TableCell({
                width: { size: PAGE.contentWidth, type: WidthType.DXA },
                shading: { fill: COLOR.primary, type: ShadingType.CLEAR },
                borders: allBorders(COLOR.primary, 0),
                margins: { top: 360, bottom: 360, left: 480, right: 480 },
                children: [
                    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 100 },
                        children: [new TextRun({ text: 'For further information', font: 'Calibri', size: 22, color: 'D9C7A8', characterSpacing: 30 })] }),
                    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 80 },
                        children: [new TextRun({ text: 'Jacob Osadiaye', font: 'Calibri', size: 36, bold: true, color: 'FFFFFF' })] }),
                    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 80 },
                        children: [new TextRun({ text: 'Dplux Technologies', font: 'Calibri', size: 22, color: 'FFFFFF' })] }),
                    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 60 },
                        children: [new TextRun({ text: 'osadiaye4real@gmail.com', font: 'Calibri', size: 22, color: 'D9C7A8' })] }),
                    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 0 },
                        children: [new TextRun({ text: 'github.com/oosadiaye/Quot-PSA', font: 'Calibri', size: 20, italics: true, color: 'D9C7A8' })] }),
                ],
            })],
        })],
    }),
];

// ─── Header / footer ──────────────────────────────────────────────────────────
const docHeader = new Header({
    children: [new Paragraph({
        tabStops: [{ type: TabStopType.RIGHT, position: PAGE.contentWidth }],
        border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: COLOR.primary, space: 4 } },
        children: [
            new TextRun({ text: 'PROPOSAL  ·  QUOT PSA UPGRADE', font: 'Calibri', size: 18, bold: true, color: COLOR.primary, characterSpacing: 24 }),
            new TextRun({ text: '\tOffice of the Accountant General, Delta State', font: 'Calibri', size: 18, italics: true, color: COLOR.muted }),
        ],
    })],
});

const docFooter = new Footer({
    children: [new Paragraph({
        tabStops: [{ type: TabStopType.RIGHT, position: PAGE.contentWidth }],
        border: { top: { style: BorderStyle.SINGLE, size: 6, color: COLOR.rule, space: 4 } },
        children: [
            new TextRun({ text: 'Dplux Technologies   ·   Confidential', font: 'Calibri', size: 16, color: COLOR.muted }),
            new TextRun({ text: '\tPage ', font: 'Calibri', size: 16, color: COLOR.muted }),
            new TextRun({ children: [PageNumber.CURRENT], font: 'Calibri', size: 16, color: COLOR.muted }),
            new TextRun({ text: ' of ', font: 'Calibri', size: 16, color: COLOR.muted }),
            new TextRun({ children: [PageNumber.TOTAL_PAGES], font: 'Calibri', size: 16, color: COLOR.muted }),
        ],
    })],
});

// ─── Document ─────────────────────────────────────────────────────────────────
const doc = new Document({
    creator: 'Dplux Technologies',
    title: 'Quot PSA Upgrade Proposal — Office of the Accountant General, Delta State',
    description: 'Proposal for the upgrade of the OAG Delta State accounting platform from Odoo to Quot PSA.',
    styles: {
        default: { document: { run: { font: 'Calibri', size: 22 } } },
        paragraphStyles: [
            { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true,
              run: { size: 36, bold: true, font: 'Calibri', color: COLOR.primary },
              paragraph: { spacing: { before: 360, after: 160 }, outlineLevel: 0 } },
            { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true,
              run: { size: 28, bold: true, font: 'Calibri', color: COLOR.primary },
              paragraph: { spacing: { before: 240, after: 100 }, outlineLevel: 1 } },
            { id: 'Heading3', name: 'Heading 3', basedOn: 'Normal', next: 'Normal', quickFormat: true,
              run: { size: 24, bold: true, font: 'Calibri', color: COLOR.accentDark },
              paragraph: { spacing: { before: 180, after: 80 }, outlineLevel: 2 } },
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
            { reference: 'numbers',
              levels: [
                { level: 0, format: LevelFormat.DECIMAL, text: '%1.', alignment: AlignmentType.LEFT,
                  style: { paragraph: { indent: { left: 720, hanging: 360 } } } },
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
            ...execSummary,
            ...currentState,
            ...solution,
            ...oagUnits,
            ...deployment,
            ...recommendation,
            ...implementation,
            ...commercials,
            ...governance,
            ...closing,
        ],
    }],
});

Packer.toBuffer(doc).then(buf => {
    const out = 'Proposal_Quot_PSA_Delta_OAG.docx';
    fs.writeFileSync(out, buf);
    console.log(`Wrote ${out} (${buf.length.toLocaleString()} bytes)`);
}).catch(err => {
    console.error('Build failed:', err);
    process.exit(1);
});

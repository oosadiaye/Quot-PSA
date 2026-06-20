/**
 * Quot PSA — Presentation deck for the
 * Office of the Accountant General, Delta State Government Secretariat.
 *
 * Presented by:  Jacob Osadiaye
 * Prepared by:   Dplux Technologies
 */
const fs = require('fs');
const pptxgen = require('pptxgenjs');
const React = require('react');
const ReactDOMServer = require('react-dom/server');
const sharp = require('sharp');
const {
    FaUniversity, FaShieldAlt, FaFileInvoiceDollar, FaBalanceScale,
    FaProjectDiagram, FaCheckCircle, FaServer, FaUsersCog, FaChartLine,
    FaHandHoldingUsd, FaScroll, FaBuilding, FaLock, FaSitemap, FaGavel,
    FaCogs, FaCloud, FaDatabase, FaUserShield, FaCoins, FaSearchDollar,
    FaCalculator, FaArrowRight, FaPhoneAlt, FaEnvelope, FaGithub, FaIndustry,
    FaClipboardCheck, FaNetworkWired,
} = require('react-icons/fa');

// ─── Palette: Delta-State emerald & gold (treasury-credible) ──────────────────
const C = {
    primary:    '0F4C3A',  // deep emerald
    primaryAlt: '1B7A5A',  // medium emerald
    accent:     'D4A574',  // warm gold
    accentDark: 'A88051',
    cream:      'F7F4ED',  // warm off-white
    creamAlt:   'EFEAD9',
    ink:        '1A2B26',  // very dark green-black
    muted:      '64748B',
    rule:       'D6CFB8',
    white:      'FFFFFF',
    danger:     '991B1B',
    ok:         '15803D',
};

// ─── Helpers ──────────────────────────────────────────────────────────────────
async function iconPng(Icon, color = '#FFFFFF', size = 256) {
    const svg = ReactDOMServer.renderToStaticMarkup(
        React.createElement(Icon, { color, size: String(size) })
    );
    const buf = await sharp(Buffer.from(svg)).png().toBuffer();
    return 'image/png;base64,' + buf.toString('base64');
}

const SLIDE_W = 13.333;
const SLIDE_H = 7.5;

// Standard side margin
const M = 0.55;

// ─── Build ────────────────────────────────────────────────────────────────────
async function main() {
    const pres = new pptxgen();
    pres.layout = 'LAYOUT_WIDE';      // 13.333 x 7.5
    pres.author = 'Dplux Technologies';
    pres.company = 'Dplux Technologies';
    pres.title  = 'Quot PSA — Briefing for the Office of the Accountant General, Delta State';

    // Pre-render the icons we'll need (one base64 PNG per icon × colour).
    const ICONS = {};
    const need = [
        ['university',     FaUniversity],
        ['shield',         FaShieldAlt],
        ['invoice',        FaFileInvoiceDollar],
        ['balance',        FaBalanceScale],
        ['flow',           FaProjectDiagram],
        ['check',          FaCheckCircle],
        ['server',         FaServer],
        ['users',          FaUsersCog],
        ['chart',          FaChartLine],
        ['hold',           FaHandHoldingUsd],
        ['scroll',         FaScroll],
        ['building',       FaBuilding],
        ['lock',           FaLock],
        ['sitemap',        FaSitemap],
        ['gavel',          FaGavel],
        ['cogs',           FaCogs],
        ['cloud',          FaCloud],
        ['database',       FaDatabase],
        ['usershield',     FaUserShield],
        ['coins',          FaCoins],
        ['searchdollar',   FaSearchDollar],
        ['calc',           FaCalculator],
        ['arrow',          FaArrowRight],
        ['phone',          FaPhoneAlt],
        ['envelope',       FaEnvelope],
        ['github',         FaGithub],
        ['industry',       FaIndustry],
        ['clipboard',      FaClipboardCheck],
        ['network',        FaNetworkWired],
    ];
    for (const [key, Icon] of need) {
        ICONS[key] = {
            white: await iconPng(Icon, '#FFFFFF'),
            primary: await iconPng(Icon, `#${C.primary}`),
            accent: await iconPng(Icon, `#${C.accent}`),
            cream: await iconPng(Icon, `#${C.cream}`),
        };
    }

    // ── Reusable layout primitives ───────────────────────────────────────────

    /** Top page-header bar: thin emerald strip with deck title left + slide tag right */
    function headerBar(slide, tag) {
        slide.addShape(pres.shapes.RECTANGLE, {
            x: 0, y: 0, w: SLIDE_W, h: 0.42,
            fill: { color: C.primary }, line: { color: C.primary, width: 0 },
        });
        slide.addText('QUOT PSA  ·  Briefing to the Office of the Accountant General, Delta State', {
            x: M, y: 0.04, w: 9.5, h: 0.34,
            fontFace: 'Calibri', fontSize: 10.5, color: C.cream, charSpacing: 18, valign: 'middle',
            margin: 0,
        });
        if (tag) {
            slide.addText(tag, {
                x: SLIDE_W - 3.5 - M, y: 0.04, w: 3.5, h: 0.34,
                fontFace: 'Calibri', fontSize: 10.5, color: C.accent, bold: true,
                align: 'right', valign: 'middle', charSpacing: 12, margin: 0,
            });
        }
    }

    /** Bottom footer */
    function footer(slide, pageNum) {
        slide.addShape(pres.shapes.LINE, {
            x: M, y: SLIDE_H - 0.42, w: SLIDE_W - 2 * M, h: 0,
            line: { color: C.rule, width: 0.75 },
        });
        slide.addText('Dplux Technologies   ·   Quot PSA Briefing   ·   Presented by Jacob Osadiaye', {
            x: M, y: SLIDE_H - 0.36, w: 9, h: 0.3,
            fontFace: 'Calibri', fontSize: 9, color: C.muted, valign: 'middle', margin: 0,
        });
        slide.addText(`${pageNum}`, {
            x: SLIDE_W - M - 0.4, y: SLIDE_H - 0.36, w: 0.4, h: 0.3,
            fontFace: 'Calibri', fontSize: 9, color: C.muted, bold: true,
            align: 'right', valign: 'middle', margin: 0,
        });
    }

    /** Big page title (no underline accent — looks AI-generated) */
    function pageTitle(slide, title, kicker) {
        if (kicker) {
            slide.addText(kicker, {
                x: M, y: 0.65, w: 8, h: 0.32,
                fontFace: 'Calibri', fontSize: 11, color: C.accentDark, bold: true,
                charSpacing: 24, margin: 0,
            });
        }
        slide.addText(title, {
            x: M, y: kicker ? 0.95 : 0.7, w: SLIDE_W - 2 * M, h: 0.85,
            fontFace: 'Georgia', fontSize: 30, color: C.primary, bold: true, margin: 0,
        });
    }

    /** Coloured circular badge with an icon centred on it. */
    function iconBadge(slide, iconKey, x, y, size = 0.55, ringColor = C.primary, iconColor = 'white') {
        slide.addShape(pres.shapes.OVAL, {
            x, y, w: size, h: size,
            fill: { color: ringColor }, line: { color: ringColor, width: 0 },
        });
        const iconSize = size * 0.55;
        slide.addImage({
            data: ICONS[iconKey][iconColor],
            x: x + (size - iconSize) / 2,
            y: y + (size - iconSize) / 2,
            w: iconSize, h: iconSize,
        });
    }

    let pageNum = 0;
    const nextPage = () => ++pageNum;

    // ════════════════════════════════════════════════════════════════════════
    // SLIDE 1 — COVER
    // ════════════════════════════════════════════════════════════════════════
    {
        const s = pres.addSlide();
        s.background = { color: C.primary };

        // Big decorative gold ring upper-right
        s.addShape(pres.shapes.OVAL, {
            x: SLIDE_W - 4.6, y: -2.5, w: 6, h: 6,
            fill: { color: C.primary }, line: { color: C.accent, width: 4 },
        });
        s.addShape(pres.shapes.OVAL, {
            x: SLIDE_W - 3.2, y: -1.1, w: 3.3, h: 3.3,
            fill: { color: C.primaryAlt }, line: { color: C.primaryAlt, width: 0 },
        });

        // Small gold square accent lower-left
        s.addShape(pres.shapes.RECTANGLE, {
            x: 0, y: SLIDE_H - 0.18, w: 4.5, h: 0.18,
            fill: { color: C.accent }, line: { color: C.accent, width: 0 },
        });

        s.addText('DPLUX  TECHNOLOGIES', {
            x: M, y: 0.55, w: 8, h: 0.4,
            fontFace: 'Calibri', fontSize: 13, color: C.accent, bold: true,
            charSpacing: 60, margin: 0,
        });

        s.addText('Quot PSA', {
            x: M, y: 2.0, w: 9, h: 1.4,
            fontFace: 'Georgia', fontSize: 80, color: C.white, bold: true, margin: 0,
        });

        s.addText('A Public Sector Accounting Platform purpose-built for the IFMIS framework, IPSAS reporting, and the Treasury Single Account.', {
            x: M, y: 3.7, w: 8.6, h: 1.2,
            fontFace: 'Calibri', fontSize: 18, color: C.cream, margin: 0, italic: false,
        });

        // Briefing-to strip
        s.addShape(pres.shapes.RECTANGLE, {
            x: M, y: 5.3, w: 0.06, h: 1.4,
            fill: { color: C.accent }, line: { color: C.accent, width: 0 },
        });
        s.addText('A Briefing to', {
            x: M + 0.22, y: 5.28, w: 6, h: 0.32,
            fontFace: 'Calibri', fontSize: 11, color: C.accent, bold: true,
            charSpacing: 24, margin: 0,
        });
        s.addText('The Office of the Accountant General', {
            x: M + 0.22, y: 5.58, w: 8, h: 0.5,
            fontFace: 'Georgia', fontSize: 22, color: C.white, bold: true, margin: 0,
        });
        s.addText('Delta State Government Secretariat, Asaba', {
            x: M + 0.22, y: 6.05, w: 8, h: 0.4,
            fontFace: 'Calibri', fontSize: 14, color: C.cream, margin: 0,
        });
        s.addText('Presented by Jacob Osadiaye  ·  Dplux Technologies', {
            x: M + 0.22, y: 6.42, w: 8, h: 0.32,
            fontFace: 'Calibri', fontSize: 12, color: C.accent, italic: true, margin: 0,
        });
    }

    // ════════════════════════════════════════════════════════════════════════
    // SLIDE 2 — AGENDA
    // ════════════════════════════════════════════════════════════════════════
    {
        const s = pres.addSlide();
        s.background = { color: C.cream };
        headerBar(s, 'AGENDA');
        pageTitle(s, 'What we will cover today', 'A 25-minute walkthrough');

        const items = [
            ['1', 'About Dplux Technologies',          'Who we are and what we have shipped'],
            ['2', 'The control problem in public-sector accounting', 'Why off-the-shelf ERP cannot satisfy IFMIS'],
            ['3', 'Quot PSA — the platform',            'Architecture, modules, and statutory alignment'],
            ['4', 'Treasury Single Account',            'TSA hierarchy, sub-accounts, and reconciliation'],
            ['5', 'Budget control & commitment accounting', 'Appropriation gating, warrants, virements'],
            ['6', 'Reporting — IPSAS, GFS 2014, OAGF returns', '19 statutory reports out of the box'],
            ['7', 'Security, audit & Segregation of Duties', 'Multi-tenancy, RBAC, SoD, MFA, full audit trail'],
            ['8', 'Proposed Delta State pilot & next steps', 'Scope, timeline, and success criteria'],
        ];

        const startY = 2.05;
        const rowH   = 0.55;
        items.forEach(([num, title, sub], i) => {
            const y = startY + i * rowH;
            // Number badge
            s.addShape(pres.shapes.OVAL, {
                x: M + 0.05, y: y + 0.04, w: 0.42, h: 0.42,
                fill: { color: C.primary }, line: { color: C.primary, width: 0 },
            });
            s.addText(num, {
                x: M + 0.05, y: y + 0.04, w: 0.42, h: 0.42,
                fontFace: 'Georgia', fontSize: 14, color: C.accent, bold: true,
                align: 'center', valign: 'middle', margin: 0,
            });
            // Title + sub
            s.addText(title, {
                x: M + 0.6, y: y - 0.02, w: 7.5, h: 0.32,
                fontFace: 'Calibri', fontSize: 16, color: C.ink, bold: true, margin: 0, valign: 'middle',
            });
            s.addText(sub, {
                x: M + 0.6, y: y + 0.24, w: 8.5, h: 0.28,
                fontFace: 'Calibri', fontSize: 11.5, color: C.muted, margin: 0, valign: 'middle',
            });
        });

        // Right-side decorative panel
        s.addShape(pres.shapes.RECTANGLE, {
            x: SLIDE_W - 3.5, y: 1.9, w: 2.95, h: 4.7,
            fill: { color: C.primary }, line: { color: C.primary, width: 0 },
        });
        s.addText('Time at a glance', {
            x: SLIDE_W - 3.35, y: 2.05, w: 2.7, h: 0.4,
            fontFace: 'Calibri', fontSize: 11, color: C.accent, bold: true,
            charSpacing: 20, margin: 0,
        });
        const time = [
            ['18 min', 'Briefing'],
            ['7 min',  'Live demo'],
            ['Open',   'Q & A'],
        ];
        time.forEach(([big, label], i) => {
            const y = 2.55 + i * 1.3;
            s.addText(big, {
                x: SLIDE_W - 3.35, y, w: 2.7, h: 0.7,
                fontFace: 'Georgia', fontSize: 36, color: C.white, bold: true, margin: 0,
            });
            s.addText(label, {
                x: SLIDE_W - 3.35, y: y + 0.7, w: 2.7, h: 0.32,
                fontFace: 'Calibri', fontSize: 11, color: C.cream, margin: 0,
            });
        });
        footer(s, nextPage());
    }

    // ════════════════════════════════════════════════════════════════════════
    // SLIDE 3 — ABOUT DPLUX
    // ════════════════════════════════════════════════════════════════════════
    {
        const s = pres.addSlide();
        s.background = { color: C.cream };
        headerBar(s, 'WHO WE ARE');
        pageTitle(s, 'Dplux Technologies', 'Engineering for institutions that cannot afford to be wrong');

        // Two-column body
        const leftX = M, leftW = 6.3;
        s.addText(
            'Dplux Technologies is a Nigerian software engineering firm that builds mission-critical platforms for finance, government, and regulated industries. ' +
            'We specialise in the kind of systems where a quiet failure is the worst kind of failure — treasuries, accounting back-offices, healthcare records, and procurement controls.',
            {
                x: leftX, y: 2.05, w: leftW, h: 1.6,
                fontFace: 'Calibri', fontSize: 14.5, color: C.ink, margin: 0, paraSpaceAfter: 6,
            }
        );

        // Three pillars
        const pillars = [
            ['flow',       'Domain-first engineering',  'We model the regulation before we model the database.'],
            ['shield',     'Audit-grade traceability',  'Every change is attributable. No silent failures.'],
            ['users',      'Operator-ready delivery',   'Runbooks, DR drills, and training included.'],
        ];
        const pillarY = 3.85;
        pillars.forEach(([icon, t, body], i) => {
            const y = pillarY + i * 0.95;
            iconBadge(s, icon, leftX, y, 0.5, C.primary, 'accent');
            s.addText(t, {
                x: leftX + 0.7, y, w: leftW - 0.7, h: 0.32,
                fontFace: 'Calibri', fontSize: 14, color: C.ink, bold: true, margin: 0, valign: 'middle',
            });
            s.addText(body, {
                x: leftX + 0.7, y: y + 0.3, w: leftW - 0.7, h: 0.5,
                fontFace: 'Calibri', fontSize: 11.5, color: C.muted, margin: 0,
            });
        });

        // Right-side stat panel
        const rx = SLIDE_W - M - 5.3;
        s.addShape(pres.shapes.RECTANGLE, {
            x: rx, y: 2.05, w: 5.3, h: 4.55,
            fill: { color: C.primary }, line: { color: C.primary, width: 0 },
        });
        s.addText('AT A GLANCE', {
            x: rx + 0.35, y: 2.2, w: 4.6, h: 0.32,
            fontFace: 'Calibri', fontSize: 11, color: C.accent, bold: true,
            charSpacing: 28, margin: 0,
        });

        // Big stat grid 2x2
        const stats = [
            ['7+',  'Years building',     'mission-critical systems'],
            ['20+', 'Functional modules', 'shipped in Quot PSA alone'],
            ['100%','Nigerian',           'engineering team'],
            ['IFMIS', 'Native', 'platform designed for the framework'],
        ];
        const gx = rx + 0.3, gy = 2.7, gw = 2.4, gh = 1.85, gap = 0.1;
        stats.forEach((st, i) => {
            const col = i % 2, row = Math.floor(i / 2);
            const x = gx + col * (gw + gap);
            const y = gy + row * (gh + gap);
            s.addShape(pres.shapes.RECTANGLE, {
                x, y, w: gw, h: gh,
                fill: { color: C.primaryAlt }, line: { color: C.primaryAlt, width: 0 },
            });
            s.addText(st[0], {
                x: x + 0.15, y: y + 0.15, w: gw - 0.3, h: 0.7,
                fontFace: 'Georgia', fontSize: 32, color: C.accent, bold: true, margin: 0,
            });
            s.addText(st[1], {
                x: x + 0.15, y: y + 0.85, w: gw - 0.3, h: 0.32,
                fontFace: 'Calibri', fontSize: 12, color: C.white, bold: true, margin: 0,
            });
            s.addText(st[2], {
                x: x + 0.15, y: y + 1.15, w: gw - 0.3, h: 0.5,
                fontFace: 'Calibri', fontSize: 10.5, color: C.cream, margin: 0,
            });
        });

        footer(s, nextPage());
    }

    // ════════════════════════════════════════════════════════════════════════
    // SLIDE 4 — OUR WORK
    // ════════════════════════════════════════════════════════════════════════
    {
        const s = pres.addSlide();
        s.background = { color: C.cream };
        headerBar(s, 'OUR WORK');
        pageTitle(s, 'Selected platforms we have shipped', 'Production systems serving regulated workloads');

        const projects = [
            {
                icon: 'university', tag: 'Public Sector',
                title: 'Quot PSA',
                body: 'A multi-tenant IFMIS-aligned Public Sector Accounting platform with TSA, IPSAS reporting, commitment control, and 19 statutory reports. (The subject of today\'s briefing.)',
            },
            {
                icon: 'invoice', tag: 'Healthcare',
                title: 'Clinical & Revenue Cycle Suite',
                body: 'A full hospital information system covering EMR, laboratory, radiology, pharmacy, billing, claims, and revenue-cycle management with PHI-grade access controls.',
            },
            {
                icon: 'sitemap', tag: 'Procurement',
                title: 'Contracts & Vendor Lifecycle',
                body: 'Vendor onboarding, contract register, IPC processing, retention scheduling, and BPP-aligned procurement workflows — the core that powers Quot PSA contracts.',
            },
            {
                icon: 'building', tag: 'Enterprise',
                title: 'Dplux ERP & HRM',
                body: 'A multi-module ERP suite — finance, HR, payroll, inventory, sales, and approval workflow — deployed for mid-sized private-sector operators across West Africa.',
            },
            {
                icon: 'cloud', tag: 'Platform',
                title: 'Multi-tenant SaaS Infrastructure',
                body: 'A reusable tenant-isolated SaaS substrate — schema-per-tenant Postgres, superadmin console, per-tenant module gating — that underpins every Dplux product line.',
            },
            {
                icon: 'shield', tag: 'Security & Audit',
                title: 'Segregation-of-Duties Engine',
                body: 'A centralised SoD evaluator that prevents conflicting actions across modules, with audit logging and policy-as-code rule authoring — embedded in Quot PSA.',
            },
        ];

        // 3 columns x 2 rows
        const gridX = M, gridY = 2.05;
        const cardW = 4.0, cardH = 2.1, gapX = 0.12, gapY = 0.16;
        projects.forEach((p, i) => {
            const col = i % 3, row = Math.floor(i / 3);
            const x = gridX + col * (cardW + gapX);
            const y = gridY + row * (cardH + gapY);
            // Card
            s.addShape(pres.shapes.RECTANGLE, {
                x, y, w: cardW, h: cardH,
                fill: { color: C.white }, line: { color: C.rule, width: 1 },
            });
            // Left accent bar
            s.addShape(pres.shapes.RECTANGLE, {
                x, y, w: 0.08, h: cardH,
                fill: { color: C.accent }, line: { color: C.accent, width: 0 },
            });
            // Icon badge
            iconBadge(s, p.icon, x + 0.25, y + 0.22, 0.45, C.primary, 'accent');
            // Tag
            s.addText(p.tag, {
                x: x + 0.8, y: y + 0.18, w: cardW - 0.95, h: 0.26,
                fontFace: 'Calibri', fontSize: 9.5, color: C.accentDark, bold: true,
                charSpacing: 20, margin: 0,
            });
            // Title
            s.addText(p.title, {
                x: x + 0.25, y: y + 0.78, w: cardW - 0.4, h: 0.42,
                fontFace: 'Georgia', fontSize: 16, color: C.primary, bold: true, margin: 0,
            });
            // Body
            s.addText(p.body, {
                x: x + 0.25, y: y + 1.18, w: cardW - 0.4, h: cardH - 1.3,
                fontFace: 'Calibri', fontSize: 10.5, color: C.ink, margin: 0,
            });
        });

        footer(s, nextPage());
    }

    // ════════════════════════════════════════════════════════════════════════
    // SLIDE 5 — THE CONTROL PROBLEM
    // ════════════════════════════════════════════════════════════════════════
    {
        const s = pres.addSlide();
        s.background = { color: C.primary };
        headerBar(s, 'THE PROBLEM');
        // Override header (it'll already be primary, but make page-title white)
        s.addShape(pres.shapes.RECTANGLE, {
            x: 0, y: 0, w: SLIDE_W, h: 0.42,
            fill: { color: C.primaryAlt }, line: { color: C.primaryAlt, width: 0 },
        });
        s.addText('QUOT PSA  ·  Briefing to the Office of the Accountant General, Delta State', {
            x: M, y: 0.04, w: 9.5, h: 0.34,
            fontFace: 'Calibri', fontSize: 10.5, color: C.cream, charSpacing: 18, valign: 'middle', margin: 0,
        });
        s.addText('THE PROBLEM', {
            x: SLIDE_W - 3.5 - M, y: 0.04, w: 3.5, h: 0.34,
            fontFace: 'Calibri', fontSize: 10.5, color: C.accent, bold: true,
            align: 'right', valign: 'middle', charSpacing: 12, margin: 0,
        });

        s.addText('The framework is public-sector. The software, mostly, is not.', {
            x: M, y: 0.85, w: SLIDE_W - 2 * M, h: 0.5,
            fontFace: 'Calibri', fontSize: 12, color: C.accent, bold: true,
            charSpacing: 20, margin: 0,
        });
        s.addText('What treasuries actually need — and what most ERPs cannot provide.', {
            x: M, y: 1.35, w: SLIDE_W - 2 * M, h: 0.85,
            fontFace: 'Georgia', fontSize: 30, color: C.white, bold: true, margin: 0,
        });

        // Two-column: left list of public-sector primitives, right "what private ERP gives"
        const colY = 2.6, colH = 4.0;
        const colW = (SLIDE_W - 2 * M - 0.4) / 2;

        // Left card — what public sector requires
        s.addShape(pres.shapes.RECTANGLE, {
            x: M, y: colY, w: colW, h: colH,
            fill: { color: C.primaryAlt }, line: { color: C.accent, width: 1.5 },
        });
        s.addText('What Public Sector Accounting requires', {
            x: M + 0.3, y: colY + 0.25, w: colW - 0.6, h: 0.4,
            fontFace: 'Calibri', fontSize: 14, color: C.accent, bold: true,
            charSpacing: 12, margin: 0,
        });
        const required = [
            'Appropriation as legal ceiling on every expenditure',
            'Commitment accounting at the PO, not at the invoice',
            'Fund accounting with restricted sources (CRF, IGR, Donor)',
            '7-segment NCoA: Admin × Economic × Functional × Programme × Fund × Geo × Project',
            'Treasury Single Account hierarchy with MDA sub-accounts',
            'IPSAS-prescribed equity structure (Accumulated Fund, Revaluation Surplus)',
            'Statutory submissions to OAGF, OAuGF, CBN, FIRS, Budget Office',
        ];
        s.addText(
            required.map((t, i) => ({ text: t, options: { bullet: { code: '25A0' }, breakLine: i !== required.length - 1, color: C.white } })),
            {
                x: M + 0.3, y: colY + 0.85, w: colW - 0.6, h: colH - 1.1,
                fontFace: 'Calibri', fontSize: 11.5, color: C.white, paraSpaceAfter: 6, margin: 0,
            }
        );

        // Right card — what a typical ERP gives
        const rx = M + colW + 0.4;
        s.addShape(pres.shapes.RECTANGLE, {
            x: rx, y: colY, w: colW, h: colH,
            fill: { color: C.cream }, line: { color: C.cream, width: 0 },
        });
        s.addText('What a typical commercial ERP gives', {
            x: rx + 0.3, y: colY + 0.25, w: colW - 0.6, h: 0.4,
            fontFace: 'Calibri', fontSize: 14, color: C.accentDark, bold: true,
            charSpacing: 12, margin: 0,
        });
        const provided = [
            'Profit & loss accounting',
            'Invoice-time commitment (already too late)',
            'Pooled cash with no fund restriction',
            'A 3 to 5-segment commercial chart of accounts',
            'Bank accounts, but no TSA model',
            'Retained Earnings (not Accumulated Fund)',
            'Quarterly investor reports, not OAGF returns',
        ];
        s.addText(
            provided.map((t, i) => ({ text: t, options: { bullet: { code: '25A1' }, breakLine: i !== provided.length - 1, color: C.ink } })),
            {
                x: rx + 0.3, y: colY + 0.85, w: colW - 0.6, h: colH - 1.1,
                fontFace: 'Calibri', fontSize: 11.5, color: C.ink, paraSpaceAfter: 6, margin: 0,
            }
        );

        // Footer (white-on-primary)
        s.addText('Dplux Technologies   ·   Presented by Jacob Osadiaye', {
            x: M, y: SLIDE_H - 0.36, w: 9, h: 0.3,
            fontFace: 'Calibri', fontSize: 9, color: C.cream, margin: 0, valign: 'middle',
        });
        s.addText(`${nextPage()}`, {
            x: SLIDE_W - M - 0.4, y: SLIDE_H - 0.36, w: 0.4, h: 0.3,
            fontFace: 'Calibri', fontSize: 9, color: C.accent, bold: true,
            align: 'right', valign: 'middle', margin: 0,
        });
    }

    // ════════════════════════════════════════════════════════════════════════
    // SLIDE 6 — INTRODUCING QUOT PSA
    // ════════════════════════════════════════════════════════════════════════
    {
        const s = pres.addSlide();
        s.background = { color: C.cream };
        headerBar(s, 'THE PLATFORM');
        pageTitle(s, 'Introducing Quot PSA', 'Built ground-up for the public sector');

        s.addText(
            'Quot PSA is a full-stack Public Sector Accounting platform. Every primitive — appropriation, warrant, commitment, fund, vote book, voucher, mandate, TSA sub-account — is modelled as a first-class object. The result is a system that enforces fiscal control at the point of commitment, not after the fact.',
            {
                x: M, y: 2.05, w: SLIDE_W - 2 * M, h: 1.0,
                fontFace: 'Calibri', fontSize: 14.5, color: C.ink, margin: 0,
            }
        );

        // Stat strip — four big numbers
        const stats = [
            ['20+',   'Functional modules'],
            ['19',    'Statutory IPSAS / GFS reports'],
            ['7-seg', 'NCoA classification'],
            ['SoD',   'Centrally enforced'],
        ];
        const stripY = 3.3, stripH = 1.5, cellW = (SLIDE_W - 2 * M - 0.3) / 4;
        stats.forEach(([big, label], i) => {
            const x = M + i * (cellW + 0.1);
            s.addShape(pres.shapes.RECTANGLE, {
                x, y: stripY, w: cellW, h: stripH,
                fill: { color: C.white }, line: { color: C.rule, width: 1 },
            });
            s.addShape(pres.shapes.RECTANGLE, {
                x, y: stripY, w: cellW, h: 0.08,
                fill: { color: C.accent }, line: { color: C.accent, width: 0 },
            });
            s.addText(big, {
                x: x + 0.2, y: stripY + 0.2, w: cellW - 0.4, h: 0.75,
                fontFace: 'Georgia', fontSize: 42, color: C.primary, bold: true, margin: 0,
            });
            s.addText(label, {
                x: x + 0.2, y: stripY + 0.95, w: cellW - 0.4, h: 0.45,
                fontFace: 'Calibri', fontSize: 12, color: C.ink, margin: 0,
            });
        });

        // Bottom row — four feature one-liners with icons
        const feats = [
            ['scroll',   'IFMIS-aligned',          'Designed around the Federal IFMIS framework, not retrofitted.'],
            ['balance',  'IPSAS-compliant',        'Cash-basis and accrual reporting out of the box.'],
            ['shield',   'Audit-grade',            'Immutable audit trail on every posting and override.'],
            ['sitemap',  'Multi-tenant',           'Per-MDA schema isolation in a single deployment.'],
        ];
        const rowY = 5.2, rowH = 1.4;
        feats.forEach(([icon, t, body], i) => {
            const x = M + i * (cellW + 0.1);
            s.addShape(pres.shapes.RECTANGLE, {
                x, y: rowY, w: cellW, h: rowH,
                fill: { color: C.primary }, line: { color: C.primary, width: 0 },
            });
            iconBadge(s, icon, x + 0.2, y = rowY + 0.18, 0.5, C.primaryAlt, 'accent');
            s.addText(t, {
                x: x + 0.85, y: rowY + 0.2, w: cellW - 1.0, h: 0.42,
                fontFace: 'Calibri', fontSize: 13, color: C.accent, bold: true,
                charSpacing: 12, margin: 0, valign: 'middle',
            });
            s.addText(body, {
                x: x + 0.2, y: rowY + 0.8, w: cellW - 0.4, h: 0.55,
                fontFace: 'Calibri', fontSize: 10.5, color: C.cream, margin: 0,
            });
        });

        footer(s, nextPage());
    }

    // ════════════════════════════════════════════════════════════════════════
    // SLIDE 7 — MODULE MAP
    // ════════════════════════════════════════════════════════════════════════
    {
        const s = pres.addSlide();
        s.background = { color: C.cream };
        headerBar(s, 'MODULE MAP');
        pageTitle(s, 'One platform, every public-sector workflow', 'Twenty integrated modules across four functional bands');

        const bands = [
            { name: 'BUDGET & APPROPRIATION',
              color: C.primary,
              items: ['MTEF & Sector Envelopes', 'Appropriation Loading', 'Warrants & AIE', 'Virements', 'Budget Check Rules'] },
            { name: 'COMMITMENT & PROCUREMENT',
              color: C.primaryAlt,
              items: ['Vendor Registry', 'Requisitions', 'POs / LPOs', 'GRN & Invoice Matching', 'Contracts & IPCs'] },
            { name: 'TREASURY, GL & TAX',
              color: C.accentDark,
              items: ['TSA Ledger', 'Bank & Cash', 'General Ledger & NCoA', 'AP / AR', 'PAYE · VAT · WHT'] },
            { name: 'REPORTING, AUDIT & SUPPORT',
              color: C.ink,
              items: ['IPSAS Reports', 'GFS 2014', 'Audit Trail · SoD · RBAC', 'HRM & Payroll', 'Inventory & Assets'] },
        ];

        const startY = 2.05;
        const rowH   = 1.15;
        bands.forEach((band, i) => {
            const y = startY + i * (rowH + 0.12);
            // Band label
            s.addShape(pres.shapes.RECTANGLE, {
                x: M, y, w: 2.7, h: rowH,
                fill: { color: band.color }, line: { color: band.color, width: 0 },
            });
            s.addText(band.name, {
                x: M + 0.2, y, w: 2.5, h: rowH,
                fontFace: 'Calibri', fontSize: 12, color: C.white, bold: true,
                valign: 'middle', charSpacing: 14, margin: 0,
            });

            // Module pills (5 per row)
            const pillX0 = M + 2.85;
            const pillW = (SLIDE_W - M - pillX0 - 0.4) / 5;
            band.items.forEach((it, k) => {
                const px = pillX0 + k * (pillW + 0.05);
                s.addShape(pres.shapes.RECTANGLE, {
                    x: px, y: y + 0.15, w: pillW, h: rowH - 0.3,
                    fill: { color: C.white }, line: { color: C.rule, width: 1 },
                });
                s.addShape(pres.shapes.RECTANGLE, {
                    x: px, y: y + 0.15, w: pillW, h: 0.06,
                    fill: { color: band.color }, line: { color: band.color, width: 0 },
                });
                s.addText(it, {
                    x: px + 0.12, y: y + 0.25, w: pillW - 0.24, h: rowH - 0.45,
                    fontFace: 'Calibri', fontSize: 11.5, color: C.ink, bold: true,
                    valign: 'middle', margin: 0,
                });
            });
        });

        footer(s, nextPage());
    }

    // ════════════════════════════════════════════════════════════════════════
    // SLIDE 8 — TSA (flagship for OAG audience)
    // ════════════════════════════════════════════════════════════════════════
    {
        const s = pres.addSlide();
        s.background = { color: C.cream };
        headerBar(s, 'TREASURY SINGLE ACCOUNT');
        pageTitle(s, 'Treasury Single Account — whole-of-government cash visibility', 'One consolidated view of every Naira held in the State treasury');

        // Left: TSA hierarchy diagram
        const dgX = M, dgY = 2.0, dgW = 6.4, dgH = 4.2;
        s.addShape(pres.shapes.RECTANGLE, {
            x: dgX, y: dgY, w: dgW, h: dgH,
            fill: { color: C.white }, line: { color: C.rule, width: 1 },
        });
        s.addText('TSA hierarchy in Quot PSA', {
            x: dgX + 0.25, y: dgY + 0.2, w: dgW - 0.5, h: 0.35,
            fontFace: 'Calibri', fontSize: 12, color: C.accentDark, bold: true, charSpacing: 14, margin: 0,
        });

        // Master TSA box
        s.addShape(pres.shapes.RECTANGLE, {
            x: dgX + 1.5, y: dgY + 0.75, w: 3.4, h: 0.7,
            fill: { color: C.primary }, line: { color: C.primary, width: 0 },
        });
        s.addText('Delta State Master TSA', {
            x: dgX + 1.5, y: dgY + 0.75, w: 3.4, h: 0.7,
            fontFace: 'Georgia', fontSize: 15, color: C.white, bold: true,
            align: 'center', valign: 'middle', margin: 0,
        });
        // Connector down
        s.addShape(pres.shapes.LINE, {
            x: dgX + 3.2, y: dgY + 1.45, w: 0, h: 0.45,
            line: { color: C.muted, width: 1.5 },
        });
        // Horizontal connector
        s.addShape(pres.shapes.LINE, {
            x: dgX + 0.6, y: dgY + 1.9, w: 5.2, h: 0,
            line: { color: C.muted, width: 1.5 },
        });
        // Four MDA boxes
        const mdas = ['Ministry of Finance', 'Health MDAs', 'Works & Housing', 'Education MDAs'];
        const mdaW = 1.25, mdaY = dgY + 1.9;
        mdas.forEach((m, i) => {
            const x = dgX + 0.4 + i * (mdaW + 0.1);
            // verticals
            s.addShape(pres.shapes.LINE, {
                x: x + mdaW / 2, y: mdaY, w: 0, h: 0.2,
                line: { color: C.muted, width: 1.5 },
            });
            s.addShape(pres.shapes.RECTANGLE, {
                x, y: mdaY + 0.2, w: mdaW, h: 0.6,
                fill: { color: C.primaryAlt }, line: { color: C.primaryAlt, width: 0 },
            });
            s.addText(m, {
                x, y: mdaY + 0.2, w: mdaW, h: 0.6,
                fontFace: 'Calibri', fontSize: 9.5, color: C.white, bold: true,
                align: 'center', valign: 'middle', margin: 0,
            });

            // sub-accounts (2 each)
            for (let k = 0; k < 2; k++) {
                const sy = mdaY + 0.95 + k * 0.45;
                s.addShape(pres.shapes.LINE, {
                    x: x + mdaW / 2, y: mdaY + 0.8, w: 0, h: 0.15 + k * 0.45,
                    line: { color: C.rule, width: 1 },
                });
                s.addShape(pres.shapes.RECTANGLE, {
                    x: x + 0.1, y: sy, w: mdaW - 0.2, h: 0.32,
                    fill: { color: C.cream }, line: { color: C.rule, width: 0.5 },
                });
                s.addText(`Sub-Acct ${k + 1}`, {
                    x: x + 0.1, y: sy, w: mdaW - 0.2, h: 0.32,
                    fontFace: 'Calibri', fontSize: 8.5, color: C.muted,
                    align: 'center', valign: 'middle', margin: 0,
                });
            }
        });

        // Note at bottom of diagram
        s.addText('Every MDA sub-account reconciles to the master daily — no shadow ledgers.', {
            x: dgX + 0.25, y: dgY + dgH - 0.5, w: dgW - 0.5, h: 0.3,
            fontFace: 'Calibri', fontSize: 10.5, color: C.muted, italic: true, margin: 0,
        });

        // Right: TSA capabilities
        const rx = SLIDE_W - M - 5.0;
        s.addShape(pres.shapes.RECTANGLE, {
            x: rx, y: 2.0, w: 5.0, h: 4.6,
            fill: { color: C.primary }, line: { color: C.primary, width: 0 },
        });
        s.addText('What Quot PSA provides', {
            x: rx + 0.3, y: 2.15, w: 4.6, h: 0.3,
            fontFace: 'Calibri', fontSize: 11, color: C.accent, bold: true, charSpacing: 24, margin: 0,
        });
        const tsaFeatures = [
            ['Real-time MDA balances',     'Live position per sub-account, refreshed on every payment.'],
            ['Deterministic TSA → GL',     'Movements resolve to the right GL account so cash-flow statements reconcile exactly.'],
            ['Race-safe bank reconciliation', 'Statement auto-match against CBN with row-level locking. No double-match.'],
            ['Mirror sync via signals',    'Updates only on confirmed payment events — never on read endpoints.'],
            ['Consolidated dashboard',     'For the Accountant-General — drill-down by MDA, fund, and sub-account.'],
        ];
        const tFY = 2.55, tFH = 0.78;
        tsaFeatures.forEach(([t, body], i) => {
            const y = tFY + i * tFH;
            iconBadge(s, 'check', rx + 0.25, y + 0.08, 0.32, C.primaryAlt, 'accent');
            s.addText(t, {
                x: rx + 0.7, y, w: 4.2, h: 0.3,
                fontFace: 'Calibri', fontSize: 12, color: C.white, bold: true, margin: 0,
            });
            s.addText(body, {
                x: rx + 0.7, y: y + 0.3, w: 4.2, h: 0.45,
                fontFace: 'Calibri', fontSize: 10, color: C.cream, margin: 0,
            });
        });

        footer(s, nextPage());
    }

    // ════════════════════════════════════════════════════════════════════════
    // SLIDE 9 — BUDGET CONTROL
    // ════════════════════════════════════════════════════════════════════════
    {
        const s = pres.addSlide();
        s.background = { color: C.cream };
        headerBar(s, 'BUDGET CONTROL');
        pageTitle(s, 'Appropriation is law — and it is enforced before the order is placed', 'The expenditure pipeline from MTEF to payment voucher');

        // Process bar
        const stages = [
            { k: 'scroll',   t: 'MTEF Envelope',        b: 'Multi-year sector ceilings' },
            { k: 'balance',  t: 'Appropriation Act',    b: 'Enacted, line-locked' },
            { k: 'gavel',    t: 'Warrant / AIE',        b: 'Released to MDA' },
            { k: 'clipboard',t: 'PR & LPO',             b: 'Commitment encumbered' },
            { k: 'invoice',  t: 'Invoice / IPC',        b: '3-way match' },
            { k: 'coins',    t: 'Voucher & Mandate',    b: 'Payment to TSA' },
        ];
        const stripY = 2.05, stripH = 1.5;
        const stepW = (SLIDE_W - 2 * M - 5 * 0.05) / stages.length;
        stages.forEach((st, i) => {
            const x = M + i * (stepW + 0.05);
            s.addShape(pres.shapes.RECTANGLE, {
                x, y: stripY, w: stepW, h: stripH,
                fill: { color: C.white }, line: { color: C.rule, width: 1 },
            });
            s.addShape(pres.shapes.RECTANGLE, {
                x, y: stripY, w: stepW, h: 0.36,
                fill: { color: C.primary }, line: { color: C.primary, width: 0 },
            });
            s.addText(`STAGE ${i + 1}`, {
                x: x + 0.1, y: stripY + 0.04, w: stepW - 0.2, h: 0.3,
                fontFace: 'Calibri', fontSize: 9.5, color: C.accent, bold: true, charSpacing: 18,
                margin: 0, valign: 'middle',
            });
            iconBadge(s, st.k, x + (stepW - 0.5) / 2, stripY + 0.5, 0.5, C.cream, 'primary');
            s.addText(st.t, {
                x: x + 0.1, y: stripY + 1.05, w: stepW - 0.2, h: 0.28,
                fontFace: 'Calibri', fontSize: 11.5, color: C.ink, bold: true, align: 'center', margin: 0,
            });
            s.addText(st.b, {
                x: x + 0.1, y: stripY + 1.28, w: stepW - 0.2, h: 0.2,
                fontFace: 'Calibri', fontSize: 9, color: C.muted, align: 'center', margin: 0,
            });
        });

        // Control gates — what blocks what
        const gateY = 3.95;
        s.addText('Gates the system enforces', {
            x: M, y: gateY, w: 5, h: 0.32,
            fontFace: 'Calibri', fontSize: 12, color: C.accentDark, bold: true, charSpacing: 18, margin: 0,
        });

        const gates = [
            ['Pre-commitment',  'Budget line balance ≥ commitment   ·   Warrant unexpired   ·   Fund matches'],
            ['SoD enforcement', 'Originator ≠ approver on every approval action — centrally evaluated'],
            ['Period control',  'Posting and reversing both validate fiscal-period open status'],
            ['Posting integrity','Unique (source_module, source_document_id) — duplicate posting impossible'],
            ['Row-level locking','select_for_update on warrants, IPCs, mobilisation, bulk approvals'],
        ];
        const gxY = 4.35, ghH = 0.42;
        gates.forEach(([t, body], i) => {
            const y = gxY + i * ghH;
            // Strip
            s.addShape(pres.shapes.RECTANGLE, {
                x: M, y, w: SLIDE_W - 2 * M, h: ghH - 0.06,
                fill: { color: i % 2 ? C.creamAlt : C.white }, line: { color: C.rule, width: 0.5 },
            });
            // Left tag
            s.addShape(pres.shapes.RECTANGLE, {
                x: M, y, w: 2.6, h: ghH - 0.06,
                fill: { color: C.primary }, line: { color: C.primary, width: 0 },
            });
            s.addText(t, {
                x: M + 0.2, y, w: 2.4, h: ghH - 0.06,
                fontFace: 'Calibri', fontSize: 11.5, color: C.white, bold: true,
                valign: 'middle', margin: 0,
            });
            s.addText(body, {
                x: M + 2.85, y, w: SLIDE_W - 2 * M - 2.95, h: ghH - 0.06,
                fontFace: 'Calibri', fontSize: 11, color: C.ink, valign: 'middle', margin: 0,
            });
        });

        footer(s, nextPage());
    }

    // ════════════════════════════════════════════════════════════════════════
    // SLIDE 10 — CONTRACTS & IPCs
    // ════════════════════════════════════════════════════════════════════════
    {
        const s = pres.addSlide();
        s.background = { color: C.cream };
        headerBar(s, 'CONTRACTS & IPCs');
        pageTitle(s, 'Works contracts, IPCs, retention and closure', 'The full lifecycle of a State capital project');

        // Two columns: lifecycle on left, capabilities on right
        // LEFT — lifecycle bullets
        const lx = M, ly = 2.05, lw = 5.7;
        s.addShape(pres.shapes.RECTANGLE, {
            x: lx, y: ly, w: lw, h: 4.6,
            fill: { color: C.white }, line: { color: C.rule, width: 1 },
        });
        s.addShape(pres.shapes.RECTANGLE, {
            x: lx, y: ly, w: 0.08, h: 4.6,
            fill: { color: C.accent }, line: { color: C.accent, width: 0 },
        });
        s.addText('Contract lifecycle', {
            x: lx + 0.3, y: ly + 0.2, w: lw - 0.5, h: 0.36,
            fontFace: 'Calibri', fontSize: 12, color: C.accentDark, bold: true, charSpacing: 18, margin: 0,
        });

        const phases = [
            ['Register',     'Parties, ceiling, BoQ, defects-liability period, attached documents.'],
            ['Mobilisation', 'Advance paid; recovery schedule tracked across subsequent IPCs.'],
            ['Measurement',  'Measurement books locked once cited — no retroactive edits.'],
            ['IPC',          'Interim Payment Certificate raised with row-level locking against double vouchers.'],
            ['Retention',    'Auto-accrual per IPC; release on completion or DLP expiry.'],
            ['Variation',    'Ceiling-increasing orders re-check appropriation availability.'],
            ['Closure',      'Two-person SoD; cascade settles outstanding IPCs and retention.'],
        ];
        const phY = ly + 0.7, phStep = 0.55;
        phases.forEach(([t, body], i) => {
            const y = phY + i * phStep;
            // bullet number
            s.addShape(pres.shapes.OVAL, {
                x: lx + 0.3, y: y + 0.05, w: 0.3, h: 0.3,
                fill: { color: C.primary }, line: { color: C.primary, width: 0 },
            });
            s.addText(`${i + 1}`, {
                x: lx + 0.3, y: y + 0.05, w: 0.3, h: 0.3,
                fontFace: 'Georgia', fontSize: 10, color: C.accent, bold: true,
                align: 'center', valign: 'middle', margin: 0,
            });
            s.addText(t, {
                x: lx + 0.7, y, w: 1.7, h: 0.4,
                fontFace: 'Calibri', fontSize: 12.5, color: C.primary, bold: true, valign: 'middle', margin: 0,
            });
            s.addText(body, {
                x: lx + 2.4, y, w: lw - 2.55, h: 0.4,
                fontFace: 'Calibri', fontSize: 11, color: C.ink, valign: 'middle', margin: 0,
            });
        });

        // RIGHT — controls panel
        const rx = M + lw + 0.3, rw = SLIDE_W - 2 * M - lw - 0.3, ry = 2.05;
        s.addShape(pres.shapes.RECTANGLE, {
            x: rx, y: ry, w: rw, h: 4.6,
            fill: { color: C.primary }, line: { color: C.primary, width: 0 },
        });
        s.addText('What this prevents', {
            x: rx + 0.25, y: ry + 0.2, w: rw - 0.5, h: 0.36,
            fontFace: 'Calibri', fontSize: 12, color: C.accent, bold: true, charSpacing: 20, margin: 0,
        });
        const prevents = [
            'Double-vouchering on the same IPC',
            'Quantity edits after a measurement is billed',
            'Variation orders that quietly breach the appropriation',
            'Retention released before defects-liability expires',
            'Contract closure by the same officer who raised the IPC',
            'Mobilisation advance forgotten and never recovered',
        ];
        s.addText(
            prevents.map((p, i) => ({ text: p, options: { bullet: { code: '25A0' }, color: C.white, breakLine: i !== prevents.length - 1 } })),
            {
                x: rx + 0.25, y: ry + 0.7, w: rw - 0.5, h: 3.7,
                fontFace: 'Calibri', fontSize: 12, color: C.white, paraSpaceAfter: 8, margin: 0,
            }
        );

        footer(s, nextPage());
    }

    // ════════════════════════════════════════════════════════════════════════
    // SLIDE 11 — REPORTING
    // ════════════════════════════════════════════════════════════════════════
    {
        const s = pres.addSlide();
        s.background = { color: C.cream };
        headerBar(s, 'REPORTING');
        pageTitle(s, 'Nineteen statutory reports, ready on day one', 'IPSAS, GFS 2014, and the OAGF / OAuGF returns calendar');

        // Three grouped columns of reports
        const groups = [
            {
                color: C.primary,
                title: 'IPSAS Financial Statements',
                items: [
                    'Statement of Financial Position',
                    'Statement of Financial Performance',
                    'Statement of Cash Flows (direct method)',
                    'Statement of Changes in Net Assets / Equity',
                    'Notes to the Financial Statements',
                ],
            },
            {
                color: C.primaryAlt,
                title: 'Budget Execution & GFS 2014',
                items: [
                    'Budget vs. Actual (GFS 2014)',
                    'Budget Performance Report',
                    'Warrant Utilisation Report',
                    'Commitment Report',
                    'Execution Report',
                    'Functional Classification (COFOG)',
                    'Programme Performance',
                ],
            },
            {
                color: C.accentDark,
                title: 'Treasury, Fund & Revenue',
                items: [
                    'TSA Cash Position',
                    'Fund Performance (CRF / Dev Fund / IGR)',
                    'Revenue Performance',
                    'Geographic Distribution',
                    'XBRL & Statutory XML exports',
                    'Trial Balance, P&L, Balance Sheet, Cash Flow (managerial pack)',
                    'Report Snapshot & cache layer',
                ],
            },
        ];

        const gw = (SLIDE_W - 2 * M - 0.3) / 3;
        const gy = 2.05, gh = 4.5;
        groups.forEach((g, i) => {
            const x = M + i * (gw + 0.15);
            s.addShape(pres.shapes.RECTANGLE, {
                x, y: gy, w: gw, h: gh,
                fill: { color: C.white }, line: { color: C.rule, width: 1 },
            });
            s.addShape(pres.shapes.RECTANGLE, {
                x, y: gy, w: gw, h: 0.65,
                fill: { color: g.color }, line: { color: g.color, width: 0 },
            });
            s.addText(g.title, {
                x: x + 0.2, y: gy, w: gw - 0.4, h: 0.65,
                fontFace: 'Calibri', fontSize: 13, color: C.white, bold: true,
                valign: 'middle', margin: 0,
            });
            s.addText(
                g.items.map((it, k) => ({ text: it, options: { bullet: { code: '25CF' }, breakLine: k !== g.items.length - 1, color: C.ink } })),
                {
                    x: x + 0.25, y: gy + 0.85, w: gw - 0.5, h: gh - 1.05,
                    fontFace: 'Calibri', fontSize: 11.5, color: C.ink, paraSpaceAfter: 6, margin: 0,
                }
            );
        });

        footer(s, nextPage());
    }

    // ════════════════════════════════════════════════════════════════════════
    // SLIDE 12 — SECURITY / AUDIT / SoD
    // ════════════════════════════════════════════════════════════════════════
    {
        const s = pres.addSlide();
        s.background = { color: C.cream };
        headerBar(s, 'SECURITY & AUDIT');
        pageTitle(s, 'Forensic-grade audit and Segregation of Duties', 'Designed for the threat model of a State treasury');

        const panels = [
            {
                icon: 'usershield', tag: 'IDENTITY',
                title: 'Multi-factor & cookie-based auth',
                bullets: [
                    'TOTP MFA with fails-closed enrollment evaluation',
                    'HttpOnly cookie sessions with configurable lifetime',
                    'Per-tenant role-based access control',
                    'Impersonation banner when superadmin acts as tenant user',
                ],
            },
            {
                icon: 'gavel', tag: 'SEGREGATION OF DUTIES',
                title: 'Conflicts blocked centrally',
                bullets: [
                    'Originator cannot approve the same document',
                    'Centralised SoD evaluator across all modules',
                    'SoDViolation maps to HTTP 403 globally — never silently allowed',
                    'Rules are declarative and audit-loggable',
                ],
            },
            {
                icon: 'database', tag: 'DATA INTEGRITY',
                title: 'No silent failures, no race conditions',
                bullets: [
                    'Unique index on (source_module, source_document_id)',
                    'select_for_update on warrants, IPCs, mobilisation, bulk approvals',
                    'Period gate on every post / reverse / unpost',
                    'Magic-byte file-type validation on document uploads',
                ],
            },
            {
                icon: 'searchdollar', tag: 'AUDIT',
                title: 'Every change is attributable',
                bullets: [
                    'Central audit-trail service writes immutable records',
                    'Override Audit page for manual edits and account overrides',
                    'Data Quality page surfaces failures and uncleared items live',
                    'Structured JSON logging for SIEM ingestion',
                ],
            },
        ];
        const px = M, py = 2.05;
        const pw = (SLIDE_W - 2 * M - 0.2) / 2;
        const ph = (SLIDE_H - py - 0.7 - 0.2) / 2;
        panels.forEach((p, i) => {
            const col = i % 2, row = Math.floor(i / 2);
            const x = px + col * (pw + 0.2);
            const y = py + row * (ph + 0.2);
            s.addShape(pres.shapes.RECTANGLE, {
                x, y, w: pw, h: ph,
                fill: { color: C.white }, line: { color: C.rule, width: 1 },
            });
            // Top stripe
            s.addShape(pres.shapes.RECTANGLE, {
                x, y, w: pw, h: 0.7,
                fill: { color: C.primary }, line: { color: C.primary, width: 0 },
            });
            iconBadge(s, p.icon, x + 0.25, y + 0.1, 0.5, C.primaryAlt, 'accent');
            s.addText(p.tag, {
                x: x + 0.9, y: y + 0.08, w: pw - 1.1, h: 0.26,
                fontFace: 'Calibri', fontSize: 10, color: C.accent, bold: true, charSpacing: 22, margin: 0,
            });
            s.addText(p.title, {
                x: x + 0.9, y: y + 0.32, w: pw - 1.1, h: 0.35,
                fontFace: 'Calibri', fontSize: 13.5, color: C.white, bold: true, margin: 0,
            });
            s.addText(
                p.bullets.map((b, k) => ({ text: b, options: { bullet: { code: '25CF' }, color: C.ink, breakLine: k !== p.bullets.length - 1 } })),
                {
                    x: x + 0.25, y: y + 0.9, w: pw - 0.5, h: ph - 1.05,
                    fontFace: 'Calibri', fontSize: 10.5, color: C.ink, paraSpaceAfter: 6, margin: 0,
                }
            );
        });

        footer(s, nextPage());
    }

    // ════════════════════════════════════════════════════════════════════════
    // SLIDE 13 — MULTI-TENANCY / MDA SCOPING
    // ════════════════════════════════════════════════════════════════════════
    {
        const s = pres.addSlide();
        s.background = { color: C.cream };
        headerBar(s, 'MULTI-TENANCY');
        pageTitle(s, 'One platform, every MDA — with absolute data isolation', 'Schema-per-tenant on PostgreSQL, not application-level filtering');

        s.addText(
            'Each State MDA is provisioned as a tenant with its own isolated PostgreSQL schema. The Office of the Accountant General supervises across MDAs through the superadmin console while each MDA only ever sees its own data.',
            {
                x: M, y: 2.05, w: SLIDE_W - 2 * M, h: 1.0,
                fontFace: 'Calibri', fontSize: 14, color: C.ink, margin: 0,
            }
        );

        // Three rings
        const items = [
            {
                icon: 'sitemap', t: 'Schema isolation',
                body: 'Postgres enforces the boundary, not the app. A bug in module code cannot leak data from one MDA into another.',
            },
            {
                icon: 'cogs', t: 'Per-MDA provisioning',
                body: 'Onboard a new MDA in 30 minutes. Defaults — currencies, NCoA segments, approval templates — seeded from JSON.',
            },
            {
                icon: 'network', t: 'Cross-MDA visibility for OAG',
                body: 'A superadmin console for the Accountant General to monitor, impersonate, audit, and report across every MDA.',
            },
        ];
        const cardY = 3.3, cardH = 3.0;
        const cardW = (SLIDE_W - 2 * M - 0.4) / 3;
        items.forEach((it, i) => {
            const x = M + i * (cardW + 0.2);
            s.addShape(pres.shapes.RECTANGLE, {
                x, y: cardY, w: cardW, h: cardH,
                fill: { color: C.white }, line: { color: C.rule, width: 1 },
            });
            // Top icon area
            s.addShape(pres.shapes.RECTANGLE, {
                x, y: cardY, w: cardW, h: 1.4,
                fill: { color: C.primary }, line: { color: C.primary, width: 0 },
            });
            iconBadge(s, it.icon, x + (cardW - 0.85) / 2, cardY + 0.3, 0.85, C.primaryAlt, 'accent');
            s.addText(it.t, {
                x: x + 0.2, y: cardY + 1.55, w: cardW - 0.4, h: 0.5,
                fontFace: 'Georgia', fontSize: 18, color: C.primary, bold: true, margin: 0,
            });
            s.addText(it.body, {
                x: x + 0.2, y: cardY + 2.05, w: cardW - 0.4, h: cardH - 2.15,
                fontFace: 'Calibri', fontSize: 11.5, color: C.ink, margin: 0,
            });
        });

        footer(s, nextPage());
    }

    // ════════════════════════════════════════════════════════════════════════
    // SLIDE 14 — ARCHITECTURE & STACK
    // ════════════════════════════════════════════════════════════════════════
    {
        const s = pres.addSlide();
        s.background = { color: C.cream };
        headerBar(s, 'TECHNOLOGY');
        pageTitle(s, 'A modern, supportable stack', 'Mainstream tools that Delta State IT can own confidently');

        // Stack table
        const rows = [
            ['Backend',           'Django 5.2 LTS · Django REST Framework 3.17 · PostgreSQL 15 · django-tenants 3.10'],
            ['Frontend',          'React 19 · Vite 7 · TypeScript · Ant Design v6 · TanStack Query · Recharts'],
            ['Auth',              'DRF Token + SimpleJWT · TOTP MFA · HttpOnly cookie sessions · per-tenant RBAC'],
            ['Background',        'Celery + Redis — depreciation runs, statutory report generation, payment cascades'],
            ['API documentation', 'drf-spectacular — live OpenAPI schema at /api/schema/'],
            ['Deployment',        'Gunicorn · Nginx · PgBouncer pooling · Docker · AlmaLinux production playbook'],
            ['Observability',     'Structured JSON logging · DRF exception handler · health endpoints'],
        ];
        const tx = M, ty = 2.05, tw = SLIDE_W - 2 * M, rowH = 0.55;
        rows.forEach((r, i) => {
            const y = ty + i * rowH;
            s.addShape(pres.shapes.RECTANGLE, {
                x: tx, y, w: tw, h: rowH - 0.05,
                fill: { color: i % 2 ? C.creamAlt : C.white }, line: { color: C.rule, width: 0.5 },
            });
            s.addShape(pres.shapes.RECTANGLE, {
                x: tx, y, w: 2.3, h: rowH - 0.05,
                fill: { color: C.primary }, line: { color: C.primary, width: 0 },
            });
            s.addText(r[0], {
                x: tx + 0.2, y, w: 2.1, h: rowH - 0.05,
                fontFace: 'Calibri', fontSize: 12, color: C.white, bold: true,
                valign: 'middle', margin: 0,
            });
            s.addText(r[1], {
                x: tx + 2.5, y, w: tw - 2.6, h: rowH - 0.05,
                fontFace: 'Calibri', fontSize: 11, color: C.ink,
                valign: 'middle', margin: 0,
            });
        });

        // Deployment options strip
        const dy = ty + rows.length * rowH + 0.25;
        s.addText('Deployment options', {
            x: M, y: dy, w: 6, h: 0.35,
            fontFace: 'Calibri', fontSize: 12, color: C.accentDark, bold: true, charSpacing: 18, margin: 0,
        });
        const depls = [
            ['On-premise',    'Within Delta State Government data centre'],
            ['Private cloud', 'State-managed VPC with network isolation'],
            ['Managed SaaS',  'Dplux-hosted with DR included'],
            ['Hybrid',        'Treasury on-prem, reporting in cloud'],
        ];
        const dx0 = M, dyy = dy + 0.4, dW = (SLIDE_W - 2 * M - 0.3) / 4;
        depls.forEach(([t, b], i) => {
            const x = dx0 + i * (dW + 0.1);
            s.addShape(pres.shapes.RECTANGLE, {
                x, y: dyy, w: dW, h: 0.9,
                fill: { color: C.white }, line: { color: C.accent, width: 1 },
            });
            s.addText(t, {
                x: x + 0.15, y: dyy + 0.1, w: dW - 0.3, h: 0.32,
                fontFace: 'Calibri', fontSize: 12, color: C.primary, bold: true, margin: 0,
            });
            s.addText(b, {
                x: x + 0.15, y: dyy + 0.42, w: dW - 0.3, h: 0.45,
                fontFace: 'Calibri', fontSize: 10, color: C.muted, margin: 0,
            });
        });

        footer(s, nextPage());
    }

    // ════════════════════════════════════════════════════════════════════════
    // SLIDE 15 — IMPLEMENTATION APPROACH
    // ════════════════════════════════════════════════════════════════════════
    {
        const s = pres.addSlide();
        s.background = { color: C.cream };
        headerBar(s, 'IMPLEMENTATION');
        pageTitle(s, 'A phased, risk-managed rollout', 'Designed to land working production for the Accountant General first');

        const phases = [
            {
                tag: 'Weeks 1–2', t: 'Discovery & Fit',
                body: 'On-site at the OAG. Walk through Delta State chart of accounts, fiscal calendar, current IFMIS, MDA inventory, TSA hierarchy, and reporting pack.',
            },
            {
                tag: 'Weeks 3–6', t: 'Configuration & Migration Design',
                body: 'NCoA mapping, fund taxonomy, approval templates per MDA, opening balances strategy, integration list with CBN / FIRS / Budget Office.',
            },
            {
                tag: 'Weeks 7–12', t: 'Pilot — Office of the Accountant General + 3 MDAs',
                body: 'Stand up production. Run treasury, AP, AR, GL, and TSA in parallel with the incumbent system. Daily reconciliation and acceptance testing.',
            },
            {
                tag: 'Weeks 13–18', t: 'Phased MDA Roll-out',
                body: 'Onboard remaining MDAs in waves of five. Each wave gets a fortnight of close support before the next wave begins.',
            },
            {
                tag: 'Weeks 19–24', t: 'Statutory Reporting Cut-over',
                body: 'First IPSAS / GFS / OAGF return generated from Quot PSA. Auditor-General walkthrough. Disaster-recovery drill.',
            },
            {
                tag: 'Ongoing',    t: 'Steady-state Support',
                body: 'Quarterly DR drill, fiscal-year roll-over support, end-of-year close, and platform upgrades.',
            },
        ];

        const py = 2.05, pH = 0.72, pW = SLIDE_W - 2 * M;
        phases.forEach((p, i) => {
            const y = py + i * pH;
            // tag column
            s.addShape(pres.shapes.RECTANGLE, {
                x: M, y, w: 2.0, h: pH - 0.08,
                fill: { color: C.accent }, line: { color: C.accent, width: 0 },
            });
            s.addText(p.tag, {
                x: M + 0.15, y, w: 1.85, h: pH - 0.08,
                fontFace: 'Calibri', fontSize: 12, color: C.primary, bold: true,
                valign: 'middle', charSpacing: 14, margin: 0,
            });
            // body
            s.addShape(pres.shapes.RECTANGLE, {
                x: M + 2.0, y, w: pW - 2.0, h: pH - 0.08,
                fill: { color: i % 2 ? C.creamAlt : C.white }, line: { color: C.rule, width: 0.5 },
            });
            s.addText(p.t, {
                x: M + 2.2, y: y + 0.06, w: 3.4, h: 0.5,
                fontFace: 'Calibri', fontSize: 12.5, color: C.primary, bold: true,
                margin: 0, valign: 'middle',
            });
            s.addText(p.body, {
                x: M + 5.7, y: y + 0.06, w: pW - 5.85, h: pH - 0.18,
                fontFace: 'Calibri', fontSize: 10.5, color: C.ink, margin: 0, valign: 'middle',
            });
        });

        footer(s, nextPage());
    }

    // ════════════════════════════════════════════════════════════════════════
    // SLIDE 16 — DELTA STATE PILOT PROPOSAL
    // ════════════════════════════════════════════════════════════════════════
    {
        const s = pres.addSlide();
        s.background = { color: C.cream };
        headerBar(s, 'PROPOSAL');
        pageTitle(s, 'A pilot we propose for Delta State', 'Twelve weeks. Three MDAs. One unambiguous success criterion.');

        // Left — scope
        const lx = M, ly = 2.05, lw = 7.5;
        s.addShape(pres.shapes.RECTANGLE, {
            x: lx, y: ly, w: lw, h: 4.6,
            fill: { color: C.white }, line: { color: C.rule, width: 1 },
        });
        s.addText('Pilot scope', {
            x: lx + 0.3, y: ly + 0.2, w: lw - 0.6, h: 0.36,
            fontFace: 'Calibri', fontSize: 12, color: C.accentDark, bold: true, charSpacing: 18, margin: 0,
        });

        const scope = [
            ['Coverage',          'Office of the Accountant General · Ministry of Finance · two further MDAs of OAG\'s choosing'],
            ['Modules in scope',  'GL & NCoA · TSA · AP & AR · Bank reconciliation · Statutory reporting (IPSAS Cash Basis)'],
            ['Parallel running',  'Quot PSA runs alongside the incumbent system for 8 weeks with daily reconciliation'],
            ['Cut-over criterion','One full month\'s OAGF return generated from Quot PSA with zero reconciling differences'],
            ['Training',          '12 OAG staff trained as system administrators · 30 MDA users trained as operators'],
            ['Hosting',           'Delta State Government data centre, or Dplux-hosted private VPC — your choice'],
            ['Investment',        'Fixed-fee pilot. No additional license cost until the cut-over criterion is independently signed off.'],
        ];
        const scY = ly + 0.7, scH = 0.55;
        scope.forEach(([k, v], i) => {
            const y = scY + i * scH;
            s.addText(k, {
                x: lx + 0.3, y, w: 2.2, h: scH - 0.08,
                fontFace: 'Calibri', fontSize: 11.5, color: C.primary, bold: true,
                valign: 'middle', margin: 0,
            });
            s.addText(v, {
                x: lx + 2.55, y, w: lw - 2.75, h: scH - 0.08,
                fontFace: 'Calibri', fontSize: 11, color: C.ink,
                valign: 'middle', margin: 0,
            });
        });

        // Right — outcomes panel
        const rx = M + lw + 0.3, rw = SLIDE_W - 2 * M - lw - 0.3, ry = 2.05;
        s.addShape(pres.shapes.RECTANGLE, {
            x: rx, y: ry, w: rw, h: 4.6,
            fill: { color: C.primary }, line: { color: C.primary, width: 0 },
        });
        s.addText('What Delta State gets', {
            x: rx + 0.25, y: ry + 0.2, w: rw - 0.5, h: 0.36,
            fontFace: 'Calibri', fontSize: 11, color: C.accent, bold: true, charSpacing: 20, margin: 0,
        });
        const outcomes = [
            'A working production deployment in 12 weeks',
            'OAGF returns generated by the system',
            'A trained internal team capable of running it',
            'A DR drill executed, not just documented',
            'A platform that any further MDA can be onboarded into in 30 minutes',
        ];
        s.addText(
            outcomes.map((o, i) => ({ text: o, options: { bullet: { code: '25A0' }, color: C.white, breakLine: i !== outcomes.length - 1 } })),
            {
                x: rx + 0.25, y: ry + 0.65, w: rw - 0.5, h: 3.7,
                fontFace: 'Calibri', fontSize: 11.5, color: C.white, paraSpaceAfter: 8, margin: 0,
            }
        );

        footer(s, nextPage());
    }

    // ════════════════════════════════════════════════════════════════════════
    // SLIDE 17 — Q&A / THANK YOU / CONTACT
    // ════════════════════════════════════════════════════════════════════════
    {
        const s = pres.addSlide();
        s.background = { color: C.primary };

        // Decorative
        s.addShape(pres.shapes.OVAL, {
            x: -1.5, y: SLIDE_H - 2.5, w: 5, h: 5,
            fill: { color: C.primaryAlt }, line: { color: C.primaryAlt, width: 0 },
        });
        s.addShape(pres.shapes.RECTANGLE, {
            x: 0, y: 0, w: SLIDE_W, h: 0.18,
            fill: { color: C.accent }, line: { color: C.accent, width: 0 },
        });

        s.addText('Thank you', {
            x: M, y: 1.4, w: 12, h: 1.5,
            fontFace: 'Georgia', fontSize: 84, color: C.white, bold: true, margin: 0,
        });
        s.addText('We welcome your questions.', {
            x: M, y: 3.0, w: 10, h: 0.6,
            fontFace: 'Calibri', fontSize: 22, color: C.accent, italic: true, margin: 0,
        });

        // Presenter card
        const cardX = SLIDE_W - 5.0 - M, cardY = 4.1, cardW = 5.0, cardH = 2.8;
        s.addShape(pres.shapes.RECTANGLE, {
            x: cardX, y: cardY, w: cardW, h: cardH,
            fill: { color: C.white }, line: { color: C.white, width: 0 },
        });
        s.addShape(pres.shapes.RECTANGLE, {
            x: cardX, y: cardY, w: 0.1, h: cardH,
            fill: { color: C.accent }, line: { color: C.accent, width: 0 },
        });
        s.addText('PRESENTED BY', {
            x: cardX + 0.3, y: cardY + 0.2, w: cardW - 0.5, h: 0.28,
            fontFace: 'Calibri', fontSize: 10, color: C.accentDark, bold: true, charSpacing: 28, margin: 0,
        });
        s.addText('Jacob Osadiaye', {
            x: cardX + 0.3, y: cardY + 0.5, w: cardW - 0.5, h: 0.5,
            fontFace: 'Georgia', fontSize: 26, color: C.primary, bold: true, margin: 0,
        });
        s.addText('Dplux Technologies', {
            x: cardX + 0.3, y: cardY + 1.0, w: cardW - 0.5, h: 0.32,
            fontFace: 'Calibri', fontSize: 13, color: C.muted, margin: 0,
        });

        const contacts = [
            ['envelope', 'osadiaye4real@gmail.com'],
            ['phone',    'Available on request'],
            ['github',   'github.com/oosadiaye/Quot-PSA'],
        ];
        contacts.forEach(([ic, txt], i) => {
            const y = cardY + 1.45 + i * 0.4;
            iconBadge(s, ic, cardX + 0.3, y, 0.3, C.primary, 'accent');
            s.addText(txt, {
                x: cardX + 0.7, y, w: cardW - 0.85, h: 0.3,
                fontFace: 'Calibri', fontSize: 12, color: C.ink, valign: 'middle', margin: 0,
            });
        });

        // Left text — about
        s.addText('About this briefing', {
            x: M, y: 4.3, w: 6.5, h: 0.32,
            fontFace: 'Calibri', fontSize: 11, color: C.accent, bold: true, charSpacing: 24, margin: 0,
        });
        s.addText(
            'Prepared by Dplux Technologies for the Office of the Accountant General, Delta State Government Secretariat, Asaba.',
            {
                x: M, y: 4.65, w: 6.5, h: 1.5,
                fontFace: 'Calibri', fontSize: 14, color: C.cream, margin: 0,
            }
        );
        s.addText('A live demo and a written proposal are available on request.', {
            x: M, y: 6.3, w: 6.5, h: 0.5,
            fontFace: 'Calibri', fontSize: 12, color: C.accent, italic: true, margin: 0,
        });
    }

    // ── Write ────────────────────────────────────────────────────────────────
    const outName = 'Quot_PSA_Briefing_Delta_State_OAG.pptx';
    await pres.writeFile({ fileName: outName });
    const stats = fs.statSync(outName);
    console.log(`Wrote ${outName} (${stats.size.toLocaleString()} bytes, ${pageNum + 2} slides total)`);
}

main().catch(err => { console.error(err); process.exit(1); });

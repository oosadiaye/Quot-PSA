/**
 * Report Export Utilities — CSV (Excel-compatible) and PDF (via print)
 *
 * CSV uses UTF-8 BOM so Excel opens it with correct encoding.
 * PDF leverages the browser's print dialog with a clean print stylesheet.
 */

export interface ExportColumn {
    header: string;
    key: string;
    align?: 'left' | 'right';
}

export interface ExportSection {
    title: string;
    columns: ExportColumn[];
    rows: Record<string, string | number>[];
    totals?: Record<string, string | number>;
}

export interface ExportOptions {
    title: string;
    subtitle?: string;
    dateRange?: string;
    sections: ExportSection[];
    summary?: { label: string; value: string }[];
}

// ---------------------------------------------------------------------------
// CSV / Excel Export
// ---------------------------------------------------------------------------

function escapeCSV(value: string | number): string {
    const str = String(value ?? '');
    if (str.includes(',') || str.includes('"') || str.includes('\n')) {
        return `"${str.replace(/"/g, '""')}"`;
    }
    return str;
}

export function exportToCSV(options: ExportOptions, filename: string) {
    const lines: string[] = [];

    // Title row
    lines.push(escapeCSV(options.title));
    if (options.subtitle) lines.push(escapeCSV(options.subtitle));
    if (options.dateRange) lines.push(escapeCSV(options.dateRange));
    lines.push(''); // blank row

    for (const section of options.sections) {
        // Section title
        lines.push(escapeCSV(section.title));

        // Column headers
        lines.push(section.columns.map(c => escapeCSV(c.header)).join(','));

        // Data rows
        for (const row of section.rows) {
            lines.push(section.columns.map(c => escapeCSV(row[c.key] ?? '')).join(','));
        }

        // Totals row
        if (section.totals) {
            lines.push(section.columns.map(c => escapeCSV(section.totals![c.key] ?? '')).join(','));
        }

        lines.push(''); // blank row between sections
    }

    // Summary
    if (options.summary) {
        lines.push('Summary');
        for (const item of options.summary) {
            lines.push(`${escapeCSV(item.label)},${escapeCSV(item.value)}`);
        }
    }

    // UTF-8 BOM for Excel compatibility
    const BOM = '\uFEFF';
    const csv = BOM + lines.join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename.endsWith('.csv') ? filename : `${filename}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// PDF Export (via browser print)
// ---------------------------------------------------------------------------

function buildPrintableHTML(options: ExportOptions): string {
    const sectionColors: Record<string, string> = {
        'Revenue': '#059669',
        'Expenses': '#dc2626',
        'Assets': '#0284c7',
        'Liabilities': '#dc2626',
        'Equity': '#7c3aed',
        'Operating Activities': '#0284c7',
        'Investing Activities': '#7c3aed',
        'Financing Activities': '#d97706',
    };

    const parts: string[] = [];

    for (const section of options.sections) {
        const color = sectionColors[section.title] ?? '#1e293b';

        const headerCells = section.columns
            .map(c => `<th style="padding:8px 12px;text-align:${c.align ?? 'left'};font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:#64748b;border-bottom:2px solid #e2e8f0;">${c.header}</th>`)
            .join('');

        const dataCells = section.rows
            .map(row => {
                const cells = section.columns.map(c =>
                    `<td style="padding:8px 12px;text-align:${c.align ?? 'left'};font-size:12px;color:#334155;border-bottom:1px solid #f1f5f9;">${row[c.key] ?? ''}</td>`
                ).join('');
                return `<tr>${cells}</tr>`;
            }).join('');

        let totalsCells = '';
        if (section.totals) {
            const cells = section.columns.map(c =>
                `<td style="padding:10px 12px;text-align:${c.align ?? 'left'};font-size:12px;font-weight:700;color:#1e293b;border-top:2px solid #e2e8f0;">${section.totals![c.key] ?? ''}</td>`
            ).join('');
            totalsCells = `<tfoot><tr>${cells}</tr></tfoot>`;
        }

        parts.push(`
            <div style="margin-bottom:24px;">
                <div style="font-size:14px;font-weight:700;color:${color};padding:8px 0;border-bottom:2px solid ${color};margin-bottom:4px;">
                    ${section.title}
                </div>
                <table style="width:100%;border-collapse:collapse;font-family:system-ui,-apple-system,sans-serif;">
                    <thead><tr>${headerCells}</tr></thead>
                    <tbody>${dataCells}</tbody>
                    ${totalsCells}
                </table>
            </div>
        `);
    }

    let summaryBlock = '';
    if (options.summary && options.summary.length > 0) {
        const cards = options.summary.map(item => `
            <div style="flex:1;padding:12px 16px;border:1px solid #e2e8f0;border-radius:8px;text-align:center;">
                <div style="font-size:10px;font-weight:600;color:#64748b;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px;">${item.label}</div>
                <div style="font-size:16px;font-weight:700;color:#1e293b;">${item.value}</div>
            </div>
        `).join('');
        summaryBlock = `<div style="display:flex;gap:12px;margin-top:20px;">${cards}</div>`;
    }

    const timestamp = `${new Date().toLocaleDateString()} at ${new Date().toLocaleTimeString()}`;

    return [
        '<!DOCTYPE html><html><head>',
        `<title>${options.title}</title>`,
        '<style>',
        '@media print { body { margin:0; padding:20px; } @page { margin:15mm; size:A4; } }',
        'body { font-family:system-ui,-apple-system,sans-serif; color:#1e293b; max-width:800px; margin:0 auto; padding:24px; }',
        '</style></head><body>',
        '<div style="text-align:center;margin-bottom:24px;padding-bottom:16px;border-bottom:2px solid #e2e8f0;">',
        `<h1 style="font-size:22px;font-weight:800;margin:0 0 4px 0;color:#1e293b;">${options.title}</h1>`,
        options.subtitle ? `<div style="font-size:13px;color:#64748b;">${options.subtitle}</div>` : '',
        options.dateRange ? `<div style="font-size:12px;color:#94a3b8;margin-top:4px;">${options.dateRange}</div>` : '',
        '</div>',
        ...parts,
        summaryBlock,
        `<div style="margin-top:32px;padding-top:12px;border-top:1px solid #e2e8f0;text-align:center;font-size:10px;color:#94a3b8;">Generated on ${timestamp} — QUOT ERP</div>`,
        '</body></html>',
    ].join('\n');
}

export function exportToPDF(options: ExportOptions) {
    const printWindow = window.open('', '_blank', 'width=900,height=700');
    if (!printWindow) {
        alert('Please allow popups to export PDF.');
        return;
    }

    const html = buildPrintableHTML(options);
    printWindow.document.open();
    printWindow.document.writeln(html);
    printWindow.document.close();

    // Wait for content to render then trigger print
    setTimeout(() => {
        printWindow.print();
    }, 400);
}

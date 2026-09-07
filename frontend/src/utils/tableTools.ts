/* ═══════════════════════════════════════════════════════════════════
   tableTools — sort, total and filter on every list view.

   WHY THIS IS A DOM ENHANCER, NOT A COMPONENT
   -------------------------------------------
   117 pages hand-roll their own <table>; only 4 route through a shared
   component. Adding sort/total/filter by editing each page is a
   multi-week change across screens that post to the general ledger.
   This attaches to any table already on the page, so every list gets
   the behaviour at once and pages stay untouched.

   WHY IT IS SAFE TO REORDER REACT'S ROWS
   --------------------------------------
   Sorting moves <tr> nodes inside the tbody React rendered. React keeps
   a direct DOM reference per fiber, so a later update writes to the same
   node even after we have moved it — a row's figures cannot land on a
   different row's line, which is the only failure mode that would
   actually matter in a ledger. What CAN happen is React restoring its
   own order on re-render; the observer re-applies the active sort when
   that occurs.

   INJECTION POINTS
   ----------------
   The toolbar is a <caption> and the totals are a <tfoot>. Both are
   legal children of <table>, so no wrapper element is inserted into a
   parent React controls. If React ever strips them, the observer puts
   them back.

   OPT OUT
   -------
   `data-plain-table` (already used by the bank letter and warrant
   printout) or `data-no-tools` — no toolbar, no totals, no sorting.

   `data-no-sort` keeps the filter and totals but leaves ordering to the
   page. Needed where a page already sorts on header click: React binds
   through delegation, so there is no onclick attribute in the DOM for
   us to detect, and both handlers would fire. JournalList is the case
   that matters — its sort sets an `ordering` parameter on the API call,
   so a client-side reorder would shuffle one page against the server's
   own ordering and look like corrupted paging.
   ═══════════════════════════════════════════════════════════════════ */

type ColKind = 'number' | 'date' | 'text';

const SORT_KEY = '__tableToolsSort';
const NBSP = / /g;

interface SortState { index: number; dir: 'asc' | 'desc'; }
interface Tagged extends HTMLTableElement { [SORT_KEY]?: SortState | null; }

/* ── value parsing ─────────────────────────────────────────────────── */

const clean = (s: string) => s.replace(NBSP, ' ').trim();

/** A ledger writes nil as a dash, not as 0.00. Those cells carry no
 *  value and must not count toward a column's type: a Balance column
 *  showing 100.00 / — / 50.00 is still a money column, and counting the
 *  dash as an unparseable value drops it below the threshold and loses
 *  the total. */
const BLANKISH = new Set(['', '—', '-', '–', 'N/A', 'n/a', 'nil', '--']);
const isBlankish = (s: string) => BLANKISH.has(clean(s));

/** Parse a displayed figure. Handles ₦ and other symbols, thousands
 *  separators, and the accounting convention of parentheses for
 *  negatives — (1,234.56) is -1234.56, not 1234.56.
 *
 *  Deliberately strict about what counts as a figure. An earlier version
 *  stripped every non-digit, which turned the document number JV-000118
 *  into -118 and totalled the Document No column to -2,348.00 — a
 *  reference column presented as money. Anything still carrying a letter
 *  or a path separator after the currency symbol and Dr/Cr suffix come
 *  off is an identifier, not an amount. */
function parseNumber(raw: string): number | null {
  let s = clean(raw);
  if (!s || s === '—' || s === '-' || s === '–' || s === 'N/A') return null;

  let negative = false;
  if (/^\(.*\)$/.test(s)) { negative = true; s = s.slice(1, -1); }

  // Currency symbols, spaces and the trial balance's Dr/Cr suffix are
  // presentation; everything else must already look like a number.
  s = s.replace(/(?:Dr|Cr)\.?$/i, '')
       .replace(/[₦$£€¥]/g, '')
       .replace(/\s/g, '')
       .trim();

  // An identifier (JV-000118, PB/2026/0001, DEMO-REG-REV-2026-12-03)
  // must not reach Number().
  if (!/^[+-]?[\d,]*\.?\d+$/.test(s)) return null;

  if (s.startsWith('-')) { negative = true; s = s.slice(1); }
  else if (s.startsWith('+')) { s = s.slice(1); }
  s = s.replace(/,/g, '');
  const n = Number(s);
  if (!isFinite(n)) return null;
  return negative ? -n : n;
}

/** Does this cell read as a *formatted* figure rather than a bare
 *  integer? Every monetary value in this application renders with two
 *  decimals, so a decimal point or a thousands separator is what
 *  separates ₦11,100.00 from the NCoA code 11100100 — both of which are
 *  valid numbers, only one of which should ever be summed. */
function looksLikeMoney(raw: string): boolean {
  return /[.,]/.test(clean(raw)) && parseNumber(raw) !== null;
}

/** DD/MM/YYYY first — the house format — then ISO. */
function parseDate(raw: string): number | null {
  const s = clean(raw);
  let m = /^(\d{2})[/-](\d{2})[/-](\d{4})$/.exec(s);
  if (m) return Date.UTC(+m[3], +m[2] - 1, +m[1]);
  m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  if (m) return Date.UTC(+m[1], +m[2] - 1, +m[3]);
  return null;
}

/** 1 when the row-number gutter is present, 0 otherwise.
 *
 *  Every column index is stored relative to the page's own columns and
 *  offset by this at the moment it is used. Storing raw cellIndex would
 *  silently sort the wrong column the first time someone turned the
 *  gutter off with a sort already active. */
function gutterOffset(table: HTMLTableElement): number {
  const head = table.tHead;
  if (!head || head.rows.length === 0) return 0;
  const fieldRow = Array.from(head.rows).find((r) => !r.hasAttribute('data-tools-letters'));
  return fieldRow?.cells[0]?.classList.contains('tt-corner') ? 1 : 0;
}

function cellText(row: HTMLTableRowElement, index: number): string {
  const cell = row.cells[index];
  return cell ? clean(cell.textContent || '') : '';
}

/** Decide a column's type from its populated cells. Requires a clear
 *  majority so a stray "—" or a code that happens to be digits does not
 *  flip an entire column. */
function columnKind(rows: HTMLTableRowElement[], index: number): ColKind {
  let filled = 0, numeric = 0, dated = 0, money = 0;
  for (const row of rows.slice(0, 40)) {
    const text = cellText(row, index);
    if (isBlankish(text)) continue;
    filled++;
    if (parseDate(text) !== null) dated++;
    else if (parseNumber(text) !== null) {
      numeric++;
      if (looksLikeMoney(text)) money++;
    }
  }
  if (filled < 2) return 'text';
  if (dated / filled > 0.7) return 'date';
  // Sorting wants any numeric column ordered by value; totalling wants
  // only real figures. `money` is what renderTotals consults, so a
  // column of bare integers still sorts numerically without being added
  // up as if it were currency.
  if (numeric / filled > 0.7) return money / filled > 0.7 ? 'number' : 'text';
  return 'text';
}

/** Sort key type — looser than the totals test above. A column of plain
 *  integers (a line count, a quantity) should still order by value. */
function sortKind(rows: HTMLTableRowElement[], index: number): ColKind {
  let filled = 0, numeric = 0, dated = 0;
  for (const row of rows.slice(0, 40)) {
    const text = cellText(row, index);
    if (isBlankish(text)) continue;
    filled++;
    if (parseDate(text) !== null) dated++;
    else if (parseNumber(text) !== null) numeric++;
  }
  if (filled < 2) return 'text';
  if (dated / filled > 0.7) return 'date';
  if (numeric / filled > 0.7) return 'number';
  return 'text';
}

/* ── eligibility ───────────────────────────────────────────────────── */

function eligible(table: HTMLTableElement): boolean {
  if (table.closest('[data-plain-table],[data-no-tools]')) return false;
  const head = table.tHead;
  const body = table.tBodies[0];
  if (!head || !body) return false;
  if (head.rows.length === 0 || body.rows.length < 2) return false;
  // A layout table has no real header cells.
  return head.rows[head.rows.length - 1].querySelectorAll('th').length >= 2;
}

function bodyRows(table: HTMLTableElement): HTMLTableRowElement[] {
  const body = table.tBodies[0];
  if (!body) return [];
  return Array.from(body.rows).filter(
    (r) => !r.hasAttribute('data-tools-row') && r.cells.length > 1,
  );
}

/* ── sorting ───────────────────────────────────────────────────────── */

function applySort(table: Tagged) {
  const state = table[SORT_KEY];
  const body = table.tBodies[0];
  if (!state || !body) return;

  const rows = bodyRows(table);
  if (rows.length < 2) return;

  const col = state.index + gutterOffset(table);
  const kind = sortKind(rows, col);
  const sign = state.dir === 'asc' ? 1 : -1;

  // Decorate–sort–undecorate keeps the comparator cheap and the sort
  // stable on equal keys (ties hold their original ledger order).
  const decorated = rows.map((row, i) => {
    const text = cellText(row, col);
    let key: number | string | null;
    if (kind === 'number') key = parseNumber(text);
    else if (kind === 'date') key = parseDate(text);
    else key = text.toLowerCase();
    return { row, key, i };
  });

  decorated.sort((a, b) => {
    const ak = a.key, bk = b.key;
    // Blanks sort last in both directions — an empty cell is not a
    // small value, and burying them keeps the populated rows together.
    const aEmpty = ak === null || ak === '';
    const bEmpty = bk === null || bk === '';
    if (aEmpty && bEmpty) return a.i - b.i;
    if (aEmpty) return 1;
    if (bEmpty) return -1;
    if (ak! < bk!) return -1 * sign;
    if (ak! > bk!) return 1 * sign;
    return a.i - b.i;
  });

  const frag = document.createDocumentFragment();
  decorated.forEach((d) => frag.appendChild(d.row));
  body.appendChild(frag);
}

function markHeaders(table: Tagged) {
  const head = table.tHead;
  if (!head) return;
  const headerRow = head.rows[head.rows.length - 1];
  const state = table[SORT_KEY];
  const offset = gutterOffset(table);

  Array.from(headerRow.cells).forEach((th, cellIdx) => {
    // The gutter corner is not a column anyone sorts by.
    if (th.classList.contains('tt-corner')) return;
    const index = cellIdx - offset;
    th.classList.add('tt-sortable');
    th.setAttribute('role', 'button');
    th.setAttribute('tabindex', '0');
    const active = state && state.index === index;
    th.setAttribute('aria-sort', active ? (state!.dir === 'asc' ? 'ascending' : 'descending') : 'none');
    th.classList.toggle('tt-sorted', !!active);
    th.classList.toggle('tt-desc', !!active && state!.dir === 'desc');
  });
}

function toggleSort(table: Tagged, index: number) {
  const cur = table[SORT_KEY];
  if (!cur || cur.index !== index) table[SORT_KEY] = { index, dir: 'asc' };
  else if (cur.dir === 'asc') table[SORT_KEY] = { index, dir: 'desc' };
  else table[SORT_KEY] = null; // third click restores the source order
  if (table[SORT_KEY]) applySort(table);
  markHeaders(table);
  refresh(table);
}

/* ── filtering ─────────────────────────────────────────────────────── */

function applyFilter(table: HTMLTableElement, term: string) {
  const q = term.trim().toLowerCase();
  bodyRows(table).forEach((row) => {
    const hit = !q || (row.textContent || '').toLowerCase().includes(q);
    row.toggleAttribute('data-tt-hidden', !hit);
    (row as HTMLElement).style.display = hit ? '' : 'none';
  });
}

function visibleRows(table: HTMLTableElement): HTMLTableRowElement[] {
  return bodyRows(table).filter((r) => !r.hasAttribute('data-tt-hidden'));
}

/* ── totals ────────────────────────────────────────────────────────── */

const fmt = new Intl.NumberFormat('en-NG', {
  minimumFractionDigits: 2, maximumFractionDigits: 2,
});

/** Append a totals row, but only where the page does not already
 *  provide one — a page-authored tfoot knows more than we do about
 *  which columns should be summed. */
function renderTotals(table: HTMLTableElement) {
  const existing = table.querySelector('tfoot[data-tools-foot]') as HTMLTableSectionElement | null;
  const pageFoot = Array.from(table.tFoot ? [table.tFoot] : []).find(
    (f) => !f.hasAttribute('data-tools-foot'),
  );
  if (pageFoot) { existing?.remove(); return; }

  const rows = visibleRows(table);
  const headerRow = table.tHead!.rows[table.tHead!.rows.length - 1];
  const colCount = headerRow.cells.length;
  if (rows.length === 0) { existing?.remove(); return; }

  const sums: (number | null)[] = [];
  let any = false;
  for (let c = 0; c < colCount; c++) {
    if (columnKind(rows, c) !== 'number') { sums.push(null); continue; }
    let total = 0, seen = 0;
    for (const row of rows) {
      const v = parseNumber(cellText(row, c));
      if (v !== null) { total += v; seen++; }
    }
    if (seen === 0) { sums.push(null); continue; }
    sums.push(total);
    any = true;
  }
  if (!any) { existing?.remove(); return; }

  const foot = existing || document.createElement('tfoot');
  foot.setAttribute('data-tools-foot', '');
  foot.replaceChildren();

  const tr = foot.insertRow();
  tr.setAttribute('data-tools-row', '');
  let labelled = false;
  for (let c = 0; c < colCount; c++) {
    const td = tr.insertCell();
    if (sums[c] !== null) {
      td.textContent = fmt.format(sums[c] as number);
      td.className = 'tt-total-num';
      if ((sums[c] as number) < 0) td.setAttribute('data-negative', '');
    } else if (!labelled) {
      td.textContent = `Σ ${rows.length} row${rows.length === 1 ? '' : 's'}`;
      td.className = 'tt-total-label';
      labelled = true;
    }
  }
  if (!existing) table.appendChild(foot);
}

/* ── row-number gutter ─────────────────────────────────────────────── */

/** The numbered column down the left, as the approved mockup showed.
 *
 *  Inserting a cell into rows React rendered is more invasive than the
 *  caption and tfoot, so this is written to be idempotent: every pass
 *  removes what it previously added and rebuilds, which means a React
 *  re-render can never leave two gutters or a gutter on some rows only.
 *
 *  Numbers follow what is on screen, not the underlying record — after a
 *  sort or a filter row 3 is the third row you can see. That matches a
 *  spreadsheet, and it is the only reading that stays true when the list
 *  is server-paginated.
 *
 *  Off via `data-grid-rownums="off"` on <body>. */
function syncGutter(table: HTMLTableElement) {
  const wanted = document.body.getAttribute('data-grid-rownums') !== 'off';

  table.querySelectorAll('.tt-gutter, .tt-corner').forEach((n) => n.remove());
  if (!wanted) return;

  const head = table.tHead;
  if (!head) return;
  const headerCols = head.rows[head.rows.length - 1].cells.length;

  for (const row of Array.from(head.rows)) {
    const th = document.createElement('th');
    th.className = 'tt-corner';
    th.setAttribute('aria-hidden', 'true');
    row.insertBefore(th, row.firstChild);
  }

  let n = 0;
  for (const row of Array.from(table.tBodies[0]?.rows || [])) {
    const td = document.createElement('td');
    td.className = 'tt-gutter';
    // A full-width message row ("No records found") keeps its colspan;
    // the gutter simply sits beside it, so the widths still add up.
    const isMessage = row.cells.length === 1 &&
      (row.cells[0].colSpan >= headerCols || row.cells[0].colSpan > 1);
    if (!row.hasAttribute('data-tt-hidden') && !isMessage) {
      n += 1;
      td.textContent = String(n);
    }
    row.insertBefore(td, row.firstChild);
  }

  for (const foot of Array.from(table.tFoot ? [table.tFoot] : [])) {
    for (const row of Array.from(foot.rows)) {
      const td = document.createElement('td');
      td.className = 'tt-gutter';
      row.insertBefore(td, row.firstChild);
    }
  }
}

/** Column letters (A, B, C…) above the field names.
 *
 *  Opt-in rather than default. They are authentic to a spreadsheet and
 *  useful when an auditor cites "column F", but they cost a row of
 *  vertical space on every list and the letters match nothing the user
 *  can export — so the default is off and a tenant that wants them sets
 *  `data-grid-letters="on"` on <body>. */
function syncColumnLetters(table: HTMLTableElement) {
  const wanted = document.body.getAttribute('data-grid-letters') === 'on';
  const existing = table.querySelector('tr[data-tools-letters]');
  if (!wanted) { existing?.remove(); return; }

  const head = table.tHead;
  if (!head || head.rows.length === 0) return;
  const fieldRow = Array.from(head.rows).find((r) => !r.hasAttribute('data-tools-letters'));
  if (!fieldRow) return;

  const count = fieldRow.cells.length;
  const row = existing || head.insertRow(0);
  row.setAttribute('data-tools-letters', '');
  row.replaceChildren();

  for (let i = 0; i < count; i++) {
    const th = document.createElement('th');
    th.className = 'tt-letter';
    // The first slot is the gutter corner when row numbers are on.
    const isCorner = fieldRow.cells[i]?.classList.contains('tt-corner');
    th.textContent = isCorner ? '' : columnLetter(i - (fieldRow.cells[0]?.classList.contains('tt-corner') ? 1 : 0));
    row.appendChild(th);
  }
  if (head.rows[0] !== row) head.insertBefore(row, head.rows[0]);
}

function columnLetter(index: number): string {
  if (index < 0) return '';
  let n = index, out = '';
  do { out = String.fromCharCode(65 + (n % 26)) + out; n = Math.floor(n / 26) - 1; } while (n >= 0);
  return out;
}

/* ── toolbar ───────────────────────────────────────────────────────── */

function ensureToolbar(table: HTMLTableElement) {
  let cap = table.querySelector('caption[data-tools-bar]') as HTMLTableCaptionElement | null;
  if (!cap) {
    cap = document.createElement('caption');
    cap.setAttribute('data-tools-bar', '');

    // Built node by node rather than from an HTML string. The string
    // would be a static literal with nothing interpolated, so it is not
    // actually an injection vector — but this is a ledger, and a
    // reviewer should not have to prove that to themselves.
    const bar = document.createElement('div');
    bar.className = 'tt-bar';

    const input = document.createElement('input');
    input.className = 'tt-filter';
    input.type = 'search';
    input.placeholder = 'Filter these rows…';
    input.setAttribute('aria-label', 'Filter rows');

    const count = document.createElement('span');
    count.className = 'tt-count';

    const clearBtn = document.createElement('button');
    clearBtn.type = 'button';
    clearBtn.className = 'tt-clear';
    clearBtn.hidden = true;
    clearBtn.textContent = 'Clear sort';

    bar.append(input, count, clearBtn);
    cap.appendChild(bar);
    table.insertBefore(cap, table.firstChild);
    input.addEventListener('input', () => {
      applyFilter(table, input.value);
      renderTotals(table);
      updateCount(table);
    });
    // Stop a click in the toolbar from reaching a row handler beneath.
    cap.addEventListener('click', (e) => {
      const target = e.target as HTMLElement;
      if (target.classList.contains('tt-clear')) {
        (table as Tagged)[SORT_KEY] = null;
        markHeaders(table as Tagged);
        refresh(table);
      }
      e.stopPropagation();
    });
  }
  return cap;
}

function updateCount(table: HTMLTableElement) {
  const cap = table.querySelector('caption[data-tools-bar]');
  if (!cap) return;
  const count = cap.querySelector('.tt-count') as HTMLElement;
  const clear = cap.querySelector('.tt-clear') as HTMLButtonElement;
  const total = bodyRows(table).length;
  const shown = visibleRows(table).length;
  count.textContent = shown === total ? `${total} rows` : `${shown} of ${total} rows`;
  clear.hidden = !(table as Tagged)[SORT_KEY];
}

/* ── wiring ────────────────────────────────────────────────────────── */

function refresh(table: HTMLTableElement) {
  // Totals are computed on the page's own columns, before the gutter
  // and letters go back on — so a derived footer never has to reason
  // about decorations we added ourselves.
  table.querySelectorAll('.tt-gutter, .tt-corner').forEach((n) => n.remove());
  table.querySelector('tr[data-tools-letters]')?.remove();
  renderTotals(table);
  syncGutter(table);
  syncColumnLetters(table);
  updateCount(table);
}

function attach(table: HTMLTableElement) {
  if (table.hasAttribute('data-tools-ready')) return;
  if (!eligible(table)) return;
  table.setAttribute('data-tools-ready', '');

  const head = table.tHead!;
  const pageOwnsSort = !!table.closest('[data-no-sort]');

  if (!pageOwnsSort) {
  head.addEventListener('click', (e) => {
    const th = (e.target as HTMLElement).closest('th');
    if (!th || !head.contains(th)) return;
    // Ignore the select-all checkbox cell.
    if (th.querySelector('input,button')) return;
    if (th.classList.contains('tt-corner') || th.classList.contains('tt-letter')) return;
    toggleSort(table as Tagged,
      (th as HTMLTableCellElement).cellIndex - gutterOffset(table));
  });
  head.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    const th = (e.target as HTMLElement).closest('th');
    if (!th || !head.contains(th)) return;
    if (th.querySelector('input,button')) return;
    if (th.classList.contains('tt-corner') || th.classList.contains('tt-letter')) return;
    e.preventDefault();
    toggleSort(table as Tagged,
      (th as HTMLTableCellElement).cellIndex - gutterOffset(table));
  });
  }

  ensureToolbar(table);
  if (!pageOwnsSort) markHeaders(table as Tagged);
  refresh(table);
}

function scan(root: ParentNode = document) {
  root.querySelectorAll?.('table').forEach((t) => {
    try { attach(t as HTMLTableElement); } catch { /* never break a page */ }
  });
}

let pending = 0;
function schedule() {
  if (pending) return;
  pending = window.setTimeout(() => {
    pending = 0;
    scan();
    // React may have re-rendered rows out from under an active sort, or
    // replaced the body wholesale after a fetch. Re-apply and re-total.
    document.querySelectorAll('table[data-tools-ready]').forEach((t) => {
      const table = t as Tagged;
      try {
        if (table[SORT_KEY]) applySort(table);
        ensureToolbar(table);
        if (!table.closest('[data-no-sort]')) markHeaders(table);
        // A filter survives a re-render only if it is re-applied: React
        // hands back fresh rows with no display style of ours on them.
        const input = table.querySelector('caption[data-tools-bar] .tt-filter') as HTMLInputElement | null;
        if (input && input.value) applyFilter(table, input.value);
        refresh(table);
      } catch { /* never break a page */ }
    });
  }, 120);
}

export function initTableTools() {
  if (typeof window === 'undefined') return;
  scan();
  new MutationObserver(schedule).observe(document.body, { childList: true, subtree: true });
}

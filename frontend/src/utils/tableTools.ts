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
   printout) or `data-no-tools` on the table or any ancestor.
   ═══════════════════════════════════════════════════════════════════ */

type ColKind = 'number' | 'date' | 'text';

const SORT_KEY = '__tableToolsSort';
const NBSP = / /g;

interface SortState { index: number; dir: 'asc' | 'desc'; }
interface Tagged extends HTMLTableElement { [SORT_KEY]?: SortState | null; }

/* ── value parsing ─────────────────────────────────────────────────── */

const clean = (s: string) => s.replace(NBSP, ' ').trim();

/** Parse a displayed figure. Handles ₦ and other symbols, thousands
 *  separators, and the accounting convention of parentheses for
 *  negatives — (1,234.56) is -1234.56, not 1234.56. */
function parseNumber(raw: string): number | null {
  let s = clean(raw);
  if (!s || s === '—' || s === '-' || s === '–' || s === 'N/A') return null;

  let negative = false;
  if (/^\(.*\)$/.test(s)) { negative = true; s = s.slice(1, -1); }
  // Strip currency symbols, spaces and the Dr/Cr suffix used on the
  // trial balance. Keep digits, separators and a leading sign.
  s = s.replace(/(?:Dr|Cr)\.?$/i, '').replace(/[^\d.,+-]/g, '');
  if (!s || !/\d/.test(s)) return null;
  if (s.startsWith('-')) { negative = true; s = s.slice(1); }
  else if (s.startsWith('+')) { s = s.slice(1); }
  s = s.replace(/,/g, '');
  const n = Number(s);
  if (!isFinite(n)) return null;
  return negative ? -n : n;
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

function cellText(row: HTMLTableRowElement, index: number): string {
  const cell = row.cells[index];
  return cell ? clean(cell.textContent || '') : '';
}

/** Decide a column's type from its populated cells. Requires a clear
 *  majority so a stray "—" or a code that happens to be digits does not
 *  flip an entire column. */
function columnKind(rows: HTMLTableRowElement[], index: number): ColKind {
  let filled = 0, numeric = 0, dated = 0;
  for (const row of rows.slice(0, 40)) {
    const text = cellText(row, index);
    if (!text) continue;
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

  const kind = columnKind(rows, state.index);
  const sign = state.dir === 'asc' ? 1 : -1;

  // Decorate–sort–undecorate keeps the comparator cheap and the sort
  // stable on equal keys (ties hold their original ledger order).
  const decorated = rows.map((row, i) => {
    const text = cellText(row, state.index);
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

  Array.from(headerRow.cells).forEach((th, index) => {
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
  renderTotals(table);
  updateCount(table);
}

function attach(table: HTMLTableElement) {
  if (table.hasAttribute('data-tools-ready')) return;
  if (!eligible(table)) return;
  table.setAttribute('data-tools-ready', '');

  const head = table.tHead!;
  head.addEventListener('click', (e) => {
    const th = (e.target as HTMLElement).closest('th');
    if (!th || !head.contains(th)) return;
    // Ignore the select-all checkbox cell.
    if (th.querySelector('input,button')) return;
    toggleSort(table as Tagged, (th as HTMLTableCellElement).cellIndex);
  });
  head.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    const th = (e.target as HTMLElement).closest('th');
    if (!th || !head.contains(th)) return;
    if (th.querySelector('input,button')) return;
    e.preventDefault();
    toggleSort(table as Tagged, (th as HTMLTableCellElement).cellIndex);
  });

  ensureToolbar(table);
  markHeaders(table as Tagged);
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
        markHeaders(table);
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

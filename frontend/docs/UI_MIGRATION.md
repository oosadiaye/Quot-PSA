# Frontend UI Migration Guide

This project is migrating all pages onto a small set of shared primitives that
enforce consistent visual language, responsive behaviour, and accessibility
across mobile / tablet / desktop.

Status: **partial** — primitives landed and the three auth pages (Login,
ForgotPassword, ResetPassword) + PageHeader are converted. The AccountProfile
page and ~32 list pages still use ad-hoc inline styles and must be migrated.

---

## 1. The primitives

All live under `frontend/src/components/`.

### 1.1 `auth/AuthShell`
Location: `components/auth/AuthShell.tsx`

The responsive 2-pane layout used by every unauthenticated page
(Login, ForgotPassword, ResetPassword, Register, Setup, etc.).

Desktop (>= 1024px):
- 50/50 split
- Left: gradient brand panel with logo, tagline, optional `brandContent`
- Right: white form panel with title / subtitle / children / footer

Tablet (768–1023px): 55/45 compact

Mobile (<768px): single column, compact gradient logo lockup above the form.

```tsx
import AuthShell from '../components/auth/AuthShell';

<AuthShell
  title="Welcome back"
  subtitle="Sign in to your account to continue"
  brandTagline={'Public Sector Accounting\nBuilt on IPSAS & IFMIS'}
  brandContent={<FeatureList />}
  footer={<>Don't have an account? <a href="/register">Create Account</a></>}
>
  {/* form fields */}
</AuthShell>
```

Props:
| prop | type | notes |
|---|---|---|
| `title` | string | large heading on form side |
| `subtitle` | string? | muted line below title |
| `brandTagline` | string? | two-line tagline under logo (use `\n`) |
| `brandContent` | ReactNode? | e.g. feature list or callout card |
| `footer` | ReactNode? | small text under form (links etc.) |
| `showTrustBadge` | boolean? (default true) | SSL / SOC2 line |
| `children` | ReactNode | form content |

### 1.2 `forms/FormField`
Location: `components/forms/FormField.tsx`

Drop-in replacement for every `<label> + <input>` pair in the codebase.

```tsx
import { FormField } from '../components/forms';

<FormField
  label="Email Address"
  name="email"
  type="email"
  value={email}
  onChange={setEmail}
  placeholder="Enter your email"
  autoComplete="email"
  required
  error={errors.email}
  rightAdornment={<EyeToggle />}
/>
```

Highlights:
- 13px uppercase label, 0.5px tracking, weight 600
- 14px input (16px on mobile — prevents iOS zoom)
- Primary-blue focus ring + subtle background swap
- `tone` prop for inline success ("Passwords match") / error states
- `rightAdornment` slot for show/hide password, unit suffixes, etc.
- Border-colour hierarchy: `error` > `tone==='success'` > `tone==='error'` > focused > default

### 1.3 `forms/ResponsiveFormGrid`
Location: `components/forms/ResponsiveFormGrid.tsx`

Replaces inline `display:grid; gridTemplateColumns:'1fr 1fr 1fr'` patterns.

```tsx
import { ResponsiveFormGrid, FormField } from '../components/forms';

<ResponsiveFormGrid columns={3} tabletColumns={2} mobileColumns={1} gap={16}>
  <FormField label="First Name" .../>
  <FormField label="Last Name" .../>
  <FormField label="Middle Name" .../>
</ResponsiveFormGrid>
```

Defaults: `columns={2}`, `tabletColumns=min(columns,2)`, `mobileColumns={1}`, `gap={16}`.

### 1.4 `PageHeader` (responsive)
Location: `components/PageHeader.tsx`

Already converted. Mobile collapses to a column with stacked title + wrapped actions row; desktop stays inline. No API change — existing call sites keep working.

---

## 2. Migrating AccountProfile (721 lines)

`frontend/src/pages/AccountProfile.tsx` is the single highest-value next
migration because it is user-facing settings and heavy with `<input>` markup.

Steps:
1. Replace the page-level wrapper div + inline style block with the existing
   `PageHeader` + a glass card container (see `GlassCard` in the design
   system).
2. Swap every `<label>…<input>` pair for `<FormField>`. Keep the `value` /
   `onChange` wiring — `FormField`'s `onChange` gives the raw value (not the
   event), so adapters like `onChange={(v) => setX(v)}` suffice.
3. Wrap each logical group of fields in `<ResponsiveFormGrid columns={2}>`.
   Use `columns={1}` for "About" / long-text sections.
4. The "Change password" block is a natural sub-card — consider extracting
   it into `AccountPasswordCard` (< 150 lines) and importing into
   `AccountProfile.tsx`. Same for "Two-factor auth", "Sessions", etc.
5. Delete the local `input` / `label` style constants once all fields are
   migrated.

Target: < 400 lines per file, no inline `<input>` tags.

---

## 3. Migrating list pages (~32 files)

List pages live under `frontend/src/pages/gov/**`, `frontend/src/pages/accounting/**`,
`frontend/src/pages/hr/**`, etc.

Common issues today:
- Bespoke `<table>` markup with inline styles (not responsive — overflows on mobile)
- Filter bars built from ad-hoc flex rows (don't wrap gracefully)
- Inconsistent row density, header styling, empty states

Target pattern:
```tsx
<PageHeader title="Journal Entries" subtitle="Posted & draft entries" actions={…} />

<GlassCard>
  <FilterBar>
    <FormField label="Search" .../>
    <FormField label="Status" type="select" .../>
    <FormField label="Date from" type="date" .../>
  </FilterBar>

  <ResponsiveTable
    columns={columns}
    rows={rows}
    loading={isLoading}
    emptyState={<EmptyState .../>}
    rowActions={(row) => …}
  />

  <Pagination .../>
</GlassCard>
```

Components to build or adopt (not yet shipped — deferred):
- `FilterBar` — wraps `ResponsiveFormGrid` with sticky behaviour on scroll
- `ResponsiveTable` — desktop = `<table>`, mobile = stacked cards with label/value pairs
- `EmptyState` — centred icon + heading + action CTA
- `Pagination` — page/size controls that collapse to prev/next on mobile

### Migration order (by user impact)

1. `/accounting` (Journal Entries) — most-used page
2. `/gov/budget` and `/gov/commitments` — daily gov-finance use
3. `/hr/employees` and `/hr/payroll` — monthly cadence
4. `/accounting/assets/*` — depreciation workflow
5. Report pages under `/gov/reports/*` (14 files) — already partially
   styled; lowest urgency
6. Remaining admin / setup pages

Each migration should:
- [ ] Replace page header → `PageHeader`
- [ ] Replace filter bar → `FormField` + `ResponsiveFormGrid`
- [ ] Replace `<table>` → `ResponsiveTable` (once built)
- [ ] Verify at 375 / 768 / 1440 px
- [ ] Verify keyboard navigation + focus rings
- [ ] Remove now-unused inline style constants

---

## 4. Design tokens — known divergence

There are two conflicting token files:
- `styles/design-tokens.css` → `--color-primary: #242a88`
- `styles/glassmorphism.css` → `--primary: #191e6a`

Both are imported globally. Until one is retired, new code should reference
the gradient literal `linear-gradient(135deg, #242a88, #2e35a0)` used in the
auth pages rather than the ambiguous CSS variables.

Consolidation task (future):
1. Pick one canonical token set (`design-tokens.css` recommended).
2. `grep` for `--primary` usages and rewrite to `--color-primary`.
3. Delete the duplicate file.

---

## 5. Testing checklist

For any migrated page, visually verify:

| Viewport | What to check |
|---|---|
| 375 × 812 (mobile) | No horizontal scroll, tap targets ≥ 44px, labels readable |
| 768 × 1024 (tablet) | Grid columns reduce sensibly, no orphaned whitespace |
| 1280 × 800 (desktop) | Two-column forms, inline action bars |
| 1440 × 900 (wide) | Max-width containers don't sprawl past ~1200px |

Also:
- [ ] `npx tsc --noEmit` passes
- [ ] Focus ring visible on every interactive element
- [ ] Error / success states readable (colour contrast ≥ 4.5:1)

---

## 6. Out of scope for this session

The following remained intentionally untouched in the UI/UX pass and should
be tackled in follow-up sessions:

- AccountProfile.tsx rewrite (will use primitives above)
- ResponsiveTable + FilterBar + EmptyState primitives
- 32 list-page migrations
- Design-token consolidation
- Dark-mode audit (currently light-mode only)

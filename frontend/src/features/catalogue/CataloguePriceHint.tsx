import { useQuery } from '@tanstack/react-query';
import apiClient from '../../api/client';
import { useTenantModules } from '../../hooks/useTenantModules';

interface Props {
  vendorId: string;
  itemId: string;
  /** What is typed in the line now. */
  current: string;
  onUse: (price: string) => void;
  format: (value: number) => string;
}

interface Line { id: number; unit_price: string }

/**
 * The extension slot the catalogue module adds to a purchase order line: when the supplier has a price in force for the
 * item, show it, offer to use it, and say so when the typed price is above it. Renders nothing while the catalogue module is
 * off, or when there is no catalogue price, so the order form is otherwise exactly as it was.
 */
export default function CataloguePriceHint({ vendorId, itemId, current, onUse, format }: Props) {
  const modules = useTenantModules();
  const on = modules.data?.enabled_modules?.catalogue === true;
  const price = useQuery({
    queryKey: ['catalogue', 'price-hint', vendorId, itemId],
    enabled: on && !!vendorId && !!itemId,
    staleTime: 60_000,
    retry: false,
    queryFn: async (): Promise<string | null> => {
      const { data } = await apiClient.get('/catalogue/items/', {
        params: { item: itemId, catalogue__supplier: vendorId, catalogue__status: 'active', is_active: true, page_size: 1 },
      });
      const rows: Line[] = data.results ?? data ?? [];
      return rows[0]?.unit_price ?? null;
    },
  });

  if (!on || !price.data) return null;
  const agreed = Number(price.data);
  const typed = Number(current);
  const above = Number.isFinite(typed) && typed > agreed;
  const same = Number.isFinite(typed) && typed === agreed;

  return (
    <div data-testid="catalogue-hint" style={{ marginTop: 4, fontSize: 'var(--text-xs)', color: above ? '#a1261a' : 'var(--color-text-muted)' }}>
      Catalogue price {format(agreed)}
      {above && <> · this is {format(typed - agreed)} above it</>}
      {!same && (
        <> · <button type="button" onClick={() => onUse(price.data!)} data-testid="catalogue-use"
          style={{ background: 'none', border: 0, padding: 0, color: 'var(--color-primary, #242a88)', fontWeight: 700, cursor: 'pointer', textDecoration: 'underline' }}>Use it</button></>
      )}
    </div>
  );
}

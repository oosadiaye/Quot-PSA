import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

vi.mock('../../api/client', () => ({ default: { post: vi.fn() } }));
import apiClient from '../../api/client';
import { useDuplicateGuard, useDuplicateLookup, type DupMatch } from '../useDuplicateCheck';
import { useGlCodingGuard } from '../useGlCodingGuard';

const post = apiClient.post as unknown as ReturnType<typeof vi.fn>;

const match = (over: Partial<DupMatch> = {}): DupMatch => ({
  id: 7, code: 'V001', name: 'Acme Nigeria Limited', is_active: true,
  level: 'likely', score: 0.97, reasons: ['Almost the same name'], extra: {}, ...over,
});

beforeEach(() => { post.mockReset(); });

describe('useDuplicateGuard', () => {
  it('saves straight away when nothing matches', async () => {
    post.mockResolvedValue({ data: { label: 'Vendor', matches: [] } });
    const { result } = renderHook(() => useDuplicateGuard('vendor'));
    const proceed = vi.fn();
    await act(() => result.current.guard({ name: 'Zed Ltd' }, proceed));
    expect(proceed).toHaveBeenCalledOnce();
    expect(result.current.modalProps.matches).toBeNull();
  });

  it('does not call the server for an empty form', async () => {
    const { result } = renderHook(() => useDuplicateGuard('vendor'));
    const proceed = vi.fn();
    await act(() => result.current.guard({ name: '  ', code: '' }, proceed));
    expect(post).not.toHaveBeenCalled();
    expect(proceed).toHaveBeenCalledOnce();
  });

  it('holds the save and offers to adopt, create anyway, or cancel', async () => {
    post.mockResolvedValue({ data: { label: 'Vendor', matches: [match()] } });
    const { result } = renderHook(() => useDuplicateGuard('vendor'));
    const proceed = vi.fn();
    const adopt = vi.fn();

    await act(() => result.current.guard({ name: 'ACME Nig Ltd' }, proceed, { onUseExisting: adopt }));
    expect(proceed).not.toHaveBeenCalled();
    expect(result.current.modalProps.matches).toHaveLength(1);
    expect(result.current.modalProps.canAdopt).toBe(true);

    act(() => result.current.modalProps.onUseExisting(match()));
    expect(adopt).toHaveBeenCalledWith(expect.objectContaining({ id: 7 }));
    expect(proceed).not.toHaveBeenCalled();
    expect(result.current.modalProps.matches).toBeNull();

    await act(() => result.current.guard({ name: 'ACME Nig Ltd' }, proceed));
    act(() => result.current.modalProps.onCreateAnyway());
    expect(proceed).toHaveBeenCalledOnce();

    await act(() => result.current.guard({ name: 'ACME Nig Ltd' }, proceed));
    act(() => result.current.modalProps.onCancel());
    expect(proceed).toHaveBeenCalledOnce();           // cancel did not save
  });

  it('hides "create anyway" when the code collides (server would reject it)', async () => {
    post.mockResolvedValue({ data: { label: 'GL account', matches: [match({ level: 'exact', reasons: ['Same code'] })] } });
    const { result } = renderHook(() => useDuplicateGuard('account'));
    await act(() => result.current.guard({ code: '1' }, vi.fn()));
    expect(result.current.modalProps.blocksCreate).toBe(true);
  });

  it('never blocks a save when the lookup itself fails', async () => {
    post.mockImplementation(async () => { throw new Error('boom'); });
    const { result } = renderHook(() => useDuplicateGuard('vendor'));
    const proceed = vi.fn();
    await act(() => result.current.guard({ name: 'Acme' }, proceed));
    expect(proceed).toHaveBeenCalledOnce();
  });
});

describe('useDuplicateLookup', () => {
  it('debounces and returns matches', async () => {
    post.mockResolvedValue({ data: { label: 'Vendor', matches: [match()] } });
    const { result } = renderHook(() => useDuplicateLookup('vendor', { name: 'Acme' }, { debounceMs: 10 }));
    await waitFor(() => expect(result.current.matches).toHaveLength(1));
    expect(post).toHaveBeenCalledTimes(1);
    expect(post.mock.calls[0][1]).toMatchObject({ entity: 'vendor', values: { name: 'Acme' } });
  });

  it('stays idle when disabled or blank', async () => {
    const { result } = renderHook(() => useDuplicateLookup('vendor', { name: '' }, { debounceMs: 5 }));
    await new Promise((r) => setTimeout(r, 30));
    expect(post).not.toHaveBeenCalled();
    expect(result.current.matches).toEqual([]);
  });
});

describe('useGlCodingGuard — adopt an existing GL', () => {
  const suggestion = { id: 11, code: '22101001', name: 'Motor Vehicle Fuel', account_type: 'Expense', score: 1, source: 'name' as const };
  const reply = (suggestions = [suggestion]) => ({
    data: { results: [{ index: 1, name: 'Bank Charges', code: '22109999', description: 'diesel', verdict: 'suspect', reason: 'no fit', suggestions }] },
  });
  const lines = [
    { name: 'Motor Vehicle Fuel', code: '22101001', description: 'diesel' },
    { name: 'Bank Charges', code: '22109999', description: 'diesel' },
  ];

  it('adopting recodes the line and closes without posting', async () => {
    post.mockResolvedValue(reply());
    const { result } = renderHook(() => useGlCodingGuard());
    const proceed = vi.fn();
    const adopt = vi.fn();
    await act(() => result.current.guard(lines, proceed, adopt));
    const s = result.current.modalProps.suspects![0];
    expect(s.index).toBe(1);
    expect(result.current.modalProps.canAdopt).toBe(true);

    act(() => result.current.modalProps.onAdopt(s, suggestion));
    expect(adopt).toHaveBeenCalledWith(1, suggestion);
    expect(proceed).not.toHaveBeenCalled();
    expect(result.current.modalProps.suspects).toBeNull();
  });

  it('only offers suggestions the form can select', async () => {
    post.mockResolvedValue(reply());
    const { result } = renderHook(() => useGlCodingGuard());
    await act(() => result.current.guard(lines, vi.fn(), vi.fn(), () => false));
    expect(result.current.modalProps.suspects![0].suggestions).toEqual([]);
  });

  it('"Post anyway" still posts', async () => {
    post.mockResolvedValue(reply());
    const { result } = renderHook(() => useGlCodingGuard());
    const proceed = vi.fn();
    await act(() => result.current.guard(lines, proceed));
    expect(result.current.modalProps.canAdopt).toBe(false);   // no onAdopt → suggestions are informational
    act(() => result.current.modalProps.onConfirm());
    expect(proceed).toHaveBeenCalledOnce();
  });
});

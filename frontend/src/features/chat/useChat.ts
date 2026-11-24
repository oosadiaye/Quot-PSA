import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../api/client';
import { getActiveTenantDomain } from '../../utils/tenantResolver';
import type { ChatMessage, ContactsPayload, Summary } from './types';

const BASE = '/core/chat';

/** The launcher polls slowly; an open panel polls quickly. Nothing polls in a hidden tab. */
const CLOSED_POLL_MS = 20_000;
const LIST_POLL_MS = 10_000;
const THREAD_POLL_MS = 4_000;

const visible = () => (typeof document === 'undefined' || document.visibilityState === 'visible');

/** Every chat query key carries the active tenant, so one tenant's cached people
 *  and messages can never be shown under another after the user switches. */
export const chatKey = (...parts: unknown[]) => ['chat', getActiveTenantDomain() ?? 'none', ...parts];

/** Unread count and people online: all the closed widget needs. */
export function useChatSummary(enabled: boolean) {
    return useQuery<Summary>({
        queryKey: chatKey('summary'),
        queryFn: async () => (await apiClient.get(`${BASE}/summary/`)).data,
        enabled,
        refetchInterval: () => (visible() ? CLOSED_POLL_MS : false),
        refetchOnWindowFocus: true,
        staleTime: 5_000,
    });
}

export function useContacts(enabled: boolean) {
    return useQuery<ContactsPayload>({
        queryKey: chatKey('contacts'),
        queryFn: async () => (await apiClient.get(`${BASE}/contacts/`)).data,
        enabled,
        refetchInterval: () => (visible() ? LIST_POLL_MS : false),
        refetchOnWindowFocus: true,
        staleTime: 2_000,
    });
}

/** The conversation with one person. Fetching it also marks what they sent as read. */
export function useThread(contactId: number | null) {
    return useQuery<ChatMessage[]>({
        queryKey: chatKey('thread', contactId),
        queryFn: async () => (await apiClient.get(`${BASE}/messages/`, { params: { with: contactId, read: 1 } })).data.messages,
        enabled: contactId !== null,
        refetchInterval: () => (visible() ? THREAD_POLL_MS : false),
        refetchOnWindowFocus: true,
        staleTime: 0,
    });
}

export interface SendArgs { recipient: number; body: string; file: File | null }

export function useSendMessage() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async ({ recipient, body, file }: SendArgs) => {
            const form = new FormData();
            form.append('recipient', String(recipient));
            form.append('body', body);
            if (file) form.append('attachment', file);
            // This client's default Content-Type is JSON, and axios would then flatten the form to JSON and
            // silently drop the file. Naming multipart (as every upload in the app does) makes axios hand the
            // form to the browser, which writes the real header with its boundary.
            return (await apiClient.post(`${BASE}/messages/`, form, {
                headers: { 'Content-Type': 'multipart/form-data' },
            })).data as ChatMessage;
        },
        onSuccess: (_message, { recipient }) => {
            void qc.invalidateQueries({ queryKey: chatKey('thread', recipient) });
            void qc.invalidateQueries({ queryKey: chatKey('contacts') });
        },
    });
}

/** Download a received or sent file through the authenticated endpoint (a bare link would carry no token). */
export async function fetchAttachment(url: string): Promise<Blob> {
    return (await apiClient.get(url, { responseType: 'blob' })).data as Blob;
}

/** A sentence for a failed send: the server's own reason (`error`, or `detail` for a throttle),
 *  the network message when the server was not reached, otherwise a plain fallback. */
export function sendErrorText(err: unknown): string {
    const fallback = 'The message was not sent.';
    const e = err as { response?: { data?: { error?: unknown; detail?: unknown } }; message?: unknown };
    const data = e?.response?.data;
    if (typeof data?.error === 'string') return data.error;
    if (typeof data?.detail === 'string') return data.detail;
    if (!e?.response && typeof e?.message === 'string' && e.message) return e.message;
    return fallback;
}

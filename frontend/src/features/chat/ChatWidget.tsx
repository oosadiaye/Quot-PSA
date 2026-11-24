import { Suspense, lazy, useEffect, useState } from 'react';
import { HelpCircle, MessageCircle, X } from 'lucide-react';
import { useLocation } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { isImpersonating } from '../../components/ImpersonationBanner';
import ContactList from './ContactList';
import Conversation from './Conversation';
import { useChatSummary, useContacts } from './useChat';
import type { Contact } from './types';
import './chat.css';

const AskAi = lazy(() => import('./AskAi'));

type Tab = 'chat' | 'ask';

/** Pages with no signed-in workspace (or a focused flow): the widget is never shown on them. */
const HIDDEN_ON = /^\/(login|register|forgot-password|reset-password|verify-email|setup|superadmin)(\/|$)/;

/**
 * Team chat, bottom right. Message the other people in your workspace and share a file of up to 2 MB.
 * Everyone who is signed in shows as online; signing out takes them offline at once.
 *
 * Not shown while a superadmin is impersonating a user: anything sent would be attributed to the
 * person being impersonated.
 */
export default function ChatWidget() {
    const { isAuthenticated } = useAuth();
    const { pathname } = useLocation();
    const available = isAuthenticated && !HIDDEN_ON.test(pathname) && !isImpersonating();
    const [open, setOpen] = useState(false);
    const [peerId, setPeerId] = useState<number | null>(null);
    const [tab, setTab] = useState<Tab>('chat');

    const summary = useChatSummary(available && !open);
    const contactsQuery = useContacts(available && open);
    const contacts = contactsQuery.data?.contacts ?? [];
    // Keep the open conversation's header (name, online) fresh from the polled list.
    const peer = peerId === null ? null : contacts.find(c => c.id === peerId) ?? null;

    useEffect(() => {
        if (!open) return;
        const onKey = (e: KeyboardEvent) => {
            if (e.key !== 'Escape') return;
            if (peerId !== null) setPeerId(null); else setOpen(false);
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [open, peerId]);

    if (!available) return null;

    const unread = open ? (contactsQuery.data?.unread_total ?? 0) : (summary.data?.unread_total ?? 0);
    const online = open ? (contactsQuery.data?.online_count ?? 0) : (summary.data?.online_count ?? 0);
    const maxBody = contactsQuery.data?.limits.max_body_chars ?? 4000;

    const openPeer = (c: Contact) => setPeerId(c.id);

    return (
        <>
            {open && (
                <section className="chat-panel" role="dialog" aria-label="Team chat" data-testid="chat-panel">
                    {peer ? (
                        <Conversation key={peer.id} contact={peer} maxBody={maxBody} onBack={() => setPeerId(null)} />
                    ) : (
                        <>
                            <div className="chat-head">
                                <h2>
                                    {tab === 'chat' ? 'Team chat' : 'Help'}
                                    <small data-testid="chat-online-count">{tab === 'chat' ? `${online} online` : 'Ask how to do something'}</small>
                                </h2>
                                <button type="button" className="chat-iconbtn" onClick={() => setOpen(false)} aria-label="Close chat"
                                    data-testid="chat-close"><X size={18} /></button>
                            </div>
                            <div className="chat-tabs" role="tablist">
                                <button type="button" role="tab" aria-selected={tab === 'chat'} className={`chat-tab${tab === 'chat' ? ' on' : ''}`}
                                    data-testid="tab-chat" onClick={() => setTab('chat')}>
                                    <MessageCircle size={15} aria-hidden="true" /> Chat
                                    {unread > 0 && <span className="chat-tab-count">{unread > 99 ? '99+' : unread}</span>}
                                </button>
                                <button type="button" role="tab" aria-selected={tab === 'ask'} className={`chat-tab${tab === 'ask' ? ' on' : ''}`}
                                    data-testid="tab-ask" onClick={() => setTab('ask')}>
                                    <HelpCircle size={15} aria-hidden="true" /> Ask AI
                                </button>
                            </div>
                            {tab === 'chat' ? (
                                <ContactList contacts={contacts} loading={contactsQuery.isLoading} onOpen={openPeer} />
                            ) : (
                                <Suspense fallback={<div className="chat-empty">Loading...</div>}>
                                    <AskAi onNavigate={() => setOpen(false)} />
                                </Suspense>
                            )}
                        </>
                    )}
                </section>
            )}
            <button type="button" className="chat-launcher" data-testid="chat-launcher"
                onClick={() => { setOpen(o => !o); setPeerId(null); }}
                aria-label={`Team chat${unread ? `, ${unread} unread` : ''}${online ? `, ${online} online` : ''}`}
                aria-expanded={open}>
                <MessageCircle size={26} aria-hidden="true" />
                {unread > 0 && <span className="chat-badge" data-testid="chat-badge">{unread > 99 ? '99+' : unread}</span>}
                {online > 0 && unread === 0 && <span className="chat-online-dot" title={`${online} online`} />}
            </button>
        </>
    );
}

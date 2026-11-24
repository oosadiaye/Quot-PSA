import { useMemo, useState } from 'react';
import { initials, messageTime } from './chatFormat';
import type { Contact } from './types';

interface Props {
    contacts: Contact[];
    loading: boolean;
    onOpen: (contact: Contact) => void;
}

/** Everyone else in the workspace: online first, with unread counts and the last message. */
export default function ContactList({ contacts, loading, onOpen }: Props) {
    const [query, setQuery] = useState('');
    const shown = useMemo(() => {
        const q = query.trim().toLowerCase();
        return q ? contacts.filter(c => c.name.toLowerCase().includes(q) || c.username.toLowerCase().includes(q)) : contacts;
    }, [contacts, query]);

    return (
        <>
            <div className="chat-search">
                <input type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Search people"
                    aria-label="Search people" data-testid="chat-search" />
            </div>
            <div className="chat-list" data-testid="chat-contacts">
                {loading && contacts.length === 0 && <div className="chat-empty">Loading…</div>}
                {!loading && contacts.length === 0 && (
                    <div className="chat-empty">No one else is in this workspace yet.</div>
                )}
                {!loading && contacts.length > 0 && shown.length === 0 && <div className="chat-empty">Nobody matches.</div>}
                {shown.map(c => (
                    <button key={c.id} type="button" className="chat-row" onClick={() => onOpen(c)}
                        data-testid={`chat-contact-${c.username}`}
                        aria-label={`${c.name}, ${c.online ? 'online' : 'offline'}${c.unread ? `, ${c.unread} unread` : ''}`}>
                        <span className="chat-avatar" aria-hidden="true">
                            {initials(c.name)}
                            <span className={`chat-presence${c.online ? ' on' : ''}`} data-testid={c.online ? 'presence-online' : 'presence-offline'} />
                        </span>
                        <span className="chat-who">
                            <span className="chat-name">
                                <span>{c.name}</span>
                                {c.last_message && <time dateTime={c.last_message.at}>{messageTime(c.last_message.at)}</time>}
                            </span>
                            <span className="chat-preview">
                                {c.last_message
                                    ? `${c.last_message.mine ? 'You: ' : ''}${c.last_message.preview}`
                                    : (c.online ? 'Online' : 'Offline')}
                            </span>
                        </span>
                        {c.unread > 0 && <span className="chat-unread" data-testid="chat-unread">{c.unread}</span>}
                    </button>
                ))}
            </div>
        </>
    );
}

import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, Download, Paperclip, Send, X } from 'lucide-react';
import { downloadBlob } from '../../utils/downloadBlob';
import { attachmentProblem, formatBytes, MAX_ATTACHMENT_BYTES, messageTime } from './chatFormat';
import { fetchAttachment, sendErrorText, useSendMessage, useThread } from './useChat';
import type { ChatMessage, Contact } from './types';

interface Props {
    contact: Contact;
    maxBody: number;
    onBack: () => void;
}

function FileLine({ message }: { message: ChatMessage }) {
    const [busy, setBusy] = useState(false);
    const [failed, setFailed] = useState(false);
    const a = message.attachment!;
    const open = async () => {
        setBusy(true);
        setFailed(false);
        try { downloadBlob(await fetchAttachment(a.url), a.name); } catch { setFailed(true); } finally { setBusy(false); }
    };
    return (
        <>
            <button type="button" className="chat-file" onClick={open} disabled={busy} title="Download"
                data-testid="chat-file" aria-label={`Download ${a.name}, ${formatBytes(a.size)}`}>
                <Download size={14} aria-hidden="true" />
                <span>{a.name}</span>
                <small>{formatBytes(a.size)}</small>
            </button>
            {failed && <div className="chat-error" role="alert">The file could not be downloaded.</div>}
        </>
    );
}

/** One conversation: messages, a composer, and an attachment of up to 2 MB. */
export default function Conversation({ contact, maxBody, onBack }: Props) {
    const { data: messages = [], isLoading } = useThread(contact.id);
    const send = useSendMessage();
    const [text, setText] = useState('');
    const [file, setFile] = useState<File | null>(null);
    const [error, setError] = useState('');
    const bottom = useRef<HTMLDivElement>(null);
    const picker = useRef<HTMLInputElement>(null);
    const lastId = messages.length ? messages[messages.length - 1].id : 0;

    // Stay at the newest message when one arrives.
    useEffect(() => { bottom.current?.scrollIntoView({ block: 'end' }); }, [lastId]);

    const choose = (picked: File | undefined) => {
        if (!picked) return;
        const problem = attachmentProblem(picked, MAX_ATTACHMENT_BYTES);
        setError(problem ?? '');
        setFile(problem ? null : picked);
        if (picker.current) picker.current.value = '';
    };

    const submit = async () => {
        if ((!text.trim() && !file) || send.isPending) return;
        setError('');
        try {
            await send.mutateAsync({ recipient: contact.id, body: text, file });
            setText('');
            setFile(null);
        } catch (err) {
            setError(sendErrorText(err));
        }
    };

    return (
        <>
            <div className="chat-head">
                <button type="button" className="chat-iconbtn" onClick={onBack} aria-label="Back to people" data-testid="chat-back">
                    <ArrowLeft size={18} />
                </button>
                <h2>
                    {contact.name}
                    <small data-testid="chat-peer-status">{contact.online ? 'Online' : 'Offline'}</small>
                </h2>
            </div>
            <div className="chat-thread" data-testid="chat-thread" role="log" aria-live="polite">
                {isLoading && <div className="chat-empty">Loading…</div>}
                {!isLoading && messages.length === 0 && <div className="chat-empty">No messages yet. Say hello.</div>}
                {messages.map(m => (
                    <div key={m.id} className={`chat-msg ${m.mine ? 'mine' : 'theirs'}`} data-testid="chat-message">
                        {m.body && <div>{m.body}</div>}
                        {m.attachment && <FileLine message={m} />}
                        <time dateTime={m.created_at}>{messageTime(m.created_at)}</time>
                    </div>
                ))}
                <div ref={bottom} />
            </div>
            <div className="chat-composer">
                {file && (
                    <div className="chat-chip" data-testid="chat-pending-file">
                        <Paperclip size={13} aria-hidden="true" />
                        <span>{file.name}</span>
                        <small>{formatBytes(file.size)}</small>
                        <button type="button" className="chat-iconbtn" style={{ color: 'inherit' }} onClick={() => setFile(null)}
                            aria-label="Remove attachment"><X size={13} /></button>
                    </div>
                )}
                {error && <div className="chat-error" role="alert" data-testid="chat-error">{error}</div>}
                <div className="row">
                    <input ref={picker} type="file" hidden data-testid="chat-file-input" onChange={e => choose(e.target.files?.[0])} />
                    <button type="button" className="chat-attach" onClick={() => picker.current?.click()}
                        aria-label="Attach a file (up to 2 MB)" title="Attach a file (up to 2 MB)">
                        <Paperclip size={17} />
                    </button>
                    <textarea
                        value={text} rows={1} maxLength={maxBody} placeholder="Write a message" aria-label="Message"
                        data-testid="chat-input"
                        onChange={e => setText(e.target.value)}
                        onKeyDown={e => {
                            // Enter sends; Shift+Enter adds a line.
                            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void submit(); }
                        }}
                    />
                    <button type="button" className="chat-send" onClick={() => void submit()} data-testid="chat-send"
                        disabled={(!text.trim() && !file) || send.isPending} aria-label="Send">
                        <Send size={16} />
                    </button>
                </div>
                <div className="chat-hint">Files up to 2 MB. Enter sends, Shift+Enter for a new line.</div>
            </div>
        </>
    );
}

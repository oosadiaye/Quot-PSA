export interface Contact {
    id: number;
    name: string;
    username: string;
    online: boolean;
    unread: number;
    last_message: { preview: string; at: string; mine: boolean } | null;
}

export interface ContactsPayload {
    contacts: Contact[];
    unread_total: number;
    online_count: number;
    limits: { max_attachment_bytes: number; max_body_chars: number };
}

export interface Summary { unread_total: number; online_count: number }

export interface Attachment { name: string; size: number; is_image: boolean; url: string }

export interface ChatMessage {
    id: number;
    sender: number;
    recipient: number;
    mine: boolean;
    body: string;
    created_at: string;
    read: boolean;
    attachment: Attachment | null;
}

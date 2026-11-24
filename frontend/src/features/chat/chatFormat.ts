import { formatDate } from '../../utils/date';

/** The attachment limit: 2 MB, the same number the server enforces. */
export const MAX_ATTACHMENT_BYTES = 2 * 1024 * 1024;

/** Files that can run, carry a script or macro are refused before upload. Mirrors BLOCKED_EXTENSIONS in
 *  core/services/chat.py (the server enforces it; this only saves the upload). Keep the two lists identical. */
const BLOCKED = new Set([
    'exe', 'msi', 'bat', 'cmd', 'com', 'scr', 'pif', 'dll', 'lnk', 'reg', 'jar', 'apk', 'app', 'dmg', 'pkg',
    'command', 'cpl', 'inf', 'msc', 'msp', 'jnlp', 'gadget', 'appref-ms', 'xll', 'iqy', 'scf', 'url', 'js', 'mjs',
    'jse', 'vbs', 'vbe', 'wsf', 'wsh', 'wsc', 'ps1', 'psm1', 'ps1xml', 'psc1', 'sh', 'py', 'pyw', 'pyc', 'rb', 'pl',
    'hta', 'html', 'htm', 'xhtml', 'xht', 'shtml', 'shtm', 'svg', 'xml', 'php', 'php3', 'php4', 'php5', 'php7',
    'phtml', 'phar', 'jsp', 'jspx', 'asp', 'aspx', 'cgi', 'swf', 'docm', 'xlsm', 'pptm', 'dotm', 'chm', 'iso', 'img',
    'vhd',
]);

export function formatBytes(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(bytes < 10 * 1024 ? 1 : 0)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Why this file cannot be attached, or ``null`` when it can. */
export function attachmentProblem(file: { name: string; size: number }, max = MAX_ATTACHMENT_BYTES): string | null {
    if (file.size <= 0) return 'That file is empty.';
    if (file.size > max) return `Files are limited to ${formatBytes(max)}. This one is ${formatBytes(file.size)}.`;
    const extension = file.name.includes('.') ? file.name.split('.').pop()!.toLowerCase() : '';
    if (BLOCKED.has(extension)) return `.${extension} files cannot be sent in chat.`;
    return null;
}

export function initials(name: string): string {
    const parts = name.trim().split(/\s+/).filter(Boolean);
    if (parts.length === 0) return '?';
    return (parts.length === 1 ? parts[0].slice(0, 2) : parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/** "14:05" today, "Mon 14:05" this week, otherwise DD/MM/YYYY (the house date format).
 *
 *  The locale is pinned to en-GB rather than left to the viewer's machine, so
 *  two colleagues reading the same message see the same text, and an older
 *  message never reads as MM/DD/YYYY. */
export function messageTime(iso: string, now: Date = new Date()): string {
    const when = new Date(iso);
    if (Number.isNaN(when.getTime())) return '';
    const time = when.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
    if (when.toDateString() === now.toDateString()) return time;
    const days = (now.getTime() - when.getTime()) / 86_400_000;
    if (days >= 0 && days < 6) return `${when.toLocaleDateString('en-GB', { weekday: 'short' })} ${time}`;
    return formatDate(when);
}

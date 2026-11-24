import { describe, expect, it } from 'vitest';
import { attachmentProblem, formatBytes, initials, MAX_ATTACHMENT_BYTES, messageTime } from './chatFormat';
import { sendErrorText } from './useChat';

describe('attachmentProblem', () => {
    it('allows a file of exactly 2 MB and refuses one byte more', () => {
        expect(attachmentProblem({ name: 'a.pdf', size: MAX_ATTACHMENT_BYTES })).toBeNull();
        expect(attachmentProblem({ name: 'a.pdf', size: MAX_ATTACHMENT_BYTES + 1 })).toMatch(/limited to 2\.0 MB/);
    });

    it('refuses an empty file', () => {
        expect(attachmentProblem({ name: 'a.pdf', size: 0 })).toMatch(/empty/);
    });

    it('refuses files that can run or carry a script, whatever the case', () => {
        for (const name of ['setup.exe', 'run.BAT', 'page.html', 'logo.svg', 'x.js', 'tool.ps1']) {
            expect(attachmentProblem({ name, size: 100 }), name).toMatch(/cannot be sent/);
        }
    });

    it('also refuses macro-enabled Office files, disk images and server-side scripts', () => {
        for (const name of ['m.docm', 'm.XLSM', 'disk.iso', 'help.chm', 'x.url', 'p.aspx', 'run.py', 'cfg.xml', 's.phtml']) {
            expect(attachmentProblem({ name, size: 100 }), name).toMatch(/cannot be sent/);
        }
    });

    it('accepts ordinary documents and images, and names with no extension', () => {
        for (const name of ['report.pdf', 'sheet.xlsx', 'deck.pptx', 'minutes.docx', 'data.csv', 'bundle.zip', 'photo.PNG', 'notes.txt', 'README']) {
            expect(attachmentProblem({ name, size: 100 }), name).toBeNull();
        }
    });
});

describe('formatBytes', () => {
    it('reads naturally at each scale', () => {
        expect(formatBytes(512)).toBe('512 B');
        expect(formatBytes(2048)).toBe('2.0 KB');
        expect(formatBytes(150 * 1024)).toBe('150 KB');
        expect(formatBytes(2 * 1024 * 1024)).toBe('2.0 MB');
    });
});

describe('initials', () => {
    it('uses the first and last name, or the first two letters of a single name', () => {
        expect(initials('Alice Ngozi')).toBe('AN');
        expect(initials('Mary Jane Watson')).toBe('MW');
        expect(initials('admin')).toBe('AD');
        expect(initials('   ')).toBe('?');
    });
});

describe('messageTime', () => {
    const now = new Date('2026-10-12T15:00:00');

    it('shows the time for today', () => {
        expect(messageTime('2026-10-12T09:05:00', now)).toBe('09:05');
    });

    it('shows the weekday and time for this week', () => {
        expect(messageTime('2026-10-10T09:05:00', now)).toBe('Sat 09:05');
    });

    it('shows the date in the house DD/MM/YYYY format for anything older', () => {
        expect(messageTime('2026-08-01T09:05:00', now)).toBe('01/08/2026');
        expect(messageTime('2026-09-30T09:05:00', now)).toBe('30/09/2026');
    });

    it('never reads as month-first, even when the day could be a month', () => {
        // 03/04 must mean 3 April, not March 4th.
        expect(messageTime('2026-04-03T09:05:00', now)).toBe('03/04/2026');
    });

    it('shows nothing for an unreadable timestamp rather than "Invalid Date"', () => {
        expect(messageTime('not a date', now)).toBe('');
    });
});

describe('sendErrorText', () => {
    it('uses the server\'s own reason', () => {
        expect(sendErrorText({ response: { data: { error: 'Files are limited to 2 MB. Choose a smaller file.' } } }))
            .toBe('Files are limited to 2 MB. Choose a smaller file.');
    });

    it('uses `detail` for a throttled request', () => {
        expect(sendErrorText({ response: { data: { detail: 'Request was throttled. Expected available in 30 seconds.' } } }))
            .toMatch(/throttled/);
    });

    it('uses the network message when the server was never reached', () => {
        expect(sendErrorText(new Error('Network error: Unable to reach the server.'))).toMatch(/Network error/);
    });

    it('falls back to a plain sentence, never a page of HTML', () => {
        expect(sendErrorText({ response: { data: '<!doctype html><html>500</html>' } })).toBe('The message was not sent.');
        expect(sendErrorText(undefined)).toBe('The message was not sent.');
    });
});

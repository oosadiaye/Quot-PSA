/** Save a Blob to disk under ``filename`` (an in-memory file the browser cannot link to). */
export function downloadBlob(blob: Blob, filename: string): void {
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    // Revoke after the click has been handed to the browser, not before.
    setTimeout(() => URL.revokeObjectURL(url), 0);
}

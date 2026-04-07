import { useEffect, useRef, useCallback } from 'react';

const FOCUSABLE_SELECTOR =
    'a[href],button:not([disabled]),textarea:not([disabled]),input:not([disabled]),select:not([disabled]),[tabindex]:not([tabindex="-1"])';

/**
 * Hook to trap keyboard focus inside a container element.
 * Handles Tab/Shift-Tab cycling and Escape to close.
 *
 * Usage:
 *   const containerRef = useFocusTrap(isOpen, onClose);
 *   <div ref={containerRef} role="dialog" aria-modal="true">...</div>
 */
export function useFocusTrap(isOpen: boolean, onClose: () => void) {
    const containerRef = useRef<HTMLDivElement>(null);
    const previousActiveElement = useRef<Element | null>(null);

    const handleKeyDown = useCallback((e: KeyboardEvent) => {
        if (e.key === 'Escape') { onClose(); return; }
        if (e.key !== 'Tab' || !containerRef.current) return;

        const focusable = containerRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR);
        if (focusable.length === 0) return;

        const first = focusable[0];
        const last = focusable[focusable.length - 1];

        if (e.shiftKey && document.activeElement === first) {
            e.preventDefault();
            last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
            e.preventDefault();
            first.focus();
        }
    }, [onClose]);

    useEffect(() => {
        if (!isOpen) return;

        previousActiveElement.current = document.activeElement;
        document.addEventListener('keydown', handleKeyDown);

        // Auto-focus first focusable element
        requestAnimationFrame(() => {
            const first = containerRef.current?.querySelector<HTMLElement>(FOCUSABLE_SELECTOR);
            first?.focus();
        });

        return () => {
            document.removeEventListener('keydown', handleKeyDown);
            if (previousActiveElement.current instanceof HTMLElement) {
                previousActiveElement.current.focus();
            }
        };
    }, [isOpen, handleKeyDown]);

    return containerRef;
}

import { Link, useLocation } from 'react-router-dom';

/**
 * 404 page for unmatched routes.
 *
 * Before this existed the app had no catch-all, so any mistyped, stale or
 * removed URL rendered an empty document — body content was just the skip
 * link. A user following a dead link landed on a white screen with no
 * navigation and no way back except editing the address bar.
 */
export default function NotFound() {
    const location = useLocation();

    return (
        <main
            id="main-content"
            style={{
                minHeight: '70vh',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                padding: '2rem',
            }}
        >
            <div style={{ textAlign: 'center', maxWidth: '30rem' }}>
                <p
                    style={{
                        fontSize: '3.5rem',
                        fontWeight: 800,
                        letterSpacing: '-0.02em',
                        color: '#94a3b8',
                        margin: 0,
                        lineHeight: 1,
                    }}
                >
                    404
                </p>
                <h1
                    style={{
                        fontSize: '1.5rem',
                        fontWeight: 700,
                        color: '#1e293b',
                        margin: '0.75rem 0 0.5rem',
                    }}
                >
                    Page not found
                </h1>
                <p style={{ color: '#64748b', margin: '0 0 0.5rem' }}>
                    Nothing is routed to this address.
                </p>
                <p
                    style={{
                        color: '#94a3b8',
                        fontFamily: 'monospace',
                        fontSize: '0.8125rem',
                        wordBreak: 'break-all',
                        margin: '0 0 1.75rem',
                    }}
                >
                    {location.pathname}
                </p>
                <div
                    style={{
                        display: 'flex',
                        gap: '0.75rem',
                        justifyContent: 'center',
                        flexWrap: 'wrap',
                    }}
                >
                    <Link
                        to="/dashboard"
                        style={{
                            padding: '0.625rem 1.25rem',
                            borderRadius: '0.5rem',
                            background: '#1e3a8a',
                            color: '#fff',
                            fontWeight: 600,
                            textDecoration: 'none',
                            fontSize: '0.875rem',
                        }}
                    >
                        Go to Dashboard
                    </Link>
                    <button
                        type="button"
                        onClick={() => window.history.back()}
                        style={{
                            padding: '0.625rem 1.25rem',
                            borderRadius: '0.5rem',
                            border: '1px solid #cbd5e1',
                            background: '#fff',
                            color: '#334155',
                            fontWeight: 600,
                            cursor: 'pointer',
                            fontSize: '0.875rem',
                            fontFamily: 'inherit',
                        }}
                    >
                        Go back
                    </button>
                </div>
            </div>
        </main>
    );
}

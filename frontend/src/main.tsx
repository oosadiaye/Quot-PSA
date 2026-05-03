import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import './styles/responsive.css'
import App from './App.tsx'
import { consumeTenantBootstrap } from './utils/tenantBootstrap'

// Cross-host tenant handoff: when the apex login redirects a user to
// their tenant subdomain, it stuffs the auth token into the URL
// fragment (``localStorage`` doesn't cross origins). We must consume
// it BEFORE React mounts so the very first API call already has the
// token in storage. ``replaceState`` strips the fragment so it
// doesn't leak into history. Safe no-op when there's no fragment.
consumeTenantBootstrap()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'
import { getSiteConfig } from './hooks/useSiteConfig'

// Synchronously apply the configured site theme-style BEFORE first paint.
// This avoids a flash of unstyled/wrong-theme content: the CSS relies on
// [data-theme-style] (default/luogu/hydro) to scope variables and rules,
// so the attribute must be set before React renders.
const siteTheme = getSiteConfig().site.theme
document.documentElement.setAttribute('data-theme-style', siteTheme)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

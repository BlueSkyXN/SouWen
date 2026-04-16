import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@core/i18n'
import 'virtual:skin-loader'
import { getSkinOrDefault, getDefaultSkinId, setActiveSkinId } from '@core/skin-registry'
import App from './App'

// Synchronous bootstrap — apply skin attributes before first render
const savedSkinId = localStorage.getItem('souwen_skin') || getDefaultSkinId()
const activeSkin = getSkinOrDefault(savedSkinId)
setActiveSkinId(activeSkin.id)
document.documentElement.setAttribute('data-skin', activeSkin.id)

// Persist valid skin ID (corrects invalid/stale values)
if (savedSkinId !== activeSkin.id) {
  localStorage.setItem('souwen_skin', activeSkin.id)
}

// Load mode/scheme from localStorage and apply to DOM synchronously
activeSkin.skinModule.bootstrap()

const { ErrorBoundary } = activeSkin.skinModule

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>,
)

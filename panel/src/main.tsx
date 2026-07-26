import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@core/styles/base.scss'
import '@core/styles/calm-precision.scss'
import App from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

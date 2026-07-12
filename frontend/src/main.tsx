import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './i18n/config' // 初始化 i18n
import './styles/index.css'
import { registerServiceWorker } from './utils/serviceWorker'

registerServiceWorker()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)




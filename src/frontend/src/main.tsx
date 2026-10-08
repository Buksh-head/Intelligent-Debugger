/**
 * App entry point. Mounts React into the #root div in index.html
 * and wraps the app in the providers every page needs.
 */
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App.tsx'
import { AuthProvider } from './auth/AuthContext'
import { StudentSessionProvider } from './session/StudentSessionContext'

createRoot(document.getElementById('root')!).render(
    // StrictMode runs some code twice in development to catch bugs.
  <StrictMode>
    {/* Handles page URLs and navigation. */}
    <BrowserRouter>
      {/* Instructor login state, available on every page. */}
      <AuthProvider>
        {/* Student session state, available on every page. */}
        <StudentSessionProvider>
          <App />
        </StudentSessionProvider>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
)

/**
 * Wraps pages that need an instructor login. Sends anyone not logged in
 * back to the start.
 */
import type { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from './useAuth';

export default function ProtectedRoute({ children }: { children: ReactNode }) {
  const { session, loading } = useAuth();

  // Wait for the login check, otherwise logged-in instructors get
  // bounced on page refresh.
  if (loading) {
    return <p className="text-center mt-20">Loading...</p>;
  }

  // /login now redirects to the welcome page.
  if (!session) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}

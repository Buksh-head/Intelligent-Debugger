/**
 * Wraps pages that need a login. Pass requiredRole to limit a page to one
 * role. Instructors can also open student pages. Anyone else is sent to
 * the page that suits their role.
 */
import type { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from './useAuth';
import type { Role } from './context';

export default function ProtectedRoute({
  children,
  requiredRole,
}: {
  children: ReactNode;
  requiredRole?: Role;
}) {
  const { session, role, loading } = useAuth();

  // Wait for the login check and the role lookup, otherwise logged-in
  // users get bounced on page refresh.
  if (loading) {
    return <p className="text-center mt-20">Loading...</p>;
  }

  // Not logged in: back to the welcome page.
  if (!session) {
    return <Navigate to="/" replace />;
  }

  // Student pages are open to students and instructors.
  // Instructor pages are open to instructors only.
  const allowed =
    !requiredRole ||
    role === requiredRole ||
    (requiredRole === 'student' && role === 'instructor');

  if (!allowed) {
    // No profile row: send to the welcome page rather than looping.
    if (!role) return <Navigate to="/" replace />;
    return <Navigate to="/student/sessions" replace />;
  }

  return <>{children}</>;
}
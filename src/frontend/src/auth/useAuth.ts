/**
 * Hook for reading the instructor login state, e.g. const { session } = useAuth().
 * Throws if used outside AuthProvider, so the mistake shows up straight away.
 */
import { useContext } from 'react';
import { AuthContext, type AuthContextValue } from './context';

export function useAuth(): AuthContextValue {
  // Components use this hook rather than reading the context directly.
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
/**
 * The auth context and its type. Kept separate from AuthContext.tsx
 */
import { createContext } from 'react';
import type { Session } from '@supabase/supabase-js';

export type AuthContextValue = {
  session: Session | null; // null when no instructor is logged in
  loading: boolean;
  signIn: (email: string, password: string) => Promise<{ error: string | null }>;
  signUp: (email: string, password: string) => Promise<{ error: string | null }>;
  signOut: () => Promise<void>;
};

export const AuthContext = createContext<AuthContextValue | null>(null);
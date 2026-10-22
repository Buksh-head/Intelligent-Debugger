/**
 * The auth context and its type. Kept separate from AuthContext.tsx
 */
import { createContext } from "react";
import type { Session } from "@supabase/supabase-js";

export type Role = "student" | "instructor";

export type AuthContextValue = {
  // The context exposes only the authentication operations and state that
  // pages need; Supabase remains behind AuthProvider.
  session: Session | null; // null when no one is logged in
  role: Role | null; // from the profiles table; null when logged out or no profile row
  loading: boolean;
  signIn: (
    email: string,
    password: string,
  ) => Promise<{ error: string | null; role: Role | null }>;
  signUp: (
    email: string,
    password: string,
    role?: Role,
  ) => Promise<{ error: string | null }>;
  signOut: () => Promise<void>;
};

export const AuthContext = createContext<AuthContextValue | null>(null);

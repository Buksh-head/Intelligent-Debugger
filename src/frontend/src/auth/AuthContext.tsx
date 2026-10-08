/**
 * Keeps track of whether an instructor is logged in, and shares the
 * login, sign-up and logout functions with the rest of the app.
 * Students don't use this. They stay anonymous.
 */
import { useEffect, useState, type ReactNode } from 'react';
import type { Session } from '@supabase/supabase-js';
import { supabase } from '../lib/supabaseClient';
import { AuthContext, type AuthContextValue } from './context';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  // True until we've checked for an existing login, so pages don't
  // redirect before we know.
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Pick up a login saved from an earlier visit.
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setLoading(false);
    });

    // Update whenever the instructor logs in, logs out or the session expires.
    const { data: subscription } = supabase.auth.onAuthStateChange((_event, newSession) => {
      setSession(newSession);
    });

    return () => subscription.subscription.unsubscribe();
  }, []);

  // Returns an error message, or null if it worked.
  const signIn: AuthContextValue['signIn'] = async (email, password) => {
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    return { error: error?.message ?? null };
  };

  // Returns an error message, or null if it worked
  const signUp: AuthContextValue['signUp'] = async (email, password) => {
    const { error } = await supabase.auth.signUp({ email, password });
    return { error: error?.message ?? null };
  };

  const signOut = async () => {
    await supabase.auth.signOut();
  };

  return (
    <AuthContext.Provider value={{ session, loading, signIn, signUp, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}


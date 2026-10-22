/**
 * Keeps track of who is logged in and what role they have, and shares the
 * login, sign-up and logout functions with the rest of the app.
 * The role comes from the profiles table, never from the client.
 */
import { useEffect, useState, type ReactNode } from "react";
import type { Session } from "@supabase/supabase-js";
import { supabase } from "../lib/supabaseClient";
import { AuthContext, type AuthContextValue, type Role } from "./context";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [role, setRole] = useState<Role | null>(null);
  // The user id the current `role` was fetched for.
  const [roleFor, setRoleFor] = useState<string | null>(null);
  // True until we've checked for an existing login.
  const [sessionLoading, setSessionLoading] = useState(true);

  // Effect 1: track the session.
  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setSessionLoading(false);
    });

    const { data: subscription } = supabase.auth.onAuthStateChange(
      (_event, newSession) => {
        setSession(newSession);
      },
    );

    return () => subscription.subscription.unsubscribe();
  }, []);

  // Effect 2: fetch the role whenever the logged-in user changes.
  useEffect(() => {
    const userId = session?.user.id;
    if (!userId) return;

    let cancelled = false;
    supabase
      .from("profiles")
      .select("role")
      .eq("id", userId)
      .single()
      .then(({ data }) => {
        if (cancelled) return;
        setRole((data?.role as Role) ?? null);
        setRoleFor(userId);
      });

    return () => {
      cancelled = true;
    };
  }, [session?.user.id]);

  // Still loading if we haven't checked the session, or we have a user
  // whose role hasn't been fetched yet.
  const loading =
    sessionLoading || (session !== null && roleFor !== session.user.id);
  // Only the role fetched for the current user counts, so nobody is shown a
  // role left over from an earlier login.
  const currentRole =
    session !== null && roleFor === session.user.id ? role : null;

  // Returns an error message, or null if it worked.
  const signIn: AuthContextValue["signIn"] = async (email, password) => {
    const { data, error } = await supabase.auth.signInWithPassword({
      email,
      password,
    });
    if (error || !data.user) {
      return { error: error?.message ?? "Unable to sign in.", role: null };
    }

    // Look up the role straight away so the caller can check it.
    const { data: profile } = await supabase
      .from("profiles")
      .select("role")
      .eq("id", data.user.id)
      .single();

    return { error: null, role: (profile?.role as Role) ?? null };
  };

  const signUp: AuthContextValue["signUp"] = async (email, password, role) => {
    const { error } = await supabase.auth.signUp({
      email,
      password,
      options: { data: { role } },
    });
    return { error: error?.message ?? null };
  };

  const signOut = async () => {
    await supabase.auth.signOut();
  };

  return (
    <AuthContext.Provider
      value={{ session, role: currentRole, loading, signIn, signUp, signOut }}
    >
      {children}
    </AuthContext.Provider>
  );
}

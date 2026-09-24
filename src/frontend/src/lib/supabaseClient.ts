// Supabase client for instructor authentication only. Student submissions
// never touch Supabase Auth, they stay anonymous via session_id (see
// docs/decisions/features/instructor-authentication.md).
import { createClient } from '@supabase/supabase-js';

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

if (!supabaseUrl || !supabaseAnonKey) {
  throw new Error(
    'VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY must be set (see deployment/.env.example)',
  );
}

export const supabase = createClient(supabaseUrl, supabaseAnonKey);

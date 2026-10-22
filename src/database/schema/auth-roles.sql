-- Account roles for Supabase Auth (#165, #210, #211).
--
-- Every account is either a student or an instructor. The Welcome page sends
-- the role chosen on its Student / Instructor tab as sign-up metadata, and the
-- trigger below copies it into public.profiles. The frontend reads the role
-- from that table (src/frontend/src/auth/AuthContext.tsx), never from the
-- browser, and only the trigger can write it.
--
-- Run this once in the Supabase SQL Editor, after schema.sql. It references
-- the auth schema, so it only runs on Supabase, not on plain Postgres.
--
-- Transcribed from the SQL the team ran on the shared project, recorded in
-- evidence/screenshots/SupaBase-SQL-Progs/.

-- 1. Profiles table
create table if not exists public.profiles (
  id uuid references auth.users on delete cascade primary key,
  role text check (role in ('student', 'instructor')) not null default 'student'
);

alter table public.profiles enable row level security;

-- 2. Policies: users can only read their own row. Nobody can write from the browser.
drop policy if exists "Instructors only" on public.profiles;
drop policy if exists "Allow users to read their own profile" on public.profiles;

create policy "Allow users to read their own profile"
on public.profiles for select
using (auth.uid() = id);

-- 3. New sign-ups get a profile automatically.
--    Registering on the Instructor tab sends role = 'instructor'.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  insert into public.profiles (id, role)
  values (
    new.id,
    case when new.raw_user_meta_data ->> 'role' = 'instructor'
         then 'instructor' else 'student' end
  );
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- 4. Backfill accounts that existed before the trigger (same role rule).
insert into public.profiles (id, role)
select id,
       case when raw_user_meta_data ->> 'role' = 'instructor'
            then 'instructor' else 'student' end
from auth.users
on conflict (id) do nothing;

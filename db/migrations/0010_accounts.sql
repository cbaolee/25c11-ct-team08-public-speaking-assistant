-- 0010_accounts.sql: which project holds each user's sessions (multi-project DB, ADR-012)
-- Run: any time, on the core project only (psc-dev). Safe to run again.
-- Applied: psc-dev not yet
-- Effect: creates public.accounts (one row per user: user_id -> shard_ref), its index and RLS
--         with no policy, so only the service key can read or write it.
--         shard_ref is 'core' for the core project, else the project ref of a shard, the
--         first part of its URL (https://<ref>.supabase.co in SUPABASE_SHARDS).
--         Gives every existing profile shard_ref = 'core', so users created before this
--         migration keep their sessions and files where they are.
--         Running again adds rows only for profiles that still have none; nothing else changes.
-- The backend gives a shard to a new user the first time it needs one (src/app/db/sharding.py).
-- Deleting the auth user deletes its accounts row (on delete cascade).

create table if not exists public.accounts (
  user_id     uuid primary key references auth.users(id) on delete cascade,
  shard_ref   text not null check (shard_ref ~ '^[a-z0-9-]+$'),
  created_at  timestamptz not null default now()
);
create index if not exists accounts_shard_ref on public.accounts(shard_ref);

alter table public.accounts enable row level security;
-- No policy for anon / authenticated: the app reads accounts only with the service key.
grant select, insert, update, delete on public.accounts to service_role;

insert into public.accounts (user_id, shard_ref)
select p.id, 'core' from public.profiles p
on conflict (user_id) do nothing;

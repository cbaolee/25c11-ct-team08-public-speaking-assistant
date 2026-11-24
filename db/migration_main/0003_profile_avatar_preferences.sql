-- 0003_profile_avatar_preferences.sql: avatar and user preferences
-- Run: any time (safe to run again)
-- Where: core project only (psc-main). Never on a shard project.
-- Applied: psc-main, last run 2026-11-20
-- Effect: adds profiles.avatar_path (null) and profiles.preferences ('{}') to every existing row,
--         creates private bucket 'avatars' and its per-user policy, and function
--         merge_profile_preferences (backend only). No existing data is changed.
--         Running again changes nothing (columns and bucket already exist, policy and function
--         are recreated the same).
alter table public.profiles
  add column if not exists avatar_path text,
  add column if not exists preferences jsonb not null default '{}'::jsonb;

insert into storage.buckets (id, name, public)
values ('avatars', 'avatars', false)
on conflict (id) do nothing;

drop policy if exists own_avatar on storage.objects;
create policy own_avatar on storage.objects for all
  using (bucket_id = 'avatars' and (storage.foldername(name))[1] = auth.uid()::text)
  with check (bucket_id = 'avatars' and (storage.foldername(name))[1] = auth.uid()::text);

-- Merge the sent keys into profiles.preferences in one statement, so two saves close together
-- cannot drop each other's keys. Called by the backend (service key) only.
create or replace function public.merge_profile_preferences(p_user_id uuid, p_patch jsonb)
returns setof public.profiles
language sql
as $$
  update public.profiles
     set preferences = preferences || p_patch
   where id = p_user_id
  returning *;
$$;

revoke execute on function public.merge_profile_preferences(uuid, jsonb) from public, anon, authenticated;
grant execute on function public.merge_profile_preferences(uuid, jsonb) to service_role;

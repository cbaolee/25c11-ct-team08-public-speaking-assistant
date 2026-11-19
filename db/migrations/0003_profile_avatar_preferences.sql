-- 0003_profile_avatar_preferences.sql: avatar and user preferences
-- Run: any time (safe to run again)
-- Applied: psc-dev 2026-11-19 | psc-prod not yet
-- Effect: adds profiles.avatar_path (null) and profiles.preferences ('{}') to every existing row,
--         creates private bucket 'avatars' and its per-user policy. No existing data is changed.
--         Running again changes nothing (columns and bucket already exist, policy is recreated the same).
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

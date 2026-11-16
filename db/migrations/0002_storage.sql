-- 0002_storage.sql: private buckets with per-user folder policies

insert into storage.buckets (id, name, public)
values ('audio', 'audio', false), ('series', 'series', false), ('baselines', 'baselines', false);

create policy own_audio on storage.objects for all
  using (bucket_id = 'audio' and (storage.foldername(name))[1] = auth.uid()::text)
  with check (bucket_id = 'audio' and (storage.foldername(name))[1] = auth.uid()::text);

create policy own_series on storage.objects for all
  using (bucket_id = 'series' and (storage.foldername(name))[1] = auth.uid()::text)
  with check (bucket_id = 'series' and (storage.foldername(name))[1] = auth.uid()::text);

create policy own_baselines on storage.objects for all
  using (bucket_id = 'baselines' and (storage.foldername(name))[1] = auth.uid()::text)
  with check (bucket_id = 'baselines' and (storage.foldername(name))[1] = auth.uid()::text);
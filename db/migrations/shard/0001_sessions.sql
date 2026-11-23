-- shard/0001_sessions.sql: sessions table and session buckets of a shard project (ADR-012)
-- Run: once (running again fails: relation / bucket already exists)
-- Where: every shard project (psc-shard01 ... psc-shard09). Never on the core (psc-main):
--        the core already has public.sessions from 0001.
-- Applied: not yet
-- Effect: creates public.sessions with the same columns as the core table, buckets audio and
--         series (private). Running again fails ("relation already exists" / duplicate
--         bucket id) and changes nothing.
-- Differences from the core table: user_id, script_id and baseline_id are plain UUIDs.
--         Users, scripts and baselines live in the core project, so no foreign key can point
--         to them. Deleting an account deletes these rows from the backend (routes/auth.py).
-- RLS is on with no policy: only the backend (service key) reads or writes a shard.

create table public.sessions (
  id                    uuid primary key default gen_random_uuid(),
  user_id               uuid not null,
  script_id             uuid,
  script_snapshot       text not null,
  topic                 text,
  accent                text,
  status                text not null check (status in ('ok','insufficient_audio')),
  reason                text,
  overall               double precision,
  label                 text,
  components            jsonb,
  result                jsonb not null,
  result_schema_version text not null,
  is_compact            boolean not null default false,
  mistakes              jsonb,
  audio_path            text,
  series_path           text,
  audio_duration_s      double precision,
  stt_provider          text,
  stt_model             text,
  baseline_id           uuid,
  created_at            timestamptz not null default now()
);
create index sessions_user_created on public.sessions(user_id, created_at desc, id desc);

alter table public.sessions enable row level security;
grant select, insert, update, delete on public.sessions to service_role;

insert into storage.buckets (id, name, public)
values ('audio', 'audio', false), ('series', 'series', false);

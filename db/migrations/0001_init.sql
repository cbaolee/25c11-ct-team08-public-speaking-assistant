-- 0001_init.sql: initial schema for profiles, baselines, scripts, sessions

create table public.profiles (
  id                 uuid primary key references auth.users(id) on delete cascade,
  display_name       text check (char_length(display_name) <= 50),  -- D-05, nullable
  age                smallint check (age between 1 and 120),
  gender             text,
  target_accent      text not null,
  topics             text[] not null default '{}',
  consent_recording  boolean not null default false,
  consent_updated_at timestamptz,
  created_at         timestamptz not null default now()
);

create table public.baselines (
  id                     uuid primary key default gen_random_uuid(),
  user_id                uuid not null references public.profiles(id) on delete cascade,
  median_pause_s         double precision,
  hesitation_threshold_s double precision not null,
  median_f0_hz           double precision,
  mean_loudness_db       double precision,
  flags                  text[] not null default '{}',
  audio_path             text,                                   -- D-03: path in bucket 'baselines'
  is_current             boolean not null default true,
  recorded_at            timestamptz not null default now()
);
create unique index baselines_one_current on public.baselines(user_id) where is_current;

create table public.scripts (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null references public.profiles(id) on delete cascade,
  title         text not null,
  topic         text,
  category      text,
  source        text not null check (source in ('generated_template','generated_llm','written')),
  duration_min  smallint check (duration_min in (5,10,15,20)),
  body          text not null,
  word_count    integer not null,
  citations     jsonb not null default '[]',
  template_id   text,
  models_used   text[] not null default '{}',                    -- matches GeneratedScript.models_used
  content_hash  text not null,
  created_at    timestamptz not null default now()
);
create index scripts_user_created on public.scripts(user_id, created_at desc, id desc);

create table public.sessions (
  id                    uuid primary key default gen_random_uuid(),
  user_id               uuid not null references public.profiles(id) on delete cascade,
  script_id             uuid references public.scripts(id) on delete set null,  -- null until Script team links
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
  is_compact            boolean not null default false,          -- D-16
  mistakes              jsonb,                                   -- D-16, filled when compacted
  audio_path            text,
  series_path           text,
  audio_duration_s      double precision,
  stt_provider          text,
  stt_model             text,
  baseline_id           uuid references public.baselines(id) on delete set null,
  created_at            timestamptz not null default now()
);
create index sessions_user_created on public.sessions(user_id, created_at desc, id desc);

alter table public.profiles  enable row level security;
alter table public.baselines enable row level security;
alter table public.scripts   enable row level security;
alter table public.sessions  enable row level security;

create policy own_profile  on public.profiles  for all using (auth.uid() = id)      with check (auth.uid() = id);
create policy own_baseline on public.baselines for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy own_scripts  on public.scripts   for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy own_sessions on public.sessions  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- table privileges: RLS only filters rows, roles still need GRANT to touch the tables
grant select, insert, update, delete
  on public.profiles, public.baselines, public.scripts, public.sessions
  to authenticated, service_role;
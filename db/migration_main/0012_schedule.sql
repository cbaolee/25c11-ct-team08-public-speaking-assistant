-- 0012_schedule.sql: real Schedule tables on core (ADR-016)
-- Run: required, once, before the /api/schedule routes are used (after 0001).
--      Safe to run again: tables and indexes are skipped when they exist and the function
--      is replaced. Running again does not change an existing table, so a later column or
--      check change needs a new migration with alter table.
-- Where: core project only (psc-main). Never on a shard project.
-- Applied: psc-main 2026-11-28
-- Effect: creates public.schedule_events, public.schedule_checkins, public.schedule_reminders
--         with RLS on and no policy, and public.split_schedule_event(), which only the service
--         key can run. Running again replaces the function; no existing rows change.
-- Time: start_date, start_time, end_until and occ_day are local wall time in the event's
--         timezone (IANA name). Every timestamptz column is UTC.
-- How: run this file in the Supabase SQL Editor of psc-main. The app never runs it.
-- Check with: select count(*) from public.schedule_events;
--         select * from public.schedule_reminders order by attempted_at desc limit 20;
-- Remove: drop function if exists public.split_schedule_event(uuid, uuid, date, jsonb);
--         drop table if exists public.schedule_reminders, public.schedule_checkins,
--         public.schedule_events;

create table if not exists public.schedule_events (
  id                 uuid primary key default gen_random_uuid(),
  user_id            uuid not null references auth.users(id) on delete cascade,
  start_date         date not null,
  all_day            boolean not null,
  start_time         time null,
  timezone           text not null check (char_length(timezone) between 1 and 64),
  duration_min       smallint null check (duration_min in (5, 10, 15, 20)),
  category           text not null check (category in (
                       'any', 'cinematography', 'gender_studies', 'information_technology',
                       'learning_experiences', 'sports', 'wildlife')),
  color              text not null check (color in (
                       'lime', 'blue', 'green', 'amber', 'brown', 'red', 'slate', 'gray', 'sky')),
  script_kind        text not null check (script_kind in ('free', 'saved', 'ai')),
  -- No foreign key: deleting a saved script must not delete or block the event (ADR-016).
  script_id          uuid null,
  script_title       text null,
  note               text not null default '' check (char_length(note) <= 200),
  repeat_kind        text not null check (repeat_kind in ('none', 'daily', 'weekly', 'custom')),
  repeat_days        smallint[] not null default '{}'
                       check (repeat_days <@ array[1, 2, 3, 4, 5, 6, 7]::smallint[]),
  end_kind           text not null check (end_kind in ('never', 'until', 'count')),
  end_until          date null,
  end_count          smallint null check (end_count between 1 and 99),
  schedule_set_at    timestamptz not null default now(),
  details_edited_at  timestamptz null,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now(),
  -- The checks below follow isValidEvent and normalizeRecurrence in schedule_store.js.
  constraint schedule_events_time check (
    (all_day and start_time is null) or (not all_day and start_time is not null)),
  constraint schedule_events_saved_script check (
    script_kind <> 'saved' or (script_id is not null and script_title is not null)),
  constraint schedule_events_ai_script check (
    script_kind <> 'ai' or (duration_min is not null and category <> 'any')),
  constraint schedule_events_repeat_days check (
    (repeat_kind = 'custom' and cardinality(repeat_days) > 0)
    or (repeat_kind <> 'custom' and cardinality(repeat_days) = 0)),
  constraint schedule_events_no_repeat_end check (repeat_kind <> 'none' or end_kind = 'never'),
  constraint schedule_events_end check (
    (end_kind = 'never' and end_until is null and end_count is null)
    or (end_kind = 'until' and end_until is not null and end_count is null
        and end_until >= start_date)
    or (end_kind = 'count' and end_count is not null and end_until is null))
);
create index if not exists schedule_events_user_id on public.schedule_events(user_id);

create table if not exists public.schedule_checkins (
  event_id    uuid not null references public.schedule_events(id) on delete cascade,
  occ_day     date not null,
  user_id     uuid not null references auth.users(id) on delete cascade,
  checkin_at  timestamptz not null,
  done_at     timestamptz null check (done_at >= checkin_at),
  -- No foreign key: the session may live on a shard project (ADR-012).
  session_id  uuid null,
  primary key (event_id, occ_day)
);
create index if not exists schedule_checkins_user_id on public.schedule_checkins(user_id);

create table if not exists public.schedule_reminders (
  event_id      uuid not null references public.schedule_events(id) on delete cascade,
  occ_day       date not null,
  status        text not null check (status in ('sent', 'failed', 'skipped')),
  attempted_at  timestamptz not null,
  sent_at       timestamptz null,
  primary key (event_id, occ_day)
);

alter table public.schedule_events enable row level security;
alter table public.schedule_checkins enable row level security;
alter table public.schedule_reminders enable row level security;
-- No policy for anon / authenticated: only the service key reads or writes them.
grant select, insert, update, delete on public.schedule_events to service_role;
grant select, insert, update, delete on public.schedule_checkins to service_role;
grant select, insert, update, delete on public.schedule_reminders to service_role;

-- "This and following": end the old event on p_end_until and, when p_new_event is given, add
-- the new event, in one transaction. Two separate writes could lose a session or double it
-- (and send two emails) if the second write failed. Returns no row when the user does not own
-- the event. p_new_event holds the event columns as JSON, without id and user_id.
create or replace function public.split_schedule_event(
  p_user_id uuid,
  p_event_id uuid,
  p_end_until date,
  p_new_event jsonb
)
returns setof public.schedule_events
language plpgsql
security invoker
as $$
declare
  n public.schedule_events;
begin
  return query
    update public.schedule_events
       set end_kind = 'until', end_until = p_end_until, end_count = null, updated_at = now()
     where id = p_event_id and user_id = p_user_id
    returning *;
  if not found or p_new_event is null then
    return;
  end if;
  n := jsonb_populate_record(null::public.schedule_events, p_new_event);
  return query
    insert into public.schedule_events (
      user_id, start_date, all_day, start_time, timezone, duration_min, category, color,
      script_kind, script_id, script_title, note, repeat_kind, repeat_days, end_kind,
      end_until, end_count, schedule_set_at, details_edited_at)
    values (
      p_user_id, n.start_date, n.all_day, n.start_time, n.timezone, n.duration_min,
      n.category, n.color, n.script_kind, n.script_id, n.script_title, coalesce(n.note, ''),
      n.repeat_kind, coalesce(n.repeat_days, '{}'), n.end_kind, n.end_until, n.end_count,
      coalesce(n.schedule_set_at, now()), n.details_edited_at)
    returning *;
end
$$;

revoke execute on function public.split_schedule_event(uuid, uuid, date, jsonb)
  from public, anon, authenticated;
grant execute on function public.split_schedule_event(uuid, uuid, date, jsonb) to service_role;

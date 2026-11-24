-- 0011_auth_rate_limits.sql: attempt counters for the account endpoints (ADR-011)
-- Run: required, any time (after 0001; safe to run again). Needs the pg_cron extension.
--      Required because the backend calls hit_rate_limit() on every code, reset and re-auth
--      request. Until it has run, the backend lets every request through (it fails open and
--      logs a warning), so only Supabase Auth's own limits apply.
-- Where: core project only (psc-main). Never on a shard project.
-- Applied: not yet
-- Effect: creates public.auth_rate_limits (one row per bucket and key) with RLS on and no
--         policy, and public.hit_rate_limit(), which only the service key can run.
--         Schedules the pg_cron job purge_auth_rate_limits (every hour, UTC) that deletes rows
--         whose window started more than one day ago. Running again replaces the function and
--         the job; no existing rows change.
-- Keys: the backend sends a SHA-256 hash of the email or of the user id, never the email.
-- Buckets (src/app/routes/auth.py): signup_resend, signup_verify, reset_send, reset_verify,
--         reauth. Limits come from app_constants.toml [auth].
-- Window: fixed, not sliding. A window starts at the first hit; once window_s seconds have
--         passed, the next hit starts a new window. A user can therefore get up to 2 x max
--         hits around a window edge, which is acceptable for 5 tries per 10 minutes.
-- How: on Supabase, enable pg_cron in Dashboard -> Database -> Extensions, then run this file
--         in the SQL Editor. The app never runs it.
-- Check with: select * from public.auth_rate_limits order by window_start desc limit 20;
--         select * from cron.job where jobname = 'purge_auth_rate_limits';
-- Remove: select cron.unschedule('purge_auth_rate_limits');

create extension if not exists pg_cron;

create table if not exists public.auth_rate_limits (
  bucket        text not null check (bucket ~ '^[a-z_]{1,40}$'),
  key           text not null check (key ~ '^[0-9a-f]{64}$'),
  window_start  timestamptz not null default now(),
  hits          integer not null default 1 check (hits >= 1),
  primary key (bucket, key)
);
create index if not exists auth_rate_limits_window_start on public.auth_rate_limits(window_start);

alter table public.auth_rate_limits enable row level security;
-- No policy for anon / authenticated: only the service key reads or writes it.
grant select, insert, update, delete on public.auth_rate_limits to service_role;

-- Counts one hit and says whether it is allowed. One statement, so two requests at the same
-- moment cannot both slip under the limit: the row lock of `on conflict do update` orders them.
create or replace function public.hit_rate_limit(
  p_bucket text,
  p_key text,
  p_max integer,
  p_window_s integer
)
returns boolean
language sql
security invoker
as $$
  insert into public.auth_rate_limits as r (bucket, key, window_start, hits)
  values (p_bucket, p_key, now(), 1)
  on conflict (bucket, key) do update
     set window_start = case
           when now() - r.window_start >= make_interval(secs => p_window_s) then now()
           else r.window_start
         end,
         hits = case
           when now() - r.window_start >= make_interval(secs => p_window_s) then 1
           else r.hits + 1
         end
  returning hits <= p_max;
$$;

revoke execute on function public.hit_rate_limit(text, text, integer, integer)
  from public, anon, authenticated;
grant execute on function public.hit_rate_limit(text, text, integer, integer) to service_role;

do $purge$
begin
    if exists (select 1 from cron.job where jobname = 'purge_auth_rate_limits') then
        perform cron.unschedule('purge_auth_rate_limits');
    end if;
end
$purge$;

-- The job runs as postgres and bypasses RLS intentionally, to clean rows of all users.
select cron.schedule('purge_auth_rate_limits', '17 * * * *', $$
    delete from public.auth_rate_limits where window_start < now() - interval '1 day'
$$);

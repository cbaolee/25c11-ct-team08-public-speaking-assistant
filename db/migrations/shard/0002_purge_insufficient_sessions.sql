-- shard/0002_purge_insufficient_sessions.sql: same job as 0005, on every shard project (ADR-012)
-- Run: required, any time (safe to run again). Needs the pg_cron extension.
--      Required because the UI tells users insufficient sessions are deleted after 7 days.
-- Where: every shard project (psc-shard01 ... psc-shard09), after shard/0001.
-- Applied: not yet
-- Effect: purges insufficient-audio sessions after their retention period.
-- Source: app_constants.toml [retention] insufficient_days. If it changes, update
-- this file and the fallback in src/web/static/js/state.js as well.
-- On Supabase: enable pg_cron in Dashboard -> Database -> Extensions, then run
-- this file in the SQL Editor. The schedule uses UTC.
-- The job runs as postgres and bypasses RLS intentionally to delete sessions for all users.
-- pg_cron >= 1.4 updates schedules with the same name automatically; the DO block
-- keeps reruns safe on older versions; check with select * from cron.job;
--        select * from cron.job_run_details order by start_time desc limit 5;
-- Remove: select cron.unschedule('purge_insufficient_sessions');

create extension if not exists pg_cron;

do $purge$
begin
    if exists (select 1 from cron.job where jobname = 'purge_insufficient_sessions') then
        perform cron.unschedule('purge_insufficient_sessions');
    end if;
end
$purge$;

select cron.schedule('purge_insufficient_sessions', '17 3 * * *', $$
    delete from public.sessions
    where status = 'insufficient_audio' and created_at < now() - interval '7 days'
$$);

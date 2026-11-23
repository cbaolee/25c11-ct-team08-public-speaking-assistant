-- 0006_purge_unconfirmed_accounts.sql: delete accounts that never confirmed their email (ADR-011)
-- Run: optional, any time (after 0001). Needs the pg_cron extension.
-- Applied: psc-dev done | psc-prod not yet
-- Effect: every 15 minutes (UTC), deletes auth.users rows whose email is still unconfirmed
--         and whose last code was sent more than 60 minutes ago. `on delete cascade` then
--         removes their profiles row (created at sign up, ADR-010 D4) and any other rows.
--         Running again replaces the job with the same schedule; no other data changes.
-- Source: app_constants.toml [auth] unconfirmed_ttl_min (60). If it changes, update the
--         interval below and the fallback in src/web/static/js/state.js as well
--         (tests/db/test_purge_sql.py checks they match).
-- How: on Supabase, enable pg_cron in Dashboard -> Database -> Extensions, then run this
--         file in the SQL Editor. The app never runs it.
-- Deadline: counts from the last code sent: confirmation_sent_at, falling back to created_at.
--         ASSUMPTION, NOT CHECKED on a real Supabase project: GoTrue updates
--         confirmation_sent_at when the code is resent (POST /api/auth/resend-otp), so Resend
--         moves the deadline. If it does not, the deadline counts from the first code.
-- Files first: Supabase does not allow deleting storage.objects with SQL, so an account that
--         has any object in Storage (first folder = user id) is skipped. Unconfirmed accounts
--         cannot log in, so they normally have no files.
-- The job runs as postgres and bypasses RLS intentionally, to delete accounts of all users.
-- pg_cron >= 1.4 updates schedules with the same name automatically; the DO block keeps
-- reruns safe on older versions. Check with: select * from cron.job;
--        select * from cron.job_run_details order by start_time desc limit 5;
-- Remove: select cron.unschedule('purge_unconfirmed_accounts');

create extension if not exists pg_cron;

do $purge$
begin
    if exists (select 1 from cron.job where jobname = 'purge_unconfirmed_accounts') then
        perform cron.unschedule('purge_unconfirmed_accounts');
    end if;
end
$purge$;

select cron.schedule('purge_unconfirmed_accounts', '*/15 * * * *', $$
    delete from auth.users u
    where u.email_confirmed_at is null
      and coalesce(u.confirmation_sent_at, u.created_at) < now() - interval '60 minutes'
      and not exists (
          select 1 from storage.objects o
          where (storage.foldername(o.name))[1] = u.id::text
      )
$$);

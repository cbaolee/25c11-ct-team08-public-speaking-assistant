-- 0013_schedule_reminder_cron.sql: call the protected Schedule reminder endpoint (ADR-016)
-- Run: required, after 0012 and after the app endpoint is deployed. Safe to run again.
--      Needs the pg_cron and pg_net extensions.
-- Where: core project only (psc-main). Never on a shard project.
-- Applied: not yet run on Supabase
-- Effect: creates or replaces the schedule_reminders cron job, which calls the app every
--         five minutes. The app URL and cron secret are read from Supabase Vault at run time;
--         neither a URL nor a secret is stored in this file or in cron.job.
-- Vault: create vault secrets named schedule_app_url and schedule_cron_secret. The app URL
--         is the deployed origin without a trailing slash, for example https://example.com.
-- How: enable pg_cron and pg_net in the Supabase Dashboard, create the two Vault secrets,
--       set SCHEDULE_CRON_SECRET on the app to the same value, then run this file in the SQL
--       Editor of psc-main. The app never runs this migration.
-- Check with: select * from cron.job where jobname = 'schedule_reminders';
--         select * from cron.job_run_details order by start_time desc limit 20;
--         select status, content from net._http_response order by created desc limit 20;
-- Remove: select cron.unschedule('schedule_reminders');

create extension if not exists pg_cron;
create extension if not exists pg_net;

do $schedule_reminders$
begin
  if exists (
    select 1
    from cron.job
    where jobname = 'schedule_reminders'
  ) then
    perform cron.unschedule('schedule_reminders');
  end if;
end
$schedule_reminders$;

select cron.schedule(
  'schedule_reminders',
  '*/5 * * * *',
  $schedule_job$
    select net.http_post(
      url := concat(
        rtrim((
          select decrypted_secret
          from vault.decrypted_secrets
          where name = 'schedule_app_url'
          limit 1
        ), '/'),
        '/internal/schedule/reminders/run'
      ),
      headers := jsonb_build_object(
        'Content-Type', 'application/json',
        'X-Cron-Secret', (
          select decrypted_secret
          from vault.decrypted_secrets
          where name = 'schedule_cron_secret'
          limit 1
        )
      ),
      body := '{}'::jsonb,
      timeout_milliseconds := 30000
    );
  $schedule_job$
);

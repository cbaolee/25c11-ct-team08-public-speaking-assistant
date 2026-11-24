-- 0008_replace_baseline_delete_old.sql: keep exactly one baseline row per user
-- Run: any time (safe to run again)
-- Where: core project only (psc-main). Never on a shard project.
-- Applied: psc-main, last run 2026-11-23
-- Effect: replaces public.replace_current_baseline with the same parameters.
--         In one transaction the function locks and copies the old baseline, switches it off,
--         inserts the new baseline, then deletes every other baseline row of that user.
--         A failed insert rolls back, so the old baseline stays. The old row is returned so
--         the backend can delete its audio file. sessions.baseline_id of the deleted rows
--         becomes null (on delete set null). It changes no existing data when run.

create or replace function public.replace_current_baseline(
  p_user_id uuid,
  p_id uuid,
  p_hesitation_threshold_s double precision,
  p_median_pause_s double precision default null,
  p_median_f0_hz double precision default null,
  p_mean_loudness_db double precision default null,
  p_flags text[] default '{}',
  p_audio_path text default null
)
returns jsonb
language plpgsql
security invoker
as $$
declare
  previous_row public.baselines%rowtype;
  new_row public.baselines%rowtype;
begin
  -- Lock and copy the old baseline
  select *
    into previous_row
    from public.baselines
   where user_id = p_user_id
     and is_current = true
   for update;

  -- Needed because baselines_one_current allows one current row per user
  update public.baselines
     set is_current = false
   where user_id = p_user_id
     and is_current = true;

  insert into public.baselines (
    id,
    user_id,
    median_pause_s,
    hesitation_threshold_s,
    median_f0_hz,
    mean_loudness_db,
    flags,
    audio_path,
    is_current
  )
  values (
    p_id,
    p_user_id,
    p_median_pause_s,
    p_hesitation_threshold_s,
    p_median_f0_hz,
    p_mean_loudness_db,
    coalesce(p_flags, '{}'::text[]),
    p_audio_path,
    true
  )
  returning * into new_row;

  -- The new row is saved, now drop the old ones
  delete from public.baselines
   where user_id = p_user_id
     and id <> new_row.id;

  return jsonb_build_object(
    'new_row', to_jsonb(new_row),
    'previous_row', case
      when previous_row.id is null then null
      else to_jsonb(previous_row)
    end
  );
end;
$$;

revoke execute on function public.replace_current_baseline(
  uuid, uuid, double precision, double precision, double precision,
  double precision, text[], text
) from public, anon, authenticated;
grant execute on function public.replace_current_baseline(
  uuid, uuid, double precision, double precision, double precision,
  double precision, text[], text
) to service_role;

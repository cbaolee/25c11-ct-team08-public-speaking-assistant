-- 0004_replace_baseline_fn.sql: replace the current baseline in one transaction
-- Run: any time
-- Applied: psc-dev 2026-11-20
-- Effect: creates or replaces the public.replace_current_baseline SQL function.
--         The function locks and switches off the old baseline, inserts the new baseline,
--         and returns both rows in one transaction. Callable by the backend (service_role) only.
--         It changes no existing data.
--         Running again replaces the function with the same implementation.

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
  select *
    into previous_row
    from public.baselines
   where user_id = p_user_id
     and is_current = true
   for update;

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

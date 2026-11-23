-- 0006_scripts_title_body_only.sql: saved scripts keep only title and body
-- Run: once (running again fails: the dropped columns no longer exist)
-- Where: core project only (psc-main). Never on a shard project.
-- Applied: psc-main 2026-11-23
-- Effect: reduce scripts to title/body plus technical fields, remove duplicate rows and
--         names, and enforce per-user title/body uniqueness.

-- Keep the oldest row when content_hash duplicates exist.
delete from public.scripts duplicate
where duplicate.id in (
  select id
  from (
    select id,
           row_number() over (
             partition by user_id, content_hash
             order by created_at, id
           ) as rn
    from public.scripts
  ) ranked
  where rn > 1
);

-- Strip existing names, then rename newer case-insensitive duplicates.
update public.scripts
set title = btrim(title);

with ranked as (
  select id,
         title,
         row_number() over (
           partition by user_id, lower(btrim(title))
           order by created_at, id
         ) as rn
  from public.scripts
),
renamed as (
  select id, title || ' (' || rn || ')' as new_title
  from ranked
  where rn > 1
)
update public.scripts as script
set title = renamed.new_title
from renamed
where script.id = renamed.id;

alter table public.scripts
  drop column topic,
  drop column category,
  drop column source,
  drop column duration_min,
  drop column word_count,
  drop column citations,
  drop column template_id,
  drop column models_used;

create unique index scripts_user_title_unique
  on public.scripts(user_id, lower(title));
create unique index scripts_user_hash_unique
  on public.scripts(user_id, content_hash);

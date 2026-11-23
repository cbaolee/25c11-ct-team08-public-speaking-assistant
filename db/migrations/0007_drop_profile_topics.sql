-- Run once. Effect: remove the per-user topic list from profiles.
-- Template categories (Script Studio, /api/topics) are not stored here and stay.

alter table public.profiles drop column if exists topics;

-- 0007_drop_profile_topics.sql: remove the per-user topic list from profiles
-- Run: any time (safe to run again: drop column if exists)
-- Where: core project only (psc-main). Never on a shard project.
-- Applied: psc-main, last run 2026-11-23
-- Effect: drops profiles.topics.
-- Template categories (Script Studio, /api/topics) are not stored here and stay.

alter table public.profiles drop column if exists topics;

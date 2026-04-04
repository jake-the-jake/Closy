-- Lightweight outfit suggestion feedback for signed-in users (Closy suggest-outfit flow).
-- Local: app persists the same shape in AsyncStorage; cloud row when Supabase + session available.
-- Future: recommenders can down-rank item pairs / templates with repeated negative_not_my_style, etc.

create table if not exists public.outfit_suggestion_feedback (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  occasion text not null,
  feedback_type text not null,
  clothing_item_ids text[] not null default '{}',
  suggestion_key text not null,
  score_snapshot double precision,
  created_at timestamptz not null default now(),
  constraint outfit_suggestion_feedback_type_chk check (
    feedback_type in (
      'positive_like',
      'negative_not_my_style',
      'regenerate',
      'saved'
    )
  )
);

create index if not exists outfit_suggestion_feedback_user_created_idx
  on public.outfit_suggestion_feedback (user_id, created_at desc);

comment on table public.outfit_suggestion_feedback is
  'User feedback on generated outfit suggestions; used for future ranking — no ML in v1.';

alter table public.outfit_suggestion_feedback enable row level security;

drop policy if exists "Users read own outfit suggestion feedback"
  on public.outfit_suggestion_feedback;
create policy "Users read own outfit suggestion feedback"
  on public.outfit_suggestion_feedback for select
  to authenticated
  using (auth.uid() = user_id);

drop policy if exists "Users insert own outfit suggestion feedback"
  on public.outfit_suggestion_feedback;
create policy "Users insert own outfit suggestion feedback"
  on public.outfit_suggestion_feedback for insert
  to authenticated
  with check (auth.uid() = user_id);

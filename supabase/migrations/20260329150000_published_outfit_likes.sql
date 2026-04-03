-- One like per user per published outfit. Counts are readable for Discover; writes are owner-only.

create table if not exists public.published_outfit_likes (
  published_outfit_id uuid not null references public.published_outfits (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (published_outfit_id, user_id)
);

create index if not exists published_outfit_likes_user_idx
  on public.published_outfit_likes (user_id);

alter table public.published_outfit_likes enable row level security;

drop policy if exists "Published outfit likes are world readable" on public.published_outfit_likes;
create policy "Published outfit likes are world readable"
  on public.published_outfit_likes for select
  using (true);

drop policy if exists "Users insert own published outfit like" on public.published_outfit_likes;
create policy "Users insert own published outfit like"
  on public.published_outfit_likes for insert
  to authenticated
  with check (auth.uid() = user_id);

drop policy if exists "Users delete own published outfit like" on public.published_outfit_likes;
create policy "Users delete own published outfit like"
  on public.published_outfit_likes for delete
  to authenticated
  using (auth.uid() = user_id);

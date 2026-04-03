-- Creator follow edges: public read for counts/state; only the follower can insert/delete their row.

create table if not exists public.user_follows (
  follower_id uuid not null references auth.users (id) on delete cascade,
  followed_id uuid not null references auth.users (id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (follower_id, followed_id),
  constraint user_follows_no_self check (follower_id <> followed_id)
);

create index if not exists user_follows_followed_idx
  on public.user_follows (followed_id);

create index if not exists user_follows_follower_idx
  on public.user_follows (follower_id);

comment on table public.user_follows is
  'Directed follow: follower_id follows followed_id. No self-follow; PK prevents duplicates.';

alter table public.user_follows enable row level security;

drop policy if exists "User follows are world readable" on public.user_follows;
create policy "User follows are world readable"
  on public.user_follows for select
  using (true);

drop policy if exists "Users insert own follow rows" on public.user_follows;
create policy "Users insert own follow rows"
  on public.user_follows for insert
  to authenticated
  with check (auth.uid() = follower_id);

drop policy if exists "Users delete own follow rows" on public.user_follows;
create policy "Users delete own follow rows"
  on public.user_follows for delete
  to authenticated
  using (auth.uid() = follower_id);

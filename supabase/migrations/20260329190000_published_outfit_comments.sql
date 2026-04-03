-- Flat comments on Discover posts (no threads in v1). Removed when post is deleted.

create table if not exists public.published_outfit_comments (
  id uuid primary key default gen_random_uuid(),
  published_outfit_id uuid not null references public.published_outfits (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  body text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz
);

comment on table public.published_outfit_comments is
  'World-readable; authors insert/delete own rows only; body trimmed in app (max length enforced in API layer later if needed).';

comment on column public.published_outfit_comments.updated_at is
  'Reserved for future edit support; unused in v1.';

create index if not exists published_outfit_comments_post_created_idx
  on public.published_outfit_comments (published_outfit_id, created_at asc);

alter table public.published_outfit_comments enable row level security;

drop policy if exists "Published outfit comments are world readable" on public.published_outfit_comments;
create policy "Published outfit comments are world readable"
  on public.published_outfit_comments for select
  using (true);

drop policy if exists "Signed-in users insert comments on existing posts" on public.published_outfit_comments;
create policy "Signed-in users insert comments on existing posts"
  on public.published_outfit_comments for insert
  to authenticated
  with check (
    auth.uid() = user_id
    and exists (
      select 1
      from public.published_outfits po
      where po.id = published_outfit_id
    )
  );

drop policy if exists "Users delete own published outfit comments" on public.published_outfit_comments;
create policy "Users delete own published outfit comments"
  on public.published_outfit_comments for delete
  to authenticated
  using (auth.uid() = user_id);

-- Per-user activity feed (in-app notifications v1). Rows are written by triggers; recipients read via RLS only.

create table if not exists public.user_activity (
  id uuid primary key default gen_random_uuid(),
  recipient_user_id uuid not null references auth.users (id) on delete cascade,
  actor_user_id uuid not null references auth.users (id) on delete cascade,
  activity_type text not null,
  published_outfit_id uuid references public.published_outfits (id) on delete cascade,
  comment_id uuid references public.published_outfit_comments (id) on delete set null,
  created_at timestamptz not null default now(),
  constraint user_activity_type_chk check (activity_type in ('follow', 'like', 'comment')),
  constraint user_activity_follow_no_post check (
    activity_type <> 'follow' or published_outfit_id is null
  ),
  constraint user_activity_like_has_post check (
    activity_type <> 'like' or published_outfit_id is not null
  ),
  constraint user_activity_comment_has_post check (
    activity_type <> 'comment' or published_outfit_id is not null
  )
);

create index if not exists user_activity_recipient_created_idx
  on public.user_activity (recipient_user_id, created_at desc);

comment on table public.user_activity is
  'Social events visible to recipient_user_id: follow, like on their post, or comment on their post.';

alter table public.user_activity enable row level security;

drop policy if exists "Users read own activity feed" on public.user_activity;
create policy "Users read own activity feed"
  on public.user_activity for select
  to authenticated
  using (auth.uid() = recipient_user_id);

create or replace function public.user_activity_on_follow()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.user_activity (
    recipient_user_id,
    actor_user_id,
    activity_type,
    published_outfit_id,
    comment_id
  )
  values (new.followed_id, new.follower_id, 'follow', null, null);
  return new;
end;
$$;

drop trigger if exists user_activity_after_insert_follow on public.user_follows;
create trigger user_activity_after_insert_follow
  after insert on public.user_follows
  for each row
  execute function public.user_activity_on_follow();

create or replace function public.user_activity_on_like()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  author_id uuid;
begin
  select po.user_id into author_id
  from public.published_outfits po
  where po.id = new.published_outfit_id;

  if author_id is null or author_id = new.user_id then
    return new;
  end if;

  insert into public.user_activity (
    recipient_user_id,
    actor_user_id,
    activity_type,
    published_outfit_id,
    comment_id
  )
  values (author_id, new.user_id, 'like', new.published_outfit_id, null);
  return new;
end;
$$;

drop trigger if exists user_activity_after_insert_like on public.published_outfit_likes;
create trigger user_activity_after_insert_like
  after insert on public.published_outfit_likes
  for each row
  execute function public.user_activity_on_like();

create or replace function public.user_activity_on_comment()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  author_id uuid;
begin
  select po.user_id into author_id
  from public.published_outfits po
  where po.id = new.published_outfit_id;

  if author_id is null or author_id = new.user_id then
    return new;
  end if;

  insert into public.user_activity (
    recipient_user_id,
    actor_user_id,
    activity_type,
    published_outfit_id,
    comment_id
  )
  values (author_id, new.user_id, 'comment', new.published_outfit_id, new.id);
  return new;
end;
$$;

drop trigger if exists user_activity_after_insert_comment on public.published_outfit_comments;
create trigger user_activity_after_insert_comment
  after insert on public.published_outfit_comments
  for each row
  execute function public.user_activity_on_comment();

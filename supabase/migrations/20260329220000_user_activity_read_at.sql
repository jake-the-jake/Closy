-- Read/unread for user_activity. Recipients may update read_at only; RLS limits updates to own rows.

alter table public.user_activity
  add column if not exists read_at timestamptz;

comment on column public.user_activity.read_at is
  'Set when the recipient marked the row read; null = unread.';

-- Existing rows: treat as already seen (avoid a one-time mass "unread" after deploy).
update public.user_activity
set read_at = coalesce(read_at, created_at)
where read_at is null;

create index if not exists user_activity_recipient_unread_idx
  on public.user_activity (recipient_user_id)
  where read_at is null;

create or replace function public.user_activity_restrict_updates()
returns trigger
language plpgsql
as $$
begin
  if new.id is distinct from old.id
     or new.recipient_user_id is distinct from old.recipient_user_id
     or new.actor_user_id is distinct from old.actor_user_id
     or new.activity_type is distinct from old.activity_type
     or new.published_outfit_id is distinct from old.published_outfit_id
     or new.comment_id is distinct from old.comment_id
     or new.created_at is distinct from old.created_at
  then
    raise exception 'user_activity: only read_at may be updated';
  end if;
  if new.read_at is null then
    raise exception 'user_activity: read_at cannot be cleared';
  end if;
  return new;
end;
$$;

drop trigger if exists user_activity_restrict_updates_trigger on public.user_activity;
create trigger user_activity_restrict_updates_trigger
  before update on public.user_activity
  for each row
  execute function public.user_activity_restrict_updates();

drop policy if exists "Users update own activity read state" on public.user_activity;
create policy "Users update own activity read state"
  on public.user_activity for update
  to authenticated
  using (auth.uid() = recipient_user_id)
  with check (auth.uid() = recipient_user_id);

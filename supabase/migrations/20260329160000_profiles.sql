-- Public user profiles for Discover author identity (display name + optional avatar URL).
-- Anyone with the anon key may read; users may insert/update only their own row.

create table if not exists public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  display_name text not null default '',
  avatar_url text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on table public.profiles is
  'App-level profile; public read for Discover; authors update their own row.';

create or replace function public.touch_profiles_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

drop trigger if exists profiles_touch_updated_at on public.profiles;
create trigger profiles_touch_updated_at
  before update on public.profiles
  for each row
  execute function public.touch_profiles_updated_at();

alter table public.profiles enable row level security;

drop policy if exists "Profiles are world readable" on public.profiles;
create policy "Profiles are world readable"
  on public.profiles for select
  using (true);

drop policy if exists "Users insert own profile" on public.profiles;
create policy "Users insert own profile"
  on public.profiles for insert
  to authenticated
  with check (auth.uid() = id);

drop policy if exists "Users update own profile" on public.profiles;
create policy "Users update own profile"
  on public.profiles for update
  to authenticated
  using (auth.uid() = id)
  with check (auth.uid() = id);

-- New auth users get a profile row (display name / avatar from raw metadata when present).
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, display_name, avatar_url)
  values (
    new.id,
    coalesce(new.raw_user_meta_data->>'display_name', ''),
    nullif(trim(coalesce(new.raw_user_meta_data->>'avatar_url', '')), '')
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row
  execute function public.handle_new_user();

-- Existing users (created before this migration): one row per auth user.
insert into public.profiles (id, display_name, avatar_url)
select
  u.id,
  coalesce(u.raw_user_meta_data->>'display_name', ''),
  nullif(trim(coalesce(u.raw_user_meta_data->>'avatar_url', '')), '')
from auth.users u
where not exists (select 1 from public.profiles p where p.id = u.id)
on conflict (id) do nothing;

-- Run in Supabase SQL Editor or via Supabase CLI. Requires auth.users (built-in).
-- After applying, enable Email provider under Authentication → Providers if needed.

create table if not exists public.wardrobe_items (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  name text not null,
  category text not null,
  colour text not null,
  brand text not null default '',
  image_url text not null default '',
  tags text[] not null default '{}',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists wardrobe_items_user_id_idx
  on public.wardrobe_items (user_id);

create index if not exists wardrobe_items_user_created_idx
  on public.wardrobe_items (user_id, created_at desc);

alter table public.wardrobe_items enable row level security;

drop policy if exists "Users read own wardrobe items" on public.wardrobe_items;
create policy "Users read own wardrobe items"
  on public.wardrobe_items for select
  using (auth.uid() = user_id);

drop policy if exists "Users insert own wardrobe items" on public.wardrobe_items;
create policy "Users insert own wardrobe items"
  on public.wardrobe_items for insert
  with check (auth.uid() = user_id);

drop policy if exists "Users update own wardrobe items" on public.wardrobe_items;
create policy "Users update own wardrobe items"
  on public.wardrobe_items for update
  using (auth.uid() = user_id);

drop policy if exists "Users delete own wardrobe items" on public.wardrobe_items;
create policy "Users delete own wardrobe items"
  on public.wardrobe_items for delete
  using (auth.uid() = user_id);

-- Outfits per user. `clothing_item_ids` stores wardrobe `ClothingItem.id` strings (UUID or legacy local ids).

create table if not exists public.outfits (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  name text not null,
  clothing_item_ids text[] not null default '{}',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists outfits_user_id_idx
  on public.outfits (user_id);

create index if not exists outfits_user_created_idx
  on public.outfits (user_id, created_at desc);

alter table public.outfits enable row level security;

drop policy if exists "Users read own outfits" on public.outfits;
create policy "Users read own outfits"
  on public.outfits for select
  using (auth.uid() = user_id);

drop policy if exists "Users insert own outfits" on public.outfits;
create policy "Users insert own outfits"
  on public.outfits for insert
  with check (auth.uid() = user_id);

drop policy if exists "Users update own outfits" on public.outfits;
create policy "Users update own outfits"
  on public.outfits for update
  using (auth.uid() = user_id);

drop policy if exists "Users delete own outfits" on public.outfits;
create policy "Users delete own outfits"
  on public.outfits for delete
  using (auth.uid() = user_id);

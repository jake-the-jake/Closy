-- Public Discover posts: frozen outfit snapshots. Readable by anyone with the anon key;
-- inserts require an authenticated user (author = auth.uid()).

create table if not exists public.published_outfits (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  source_outfit_id text not null,
  name text not null,
  piece_count int not null default 0,
  snapshot jsonb not null,
  created_at timestamptz not null default now()
);

create index if not exists published_outfits_created_idx
  on public.published_outfits (created_at desc);

create index if not exists published_outfits_user_idx
  on public.published_outfits (user_id);

alter table public.published_outfits enable row level security;

drop policy if exists "Published outfits are world readable" on public.published_outfits;
create policy "Published outfits are world readable"
  on public.published_outfits for select
  using (true);

drop policy if exists "Users insert own published outfits" on public.published_outfits;
create policy "Users insert own published outfits"
  on public.published_outfits for insert
  to authenticated
  with check (auth.uid() = user_id);

-- No update/delete MVP — add author edit or unpublish in a future migration.

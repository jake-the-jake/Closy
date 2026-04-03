-- Canonical wardrobe image URLs: original + thumbnail (square padded) + display (aspect-preserved).
-- Legacy rows keep `image_url` only; app resolves fallbacks.

alter table public.wardrobe_items
  add column if not exists image_refs jsonb;

comment on column public.wardrobe_items.image_refs is
  '{"original":"...","thumbnail":"...","display":"..."} — derivatives from Edge Function; null for legacy.';

comment on column public.wardrobe_items.image_url is
  'Preferred display URL for legacy clients; should match image_refs.display when refs exist.';

-- Larger originals (server generates smaller derivatives)
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'wardrobe-images',
  'wardrobe-images',
  true,
  15728640,
  array['image/jpeg', 'image/png', 'image/webp', 'image/gif', 'image/heic', 'image/heif']::text[]
)
on conflict (id) do update set
  public = excluded.public,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

-- Wardrobe item photos: public bucket (stable URLs in `wardrobe_items.image_url`).
-- Paths: `{auth.uid()}/{wardrobe_item_uuid}.{ext}` — first segment must match the uploader.
--
-- Apply via Supabase SQL Editor or `supabase db push`.
-- Dashboard: Storage → confirm bucket `wardrobe-images` exists as public if you create it manually.

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'wardrobe-images',
  'wardrobe-images',
  true,
  5242880,
  array['image/jpeg', 'image/png', 'image/webp', 'image/gif', 'image/heic', 'image/heif']::text[]
)
on conflict (id) do update set
  public = excluded.public,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

drop policy if exists "Wardrobe images public read" on storage.objects;
create policy "Wardrobe images public read"
  on storage.objects for select
  using (bucket_id = 'wardrobe-images');

drop policy if exists "Users upload own wardrobe images" on storage.objects;
create policy "Users upload own wardrobe images"
  on storage.objects for insert
  to authenticated
  with check (
    bucket_id = 'wardrobe-images'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

drop policy if exists "Users update own wardrobe images" on storage.objects;
create policy "Users update own wardrobe images"
  on storage.objects for update
  to authenticated
  using (
    bucket_id = 'wardrobe-images'
    and (storage.foldername(name))[1] = auth.uid()::text
  )
  with check (
    bucket_id = 'wardrobe-images'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

drop policy if exists "Users delete own wardrobe images" on storage.objects;
create policy "Users delete own wardrobe images"
  on storage.objects for delete
  to authenticated
  using (
    bucket_id = 'wardrobe-images'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

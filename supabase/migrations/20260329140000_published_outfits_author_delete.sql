-- Author attribution (denormalized at publish time) + author-only delete (unpublish).

alter table public.published_outfits
  add column if not exists author_display_name text not null default '';

comment on column public.published_outfits.author_display_name is
  'Display label frozen at publish time (profile display name, email local part, or fallback).';

drop policy if exists "Users delete own published outfits" on public.published_outfits;
create policy "Users delete own published outfits"
  on public.published_outfits for delete
  to authenticated
  using (auth.uid() = user_id);

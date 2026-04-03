-- Ordered Discover post ids for people the current user follows (auth.uid()). Empty when signed out.
-- Depends on: published_outfits, user_follows. Client: discoverService.fetchFollowingFeed / fetchPublishedOutfitsFollowingFeed.

create or replace function public.following_published_outfit_ids(p_limit integer default 50)
returns table (outfit_id uuid)
language sql
stable
security invoker
set search_path = public
as $$
  select po.id
  from public.published_outfits po
  where auth.uid() is not null
    and exists (
      select 1
      from public.user_follows uf
      where uf.follower_id = auth.uid()
        and uf.followed_id = po.user_id
    )
  order by po.created_at desc
  limit least(coalesce(nullif(p_limit, 0), 50), 100);
$$;

comment on function public.following_published_outfit_ids(integer) is
  'Returns Discover post ids from followed authors, newest first, for the signed-in user.';

grant execute on function public.following_published_outfit_ids(integer) to anon, authenticated;

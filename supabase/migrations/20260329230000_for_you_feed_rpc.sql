-- For You: personalized Discover ordering for the signed-in user (security invoker → auth.uid()).
-- Depends on: published_outfits, user_follows, published_outfit_likes, published_outfit_comments, wardrobe_items.
--
-- Ranking (deterministic tie-break: newer created_at first). All weights are fixed integers so behavior is auditable.
--   1) Followed author bonus:        +5000 if post.user_id is in user_follows for the current user.
--   2) Engaged author bonus:         +2500 if the viewer has liked OR commented on ANY post by this author
--                                    (surfaces more from tastemakers they already interact with).
--   3) Wardrobe category overlap:    +400 per DISTINCT matching category label between
--                                    snapshot.lines[].categoryLabel (lowercased) and wardrobe_items.category for the viewer.
--                                    Skips empty/placeholder labels ("—", "–").
--   4) Popularity (light):           +8 * least(global_like_count, 30)  caps megahit dominance.
--   5) Recency (light):              +2 * max(0, 240 - floor(age_hours))  fades over ~10 days.
--
-- Pool: the 300 newest published_outfits only (keeps the query bounded). If you need fresher tail behavior,
-- raise the limit in SQL and/or add indexes.
--
-- Client: discoverService.fetchForYouFeed / fetchPublishedOutfitsForYouFeed + for_you_feed_signals.

create or replace function public.for_you_published_outfit_ids(p_limit integer default 50)
returns table (outfit_id uuid)
language sql
stable
security invoker
set search_path = public
as $$
  with params as (
    select
      auth.uid() as me,
      least(coalesce(nullif(p_limit, 0), 50), 100) as lim
  ),
  followed as (
    select uf.followed_id as author_id
    from public.user_follows uf
    cross join params p
    where p.me is not null
      and uf.follower_id = p.me
  ),
  engaged_authors as (
    select distinct po.user_id as author_id
    from public.published_outfit_likes l
    inner join public.published_outfits po on po.id = l.published_outfit_id
    cross join params p
    where p.me is not null
      and l.user_id = p.me
    union
    select distinct po.user_id as author_id
    from public.published_outfit_comments c
    inner join public.published_outfits po on po.id = c.published_outfit_id
    cross join params p
    where p.me is not null
      and c.user_id = p.me
  ),
  my_cats as (
    select distinct lower(trim(w.category)) as cat
    from public.wardrobe_items w
    cross join params p
    where p.me is not null
      and w.user_id = p.me
      and length(trim(w.category)) > 0
  ),
  like_counts as (
    select pol.published_outfit_id, count(*)::bigint as cnt
    from public.published_outfit_likes pol
    group by pol.published_outfit_id
  ),
  candidates as (
    select
      po.id,
      po.user_id,
      po.created_at,
      po.snapshot,
      coalesce(lc.cnt, 0::bigint) as like_cnt
    from public.published_outfits po
    cross join params p
    left join like_counts lc on lc.published_outfit_id = po.id
    where p.me is not null
    order by po.created_at desc
    limit 300
  ),
  scored as (
    select
      c.id,
      c.created_at,
      (
        case
          when exists (select 1 from followed f where f.author_id = c.user_id)
          then 5000 else 0
        end
        + case
          when exists (select 1 from engaged_authors ea where ea.author_id = c.user_id)
          then 2500 else 0
        end
        + coalesce(
          (
            select count(distinct lines.cl)::bigint * 400
            from (
              select lower(trim(j.elem->>'categoryLabel')) as cl
              from jsonb_array_elements(coalesce(c.snapshot->'lines', '[]'::jsonb)) as j(elem)
            ) lines
            inner join my_cats mc on mc.cat = lines.cl
            where lines.cl is not null
              and lines.cl not in ('', '—', '–')
          ),
          0::bigint
        )
        + least(c.like_cnt, 30::bigint) * 8
        + greatest(
          0::bigint,
          (240::bigint - floor(extract(epoch from (now() - c.created_at)) / 3600.0)::bigint)
        ) * 2
      )::bigint as pts
    from candidates c
  )
  select s.id as outfit_id
  from scored s
  order by s.pts desc, s.created_at desc
  limit (select lim from params);
$$;

comment on function public.for_you_published_outfit_ids(integer) is
  'Personalized Discover ordering for auth.uid(): see migration header for additive score recipe; pool = 300 newest posts.';

grant execute on function public.for_you_published_outfit_ids(integer) to anon, authenticated;


-- Compact signal counts for For You empty / “tune your feed” UI (signed-in only returns JSON).
create or replace function public.for_you_feed_signals()
returns json
language sql
stable
security invoker
set search_path = public
as $$
  select case
    when auth.uid() is null then null::json
    else json_build_object(
      'follows', (
        select coalesce(count(*)::int, 0)
        from public.user_follows
        where follower_id = auth.uid()
      ),
      'likes', (
        select coalesce(count(*)::int, 0)
        from public.published_outfit_likes
        where user_id = auth.uid()
      ),
      'comments', (
        select coalesce(count(*)::int, 0)
        from public.published_outfit_comments
        where user_id = auth.uid()
      ),
      'wardrobePieces', (
        select coalesce(count(*)::int, 0)
        from public.wardrobe_items
        where user_id = auth.uid()
      )
    )
  end;
$$;

comment on function public.for_you_feed_signals() is
  'Non-secret counts used to explain / gate “weak personalization” UX for For You.';

grant execute on function public.for_you_feed_signals() to anon, authenticated;

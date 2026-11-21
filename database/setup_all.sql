-- =====================================================================
-- ColorMuse — Supabase PostgreSQL schema
-- Run in the Supabase SQL editor (or psql) once, then run storage.sql and
-- seed_colors.sql. Safe to re-run: objects are created if missing.
--
-- Security: every private table has owner_id = auth.uid() and Row Level
-- Security policies that restrict ALL operations to the owner. The app
-- connects with the anon key + the owner's session, never the service role.
-- =====================================================================

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------- helpers
create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at := now();
  return new;
end $$;

-- ---------------------------------------------------------------- colors (reference data)
create table if not exists public.colors (
  id          uuid primary key default gen_random_uuid(),
  name        text not null unique,
  hex         text not null check (hex ~ '^#[0-9A-F]{6}$'),
  family      text not null,
  is_neutral  boolean not null default false,
  created_at  timestamptz not null default now()
);
create index if not exists colors_family_idx on public.colors (family);

-- ---------------------------------------------------------------- user_preferences
create table if not exists public.user_preferences (
  owner_id              uuid primary key default auth.uid() references auth.users (id) on delete cascade,
  display_name          text not null default '',
  favorite_colors       text[] not null default '{}',
  disliked_colors       text[] not null default '{}',
  preferred_styles      text[] not null default '{}',
  occasion_preferences  text[] not null default '{}',
  seasons               text[] not null default '{}',
  scoring_weights       jsonb not null default '{"harmony":0.35,"contrast":0.20,"category":0.15,"occasion":0.10,"style":0.10,"preference":0.10}'::jsonb,
  skin_tone             text not null default '#E8C4A8',
  hair_color            text not null default '#3B2A24',
  hair_style            text not null default 'long_waves',
  nail_shape            text not null default 'almond',
  updated_at            timestamptz not null default now()
);

-- ---------------------------------------------------------------- wardrobe_items
create table if not exists public.wardrobe_items (
  id                  uuid primary key default gen_random_uuid(),
  owner_id            uuid not null default auth.uid() references auth.users (id) on delete cascade,
  name                text not null check (char_length(name) between 1 and 120),
  category            text not null check (category in ('tops','bottoms','dresses','outerwear','shoes','bags',
                                                         'jewelry','accessories','scarves','belts','hats')),
  subcategory         text,
  primary_color       text not null check (primary_color ~ '^#[0-9A-F]{6}$'),
  primary_color_name  text,
  secondary_colors    text[] not null default '{}',
  shade               text check (shade in ('light','medium','dark')),
  pattern             text not null default 'solid',
  brand               text,
  seasons             text[] not null default '{}',
  styles              text[] not null default '{}',
  occasions           text[] not null default '{}',
  notes               text,
  favorite            boolean not null default false,
  image_path          text,
  thumb_path          text,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);
create index if not exists wardrobe_owner_created_idx on public.wardrobe_items (owner_id, created_at desc);
create index if not exists wardrobe_owner_category_idx on public.wardrobe_items (owner_id, category);
create index if not exists wardrobe_owner_favorite_idx on public.wardrobe_items (owner_id) where favorite;

-- ---------------------------------------------------------------- clothing_images (files live in Storage)
create table if not exists public.clothing_images (
  id                uuid primary key default gen_random_uuid(),
  owner_id          uuid not null default auth.uid() references auth.users (id) on delete cascade,
  wardrobe_item_id  uuid not null references public.wardrobe_items (id) on delete cascade,
  storage_path      text not null,
  thumb_path        text not null,
  width             integer,
  height            integer,
  size_bytes        integer,
  content_type      text not null default 'image/jpeg',
  is_primary        boolean not null default true,
  created_at        timestamptz not null default now()
);
create index if not exists clothing_images_item_idx on public.clothing_images (owner_id, wardrobe_item_id);

-- ---------------------------------------------------------------- outfits
create table if not exists public.outfits (
  id          uuid primary key default gen_random_uuid(),
  owner_id    uuid not null default auth.uid() references auth.users (id) on delete cascade,
  name        text not null default 'Untitled look',
  occasion    text,
  style       text,
  season      text,
  notes       text,
  favorite    boolean not null default false,
  layout      text not null default 'editorial',
  skin_tone   text not null default '#E8C4A8',
  hair_color  text not null default '#3B2A24',
  hair_style  text not null default 'long_waves',
  score       numeric(5,1),
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create index if not exists outfits_owner_updated_idx on public.outfits (owner_id, updated_at desc);
create index if not exists outfits_owner_occasion_idx on public.outfits (owner_id, occasion);

-- ---------------------------------------------------------------- outfit_items
create table if not exists public.outfit_items (
  id                uuid primary key default gen_random_uuid(),
  owner_id          uuid not null default auth.uid() references auth.users (id) on delete cascade,
  outfit_id         uuid not null references public.outfits (id) on delete cascade,
  wardrobe_item_id  uuid references public.wardrobe_items (id) on delete set null,
  slot              text not null check (slot in ('top','bottom','dress','outerwear','shoes','bag','jewelry',
                                                  'accessory','scarf','belt','hat','nails')),
  color_hex         text not null check (color_hex ~ '^#[0-9A-F]{6}$'),
  secondary_hex     text,
  pattern           text not null default 'solid',
  variant           text,
  label             text,
  position          integer not null default 0,
  unique (outfit_id, slot)
);
create index if not exists outfit_items_outfit_idx on public.outfit_items (owner_id, outfit_id);
create index if not exists outfit_items_wardrobe_idx on public.outfit_items (wardrobe_item_id);

-- ---------------------------------------------------------------- collections
create table if not exists public.outfit_collections (
  id           uuid primary key default gen_random_uuid(),
  owner_id     uuid not null default auth.uid() references auth.users (id) on delete cascade,
  name         text not null check (char_length(name) between 1 and 80),
  description  text,
  created_at   timestamptz not null default now()
);
create index if not exists collections_owner_idx on public.outfit_collections (owner_id, name);

create table if not exists public.collection_outfits (
  collection_id  uuid not null references public.outfit_collections (id) on delete cascade,
  outfit_id      uuid not null references public.outfits (id) on delete cascade,
  owner_id       uuid not null default auth.uid() references auth.users (id) on delete cascade,
  added_at       timestamptz not null default now(),
  primary key (collection_id, outfit_id)
);
create index if not exists collection_outfits_outfit_idx on public.collection_outfits (owner_id, outfit_id);

-- ---------------------------------------------------------------- recommendation_history
create table if not exists public.recommendation_history (
  id          uuid primary key default gen_random_uuid(),
  owner_id    uuid not null default auth.uid() references auth.users (id) on delete cascade,
  kind        text not null,
  request     jsonb not null default '{}'::jsonb,
  results     jsonb not null default '[]'::jsonb,
  created_at  timestamptz not null default now()
);
create index if not exists history_owner_created_idx on public.recommendation_history (owner_id, created_at desc);

-- ---------------------------------------------------------------- updated_at triggers
drop trigger if exists trg_wardrobe_updated on public.wardrobe_items;
create trigger trg_wardrobe_updated before update on public.wardrobe_items
  for each row execute function public.set_updated_at();
drop trigger if exists trg_outfits_updated on public.outfits;
create trigger trg_outfits_updated before update on public.outfits
  for each row execute function public.set_updated_at();
drop trigger if exists trg_prefs_updated on public.user_preferences;
create trigger trg_prefs_updated before update on public.user_preferences
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------- Row Level Security
alter table public.colors                  enable row level security;
alter table public.user_preferences        enable row level security;
alter table public.wardrobe_items          enable row level security;
alter table public.clothing_images         enable row level security;
alter table public.outfits                 enable row level security;
alter table public.outfit_items            enable row level security;
alter table public.outfit_collections      enable row level security;
alter table public.collection_outfits      enable row level security;
alter table public.recommendation_history  enable row level security;

-- Reference colors: readable by the signed-in owner, never writable from the app
drop policy if exists colors_read on public.colors;
create policy colors_read on public.colors for select to authenticated using (true);

-- Owner-only policies for every private table
do $$
declare t text;
begin
  foreach t in array array['user_preferences','wardrobe_items','clothing_images','outfits','outfit_items',
                           'outfit_collections','collection_outfits','recommendation_history']
  loop
    execute format('drop policy if exists %1$s_owner_select on public.%1$s', t);
    execute format('drop policy if exists %1$s_owner_insert on public.%1$s', t);
    execute format('drop policy if exists %1$s_owner_update on public.%1$s', t);
    execute format('drop policy if exists %1$s_owner_delete on public.%1$s', t);
    execute format('create policy %1$s_owner_select on public.%1$s for select to authenticated using (owner_id = auth.uid())', t);
    execute format('create policy %1$s_owner_insert on public.%1$s for insert to authenticated with check (owner_id = auth.uid())', t);
    execute format('create policy %1$s_owner_update on public.%1$s for update to authenticated using (owner_id = auth.uid()) with check (owner_id = auth.uid())', t);
    execute format('create policy %1$s_owner_delete on public.%1$s for delete to authenticated using (owner_id = auth.uid())', t);
  end loop;
end $$;

-- Child rows must point at parents the owner also owns
drop policy if exists outfit_items_parent_owned on public.outfit_items;
create policy outfit_items_parent_owned on public.outfit_items as restrictive for insert to authenticated
  with check (exists (select 1 from public.outfits o where o.id = outfit_id and o.owner_id = auth.uid()));
drop policy if exists collection_outfits_parent_owned on public.collection_outfits;
create policy collection_outfits_parent_owned on public.collection_outfits as restrictive for insert to authenticated
  with check (
    exists (select 1 from public.outfit_collections c where c.id = collection_id and c.owner_id = auth.uid())
    and exists (select 1 from public.outfits o where o.id = outfit_id and o.owner_id = auth.uid()));
drop policy if exists clothing_images_parent_owned on public.clothing_images;
create policy clothing_images_parent_owned on public.clothing_images as restrictive for insert to authenticated
  with check (exists (select 1 from public.wardrobe_items w where w.id = wardrobe_item_id and w.owner_id = auth.uid()));

-- No access at all for anonymous visitors
revoke all on all tables in schema public from anon;
grant select on public.colors to authenticated;
grant select, insert, update, delete on
  public.user_preferences, public.wardrobe_items, public.clothing_images, public.outfits, public.outfit_items,
  public.outfit_collections, public.collection_outfits, public.recommendation_history
  to authenticated;
-- =====================================================================
-- ColorMuse — Supabase Storage: private bucket + owner-folder policies
-- Objects are stored as  <auth.uid()>/items/<item>/<image>.jpg
--                        <auth.uid()>/thumbs/<item>/<image>.jpg
-- =====================================================================

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('wardrobe', 'wardrobe', false, 5242880, array['image/jpeg','image/png','image/webp'])
on conflict (id) do update
  set public = false,
      file_size_limit = excluded.file_size_limit,
      allowed_mime_types = excluded.allowed_mime_types;

drop policy if exists "wardrobe owner read"   on storage.objects;
drop policy if exists "wardrobe owner insert" on storage.objects;
drop policy if exists "wardrobe owner update" on storage.objects;
drop policy if exists "wardrobe owner delete" on storage.objects;

create policy "wardrobe owner read" on storage.objects for select to authenticated
  using (bucket_id = 'wardrobe' and (storage.foldername(name))[1] = auth.uid()::text);

create policy "wardrobe owner insert" on storage.objects for insert to authenticated
  with check (bucket_id = 'wardrobe' and (storage.foldername(name))[1] = auth.uid()::text);

create policy "wardrobe owner update" on storage.objects for update to authenticated
  using (bucket_id = 'wardrobe' and (storage.foldername(name))[1] = auth.uid()::text)
  with check (bucket_id = 'wardrobe' and (storage.foldername(name))[1] = auth.uid()::text);

create policy "wardrobe owner delete" on storage.objects for delete to authenticated
  using (bucket_id = 'wardrobe' and (storage.foldername(name))[1] = auth.uid()::text);
-- Generated by scripts/generate_color_seed.py from src/core/color_library.py. Do not edit by hand.
insert into public.colors (name, hex, family, is_neutral) values
  ('Optic White', '#FBFBF9', 'white', true),
  ('Ivory', '#F8F4EF', 'white', true),
  ('Cream', '#F3E9D2', 'white', true),
  ('Ecru', '#E9DFC9', 'white', true),
  ('Oatmeal', '#DDD1BC', 'beige', true),
  ('Sand', '#D8C3A5', 'beige', true),
  ('Beige', '#D9C4A8', 'beige', true),
  ('Nude', '#E3BFA3', 'beige', true),
  ('Taupe', '#C8AD91', 'beige', true),
  ('Greige', '#B8AD9E', 'beige', true),
  ('Khaki', '#BFAF85', 'beige', true),
  ('Camel', '#C19A6B', 'brown', true),
  ('Cognac', '#9A5B2E', 'brown', true),
  ('Tan', '#C69C72', 'brown', true),
  ('Mocha', '#7B5B4C', 'brown', true),
  ('Chocolate', '#4E3226', 'brown', true),
  ('Espresso', '#3B2A24', 'brown', true),
  ('Dove Gray', '#D3D0CB', 'gray', true),
  ('Silver Gray', '#B7B8B6', 'gray', true),
  ('Heather Gray', '#9C9A98', 'gray', true),
  ('Slate', '#6C737A', 'gray', true),
  ('Charcoal', '#302B2B', 'gray', true),
  ('Graphite', '#45474B', 'gray', true),
  ('Black', '#141414', 'black', true),
  ('Navy', '#1F2A44', 'blue', true),
  ('Midnight', '#191D33', 'blue', true),
  ('Denim', '#4A6584', 'blue', true),
  ('Light Denim', '#8EA7C1', 'blue', true),
  ('Olive', '#6B6B3A', 'green', true),
  ('Cherry Red', '#B3112E', 'red', false),
  ('Scarlet', '#D0312D', 'red', false),
  ('Tomato', '#E2533C', 'red', false),
  ('Brick', '#9C3B2E', 'red', false),
  ('Wine', '#6A1E2D', 'red', false),
  ('Burgundy', '#713E4A', 'red', false),
  ('Oxblood', '#5C1F22', 'red', false),
  ('Crimson', '#A4123F', 'red', false),
  ('Blush', '#E8C9C5', 'pink', false),
  ('Ballet Pink', '#F2D3D4', 'pink', false),
  ('Dusty Rose', '#B77E79', 'pink', false),
  ('Rose', '#D98695', 'pink', false),
  ('Mauve', '#A98095', 'pink', false),
  ('Bubblegum', '#F4A6C1', 'pink', false),
  ('Hot Pink', '#E0457B', 'pink', false),
  ('Fuchsia', '#C2185B', 'pink', false),
  ('Raspberry', '#B0305C', 'pink', false),
  ('Peony', '#E3829B', 'pink', false),
  ('Coral', '#F27F6B', 'orange', false),
  ('Peach', '#F6C1A6', 'orange', false),
  ('Apricot', '#F1A97A', 'orange', false),
  ('Tangerine', '#F28C28', 'orange', false),
  ('Burnt Orange', '#C25B26', 'orange', false),
  ('Rust', '#A0472A', 'orange', false),
  ('Terracotta', '#C46A4F', 'orange', false),
  ('Salmon', '#EE9A86', 'orange', false),
  ('Butter', '#F6E3A1', 'yellow', false),
  ('Lemon', '#F4E04D', 'yellow', false),
  ('Sunflower', '#F2B630', 'yellow', false),
  ('Mustard', '#CC9A2B', 'yellow', false),
  ('Ochre', '#B5832F', 'yellow', false),
  ('Champagne', '#EBD9B4', 'yellow', false),
  ('Mint', '#BFE3CF', 'green', false),
  ('Pistachio', '#B8CF96', 'green', false),
  ('Sage', '#A3B18A', 'green', false),
  ('Eucalyptus', '#7FA393', 'green', false),
  ('Moss', '#77814A', 'green', false),
  ('Kelly Green', '#2E9E4F', 'green', false),
  ('Emerald', '#11795A', 'green', false),
  ('Forest Green', '#2D4F3A', 'green', false),
  ('Hunter Green', '#355E3B', 'green', false),
  ('Lime', '#BFD641', 'green', false),
  ('Teal', '#1F7A7A', 'green', false),
  ('Powder Blue', '#BCD3E6', 'blue', false),
  ('Baby Blue', '#A9CBEA', 'blue', false),
  ('Sky Blue', '#7DB5E3', 'blue', false),
  ('Cornflower', '#6F8FD8', 'blue', false),
  ('Cerulean', '#2A7AB8', 'blue', false),
  ('Cobalt', '#1F4FB4', 'blue', false),
  ('Royal Blue', '#2A3FA0', 'blue', false),
  ('Sapphire', '#1D3B78', 'blue', false),
  ('Turquoise', '#3CC2C0', 'blue', false),
  ('Aqua', '#86D9D2', 'blue', false),
  ('Steel Blue', '#5B7C99', 'blue', false),
  ('Petrol', '#1F4E5F', 'blue', false),
  ('Lavender', '#C9B8DD', 'purple', false),
  ('Lilac', '#B9A2CC', 'purple', false),
  ('Wisteria', '#9C87C1', 'purple', false),
  ('Orchid', '#B06AB3', 'purple', false),
  ('Violet', '#7A4FA3', 'purple', false),
  ('Plum', '#5E2F52', 'purple', false),
  ('Eggplant', '#3F2541', 'purple', false),
  ('Amethyst', '#8E5CA8', 'purple', false),
  ('Gold', '#C9A44C', 'metallic', true),
  ('Rose Gold', '#C99584', 'metallic', true),
  ('Silver', '#BFC1C2', 'metallic', true),
  ('Bronze', '#A0703E', 'metallic', true),
  ('Pearl', '#EEE7DC', 'metallic', true)
on conflict (name) do update set hex = excluded.hex, family = excluded.family, is_neutral = excluded.is_neutral;

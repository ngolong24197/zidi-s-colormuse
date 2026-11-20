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

-- Agregado textual para la word cloud del observatorio de medios.
-- Aplicado en el proyecto bd_odesocan el 2026-08-29 (migraciones
-- `wordcloud_terms_agregado_textual` y
-- `wordcloud_truncate_revocar_anon_authenticated`).

create table if not exists medios.wordcloud_terms (
  scope_key text not null,
  medio text,
  tema text,
  term text not null,
  normalized_term text not null,
  gram_type text not null check (gram_type in ('unigram', 'bigram')),
  score numeric not null,
  doc_freq integer not null,
  term_freq numeric not null,
  sample_titles jsonb not null default '[]'::jsonb,
  n_noticias integer not null,
  generated_at timestamptz not null default now(),
  primary key (scope_key, gram_type, normalized_term)
);

create index if not exists wordcloud_terms_score_idx
  on medios.wordcloud_terms (medio, tema, score desc);

comment on table medios.wordcloud_terms is
'Agregado textual para la word cloud del observatorio de medios.';

-- RLS. El esquema `medios` está expuesto por la API, así que la tabla no puede
-- quedarse sin RLS. Se replica la convención de medios.noticias y
-- medios.scraping_log: lectura pública (el agregado deriva de titulares
-- públicos) y escritura reservada a service_role, que salta RLS.
alter table medios.wordcloud_terms enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'medios'
      and tablename = 'wordcloud_terms'
      and policyname = 'lectura_publica_wordcloud_terms'
  ) then
    create policy lectura_publica_wordcloud_terms
      on medios.wordcloud_terms
      for select
      to anon, authenticated
      using (true);
  end if;
end
$$;

grant select on medios.wordcloud_terms to anon, authenticated;

-- Acceso de service_role al esquema.
-- El esquema `medios` se creó concediendo acceso a anon y authenticated, pero
-- nunca a service_role, que no tenía ni USAGE. Sin esto el pipeline falla al
-- leer las noticias con:
--   permission denied for schema medios (42501)
-- service_role tiene BYPASSRLS, pero eso solo salta las políticas RLS: no
-- sustituye a los GRANT. Se conceden solo los privilegios que necesita
-- scripts/build_wordcloud_terms.py — leer la fuente y escribir el agregado —,
-- así que si en el futuro el script lee otra tabla habrá que ampliarlos.
grant usage  on schema medios to service_role;
grant select on medios.noticias to service_role;
grant select, insert, update on medios.wordcloud_terms to service_role;

-- Función de truncado que invoca scripts/build_wordcloud_terms.py.
-- Es SECURITY DEFINER y recibe esquema y tabla por parámetro, de modo que puede
-- truncar cualquier tabla de la base de datos. Hay que restringir quién la
-- invoca: la anon key de este proyecto es pública (está en index.html, en un
-- repositorio público), así que dejarla abierta a `anon` permitiría a cualquiera
-- vaciar tablas.
--
-- No basta con revocarla de PUBLIC: Supabase aplica ALTER DEFAULT PRIVILEGES
-- concediendo EXECUTE a anon y authenticated sobre las funciones nuevas de
-- `public`, y esas concesiones son explícitas por rol. Hay que revocarlas una
-- a una. Comprobación tras aplicar este fichero:
--
--   select grantee from information_schema.role_routine_grants
--    where routine_schema='public' and routine_name='truncate_wordcloud_terms'
--      and privilege_type='EXECUTE';
--   -- debe devolver solo: postgres, service_role
create or replace function public.truncate_wordcloud_terms(target_schema text, target_table text)
returns void
language plpgsql
security definer
set search_path = pg_catalog, pg_temp
as $$
begin
  execute format('truncate table %I.%I', target_schema, target_table);
end;
$$;

revoke all     on function public.truncate_wordcloud_terms(text, text) from public;
revoke execute on function public.truncate_wordcloud_terms(text, text) from anon;
revoke execute on function public.truncate_wordcloud_terms(text, text) from authenticated;
grant  execute on function public.truncate_wordcloud_terms(text, text) to service_role;

-- ─────────────────────────────────────────────────────────────────────────────
-- Detector de declaraciones — esquema
--
-- Sostiene la cola de verificación del observatorio: qué dijo cada cargo
-- público, dónde lo dijo y en qué estado de revisión está.
--
-- Principio que ordena todo el fichero: la detección es automática, el
-- veredicto es humano. Por eso las columnas están en dos bloques separados y
-- el pipeline sólo escribe el primero. Un reproceso del corpus no puede
-- deshacer el trabajo de una persona.
--
-- Y por eso también la tabla NO es de lectura pública salvo en las filas ya
-- publicadas. Exponer una cola de detecciones sin revisar —afirmaciones de
-- personas identificables, marcadas por una heurística como "verificables"—
-- sería publicar una acusación que nadie ha comprobado.
-- ─────────────────────────────────────────────────────────────────────────────

-- ── 1. Declaraciones ─────────────────────────────────────────────────────────

create table if not exists medios.declaraciones (
  -- Identidad y trazabilidad hacia la noticia de origen.
  hash_declaracion  text primary key,
  url_hash          text not null,
  url               text not null,
  medio             text not null,
  fecha_pub         timestamptz,

  -- ── Bloque automático: lo escribe scripts/build_declaraciones.py ──────────
  cita              text not null,
  tipo_cita         text not null
                    check (tipo_cita in ('titular', 'directa', 'indirecta', 'pospuesta')),
  actor_texto       text not null,
  actor_nombre      text,
  actor_slug        text not null,
  cargo             text,
  cargo_completo    text,
  area              text,
  ambito            text check (ambito in ('autonomico', 'insular', 'municipal', 'estatal', 'partido')),
  institucion       text,
  ex_cargo          boolean not null default false,
  verbo             text,
  verbo_lema        text,
  fuerza            text not null
                    check (fuerza in ('asercion', 'compromiso', 'prediccion', 'valoracion', 'demanda', 'neutro')),
  marcadores        text[] not null default '{}',
  temas             text[] not null default '{}',
  campo             text not null check (campo in ('titulo', 'resumen', 'texto_full')),
  contexto          text,
  prioridad         integer not null default 0 check (prioridad between 0 and 100),
  verificable       boolean not null default false,
  detectado_en      timestamptz not null default now(),

  -- ── Bloque humano: no lo toca ningún proceso automático ───────────────────
  -- `estado` gobierna la visibilidad. Sólo 'publicada' sale al exterior.
  estado            text not null default 'pendiente'
                    check (estado in ('pendiente', 'en_verificacion', 'descartada', 'publicada')),
  -- Los veredictos de hecho y los de promesa son escalas distintas y conviven
  -- en la misma columna porque la unidad de trabajo es la misma: una
  -- declaración. `fuerza` dice cuál de las dos escalas aplica.
  veredicto         text
                    check (veredicto in ('cierto', 'cierto_matizable', 'enganoso',
                                         'falso', 'insostenible', 'sin_datos',
                                         'cumplida', 'incumplida', 'en_plazo')),
  resumen_verificacion text,
  fuentes           jsonb not null default '[]'::jsonb,
  revisado_por      text,
  revisado_en       timestamptz,
  url_publicacion   text,
  notas             text,

  -- Un veredicto sin quien lo firme no es verificación, es una opinión anónima.
  constraint declaraciones_veredicto_con_autoria
    check (veredicto is null or (revisado_por is not null and revisado_en is not null)),
  -- Nada se publica sin veredicto.
  constraint declaraciones_publicada_con_veredicto
    check (estado <> 'publicada' or veredicto is not null)
);

comment on table medios.declaraciones is
'Declaraciones de cargos públicos detectadas en la prensa canaria. Detección automática, veredicto humano.';
comment on column medios.declaraciones.verificable is
'Heurística de cribado, no un juicio: indica que la afirmación tiene algún anclaje contrastable.';
comment on column medios.declaraciones.prioridad is
'Orden de trabajo sugerido (0-100). No mide gravedad ni verosimilitud.';

create index if not exists declaraciones_cola_idx
  on medios.declaraciones (estado, verificable, prioridad desc);
create index if not exists declaraciones_actor_idx
  on medios.declaraciones (actor_slug, fecha_pub desc);
create index if not exists declaraciones_medio_fecha_idx
  on medios.declaraciones (medio, fecha_pub desc);
create index if not exists declaraciones_temas_idx
  on medios.declaraciones using gin (temas);
create index if not exists declaraciones_url_hash_idx
  on medios.declaraciones (url_hash);

-- ── 2. Registro curado de actores ────────────────────────────────────────────
-- Enriquece las detecciones con partido y periodo en el cargo, que no se pueden
-- deducir del texto. Lo mantiene una persona: aquí no escribe el pipeline.

create table if not exists medios.actores (
  actor_slug      text primary key,
  nombre          text not null,
  cargo_completo  text,
  institucion     text,
  ambito          text check (ambito in ('autonomico', 'insular', 'municipal', 'estatal', 'partido')),
  partido         text,
  -- Delimitar el periodo permite atribuir una declaración al cargo que se
  -- ostentaba cuando se hizo, no al de hoy.
  desde           date,
  hasta           date,
  activo          boolean not null default true,
  notas           text,
  curado_por      text,
  actualizado_en  timestamptz not null default now()
);

comment on table medios.actores is
'Censo curado a mano de cargos públicos canarios. Ningún proceso automático escribe aquí.';

-- ── 3. Candidatos a actor ────────────────────────────────────────────────────
-- Agregación automática de los emisores hallados en el corpus, para curar el
-- censo desde los datos en vez de tecleándolo. Contiene nombres de personas
-- extraídos sin revisar: no es de lectura pública.

create table if not exists medios.actores_candidatos (
  actor_slug      text primary key,
  nombre          text,
  cargos          text[] not null default '{}',
  ambitos         text[] not null default '{}',
  instituciones   text[] not null default '{}',
  medios          text[] not null default '{}',
  n_declaraciones integer not null default 0,
  n_verificables  integer not null default 0,
  generado_en     timestamptz not null default now()
);

comment on table medios.actores_candidatos is
'Emisores detectados en el corpus, pendientes de curación. Extracción sin revisar: no se expone.';

-- ── 4. Vistas ────────────────────────────────────────────────────────────────

-- Cola de trabajo. No pública: la consume el equipo con la service_role key.
create or replace view medios.v_cola_verificacion as
select
  d.hash_declaracion, d.prioridad, d.fecha_pub, d.medio, d.url,
  coalesce(a.nombre, d.actor_nombre, d.actor_texto) as actor,
  coalesce(a.cargo_completo, d.cargo_completo)      as cargo,
  a.partido, d.ambito, d.institucion,
  d.fuerza, d.marcadores, d.temas, d.tipo_cita, d.cita, d.contexto,
  d.estado, d.detectado_en
from medios.declaraciones d
left join medios.actores a on a.actor_slug = d.actor_slug
where d.verificable
  and d.estado in ('pendiente', 'en_verificacion')
order by d.prioridad desc, d.fecha_pub desc;

comment on view medios.v_cola_verificacion is
'Cola de verificación pendiente, ordenada por prioridad editorial.';

-- Verificaciones publicadas. Esto sí es público.
create or replace view medios.v_declaraciones_publicas as
select
  d.hash_declaracion, d.fecha_pub, d.medio, d.url,
  coalesce(a.nombre, d.actor_nombre, d.actor_texto) as actor,
  coalesce(a.cargo_completo, d.cargo_completo)      as cargo,
  a.partido, d.ambito, d.institucion,
  d.cita, d.tipo_cita, d.fuerza, d.temas,
  d.veredicto, d.resumen_verificacion, d.fuentes,
  d.url_publicacion, d.revisado_en
from medios.declaraciones d
left join medios.actores a on a.actor_slug = d.actor_slug
where d.estado = 'publicada'
order by d.revisado_en desc;

comment on view medios.v_declaraciones_publicas is
'Verificaciones cerradas y publicadas. Es la única salida pública del detector.';

-- ── 5. RLS ───────────────────────────────────────────────────────────────────
-- El esquema `medios` está expuesto por la API, así que ninguna tabla puede
-- quedarse sin RLS.

alter table medios.declaraciones       enable row level security;
alter table medios.actores             enable row level security;
alter table medios.actores_candidatos  enable row level security;

do $$
begin
  -- Sólo lo publicado sale fuera. La cola pendiente queda dentro.
  if not exists (
    select 1 from pg_policies
    where schemaname = 'medios' and tablename = 'declaraciones'
      and policyname = 'lectura_publica_declaraciones_publicadas'
  ) then
    create policy lectura_publica_declaraciones_publicadas
      on medios.declaraciones for select to anon, authenticated
      using (estado = 'publicada');
  end if;

  -- El censo curado es información pública sobre cargos públicos.
  if not exists (
    select 1 from pg_policies
    where schemaname = 'medios' and tablename = 'actores'
      and policyname = 'lectura_publica_actores'
  ) then
    create policy lectura_publica_actores
      on medios.actores for select to anon, authenticated
      using (true);
  end if;

  -- `actores_candidatos` no lleva política a propósito: con RLS activo y sin
  -- policy, anon y authenticated no ven nada. Sólo service_role, que la salta.
end
$$;

grant select on medios.declaraciones to anon, authenticated;
grant select on medios.actores       to anon, authenticated;

-- Las vistas se crean como `postgres` y no son security_invoker, así que no
-- heredan la RLS de la tabla base: hay que decidir sus permisos a mano.
-- `v_cola_verificacion` se queda sin grant para anon: es la cola sin revisar.
revoke all on medios.v_cola_verificacion from anon, authenticated;
grant select on medios.v_declaraciones_publicas to anon, authenticated;
grant select on medios.v_cola_verificacion      to service_role;

-- ── 6. Permisos del pipeline ─────────────────────────────────────────────────
-- `supabase/wordcloud.sql` ya concedió `usage` sobre el esquema y `select`
-- sobre medios.noticias a service_role. Aquí sólo lo que añade este pipeline.

grant select, insert, update, delete on medios.declaraciones      to service_role;
grant select, insert, update, delete on medios.actores_candidatos to service_role;
grant select                          on medios.actores           to service_role;

-- ── 7. Truncado de candidatos ────────────────────────────────────────────────
-- El agregado de candidatos se reconstruye entero en cada pasada.
--
-- A diferencia de `public.truncate_wordcloud_terms`, esta función no recibe
-- esquema ni tabla por parámetro: trunca exactamente una tabla, escrita en el
-- cuerpo. Así, aunque alguien consiga ejecutarla, no puede vaciar ninguna otra.
-- La lección viene del propio repositorio: la función parametrizada obligó a
-- revocar el EXECUTE rol por rol porque Supabase se lo concede por defecto a
-- anon y authenticated, y la anon key de este proyecto es pública.
create or replace function public.truncate_actores_candidatos()
returns void
language plpgsql
security definer
set search_path = pg_catalog, pg_temp
as $$
begin
  truncate table medios.actores_candidatos;
end;
$$;

revoke all     on function public.truncate_actores_candidatos() from public;
revoke execute on function public.truncate_actores_candidatos() from anon;
revoke execute on function public.truncate_actores_candidatos() from authenticated;
grant  execute on function public.truncate_actores_candidatos() to service_role;

-- Comprobación tras aplicar (debe devolver sólo postgres y service_role):
--   select grantee from information_schema.role_routine_grants
--    where routine_schema = 'public'
--      and routine_name = 'truncate_actores_candidatos'
--      and privilege_type = 'EXECUTE';

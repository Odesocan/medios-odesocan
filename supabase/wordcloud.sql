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

create or replace function public.truncate_wordcloud_terms(target_schema text, target_table text)
returns void
language plpgsql
security definer
as $$
begin
  execute format('truncate table %I.%I', target_schema, target_table);
end;
$$;

comment on table medios.wordcloud_terms is
'Agregado textual para la word cloud del observatorio de medios.';

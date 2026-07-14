-- DDL de referência (Unity Catalog). Executar manualmente se as tabelas ainda não existirem.
-- O modo bootstrap também cria/sobrescreve config_subcategoria via Spark.

CREATE TABLE IF NOT EXISTS groceries_ops.similis.config_subcategoria (
  subcategoria STRING NOT NULL,
  subcategory_name STRING COMMENT 'Valor literal de business_categorization.pharmacy.subcategory_name',
  category_name STRING COMMENT 'Valor literal de business_categorization.pharmacy.category_name (desambigua subcategorias homônimas)',
  attribute STRING NOT NULL,
  attribute_type STRING NOT NULL COMMENT 'hard_filter | soft_boost | text_only | ignore',
  weight DOUBLE,
  boost_factor DOUBLE,
  top_k INT,
  min_score DOUBLE,
  quantity_ratio_bounds STRING COMMENT 'JSON "[lo, hi]" da faixa de quantidade aceita (opcional)',
  quantity_kind STRING COMMENT 'count (pack-size, default) | mass (massa/volume do nome)',
  candidate_pool_multiplier INT COMMENT 'Busca top_k*N vizinhos antes dos filtros (default 1)',
  active BOOLEAN,
  updated_by STRING,
  updated_at TIMESTAMP
)
USING DELTA;

-- Para tabelas pré-existentes sem as colunas novas (o bootstrap recria a
-- tabela com overwriteSchema=true, então elas aparecem na próxima execução):
-- ALTER TABLE groceries_ops.similis.config_subcategoria ADD COLUMN quantity_kind STRING;
-- ALTER TABLE groceries_ops.similis.config_subcategoria ADD COLUMN candidate_pool_multiplier INT;

-- Para tabelas pré-existentes (versões antigas sem subcategory_name):
-- ALTER TABLE groceries_ops.similis.config_subcategoria
--   ADD COLUMN subcategory_name STRING
--   COMMENT 'Valor literal de business_categorization.pharmacy.subcategory_name';
-- ALTER TABLE groceries_ops.similis.config_subcategoria
--   ADD COLUMN category_name STRING
--   COMMENT 'Valor literal de business_categorization.pharmacy.category_name';
-- (O modo bootstrap recria a tabela com overwriteSchema=true, então a coluna
--  aparece automaticamente na próxima execução.)

CREATE TABLE IF NOT EXISTS groceries_ops.similis.recommendations (
  ean_origem STRING NOT NULL,
  product_name_origem STRING,
  subcategoria STRING NOT NULL COMMENT 'Slug SIMPLES (baseado só no subcategory_name, ex.: fraldas) — contrato histórico. ATENÇÃO: subcategorias homônimas sob categorias diferentes colapsam neste slug e colidem na partição (última execução do dia vence). Para o recorte desambiguado por categoria use recommendations_flat (slug composto + category_name).',
  sugestoes STRING COMMENT 'JSON array ordenado do melhor para o pior substituto: [{ean, relevance, rank}, ...]. relevance = cosseno × produto dos boost_factors das regras soft_boost ativas; pode passar de 1.0.',
  n_sugestoes INT,
  model_version STRING,
  config_hash STRING,
  date STRING
)
USING DELTA
PARTITIONED BY (date, subcategoria);

CREATE TABLE IF NOT EXISTS groceries_ops.similis.recommendations_flat (
  ean_origem STRING,
  product_name_origem STRING,
  ean_sugestao STRING,
  product_name_sugestao STRING,
  rank INT,
  relevance DOUBLE,
  n_sugestoes INT,
  subcategoria STRING COMMENT 'Slug legado da subcategoria (ex.: creme_assaduras) — mesmo vocabulário da tabela aninhada recommendations.',
  categoria STRING COMMENT 'Slug da categoria (ex.: troca_de_fralda). O par (subcategoria, categoria) desambigua subcategorias homônimas.',
  model_version STRING,
  config_hash STRING,
  date STRING
)
USING DELTA
PARTITIONED BY (date, subcategoria, categoria);

-- Para tabela flat pré-existente (o writer usa mergeSchema; ajuste manual se
-- quiser trocar a chave de partição de versões antigas):
-- ALTER TABLE groceries_ops.similis.recommendations_flat
--   ADD COLUMN categoria STRING
--   COMMENT 'Slug da categoria (ex.: troca_de_fralda)';
-- (Versões antigas particionadas só por (date, subcategoria) precisam ser
--  recriadas para adotar (date, subcategoria, categoria).)

-- Tabelas intermediárias para validação/Toqan antes de publicar nas finais.
-- Mesmo schema das tabelas finais; o pipeline escreve nelas com mode=predict_staging
-- ou mode=predict_all_staging.
CREATE TABLE IF NOT EXISTS groceries_ops.similis.recommendations_staging
LIKE groceries_ops.similis.recommendations;

CREATE TABLE IF NOT EXISTS groceries_ops.similis.recommendations_flat_staging
LIKE groceries_ops.similis.recommendations_flat;

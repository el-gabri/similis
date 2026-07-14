-- Descobre atributos (keys) disponíveis em skus_metadata por subcategoria do universo Similis.
-- Alinhado a parts/subcategory_ids.py e parts/constants.py (mesmos filtros de universo).
--
-- Uso:
--   1) Rode a query "Resumo por subcategoria + key" para ver cobertura e preencher infos.yaml.
--   2) Opcional: descomente o filtro em subcategory_name para uma subcategoria só.
--   3) Use "Sugestão list_columns" para gerar linhas prontas de list_columns por slug.

WITH categorias AS (
  SELECT DISTINCT
    business_categorization.pharmacy.department_name AS department_name,
    business_categorization.pharmacy.category_name AS category_name,
    business_categorization.pharmacy.subcategory_name AS subcategory_name,
    cat.product_name,
    cat.product_ean,
    cat.product_id,
    prod.sku_id
  FROM groceries_ops.assortment.products_categorization cat
  INNER JOIN catalog_product_datasheet.skus_products prod
    ON cat.product_id = prod.product_id
   AND prod.dt = current_date()
  WHERE cat.business_categorization.pharmacy.business_type_name = 'Farmácia'
    AND cat.business_categorization.pharmacy.department_name NOT IN (
      'Medicamentos',
      'Itens de Bloqueio - Farma',
      'Teste Depto Shop'
    )
    AND cat.business_categorization.pharmacy.category_id IN (
      '441544a1-f917-4584-8ff2-7cfa3b48c026','d1468fe7-2149-47f3-a5b1-52e503c14d49',
      '2830b0a6-515d-448a-adc8-15b2cfecaad2','5ae694e9-fd85-450f-a0fb-ce5782287a47',
      'a7758f5a-f600-4f38-a0b9-71f0d6c37614','2f7c2044-2fb4-48a3-a427-83b602dd34f4',
      'f4c821af-34b5-4903-ab59-886315563e26','7b593e03-6c22-4eaa-8818-f1e05cbfab96',
      '30e61051-75db-4130-b788-37d1d27c7974','07919a47-933f-4960-9d9d-366b898500e5',
      'cdab71f6-5696-4866-89b5-9470b823b27d','30e1ad46-1fe7-4f1b-8be7-5065eef2bab1',
      '394ccd18-0fd5-4695-9373-9d69da99c08b','dce2c931-aafa-40b3-80d9-cfe1e8065eed',
      'a9118230-0005-49da-a05d-306f6d24c7bd','8cbada89-951a-4936-b8af-5c41b26a7e09',
      '77c25f6b-b7c1-4644-9693-7b5512001c73','076cf719-09bc-42e7-a4db-a227907ce0d7',
      '53bd0967-19ba-47ad-8296-924133eda166','b7415aaf-c9a7-4b46-b73a-eebe96426335',
      'a7131086-5340-4818-9471-216cedc8eaee','86a93f75-f0f2-450d-8297-c131d92fcb53',
      'df1bba83-8c31-4be4-9164-a738b8dd6333','94099530-463d-4828-9556-616de7dc4ddf',
      'a1029046-fe88-45bf-a746-c04ddfc76ebb','59a6c9e5-206a-4eea-87fb-041aeb40233a',
      '92b42a2a-3da2-40f0-bdce-c974750ca8d6','de4953f4-33db-435a-8bed-85dbabcbbaac',
      '859aa89c-f23a-4180-824e-e2264bb79754','e7a6e53f-88e4-4720-9fc7-d667eb4c5f84',
      '3700719d-d3f4-4c2d-8205-cc141b624089','ae246074-6aa6-4f7e-b220-a3e075e10fa2',
      '5cb22f87-4a82-4338-ad49-d0827cef6fc8','8caabece-a41c-4b07-8a64-9254688b2fb8',
      '23f18550-5d97-4486-b788-d087bbeb3d6c','7bf5de12-aad4-443d-96f6-0cd221345cb8',
      'adedbcfa-f942-461d-8ed2-6dbe8427b316','30b128fc-da24-427c-a886-e9a4a47ca63c',
      '458cedaf-193c-4051-9396-c2f363a4d6e5','a749a874-c2cc-434b-b4b0-b6e21b72e172',
      '1d3228a7-00d4-4f0f-a188-e9149a202120','78301b09-733d-449f-a270-af457a84d392',
      'f47daf7d-b4f3-449a-9fb1-7403476f0e41','3ed6dc4d-e9c4-4620-bc3a-63af4a793c0e',
      'dc8a1746-cf7e-468c-a814-4c1519b72fba','1463522f-4c8d-4fbd-8a2d-9cfcb3fcb5a0',
      'c61c9531-4f72-471d-8327-b98d4bdc2a93','d0b92f2f-8e4c-4fd7-a371-8bb1190edf12',
      '7c8c45d2-aa27-4145-ac1e-151e0877bde3','581da93d-04c3-45cd-a502-6ab5d9b0fe3a',
      '7ca14e2b-d19a-4433-93d6-0278b34c8534','58b42e2a-7196-4e98-93b7-48b222be5b83',
      '6bdda0ca-20e2-44ab-a6e3-4e6c9b9ba2fd','5cbbac59-b854-45f1-b94c-aef71fcbe7e0',
      'f348dbe9-ca18-4bf6-b8db-1cba96bddd06','5822db7a-0cfe-43d2-a4ff-85cd78916386',
      '95bf85f7-1543-45be-8e8e-70ab92d1d0c4','e8572e51-067a-414f-8802-f80e35a79459',
      'c57b8594-1da8-4109-acbf-36561cfc1a3d','5aa8d5a0-c418-4b3c-96bd-9b3dbc3d6d64',
      'e1cce793-223b-4c30-bc15-a219d6bb0f77','d775b1b0-1e76-45b3-a3f6-44b9b0ff1e0b',
      '7a61364e-8c1b-4cf5-ab7a-d12c0e55cffd','ccc388bd-ff8c-45f0-8dd3-4416b4cacc2f',
      'f074056c-125c-41fe-bc91-aff047fed758','c6b04ae7-fb28-48a7-b0e0-f786a76c910e',
      '2f62f9d6-af2e-4d04-8cc4-99c04625999a','5dec6d7f-6866-4baf-8919-d03a810a011a',
      '8658e25c-3bd4-458b-9999-0b64a8ee69bf','d6f54a61-8409-493d-b3bf-735b4e2b6ab0',
      'b0ec9da0-b04a-4b64-84f4-c5d396cc56c7','3068c2a6-8208-4eed-9d3b-0a95b21199b0',
      '954af7c5-10b9-400a-8641-d0e5b1e1f9c9','d3c9dd43-995c-447b-88d5-d7bdc0d1f9c9',
      'a42f957c-bdf7-4e70-9277-6a3c1153a063'
    )
),

universo AS (
  SELECT
    cat.department_name,
    cat.category_name,
    cat.subcategory_name,
    cat.sku_id,
    cat.product_ean
  FROM categorias cat
  -- Para inspecionar UMA subcategoria, filtre pelo PAR (category, subcategory):
  -- o subcategory_name não é único no catálogo (ex.: "Absorvente com Abas"
  -- existe sob "Absorvente Diurno" e "Absorvente Noturno").
  -- WHERE cat.subcategory_name = 'Absorvente com Abas'
  --   AND cat.category_name    = 'Absorvente Diurno'
),

meta AS (
  SELECT
    u.department_name,
    u.category_name,
    u.subcategory_name,
    u.sku_id,
    u.product_ean,
    mt.key,
    mt.value
  FROM universo u
  LEFT JOIN catalog_product_datasheet.skus_metadata mt
    ON mt.sku_id = u.sku_id
   AND mt.dt = current_date()
),

totais_sub AS (
  SELECT
    category_name,
    subcategory_name,
    COUNT(DISTINCT product_ean) AS qtd_ean_subcategoria
  FROM universo
  GROUP BY category_name, subcategory_name
)

-- =============================================================================
-- Query principal: resumo por subcategoria + key (cobertura e exemplos de valor)
-- =============================================================================
SELECT
  m.department_name,
  m.category_name,
  m.subcategory_name,
  m.key,
  COUNT(DISTINCT m.product_ean) AS qtd_ean_com_key,
  t.qtd_ean_subcategoria,
  ROUND(
    100.0 * COUNT(DISTINCT m.product_ean) / NULLIF(t.qtd_ean_subcategoria, 0),
    1
  ) AS pct_cobertura,
  COUNT(DISTINCT m.value) AS qtd_valores_distintos,
  COLLECT_SET(m.value)[0] AS exemplo_valor_1,
  COLLECT_SET(m.value)[1] AS exemplo_valor_2,
  COLLECT_SET(m.value)[2] AS exemplo_valor_3
FROM meta m
INNER JOIN totais_sub t
  ON m.subcategory_name = t.subcategory_name
 AND m.category_name = t.category_name
WHERE m.key IS NOT NULL
  AND TRIM(m.value) <> ''
GROUP BY
  m.department_name,
  m.category_name,
  m.subcategory_name,
  m.key,
  t.qtd_ean_subcategoria
ORDER BY
  m.category_name,
  m.subcategory_name,
  pct_cobertura DESC,
  m.key;

-- =============================================================================
-- (Opcional) Rode em outra célula: subcategorias do universo + volume de EANs
-- =============================================================================
-- SELECT
--   category_name,
--   subcategory_name,
--   department_name,
--   COUNT(DISTINCT product_ean) AS qtd_ean
-- FROM universo
-- GROUP BY ALL
-- ORDER BY qtd_ean DESC;

-- =============================================================================
-- (Opcional) INVENTÁRIO: pares (category_name, subcategory_name) do universo.
-- É a FONTE de parts/constants.py :: _SUBCATEGORY_INVENTORY. Rode e cole a
-- coluna `linha_python` de volta na lista do constants para regenerar os slugs.
-- =============================================================================
-- SELECT
--   category_name,
--   subcategory_name,
--   COUNT(DISTINCT product_ean) AS qtd_ean,
--   CONCAT('    ("', category_name, '", "', subcategory_name, '"),') AS linha_python
-- FROM universo
-- WHERE subcategory_name IS NOT NULL AND TRIM(subcategory_name) <> ''
-- GROUP BY category_name, subcategory_name
-- ORDER BY subcategory_name, category_name;

-- =============================================================================
-- (Opcional) Sugestão de list_columns para infos.yaml (keys com cobertura >= 30%)
-- Inclui product_description (coluna skus.description) e quantity_norm se houver
-- quantity + quantityUnit no metadata.
-- =============================================================================
-- WITH resumo AS (
--   SELECT
--     m.category_name,
--     m.subcategory_name,
--     m.key,
--     COUNT(DISTINCT m.product_ean) AS qtd_ean_com_key,
--     t.qtd_ean_subcategoria,
--     100.0 * COUNT(DISTINCT m.product_ean) / NULLIF(t.qtd_ean_subcategoria, 0) AS pct
--   FROM meta m
--   INNER JOIN totais_sub t
--     ON m.subcategory_name = t.subcategory_name
--    AND m.category_name = t.category_name
--   WHERE m.key IS NOT NULL AND TRIM(m.value) <> ''
--   GROUP BY m.category_name, m.subcategory_name, m.key, t.qtd_ean_subcategoria
-- ),
-- keys_filtradas AS (
--   SELECT category_name, subcategory_name, key
--   FROM resumo
--   WHERE pct >= 30
-- ),
-- por_sub AS (
--   SELECT
--     category_name,
--     subcategory_name,
--     SORT_ARRAY(COLLECT_SET(key)) AS metadata_keys
--   FROM keys_filtradas
--   GROUP BY category_name, subcategory_name
-- )
-- SELECT
--   category_name,
--   subcategory_name,
--   CONCAT(
--     '[product_description, ',
--     CASE
--       WHEN array_contains(metadata_keys, 'quantity')
--        AND array_contains(metadata_keys, 'quantityUnit')
--       THEN 'quantity_norm, '
--       ELSE ''
--     END,
--     ARRAY_JOIN(metadata_keys, ', '),
--     ']'
--   ) AS list_columns_sugerido
-- FROM por_sub
-- ORDER BY category_name, subcategory_name;

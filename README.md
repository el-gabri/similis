# Similis — Sugestão de Substitutos por Similaridade Semântica

Pipeline de recomendação de **produtos substitutos** para um catálogo Farma de e-commerce. Para cada EAN de uma subcategoria, gera uma lista ranqueada de EANs substitutos com base em similaridade semântica de embeddings (BGE-M3), refinada por regras de negócio configuráveis por subcategoria (filtros rígidos, boosts e faixa de quantidade).

> **Status:** _______________ (dev / piloto / produção)
> **Owner:** Gabriel Bonuccelli Heringer Lisboa — Varejo DS
> **Stakeholders:** _______________
> **Job DAB:** `similis_farma` (definido em `resources/similis.yml`)
> **Agendamento:** _______________ (cron / sob demanda)
> **Link do bundle / repo:** _______________

---

## Sumário

1. [Visão geral da arquitetura](#1-visão-geral-da-arquitetura)
2. [Estrutura do repositório](#2-estrutura-do-repositório)
3. [Tabelas de entrada](#3-tabelas-de-entrada)
4. [Tabelas de saída](#4-tabelas-de-saída)
5. [Configuração por subcategoria](#5-configuração-por-subcategoria)
6. [Como o score é calculado](#6-como-o-score-é-calculado)
7. [Atributos sintéticos](#7-atributos-sintéticos)
8. [Cache de embeddings](#8-cache-de-embeddings)
9. [Como executar](#9-como-executar)
10. [Checklist: adicionando uma nova subcategoria](#10-checklist-adicionando-uma-nova-subcategoria)
11. [Diagnóstico e monitoramento](#11-diagnóstico-e-monitoramento)
12. [Versionamento e rastreabilidade](#12-versionamento-e-rastreabilidade)
13. [Limitações conhecidas e roadmap](#13-limitações-conhecidas-e-roadmap)

---

## 1. Visão geral da arquitetura

```
                       ┌────────────────────────────────────────────────┐
                       │ groceries_ops.similis.config_subcategoria      │
                       │ (Delta, populada via mode=bootstrap)           │
                       └──────────────┬─────────────────────────────────┘
                                      │  fallback: infos.yaml
                                      ▼
 products_categorization ──┐   ┌─────────────┐
 skus_products ────────────┼──▶│ data_loader │  universo Farma da subcategoria
 skus ─────────────────────┤   │  (Spark)    │  + pivot dos atributos do
 skus_metadata ────────────┘   └──────┬──────┘  skus_metadata (1 linha/EAN)
                                      │ pandas DataFrame
                                      ▼
                               ┌─────────────┐  limpeza de texto, colunas
                               │ normalizer  │  sintéticas (quantity_norm,
                               └──────┬──────┘  size_norm, audience) e text_canon
                                      ▼
                               ┌─────────────┐  BGE-M3 (1024d, normalizado),
                               │  embedder   │  cache incremental em parquet
                               └──────┬──────┘  no Volume UC, por (ean, hash)
                                      ▼
                               ┌─────────────┐  partição por hard_filter →
                               │   ranker    │  FAISS IP (top-K) → filtro de
                               └──────┬──────┘  quantidade → soft_boost →
                                      │          min_score → rank
                                      ▼
                               ┌─────────────┐  groceries_ops.similis.
                               │   writer    │──▶  recommendations        (aninhada)
                               └─────────────┘──▶  recommendations_flat   (1 linha/par)
```

**Decisão central de design:** os atributos do `skus_metadata` têm três papéis possíveis, definidos por config (não por código):

| `attribute_type` | Efeito |
|---|---|
| `hard_filter` | Particiona o universo. Só EANs com o **mesmo valor** do atributo podem se sugerir mutuamente (ex.: fralda tamanho G só sugere tamanho G). O valor do atributo é **removido** do `text_canon` para não enviesar a similaridade dentro da partição. |
| `soft_boost` | Multiplica o score quando origem e candidato **batem** no atributo (`boost_factor > 1` favorece, `< 1` penaliza). O atributo também entra no `text_canon`. |
| `text_only` (default) | Só entra no `text_canon` (contribui para a similaridade semântica), sem particionar nem alterar score. |
| `ignore` | Fora de tudo. |

---

## 2. Estrutura do repositório

```
src/similis/
├── main.py                      # Entrypoint do job (flags --mode/--subcategories/--top-k
│                                #   ou posicional legado do DAB)
├── infos.yaml                   # Config fonte por subcategoria (fallback do Delta)
├── databricks_similis.ipynb     # Notebook de inspeção interativa + diagnóstico
├── parts/
│   ├── constants.py             # Tabelas, defaults, MODEL_VERSION (re-exporta slugs/inventário)
│   ├── inventory.py             # DADOS: pares (categoria, subcategoria) + category_ids
│   ├── slugs.py                 # Lógica de slug (composto, legado, overrides)
│   ├── config_loader.py         # Merge determinístico Delta > infos.yaml > template
│   ├── config_templates.py      # Templates baseline por família de subcategoria
│   ├── config_generator.py      # Gera infos.generated.yaml a partir dos templates
│   ├── subcategory_policy.py    # Escolha de template por slug/nome
│   ├── bootstrap.py             # Popula a tabela Delta de config a partir do infos.yaml
│   ├── subcategory_ids.py       # Universo de SKUs (business_categorization.pharmacy)
│   ├── data_loader.py           # Catálogo + pivot do skus_metadata (keys via registro)
│   ├── units.py                 # FONTE ÚNICA de unidades/quantidades (parse + conversão)
│   ├── text.py                  # clean_text compartilhado
│   ├── synthetics/              # REGISTRO de atributos sintéticos (1 módulo/domínio)
│   │   ├── base.py              #   SyntheticSpec + register + REGISTRY
│   │   ├── quantity.py          #   quantity_norm, metragem_norm
│   │   ├── fraldas.py           #   size_norm, audience
│   │   ├── leite.py             #   tipo_leite, base_leite, lactose
│   │   ├── formula.py           #   categoria_produto, estagio, tipo_formula
│   │   ├── sabonete.py          #   forma_sabonete, tipo_sabonete
│   │   ├── papel.py             #   tipo_lenco, tipo_folha
│   │   └── misc.py              #   tipo_papinha, tipo_kit
│   ├── universe_filters.py      # Filtros de universo nomeados (universe_exclusions)
│   ├── normalizer.py            # Orquestra: sintéticos da config + limpeza + text_canon
│   ├── embedder.py              # BGE-M3 + cache incremental atômico em Volume UC
│   ├── ranker.py                # Partição + FAISS + filtro de qtd + boost + rank
│   ├── judge.py                 # LLM-as-judge (cliente injetado via judge_fn)
│   └── writer.py                # Grava recommendations e recommendations_flat
├── tests/
│   ├── fixtures/                # Golden fixtures (normalize/rank) + gerador
│   └── test_*.py                # Suite (roda sem Spark; pytest tests/)
├── sql/
│   ├── create_tables.sql        # DDL das tabelas de saída
│   └── discover_metadata_keys.sql  # Cobertura das keys do skus_metadata por subcat
├── notebooks/
│   └── local_test_similis_2.ipynb  # Teste local (CSV Mamãe e Bebê), sem Spark
└── resources/similis.yml        # Definição do job no Databricks Asset Bundle
```

**Para adicionar um atributo sintético novo:** criar/editar UM módulo em
`parts/synthetics/`, registrando com `@register("nome", required_metadata_keys={...})`.
O `data_loader` (keys a pivotar) e o `normalizer` (o que computar) derivam do registro.
O normalizer computa **apenas** os sintéticos que a config da subcategoria usa.

---

## 3. Tabelas de entrada

| Tabela | Uso | Filtros aplicados |
|---|---|---|
| `groceries_ops.assortment.products_categorization` | Universo de produtos | `business_categorization.pharmacy.business_type_name = 'Farmácia'`; `department_name` ∉ {Medicamentos, Itens de Bloqueio - Farma, Teste Depto Shop}; `category_id` na allow-list de UUIDs (`ALLOWED_CATEGORY_IDS`); `subcategory_name` **e** `category_name` da config (o par identifica o universo — ver §5.1) |
| `catalog_product_datasheet.skus_products` | Mapeia produto → SKU | snapshot `dt = current_date()` |
| `catalog_product_datasheet.skus` | Nome e descrição do SKU | snapshot `dt = current_date()` |
| `catalog_product_datasheet.skus_metadata` | Atributos (key/value) | snapshot `dt = current_date()`; só as keys exigidas pela config (+ auxiliares dos sintéticos) |

O `data_loader` pivota o `skus_metadata` (1 coluna por key, `first(value)` por SKU), junta com o universo e devolve um pandas DataFrame deduplicado por EAN.

**Exclusões de segurança:** a subcategoria `medicamentos` está em `EXCLUDED_SUBCATEGORIES` e é bloqueada em todos os entrypoints (job, notebook e bootstrap). Substituição automática de medicamentos está **fora de escopo** por decisão de produto/regulatória.

---

## 4. Tabelas de saída

Ambas Delta, gravadas com `partitionOverwriteMode=dynamic` (cada execução sobrescreve **apenas** a própria partição). O `writer.write_recommendations` grava as duas numa única chamada. Particionamento: a aninhada por `(date, subcategoria)`; a flat por `(date, subcategoria, categoria)` — a `categoria` entra na chave porque a `subcategoria` da flat é o slug legado (sem categoria) e homônimas colidiriam sem ela.

### 4.1 `groceries_ops.similis.recommendations` (aninhada)

Uma linha por EAN de origem.

| Coluna | Tipo | Descrição |
|---|---|---|
| `ean_origem` | STRING | EAN do produto consultado |
| `product_name_origem` | STRING | Nome do produto de origem |
| `subcategoria` | STRING | Slug **simples** (baseado só no `subcategory_name`, ex.: `fraldas`) — contrato histórico. ⚠️ subcategorias homônimas sob categorias diferentes **colidem** nesta partição (ver §5.1). Para o recorte desambiguado, use a `recommendations_flat`. |
| `sugestoes` | STRING | JSON: `[{ean, relevance, rank, product_name}, ...]`, ordenado do melhor para o pior |
| `n_sugestoes` | INT | Tamanho da lista (0 = sem substituto viável) |
| `model_version` | STRING | Versão da lógica/modelo (ver §12) |
| `config_hash` | STRING | MD5 da config usada (ver §12) |
| `date` | STRING | Data da execução (`YYYY-MM-DD`) |

### 4.2 `groceries_ops.similis.recommendations_flat` (para o time de negócios)

O "explode" do JSON: **uma linha por par (origem, substituto)**, em ordem de rank. Filtrável e agregável direto no SQL editor, sem parse de JSON.

| Coluna | Tipo | Descrição |
|---|---|---|
| `ean_origem` | STRING | EAN do produto consultado |
| `product_name_origem` | STRING | Nome do produto de origem |
| `ean_sugestao` | STRING | EAN do substituto |
| `product_name_sugestao` | STRING | Nome do substituto |
| `rank` | INT | Posição na lista (1 = melhor) |
| `relevance` | DOUBLE | Score normalizado (ver §6) |
| `n_sugestoes` | INT | Total de sugestões do EAN de origem |
| `subcategoria` | STRING | Slug **legado** da subcategoria (ex.: `creme_assaduras`) — mesmo vocabulário da aninhada (ver §5.1) |
| `categoria` | STRING | Slug da categoria (ex.: `troca_de_fralda`). O par `(subcategoria, categoria)` desambigua subcategorias homônimas — substitui o antigo slug composto |
| `model_version`, `config_hash`, `date` | | Mesmos da aninhada |

> A flat é particionada por `(date, subcategoria, categoria)` — a `categoria` entra na chave porque a `subcategoria` sozinha (slug legado) colidiria entre homônimas.

> EANs **sem nenhuma sugestão** não geram linha na flat (não há par). Para auditá-los, use a aninhada com `n_sugestoes = 0`.

### 4.3 `groceries_ops.similis.config_subcategoria`

Config "viva" em Delta (1 linha por par subcategoria × atributo), populada via `mode=bootstrap`. Colunas: `subcategoria`, `subcategory_name`, `category_name`, `attribute`, `attribute_type`, `weight`, `boost_factor`, `top_k`, `min_score`, `quantity_ratio_bounds` (JSON string), `active`, `updated_by`, `updated_at`.

> O `bootstrap` cobre **todas** as subcategorias do inventário (`SUBCATEGORIES` em `parts/constants.py`): as curadas usam a config do `infos.yaml`; as demais recebem baseline por template automaticamente. Recria a tabela com `overwriteSchema=true`, então a coluna `category_name` aparece sozinha na próxima execução.

---

## 5. Configuração por subcategoria

### 5.1 Identidade: par `(category_name, subcategory_name)` e slug

O `subcategory_name` **não é único** no catálogo Farma — a mesma subcategoria
aparece sob várias categorias (ex.: `Absorvente com Abas` existe em `Absorvente
Diurno` e `Absorvente Noturno`; `Outros` existe em ~20 categorias). Usar só o
nome misturava universos distintos. Por isso a **identidade é o par
`(category_name, subcategory_name)`**, materializado num **slug** único:

```
<subcategoria>__<categoria>      ex.: fraldas__troca_de_fralda
<subcategoria>                   quando categoria == subcategoria (ex.: bronzeador)
```

- Fonte única de verdade: `SUBCATEGORIES` em `parts/constants.py` (derivada do
  inventário `_SUBCATEGORY_INVENTORY`, que vem de `products_categorization`).
- `get_universe_skus` filtra por `subcategory_name` **e** `category_name`, então
  cada slug recorta exatamente um universo.
- O slug composto é chave de config, nome do arquivo de cache de embeddings e
  valor da partição da `recommendations_flat` — sempre incluir a categoria mantém
  o slug **estável** (uma nova categoria com subcategoria homônima não renomeia um
  slug existente).
- `category_name` descreve o **universo**, não o ruleset → fica **fora do
  `config_hash`** (dois recortes com a mesma config têm o mesmo hash).

**Slug legado na tabela aninhada (`recommendations`):** por decisão de produto,
a coluna `subcategoria` da aninhada mantém o **slug legado histórico**
(`constants.nested_subcategoria(subcategory_name)`), para não quebrar o contrato
do downstream. Ele é o `simple_slug(subcategory_name)` (ex.: `fraldas`), com um
punhado de **exceções** em `LEGACY_NESTED_SLUG_OVERRIDES` — slugs abreviados
(`Creme para Assaduras` → `creme_assaduras`) ou que preservam hífen/vírgula
(`Roll-on` → `roll-on`, `Cama, Mesa e Banho` → `cama,_mesa_e_banho`), validados
1:1 contra o dicionário `SUBCATEGORY_NAMES` do consumidor. Como esse slug é chave
de partição e **não** inclui a categoria, as subcategorias homônimas **colidem na
mesma partição** e, com `partitionOverwriteMode=dynamic`, só a última execução do
dia sobrevive (ex.: as 22 categorias com subcategoria `Outros` colapsam em
`outros`; Absorvente Diurno vs Noturno colidem em `absorvente_com_abas`). O
recorte **sem perda** e desambiguado vive na `recommendations_flat`, que usa o
mesmo `subcategoria` legado **mais** a coluna `categoria` (slug, ex.:
`troca_de_fralda`) — o par `(subcategoria, categoria)` identifica o universo e
entra na chave de partição. Sempre derive o slug da aninhada com
`constants.nested_subcategoria(subcategory_name)` e o da categoria com
`constants.category_slug(category_name)` (nunca `simple_slug`/`_slugify` direto).

O antigo slug **composto** (`subcategoria__categoria`) deixou de ser gravado nas
saídas — era um paliativo para diferenciar homônimas numa única coluna. Ele
permanece apenas como identidade interna de config, cache de embeddings e
argumento `SUBCATEGORY_SLUG`.

Para regenerar o inventário: rode a query "INVENTÁRIO" de
`sql/discover_metadata_keys.sql` e cole a coluna `linha_python` em
`_SUBCATEGORY_INVENTORY`.

### Precedência

O `ConfigLoader` resolve a config nesta ordem:

1. **Delta** (`config_subcategoria`, linhas `active = true`) — fonte primária em produção.
2. **`infos.yaml`** — fallback quando a tabela está vazia/indisponível, e complemento de campos ausentes no Delta (`subcategory_name`, `category_name`, `quantity_ratio_bounds`).
3. **Template** (`parts/config_templates.py` via `subcategory_policy`) — baseline automático para qualquer slug do inventário sem entrada no Delta nem no `infos.yaml`. `category_name` também é completado a partir de `SUBCATEGORIES` quando ausente nas fontes acima.

Mudou o YAML? Rode `bootstrap` para refletir no Delta (senão produção continua lendo a config antiga da tabela).

O `infos.yaml` contém **apenas a curadoria manual** (subcategorias com config afinada à mão); as demais dependem do baseline por template (passo 3).

### Anatomia de uma entrada do `infos.yaml`

```yaml
list_ids:
  fraldas__troca_de_fralda:            # slug = subcategoria__categoria (§5.1)
    subcategory_name: "Fraldas"        # nome literal em business_categorization
    category_name: "Troca de Fralda"   # desambigua o universo (filtro + flat)
    top_k: 50                          # máx. de sugestões por EAN
    min_score: 0.5                     # corte sobre o score pós-boost
    quantity_ratio_bounds: [0.5, 2.0]  # faixa de contagem aceita (opcional)
    list_columns:                      # keys do skus_metadata + sintéticos
      - size_norm
      - audience
      - brandName
      # ...
    config_overrides:                  # só onde diverge do default (text_only)
      size_norm:
        attribute_type: hard_filter
      quantity_norm:
        attribute_type: soft_boost
        boost_factor: 1.15
```

**Defaults implícitos** (em `parts/constants.py`): `attribute_type: text_only`, `weight: 1.0` (atributo repetido 3× no `text_canon`; `repeat = round(weight × 3)`), `boost_factor: 1.0` (neutro), `top_k: 50`, `min_score: 0.50`.

**`quantity_ratio_bounds`** descarta candidatos cuja quantidade esteja fora de `[lo×origem, hi×origem]` (ex.: fralda 96un nunca sugere 10un). A comparação só ocorre quando as quantidades de origem e candidato são parseáveis e da **mesma dimensão** — unidades de massa, volume e contagem são convertidas para forma canônica (kg→g, l→ml, unidades→un) antes da comparação; unidades desconhecidas exigem igualdade literal. Quando não dá para comparar, o candidato é **mantido** (conservador).

---

## 6. Como o score é calculado

Para cada EAN de origem, dentro da sua partição de `hard_filter`:

1. **Similaridade base** — cosseno entre os embeddings BGE-M3 do `text_canon` (busca top-K via FAISS `IndexFlatIP` sobre vetores L2-normalizados; fallback numpy quando `faiss-cpu` não está instalado).
2. **Filtro de quantidade** — se `quantity_ratio_bounds` está configurado, candidatos fora da faixa são descartados antes de qualquer boost.
3. **Soft boost** — `score = similaridade × ∏ boost_factor` das regras `soft_boost` cujos valores **batem** entre origem e candidato (comparação case-insensitive, strings vazias não batem).
4. **Corte** — candidatos com score pós-boost `< min_score` são descartados.
5. **Rank** — ordenação decrescente por score; top-K recebe `rank` 1..K.
6. **Normalização da `relevance`** — os scores da **rodada inteira** são divididos pelo máximo observado, reescalando para `[0, 1]` (preserva a ordem; o melhor par da rodada tem `relevance = 1.0`).

> ⚠️ **Interpretação da `relevance`:** por causa do passo 6, a relevância é **relativa à rodada** — não compare valores absolutos entre subcategorias nem entre datas diferentes. Para comparações entre rodadas, use o `rank` ou aguarde a migração para score bruto (ver §13).

---

## 7. Atributos sintéticos

Calculados no `normalizer` (`SYNTHETIC_ATTRIBUTES = {quantity_norm, size_norm, product_description, audience}`); não existem como keys no `skus_metadata`:

| Coluna | Como é calculada | Uso típico |
|---|---|---|
| `quantity_norm` | Cascata: (1) `quantity` + `quantityUnit` do metadata, convertidos para unidade canônica (g / ml / un); (2) fallback: parser de pack size sobre o `PRODUCT_NAME` (trata multipacks: "6x22", "24 pacotes com 7un" → contagem **total**) | `soft_boost` + alvo do filtro de quantidade |
| `size_norm` | Tamanho canônico de fralda (RN/P/M/G/XG/XXG/XXXG), consolidando `sizeClassification` → `diaperSize` → regex no `PRODUCT_NAME`. **Não** use as 3 keys de origem como atributos independentes (dupla contagem + fragmentação) | `hard_filter` em fraldas |
| `audience` | `adulto` se o nome bate em padrão geriátrico/incontinência (Tena, Bigfral, Plenitud...), senão `bebe` | `hard_filter` em fraldas — impede fralda adulta de poluir o universo infantil |
| `product_description` | Descrição do datasheet, limpa; entra no `text_canon` | semântica |

### `text_canon`

Texto canônico que vai para o embedding: `PRODUCT_NAME` limpo + descrição + atributos `soft_boost`/`text_only` repetidos `round(weight × 3)` vezes. Tokens dos valores de `hard_filter` são **removidos** do texto final (já estão garantidos pela partição; mantê-los inflaria a similaridade de forma redundante). Limpeza: lowercase, ASCII-fold (unidecode), normalização de unidades.

---

## 8. Cache de embeddings

- Local: `/Volumes/groceries_ops/similis/embeddings_cache/<slug>.parquet` (sobrescrevível via env `SIMILIS_EMBEDDINGS_CACHE_DIR`).
- Granularidade: por par `(ean, md5(text_canon))` — só recomputa EANs novos ou cujo texto mudou.
- Invalidação automática: cache cuja dimensão não bate com a do modelo carregado é descartado.
- ⚠️ Se trocar de modelo de embedding mantendo a **mesma dimensão**, limpe o cache manualmente — a invalidação automática só detecta mudança de dimensão.
- Tempo de referência: primeira execução de uma subcategoria leva ~10–90 min em CPU (depende do nº de EANs); releituras são em segundos.

---

## 9. Como executar

### 9.1 Job de produção (Databricks Asset Bundle)

```bash
databricks bundle deploy --target dev

# predict (default): todas as subcategorias de FARMA_SUBCATEGORIES_DEFAULT
databricks bundle run similis_farma --target dev

# predict de subcategorias específicas
databricks bundle run similis_farma --target dev \
  --params subcategories='["fraldas", "lencos_umedecidos"]'

# bootstrap: (re)popula config_subcategoria a partir do infos.yaml
databricks bundle run similis_farma --target dev --params mode=bootstrap
```

Argumentos posicionais do `main.py`: `subcategories` (lista ou string), `mode` (`predict` | `bootstrap`), `top_k` (default 50). O bootstrap sempre repovoa **todas** as subcategorias Farma (overwrite completo da tabela de config, evita estado parcial no `for_each`).

### 9.2 Notebook interativo (`databricks_similis.ipynb`)

Para inspeção qualitativa, tuning de config e diagnóstico. Cluster sugerido: **Spark 15.4 LTS, Python 3.10**, com leitura nas tabelas e no Volume. Seções:

1–2. Setup (pin de libs + `sys.path`) e carga da config da subcategoria.
3. Catálogo + normalização + embeddings (com `TEST_SAMPLE` para iteração rápida).
4. Ranker + amostra qualitativa (`explore_ean`) para revisão humana.
5. Gravação nas duas tabelas + previews.
6. Loop por várias subcategorias.
7. **Diagnóstico**: boxplot de `n_sugestoes` por subcategoria, distribuição das relevâncias (describe, boxplot, decaimento mediano por rank).

### 9.3 Teste local (sem Spark)

`src/similis/notebooks/local_test_similis_2.ipynb` roda o pipeline sobre o CSV de Mamãe e Bebê (`similis_2.csv`), útil para iterar no normalizer/ranker sem cluster. O ranker tem fallback numpy quando `faiss-cpu` não está disponível.

### 9.4 Dependências (pinadas no notebook e no `resources/similis.yml`)

```
numpy==1.24.4  pandas==1.5.3  scipy==1.11.4  torch==2.3.1
transformers==4.46.3  sentence-transformers==3.3.1  huggingface_hub==0.25.2
scikit-learn==1.3.2  faiss-cpu  unidecode  pyyaml  pyarrow
```

> Nota: no notebook, o Arrow é desabilitado antes do `toPandas()` (incompatibilidade numpy 1.24 × pyarrow do DBR) e reabilitado antes do write.

---

## 10. Checklist: adicionando uma nova subcategoria

1. **Garantir o par no inventário** — o slug precisa existir em `SUBCATEGORIES` (`parts/constants.py`). Se for um par `(category_name, subcategory_name)` novo, adicione-o em `_SUBCATEGORY_INVENTORY` (rode a query "INVENTÁRIO" de `discover_metadata_keys.sql`). `SUBCATEGORY_NAMES`, `SUBCATEGORY_CATEGORIES` e `FARMA_SUBCATEGORIES_DEFAULT` são derivados automaticamente.
2. **Descobrir atributos disponíveis** — rodar `src/similis/sql/discover_metadata_keys.sql` em produção, descomentando o filtro pelo **par** (`AND cat.subcategory_name = '<nome>' AND cat.category_name = '<categoria>'`). Manter só keys com **cobertura ≥ 30%**.
3. **(Opcional) Curar no `infos.yaml`** — só se quiser divergir do baseline por template: use o **slug** como chave, com `subcategory_name` e `category_name` literais, `list_columns` com as keys aprovadas, `top_k`/`min_score`. Sem curadoria, o passo do bootstrap/predict já aplica o template.
4. **Definir hard_filters com cautela** — um `hard_filter` em atributo de baixa cobertura ou alta cardinalidade **esvazia partições** (EANs sozinhos na partição ficam com 0 sugestões). Em universos pequenos (< ~20 EANs), prefira só `soft_boost`.
5. **Bootstrap** — `databricks bundle run similis_farma --params mode=bootstrap`.
6. **Predict + revisão amostral** — rodar a subcategoria e revisar qualitativamente no notebook (seção 4) antes de liberar para consumo.
7. **Diagnóstico** — conferir na seção 7 do notebook: % de EANs sem sugestão, formato da distribuição de relevâncias, decaimento por rank.

Cuidados específicos já mapeados na curadoria do `infos.yaml`: `formula_infantil__alimentacao_infantil` (estágio/tipo são **críticos** — fórmula 1+ não substitui 0-6m; 4 hard_filters de segurança), `leite_em_po__alimentacao_infantil` (integral/desnatado, base do leite, lactose), `creme_para_assaduras__troca_de_fralda` (separar público adulto/geriátrico do bebê via `audience`).

---

## 11. Diagnóstico e monitoramento

**No notebook (seção 7):** distribuição de `n_sugestoes` por subcategoria (caudas em 0 indicam `min_score` agressivo ou partições esvaziadas por `hard_filter`), distribuição de relevâncias e decaimento mediano por rank (informa calibração de `top_k`/`min_score`).

**Queries úteis para o time de negócios (flat):**

```sql
-- Substitutos do EAN X na rodada mais recente
SELECT * FROM groceries_ops.similis.recommendations_flat
WHERE ean_origem = '<EAN>'
  AND date = (SELECT MAX(date) FROM groceries_ops.similis.recommendations_flat)
ORDER BY rank;

-- Saúde por subcategoria
SELECT subcategoria, date,
       COUNT(DISTINCT ean_origem) AS eans_com_sugestao,
       COUNT(*)                   AS pares,
       AVG(relevance)             AS relevancia_media
FROM groceries_ops.similis.recommendations_flat
GROUP BY subcategoria, date
ORDER BY date DESC, subcategoria;
```

**Alertas / SLAs:** _______________ (definir: % máximo de EANs sem sugestão por subcategoria, freshness da partição, volume mínimo de pares)

**Métricas de negócio downstream:** _______________ (ex.: taxa de aceite da substituição no app, % de pedidos salvos por stockout — integrar quando houver consumo em produção)

---

## 12. Versionamento e rastreabilidade

Cada partição carrega dois identificadores:

- **`model_version`** (`parts/constants.py`, ex.: `bge-m3-v1.1`) — rótulo manual da versão da **lógica** do pipeline. Deve receber bump a cada mudança que altere os resultados sem alterar a config (ex.: mudança no filtro de quantidade, no normalizer, no cálculo de score). **Não** troca o modelo de embedding — isso é `EMBEDDING_MODEL_NAME`.
- **`config_hash`** — MD5 determinístico da config efetiva (regras ordenadas + `top_k` + `min_score` + `quantity_ratio_bounds` quando definido). Muda automaticamente quando a config muda; permite saber exatamente qual configuração gerou cada partição.

Regra prática: **mudou código → bump em `MODEL_VERSION`; mudou YAML/tabela de config → o `config_hash` cuida sozinho** (mas rode o bootstrap para o Delta refletir o YAML).

Histórico de versões:

| `model_version` | Data | Mudança |
|---|---|---|
| `bge-m3-v1.0` | _______ | Versão inicial (BGE-M3 + hard_filter/soft_boost + filtro de quantidade por unidade literal) |
| `bge-m3-v1.1` | _______ | Conversão de unidades no filtro de quantidade (kg↔g, l↔ml, sinônimos de "un"), aceita vírgula decimal; tabela `recommendations_flat` |
| `bge-m3-v1.5` | _______ | Identidade por par `(category_name, subcategory_name)`: universo filtra também por `category_name`; slug composto `subcategoria__categoria` na config/cache/`recommendations_flat` + coluna `category_name` (fora do `config_hash`). A `recommendations` (aninhada) mantém o slug **simples** histórico na coluna `subcategoria` (homônimas colidem — ver §5.1) |
| `bge-m3-v1.6` | 2026-07-05 | **Fix**: regex de metragem duplicada/sombreada — com IGNORECASE, "250ml" era parseado como metragem "250 m" (poluía `metragem_norm`/`text_canon` de líquidos); agora fronteira de palavra + faixa de plausibilidade 5–600 m. Unificação das tabelas de unidade (normalizer × ranker) em `parts/units.py`. Refactor estrutural: registro de sintéticos (`parts/synthetics/`), `universe_exclusions` por config (substitui bloco hard-coded do leite em pó), merge de config determinístico com hash único. **Sem mudança de schema** nas tabelas de saída. Flags novas (default = comportamento anterior): `min_score_basis`, `suppress_same_product`, `universe_exclusions` |
| `bge-m3-v1.7` | 2026-07-08 | Correções guiadas pelo judge sobre a baseline (docs/lotes_toqan/): **fallback do `quantity_norm` em modo `count` vira unit-aware** — respeita `quantityUnit` ml/g/l do metadata em vez de cunhar "N un" (53 subcategorias comparavam volume como contagem). Sintéticos novos: `forma_bebida` (pó/cápsula × pronto), `faixa_etaria_bebe` (fase 0-6m × 6m+), `tipo_bateria` (AA/AAA/9V/botão), `tipo_agua_terapeutica` (boricada × oxigenada), `fluor` e templates `laticinios`/`higiene_oral`/`baterias`/`agua_terapeutica`. Exclusions W4 por default de slug (açúcar em adoçante, pastilha medicinal em balas, corticoide em dermocosméticos, absorvente externo em tampão, sem-álcool em alcoólicas, coletor hospitalar em bolsa térmica, geriátrico em absorvente). **Sem mudança de schema** |
| `bge-m3-v1.7.1` | 2026-07-08 | **`quantity`/`quantityUnit`/`unit` crus removidos do `text_canon`** (entravam como `text_only` e jogavam "200", "ML", "UN" no embedding — a quantidade agora entra só via `quantity_norm` canônico; o metadata segue carregado para o sintético). `forma_desodorante` ganha o rótulo `colonia_splash` (perfumaria ≠ antitranspirante) e fallback por `packagingName` quando o nome é mudo. Ambos derivados do teste manual do `aerosol_e_spray`. `candidate_pool_multiplier` default = 1 (era 3), omitido do YAML gerado. **Sem mudança de schema** |

---

## 13. Limitações conhecidas e roadmap

**Limitações atuais:**

- `relevance` é normalizada pelo máximo **da rodada** — não é comparável entre subcategorias/datas (ver §6). Candidato a mudança: expor score bruto (`score_raw`) ou normalizar por origem.
- `min_score` é aplicado **pós-boost**: um boost pode "salvar" candidato semanticamente fraco. Avaliar aplicar o corte sobre a similaridade pura.
- O FAISS busca `top_k + 1` vizinhos; quando o filtro de quantidade descarta muitos, o EAN pode entregar menos de `top_k` sugestões mesmo havendo candidatos válidos mais distantes. Mitigação: buscar com folga (ex.: `3×top_k`) quando `quantity_ratio_bounds` está ativo.
- EANs duplicados do mesmo produto (variações de cadastro) podem se sugerir mutuamente com relevância ~1.0. Mitigação planejada: cruzar com o agrupamento EAN→SKU para suprimir auto-substituição.
- `date` é STRING nas tabelas (comparação lexicográfica funciona para `YYYY-MM-DD`, mas DATE seria mais robusto para pruning e UX no SQL editor).
- Sem avaliação offline sistemática (golden set / revisão estruturada) — hoje a validação é amostral no notebook.
- `mergeSchema=true` no write permite drift silencioso de schema; remover quando o schema estabilizar.

**Roadmap:** _______________ (priorizar com Clarissa/stakeholders — sugestões: score bruto na flat, `age_norm` para fórmulas, dedup por produto, golden set de avaliação, expansão para as subcategorias Farma pendentes do `infos.yaml`)

---

## Contato

| Papel | Nome | Contato |
|---|---|---|
| Owner / DS | Gabriel B. H. Lisboa | _______________ |
| Manager | _______________ | _______________ |
| Negócio (Farma) | _______________ | _______________ |

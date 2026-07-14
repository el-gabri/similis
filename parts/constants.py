# -*- coding: utf-8 -*-
"""Constantes do pipeline Similis Farma.

Dados de inventário (pares categoria/subcategoria, category_ids) vivem em
``parts/inventory.py``; lógica de slug em ``parts/slugs.py``. Este módulo
mantém re-exports para compatibilidade (``from parts.constants import
nested_subcategoria`` etc. seguem funcionando).
"""

from collections import namedtuple

from parts.inventory import ALLOWED_CATEGORY_IDS, _SUBCATEGORY_INVENTORY  # noqa: F401
from parts.slugs import (  # noqa: F401 (re-exports de compatibilidade)
    LEGACY_NESTED_SLUG_OVERRIDES,
    _slugify,
    category_slug,
    nested_subcategoria,
    simple_slug,
    subcategory_slug as _subcategory_slug,
)

# Versão da LÓGICA do pipeline. Bump a cada mudança de código que altere
# resultados sem alterar config. Histórico no README §12.
# v1.6: fix da regex de metragem (dupla definição sombreada) + faixa de
#       plausibilidade 5–600 m; unificação das tabelas de unidade
#       (normalizer × ranker) em parts/units.py.
# v1.7: fallback do quantity_norm em modo count vira unit-aware (respeita o
#       quantityUnit ml/g/l do metadata em vez de cunhar "N un"); sintéticos
#       novos (forma_bebida, faixa_etaria_bebe, tipo_bateria,
#       tipo_agua_terapeutica) + exclusions W4 por default de slug.
# v1.7.1: quantity/quantityUnit/unit CRUS saem do text_canon (poluíam o
#       embedding); forma_desodorante ganha rótulo colonia_splash e fallback
#       por packagingName (correções do teste manual do aerosol_e_spray).
MODEL_VERSION = "bge-m3-v1.7.1"
EMBEDDING_MODEL_NAME = "BAAI/bge-m3"

CONFIG_TABLE = "groceries_ops.similis.config_atributos_subcategoria"
RECOMMENDATIONS_TABLE = "groceries_ops.similis.recommendations"
RECOMMENDATIONS_FLAT_TABLE = "groceries_ops.similis.recommendations_flat"
RECOMMENDATIONS_STAGING_TABLE = "groceries_ops.similis.recommendations_staging"
RECOMMENDATIONS_FLAT_STAGING_TABLE = "groceries_ops.similis.recommendations_flat_staging"

# Universo de atuação: products_categorization + skus + skus_metadata.
PRODUCTS_CATEGORIZATION_TABLE = "groceries_ops.assortment.products_categorization"
SKUS_TABLE = "catalog_product_datasheet.skus"
SKUS_PRODUCTS_TABLE = "catalog_product_datasheet.skus_products"
SKUS_METADATA_TABLE = "catalog_product_datasheet.skus_metadata"

EMBEDDINGS_CACHE_VOLUME = "/Volumes/groceries_ops/similis/embeddings_cache"

DEFAULT_VERTICAL = "pharmacy"
DEFAULT_BUSINESS_TYPE = "Farmácia"
DEFAULT_TOP_K = 100
DEFAULT_MIN_SCORE = 0.51
# Atributos sem override no infos.yaml herdam estes valores.
# weight=1.0  ⇒ atributo é repetido 3× no text_canon (round(weight*3) = 3).
# boost_factor=1.0 ⇒ não há boost (multiplicação neutra).
DEFAULT_SOFT_WEIGHT = 1.0
DEFAULT_BOOST_FACTOR = 1.0
# Atributos sem `attribute_type` no YAML são ``text_only``.
DEFAULT_ATTRIBUTE_TYPE = "text_only"
# Base do corte min_score: "boosted" (pós-boost, comportamento histórico) ou
# "raw_similarity" (similaridade pura, para universos de alto risco onde um
# boost não deve "salvar" candidato semanticamente fraco).
DEFAULT_MIN_SCORE_BASIS = "boosted"
MIN_SCORE_BASES = frozenset({"boosted", "raw_similarity"})

EXCLUDED_SUBCATEGORIES = frozenset({"medicamentos"})

# Departments do business_categorization.pharmacy que ficam fora do universo.
EXCLUDED_DEPARTMENTS = frozenset(
    {"Medicamentos", "Itens de Bloqueio - Farma", "Teste Depto Shop"}
)

ATTRIBUTE_TYPES = frozenset({"hard_filter", "soft_boost", "text_only", "ignore"})


Subcat = namedtuple("Subcat", ["category_name", "subcategory_name"])


def _build_subcategories(inventory):
    """Constrói o mapa ``slug -> Subcat``; erro em colisão de slug entre pares
    DIFERENTES."""
    out = {}
    for category_name, subcategory_name in inventory:
        category_name = str(category_name).strip()
        subcategory_name = str(subcategory_name).strip()
        if not subcategory_name:
            continue
        slug = _subcategory_slug(category_name, subcategory_name)
        value = Subcat(category_name=category_name, subcategory_name=subcategory_name)
        existing = out.get(slug)
        if existing is not None and existing != value:
            raise ValueError(
                f"Colisão de slug {slug!r}: {existing} vs {value}. "
                f"Ajuste a convenção de slug ou o inventário."
            )
        out[slug] = value
    return out


# Fonte única de verdade: slug -> (category_name, subcategory_name).
SUBCATEGORIES = _build_subcategories(_SUBCATEGORY_INVENTORY)

# Derivados (mantêm compatibilidade com o restante do pipeline).
SUBCATEGORY_NAMES = {slug: sc.subcategory_name for slug, sc in SUBCATEGORIES.items()}
SUBCATEGORY_CATEGORIES = {slug: sc.category_name for slug, sc in SUBCATEGORIES.items()}
KNOWN_SUBCATEGORY_NAMES = frozenset(SUBCATEGORY_NAMES.values())

FARMA_SUBCATEGORIES_DEFAULT = list(SUBCATEGORIES.keys())

# -*- coding: utf-8 -*-
"""Templates de configuração para escalar o Similis para muitas subcategorias.

Os templates são intencionalmente conservadores: geram uma base funcional para
subcategorias sem curadoria manual, deixando `hard_filter` apenas nos universos
onde a troca errada tem risco claro.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


OverrideMap = Dict[str, Dict[str, object]]


@dataclass(frozen=True)
class ConfigTemplate:
    name: str
    list_columns: List[str]
    config_overrides: OverrideMap = field(default_factory=dict)
    top_k: int = 100
    min_score: float = 0.51
    quantity_kind: str = "count"
    quantity_ratio_bounds: Optional[Tuple[float, float]] = (0.5, 2.0)
    # 1 = busca exatamente top_k+1 vizinhos (sem folga). Subir por
    # subcategoria APENAS se n_sugestoes cair demais pós-filtro de
    # quantidade (README §13).
    candidate_pool_multiplier: int = 1
    risk: str = "baixo"


# NOTA: quantity/quantityUnit/unit CRUS ficam FORA da lista — como rules
# text_only eles jogavam "200", "ML", "UN" no text_canon (poluição de
# embedding). A quantidade entra só pela forma canônica quantity_norm; o
# data_loader continua carregando quantity/quantityUnit para o sintético via
# required_metadata_keys do registry.
COMMON_COLUMNS = [
    "brandName",
    "quantity_norm",
    "packagingName",
    "productType",
    "purpose",
    "additionalInfo",
    "shortName",
    "product_description",
]


DEFAULT_TEMPLATE = ConfigTemplate(
    name="default",
    list_columns=COMMON_COLUMNS,
    config_overrides={
        "quantity_norm": {"attribute_type": "soft_boost", "boost_factor": 1.15},
    },
)


HIGIENE_TEMPLATE = ConfigTemplate(
    name="higiene",
    list_columns=COMMON_COLUMNS,
    config_overrides={
        "quantity_norm": {"attribute_type": "soft_boost", "boost_factor": 1.15},
        "productType": {"attribute_type": "soft_boost", "boost_factor": 1.10},
        "purpose": {"attribute_type": "soft_boost", "boost_factor": 1.10},
    },
    risk="medio",
)


ALIMENTOS_BEBIDAS_TEMPLATE = ConfigTemplate(
    name="alimentos_bebidas",
    list_columns=[
        # forma_bebida [v1.7]: pó/cápsula não substitui pronto (judge: 940×
        # em achocolatado_pronto, 52× whey vs barra, 21× cápsula vs chá).
        # hard_filter conservador: só separa quando a forma é DECLARADA.
        "forma_bebida",
        *COMMON_COLUMNS,
    ],
    config_overrides={
        "forma_bebida": {"attribute_type": "hard_filter"},
        "quantity_norm": {"attribute_type": "soft_boost", "boost_factor": 1.15},
        "productType": {"attribute_type": "soft_boost", "boost_factor": 1.10},
    },
    quantity_kind="mass",
    risk="medio",
)


BEBE_CUIDADOS_TEMPLATE = ConfigTemplate(
    name="bebe_cuidados",
    list_columns=[
        "audience",
        # faixa_etaria_bebe [v1.7]: chupeta/bico/mamadeira de fase errada é
        # eixo de segurança (judge: 28× "0-6m vs 6+m" em chupetas). '' quando
        # não declarada — não fragmenta o resto da família.
        "faixa_etaria_bebe",
        *COMMON_COLUMNS,
    ],
    config_overrides={
        "audience": {"attribute_type": "hard_filter"},
        "faixa_etaria_bebe": {"attribute_type": "hard_filter"},
        "quantity_norm": {"attribute_type": "soft_boost", "boost_factor": 1.15},
        "productType": {"attribute_type": "soft_boost", "boost_factor": 1.10},
    },
    risk="medio",
)


# Baterias/pilhas (judge: 250× "tipo incompatível: AAA vs AA" em
# baterias_para_monitores — era o falso "problema de quantidade" da W1).
BATERIAS_TEMPLATE = ConfigTemplate(
    name="baterias",
    list_columns=[
        "tipo_bateria",
        *COMMON_COLUMNS,
    ],
    config_overrides={
        "tipo_bateria": {"attribute_type": "hard_filter"},
        "quantity_norm": {"attribute_type": "soft_boost", "boost_factor": 1.15},
    },
    risk="medio",
)


# Águas terapêuticas (judge: 216× "boricada vs oxigenada: uso terapêutico
# distinto" em agua_oxigenada_e_boricada).
AGUA_TERAPEUTICA_TEMPLATE = ConfigTemplate(
    name="agua_terapeutica",
    list_columns=[
        "tipo_agua_terapeutica",
        *COMMON_COLUMNS,
    ],
    config_overrides={
        "tipo_agua_terapeutica": {"attribute_type": "hard_filter"},
        "quantity_norm": {"attribute_type": "soft_boost", "boost_factor": 1.15},
    },
    quantity_kind="mass",
    risk="alto",
)


FRALDAS_TEMPLATE = ConfigTemplate(
    name="fraldas",
    list_columns=[
        "size_norm",
        "audience",
        *COMMON_COLUMNS,
        "ageRange",
        "diaperSizeWeight",
        "protection",
        "protectionType",
        "hypoallergenic",
        "wetnessIndicator",
        "moistureIndicator",
    ],
    config_overrides={
        "size_norm": {"attribute_type": "hard_filter"},
        "audience": {"attribute_type": "hard_filter"},
        "quantity_norm": {"attribute_type": "soft_boost", "boost_factor": 1.15},
    },
    risk="medio",
)


FORMULA_INFANTIL_TEMPLATE = ConfigTemplate(
    name="formula_infantil",
    list_columns=[
        "categoria_produto",
        "estagio",
        "tipo_formula",
        "lactose",
        "brandName",
        "quantity_norm",
        "packagingName",
        "ageRange",
        "additionalInfo",
        "shortName",
        "product_description",
    ],
    config_overrides={
        "categoria_produto": {"attribute_type": "hard_filter"},
        "estagio": {"attribute_type": "hard_filter"},
        "tipo_formula": {"attribute_type": "hard_filter"},
        "lactose": {"attribute_type": "hard_filter"},
        "quantity_norm": {"attribute_type": "soft_boost", "boost_factor": 1.15},
    },
    quantity_kind="mass",
    risk="alto",
)


LEITE_EM_PO_TEMPLATE = ConfigTemplate(
    name="leite_em_po",
    list_columns=[
        "base_leite",
        "tipo_leite",
        "lactose",
        *COMMON_COLUMNS,
    ],
    config_overrides={
        "base_leite": {"attribute_type": "soft_boost", "boost_factor": 1.30},
        "tipo_leite": {"attribute_type": "hard_filter"},
        "lactose": {"attribute_type": "hard_filter"},
        "quantity_norm": {"attribute_type": "soft_boost", "boost_factor": 1.15},
    },
    min_score=0.70,
    quantity_kind="mass",
    risk="alto",
)


PAPINHA_TEMPLATE = ConfigTemplate(
    name="papinha",
    list_columns=[
        "tipo_papinha",
        *COMMON_COLUMNS,
    ],
    config_overrides={
        "tipo_papinha": {"attribute_type": "soft_boost", "boost_factor": 1.20},
        "quantity_norm": {"attribute_type": "soft_boost", "boost_factor": 1.10},
    },
    quantity_kind="mass",
    risk="medio",
)


PAPEL_LENCO_TEMPLATE = ConfigTemplate(
    name="papel_lenco",
    list_columns=[
        "tipo_lenco",
        "tipo_folha",
        "metragem_norm",
        *COMMON_COLUMNS,
    ],
    config_overrides={
        "tipo_lenco": {"attribute_type": "soft_boost", "boost_factor": 1.20},
        "tipo_folha": {"attribute_type": "soft_boost", "boost_factor": 1.20},
        "metragem_norm": {"attribute_type": "soft_boost", "boost_factor": 1.15},
        "quantity_norm": {"attribute_type": "soft_boost", "boost_factor": 1.20},
    },
    quantity_ratio_bounds=(0.25, 4.0),
    risk="baixo",
)


# Laticínios líquidos/frescos (Leites, Leite Fermentado, Iogurte Diversos).
# Judge sobre a baseline: 363× (leites) + 182× (leite fermentado) + 129×
# (iogurte) "restrição sem-lactose vs produto com lactose" — intolerância é
# restrição alimentar → hard_filter no sintético `lactose` (já existente).
# Volumes em ml/g com desproporção frequente (100g vs 900g) → mass + bounds.
LATICINIOS_TEMPLATE = ConfigTemplate(
    name="laticinios",
    list_columns=[
        "lactose",
        *COMMON_COLUMNS,
    ],
    config_overrides={
        "lactose": {"attribute_type": "hard_filter"},
        "quantity_norm": {"attribute_type": "soft_boost", "boost_factor": 1.15},
        "productType": {"attribute_type": "soft_boost", "boost_factor": 1.10},
    },
    quantity_kind="mass",
    quantity_ratio_bounds=(0.5, 2.0),
    risk="alto",
)


# Higiene oral — cremes e géis dentais (adulto e infantil). Judge: 215×+39×
# "sem flúor vs com flúor: restrição pediátrica" → hard_filter no sintético
# `fluor`. Medido em g (90g, 180g...) → mass + bounds (280g vs 90g reprovava).
HIGIENE_ORAL_TEMPLATE = ConfigTemplate(
    name="higiene_oral",
    list_columns=[
        "fluor",
        *COMMON_COLUMNS,
    ],
    config_overrides={
        "fluor": {"attribute_type": "hard_filter"},
        "quantity_norm": {"attribute_type": "soft_boost", "boost_factor": 1.15},
        "productType": {"attribute_type": "soft_boost", "boost_factor": 1.10},
        "purpose": {"attribute_type": "soft_boost", "boost_factor": 1.10},
    },
    quantity_kind="mass",
    quantity_ratio_bounds=(0.5, 2.0),
    risk="alto",
)


# Família Desodorante (Aerosol, Aerosol e Spray, Creme, Gel e Stick, Roll-on,
# Para os Pés, Natural e Vegano). A taxonomia já separa por forma, mas
# miscategorização upstream vaza formas entre subcategorias — o hard_filter de
# ``forma_desodorante`` particiona os intrusos entre si. Medida em ml/g:
# quantity_kind=mass (com count, "200ml" virava "200 un" via metadata sujo e
# g×ml eram comparados como se fossem a mesma unidade). top_k reduzido: com
# 100, a cauda (rank 60+, relevance achatada) era onde os intrusos apareciam.
DESODORANTE_TEMPLATE = ConfigTemplate(
    name="desodorante",
    list_columns=[
        "forma_desodorante",
        "genero",
        *COMMON_COLUMNS,
    ],
    config_overrides={
        "forma_desodorante": {"attribute_type": "hard_filter"},
        "genero": {"attribute_type": "soft_boost", "boost_factor": 1.10},
        "quantity_norm": {"attribute_type": "soft_boost", "boost_factor": 1.15},
        "productType": {"attribute_type": "soft_boost", "boost_factor": 1.10},
    },
    # top_k herda o default (100) — decisão de produto no teste manual.
    quantity_kind="mass",
    quantity_ratio_bounds=(0.4, 2.5),
    risk="medio",
)


SABONETE_TEMPLATE = ConfigTemplate(
    name="sabonete",
    list_columns=[
        "forma_sabonete",
        "tipo_sabonete",
        *COMMON_COLUMNS,
    ],
    config_overrides={
        "forma_sabonete": {"attribute_type": "hard_filter"},
        "tipo_sabonete": {"attribute_type": "soft_boost", "boost_factor": 1.15},
        "quantity_norm": {"attribute_type": "soft_boost", "boost_factor": 1.15},
    },
    quantity_kind="mass",
    risk="medio",
)


TEMPLATES = {
    t.name: t
    for t in [
        DEFAULT_TEMPLATE,
        HIGIENE_TEMPLATE,
        AGUA_TERAPEUTICA_TEMPLATE,
        ALIMENTOS_BEBIDAS_TEMPLATE,
        BATERIAS_TEMPLATE,
        BEBE_CUIDADOS_TEMPLATE,
        DESODORANTE_TEMPLATE,
        FRALDAS_TEMPLATE,
        HIGIENE_ORAL_TEMPLATE,
        LATICINIOS_TEMPLATE,
        FORMULA_INFANTIL_TEMPLATE,
        LEITE_EM_PO_TEMPLATE,
        PAPINHA_TEMPLATE,
        PAPEL_LENCO_TEMPLATE,
        SABONETE_TEMPLATE,
    ]
}

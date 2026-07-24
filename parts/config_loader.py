# -*- coding: utf-8 -*-
"""Config por subcategoria: merge determinístico Delta > infos.yaml > template.

O ``ConfigLoader`` resolve cada fonte para um dicionário parcial e faz UM
merge com precedência de campo (Delta > YAML > template), construindo o
``SubcategoryConfig`` e computando o ``config_hash`` UMA única vez ao final —
antes o hash era recomputado a cada patch de campo, com risco de ficar stale.
"""
from __future__ import annotations

import ast
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import yaml

from parts.constants import (
    ATTRIBUTE_TYPES,
    CONFIG_TABLE,
    DEFAULT_ATTRIBUTE_TYPE,
    DEFAULT_BOOST_FACTOR,
    DEFAULT_MIN_SCORE,
    DEFAULT_MIN_SCORE_BASIS,
    DEFAULT_SOFT_WEIGHT,
    DEFAULT_TOP_K,
    MIN_SCORE_BASES,
    SUBCATEGORY_CATEGORIES,
    SUBCATEGORY_NAMES,
)

logger = logging.getLogger(__name__)

# Filtros de universo aplicados por DEFAULT quando a config não declara
# ``universe_exclusions`` explicitamente (declarar na config — mesmo vazio —
# sempre vence). Chave = slug. Entradas [v1.7] vêm da triagem do judge sobre a
# baseline (evidência em docs/lotes_toqan/triagem_consolidada.md); padrões em
# parts/universe_filters.py. Entram no config_hash quando não-vazios.
_DEFAULT_UNIVERSE_EXCLUSIONS = {
    # herdado do normalizer antigo (bloco hard-coded gated no slug legado)
    "leite_em_po": ("nao_leite_em_po",),
    # W4 — segurança (judge sobre a baseline):
    "absorvente_interno__absorvente_diurno": ("absorvente_externo",),
    "adocante__mercado": ("acucar",),
    "balas_e_chicletes__mercado": ("pastilha_medicinal",),
    "bebidas_alcoolicas__bebidas": ("sem_alcool",),
    "bolsa_termica__ortopedico": ("coletor_hospitalar",),
    "outros_dermocosmeticos__dermocosmeticos": ("medicamentoso_dermo",),
    "absorvente_sem_abas__absorvente_diurno": ("produto_geriatrico",),
    "absorvente_sem_abas__absorvente_noturno": ("produto_geriatrico",),
    # W3 — intrusos de universo validados por spot-check (0 falsos+):
    "aveias_e_cereais__mercado": ("nao_cereal",),
    "agua__bebidas": ("agua_de_coco",),
}
# compat: nome antigo referenciado em testes/notebooks
_LEGACY_DEFAULT_UNIVERSE_EXCLUSIONS = _DEFAULT_UNIVERSE_EXCLUSIONS


@dataclass
class AttributeRule:
    attribute: str
    attribute_type: str
    weight: float = DEFAULT_SOFT_WEIGHT
    boost_factor: float = DEFAULT_BOOST_FACTOR

    def __post_init__(self):
        self.attribute = str(self.attribute).strip()
        self.attribute_type = str(self.attribute_type).strip().lower()
        if self.attribute_type not in ATTRIBUTE_TYPES:
            raise ValueError(
                f"attribute_type inválido: {self.attribute_type!r} "
                f"(esperado um de {sorted(ATTRIBUTE_TYPES)})"
            )


@dataclass
class SubcategoryConfig:
    subcategoria: str
    subcategory_name: str = ""
    # Segundo eixo de identidade do universo. Fora do config_hash: descreve o
    # recorte, não o ruleset — mesmo tratamento do subcategory_name.
    category_name: str = ""
    rules: List[AttributeRule] = field(default_factory=list)
    top_k: int = DEFAULT_TOP_K
    min_score: float = DEFAULT_MIN_SCORE
    quantity_ratio_bounds: Optional[Tuple[float, float]] = None
    quantity_kind: str = "count"  # "count" (pack-size) | "mass" (massa/volume)
    candidate_pool_multiplier: int = 1
    # Base do corte min_score: "boosted" (histórico) | "raw_similarity".
    min_score_basis: str = DEFAULT_MIN_SCORE_BASIS
    # Filtros de universo nomeados (parts/universe_filters.py).
    universe_exclusions: Tuple[str, ...] = ()
    # Suprime candidatos com o mesmo product_id da origem (dedup de EANs
    # duplicados do mesmo produto). Default False = comportamento histórico.
    suppress_same_product: bool = False
    config_hash: str = ""
    source: str = "delta"

    @property
    def all_attributes(self) -> List[str]:
        return [r.attribute for r in self.rules if r.attribute_type != "ignore"]

    @property
    def hard_filter_rules(self) -> List[AttributeRule]:
        return [r for r in self.rules if r.attribute_type == "hard_filter"]

    @property
    def soft_boost_rules(self) -> List[AttributeRule]:
        return [r for r in self.rules if r.attribute_type == "soft_boost"]

    @property
    def text_only_rules(self) -> List[AttributeRule]:
        return [r for r in self.rules if r.attribute_type == "text_only"]

    def to_hash_payload(self) -> List[Dict[str, Any]]:
        tail: Dict[str, Any] = {"top_k": self.top_k, "min_score": self.min_score}
        # Campos entram no hash SÓ quando divergem do default — preserva os
        # hashes históricos das configs que não os usam (sem churn).
        if self.quantity_ratio_bounds is not None:
            tail["quantity_ratio_bounds"] = list(self.quantity_ratio_bounds)
        if self.quantity_kind != "count":
            tail["quantity_kind"] = self.quantity_kind
        if self.candidate_pool_multiplier != 1:
            tail["candidate_pool_multiplier"] = self.candidate_pool_multiplier
        if self.min_score_basis != DEFAULT_MIN_SCORE_BASIS:
            tail["min_score_basis"] = self.min_score_basis
        if self.universe_exclusions:
            tail["universe_exclusions"] = sorted(self.universe_exclusions)
        if self.suppress_same_product:
            tail["suppress_same_product"] = True
        return [
            {
                "attribute": r.attribute,
                "attribute_type": r.attribute_type,
                "weight": r.weight,
                "boost_factor": r.boost_factor,
            }
            for r in sorted(self.rules, key=lambda x: x.attribute)
        ] + [tail]


def compute_config_hash(config: SubcategoryConfig) -> str:
    payload = json.dumps(config.to_hash_payload(), sort_keys=True, ensure_ascii=False)
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


def _coerce_ratio_bounds(value: Any) -> Optional[Tuple[float, float]]:
    """Normaliza a faixa de quantidade para ``(lo, hi)`` ou ``None``.

    Aceita lista/tupla, string JSON ``"[0.5, 2.0]"`` ou CSV/espaço. ``None``
    quando ausente ou inválida (tamanho != 2, não positivos, lo >= hi).
    """
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            value = ast.literal_eval(s)
        except (ValueError, SyntaxError):
            value = [p for p in re.split(r"[,\s]+", s) if p]
    try:
        seq = list(value)
    except TypeError:
        return None
    if len(seq) != 2:
        return None
    try:
        lo, hi = float(seq[0]), float(seq[1])
    except (TypeError, ValueError):
        return None
    if lo <= 0 or hi <= 0 or lo >= hi:
        logger.warning("quantity_ratio_bounds inválido: %r (ignorado)", value)
        return None
    return (lo, hi)


def _coerce_min_score_basis(value: Any) -> str:
    basis = str(value or DEFAULT_MIN_SCORE_BASIS).strip().lower()
    if basis not in MIN_SCORE_BASES:
        raise ValueError(
            f"min_score_basis inválido: {basis!r} (use um de {sorted(MIN_SCORE_BASES)})"
        )
    return basis


def _coerce_exclusions(value: Any) -> Optional[Tuple[str, ...]]:
    if value is None:
        return None
    if isinstance(value, str):
        value = [p for p in re.split(r"[,\s]+", value) if p]
    return tuple(str(v).strip() for v in value if str(v).strip())


# ---------------------------------------------------------------------------
# Fontes -> dicionário parcial de config (campos ausentes ficam de fora e o
# merge cai para a próxima fonte).
# ---------------------------------------------------------------------------


def _partial_from_infos_entry(infos_entry: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    list_columns = infos_entry.get("list_columns")
    if list_columns:
        overrides = infos_entry.get("config_overrides") or {}
        rules: List[AttributeRule] = []
        for col in list_columns:
            col_str = str(col).strip()
            if not col_str:
                continue
            ov = overrides.get(col_str) or overrides.get(col_str.upper()) or {}
            rules.append(
                AttributeRule(
                    attribute=col_str,
                    attribute_type=ov.get("attribute_type", DEFAULT_ATTRIBUTE_TYPE),
                    weight=float(ov.get("weight", DEFAULT_SOFT_WEIGHT)),
                    boost_factor=float(ov.get("boost_factor", DEFAULT_BOOST_FACTOR)),
                )
            )
        out["rules"] = rules
    if infos_entry.get("subcategory_name"):
        out["subcategory_name"] = str(infos_entry["subcategory_name"]).strip()
    if infos_entry.get("category_name"):
        out["category_name"] = str(infos_entry["category_name"]).strip()
    # ``is not None`` (não truthiness): ``top_k: 0``/``min_score: 0`` são valores
    # explícitos que o autor pode usar em config de teste; truthiness os
    # descartava silenciosamente e caía no default.
    if infos_entry.get("top_k") is not None:
        out["top_k"] = int(infos_entry["top_k"])
    if infos_entry.get("min_score") is not None:
        out["min_score"] = float(infos_entry["min_score"])
    bounds = _coerce_ratio_bounds(infos_entry.get("quantity_ratio_bounds"))
    if bounds is not None:
        out["quantity_ratio_bounds"] = bounds
    if infos_entry.get("quantity_kind"):
        out["quantity_kind"] = str(infos_entry["quantity_kind"]).strip().lower()
    if infos_entry.get("candidate_pool_multiplier"):
        out["candidate_pool_multiplier"] = max(
            1, int(infos_entry["candidate_pool_multiplier"])
        )
    if infos_entry.get("min_score_basis"):
        out["min_score_basis"] = _coerce_min_score_basis(infos_entry["min_score_basis"])
    exclusions = _coerce_exclusions(infos_entry.get("universe_exclusions"))
    if exclusions is not None:
        out["universe_exclusions"] = exclusions
    if infos_entry.get("suppress_same_product") is not None:
        out["suppress_same_product"] = bool(infos_entry["suppress_same_product"])
    return out


def _partial_from_delta(spark, subcategoria: str) -> Optional[Dict[str, Any]]:
    try:
        sdf = spark.table(CONFIG_TABLE)
    except Exception as exc:
        logger.warning("Tabela %s indisponível: %s", CONFIG_TABLE, exc)
        return None

    rows = (
        sdf.where(
            (sdf["subcategoria"] == subcategoria) & (sdf["active"] == True)  # noqa: E712
        )
        .collect()
    )
    if not rows:
        return None

    out: Dict[str, Any] = {}
    rules: List[AttributeRule] = []

    # Campos escalares: 1 valor lógico por slug, mas replicado em CADA linha de
    # atributo. Antes cada linha sobrescrevia o campo e a ÚLTIMA vencia — e
    # ``collect()`` sem ``orderBy`` não tem ordem garantida, então uma edição
    # manual inconsistente na tabela produzia config não determinística. Agora o
    # PRIMEIRO valor não-nulo vence e divergências entre linhas falham alto.
    _SCALAR_COERCERS = {
        "subcategory_name": lambda v: str(v).strip(),
        "category_name": lambda v: str(v).strip(),
        "top_k": lambda v: int(v),
        "min_score": lambda v: float(v),
        "quantity_kind": lambda v: str(v).strip().lower(),
        "candidate_pool_multiplier": lambda v: max(1, int(v)),
        "quantity_ratio_bounds": _coerce_ratio_bounds,
    }

    def _set_scalar(key: str, raw: Any):
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            return
        value = _SCALAR_COERCERS[key](raw)
        if value is None:  # coerção rejeitou (ex.: bounds inválido)
            return
        if key in out and out[key] != value:
            raise ValueError(
                f"Config Delta de {subcategoria!r} inconsistente: {key} tem "
                f"valores divergentes entre linhas ({out[key]!r} vs {value!r}). "
                f"Corrija a tabela {CONFIG_TABLE} (1 valor por slug)."
            )
        out[key] = value

    for row in rows:
        r = row.asDict() if hasattr(row, "asDict") else dict(row)
        attr = r.get("attribute")
        if not attr:
            continue
        for key in _SCALAR_COERCERS:
            _set_scalar(key, r.get(key))
        rules.append(
            AttributeRule(
                attribute=str(attr),
                attribute_type=str(r.get("attribute_type") or DEFAULT_ATTRIBUTE_TYPE),
                weight=float(r.get("weight") if r.get("weight") is not None else DEFAULT_SOFT_WEIGHT),
                boost_factor=float(
                    r.get("boost_factor")
                    if r.get("boost_factor") is not None
                    else DEFAULT_BOOST_FACTOR
                ),
            )
        )
    if not rules:
        return None
    out["rules"] = rules
    return out


def _merge_partials(
    subcategoria: str,
    partials: List[Tuple[str, Dict[str, Any]]],
    top_k_default: int,
) -> SubcategoryConfig:
    """Merge com precedência de campo: o primeiro partial que define um campo
    vence. ``rules`` vem inteiro da fonte de maior precedência que o define
    (não há merge de regra a regra entre fontes)."""

    def _first(key, default=None):
        for _, p in partials:
            if key in p:
                return p[key]
        return default

    source = partials[0][0] if partials else "delta"
    exclusions = _first("universe_exclusions")
    if exclusions is None:
        exclusions = _DEFAULT_UNIVERSE_EXCLUSIONS.get(subcategoria, ())

    cfg = SubcategoryConfig(
        subcategoria=subcategoria,
        subcategory_name=_first("subcategory_name", ""),
        category_name=_first(
            "category_name", SUBCATEGORY_CATEGORIES.get(subcategoria, "")
        ),
        rules=_first("rules", []),
        top_k=_first("top_k", top_k_default),
        min_score=_first("min_score", DEFAULT_MIN_SCORE),
        quantity_ratio_bounds=_first("quantity_ratio_bounds"),
        quantity_kind=_first("quantity_kind", "count"),
        candidate_pool_multiplier=_first("candidate_pool_multiplier", 1),
        min_score_basis=_first("min_score_basis", DEFAULT_MIN_SCORE_BASIS),
        universe_exclusions=tuple(exclusions),
        suppress_same_product=bool(_first("suppress_same_product", False)),
        source=source,
    )
    cfg.config_hash = compute_config_hash(cfg)
    return cfg


def build_config_from_infos(
    subcategoria: str,
    infos_entry: Dict[str, Any],
    top_k_default: int = DEFAULT_TOP_K,
) -> SubcategoryConfig:
    """Config a partir de uma entrada do ``infos.yaml`` (ou de template)."""
    cfg = _merge_partials(
        subcategoria,
        [("infos.yaml", _partial_from_infos_entry(infos_entry))],
        top_k_default,
    )
    return cfg


class ConfigLoader:
    """Resolve a config na ordem: Delta > infos.yaml > template.

    A fonte de MAIOR precedência que define ``rules`` determina o ruleset;
    campos escalares ausentes descem a cascata (ex.: Delta legado sem
    ``quantity_kind`` completa do YAML — mesmo comportamento do loader
    antigo, agora num único merge com hash computado uma vez).
    """

    def __init__(self, spark, infos_path: str, top_k_default: int = DEFAULT_TOP_K):
        self.spark = spark
        self.infos_path = infos_path
        self.top_k_default = top_k_default
        with open(infos_path, "r", encoding="utf-8") as f:
            self._infos = yaml.safe_load(f) or {}
        self._list_ids = self._infos.get("list_ids") or {}

    def get(self, subcategoria: str) -> SubcategoryConfig:
        partials: List[Tuple[str, Dict[str, Any]]] = []

        delta_partial = _partial_from_delta(self.spark, subcategoria)
        if delta_partial:
            partials.append(("delta", delta_partial))

        yaml_entry = self._list_ids.get(subcategoria)
        if yaml_entry:
            partials.append(("infos.yaml", _partial_from_infos_entry(yaml_entry)))

        if not any("rules" in p for _, p in partials):
            literal_name = SUBCATEGORY_NAMES.get(subcategoria)
            if not literal_name and not yaml_entry:
                raise RuntimeError(
                    f"Subcategoria '{subcategoria}' sem config em {CONFIG_TABLE}, "
                    f"sem entrada em infos.yaml e sem mapeamento em SUBCATEGORY_NAMES."
                )
            if literal_name:
                from parts.config_generator import build_infos_entry_from_template

                template_entry = build_infos_entry_from_template(
                    subcategoria, literal_name
                )
                partials.append(
                    (
                        f"generated:{template_entry.get('template', 'default')}",
                        _partial_from_infos_entry(template_entry),
                    )
                )
                logger.warning(
                    "Config de %s gerada por template (%s); Delta/YAML sem regras.",
                    subcategoria,
                    template_entry.get("template"),
                )

        cfg = _merge_partials(subcategoria, partials, self.top_k_default)
        logger.info(
            "Config de %s carregada (source=%s, %d regras, subcategory_name=%r)",
            subcategoria,
            cfg.source,
            len(cfg.rules),
            cfg.subcategory_name,
        )
        return cfg

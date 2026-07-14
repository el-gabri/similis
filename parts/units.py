# -*- coding: utf-8 -*-
"""Fonte única de parsing/conversão de unidades e quantidades.

Unifica as tabelas que antes viviam duplicadas em ``normalizer._CONVERSION``
e ``ranker._UNIT_CANON`` (com coberturas divergentes — uma unidade parseável
na normalização podia ser desconhecida no ranking, pulando silenciosamente o
filtro de quantidade).

Convenções canônicas: massa -> g, volume -> ml, contagem -> un.
"""
from __future__ import annotations

import re
from typing import Any, Optional, Tuple

import numpy as np

try:
    import unidecode as _unidecode_mod
except ImportError:
    _unidecode_mod = None


def ascii_fold(text: str) -> str:
    if _unidecode_mod is not None:
        return _unidecode_mod.unidecode(text)
    table = str.maketrans(
        "áàâãäéèêëíìîïóòôõöúùûüçñÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑ",
        "aaaaaeeeeiiiiooooouuuucnAAAAAEEEEIIIIOOOOOUUUUCN",
    )
    return text.translate(table).encode("ascii", "ignore").decode("ascii")


# unidade -> (canônica, fator). União das duas tabelas antigas.
UNITS = {
    # massa -> g
    "g": ("g", 1.0),
    "gr": ("g", 1.0),
    "grs": ("g", 1.0),
    "grama": ("g", 1.0),
    "gramas": ("g", 1.0),
    "kg": ("g", 1000.0),
    "kgr": ("g", 1000.0),
    "kgrs": ("g", 1000.0),
    "kgs": ("g", 1000.0),
    "kilo": ("g", 1000.0),
    "kilos": ("g", 1000.0),
    "kilograma": ("g", 1000.0),
    "quilo": ("g", 1000.0),
    "quilos": ("g", 1000.0),
    "mg": ("g", 0.001),
    "mgs": ("g", 0.001),
    # volume -> ml
    "ml": ("ml", 1.0),
    "mls": ("ml", 1.0),
    "l": ("ml", 1000.0),
    "lt": ("ml", 1000.0),
    "lts": ("ml", 1000.0),
    "litro": ("ml", 1000.0),
    "litros": ("ml", 1000.0),
    # contagem -> un
    "un": ("un", 1.0),
    "und": ("un", 1.0),
    "unds": ("un", 1.0),
    "uni": ("un", 1.0),
    "unid": ("un", 1.0),
    "unidade": ("un", 1.0),
    "unidades": ("un", 1.0),
    "pc": ("un", 1.0),
    "pcs": ("un", 1.0),
}

_QTY_RE = re.compile(r"(\d+[.,]?\d*)\s*([a-z]+)")


def parse_quantity(value: Any) -> Optional[Tuple[float, str]]:
    """``(valor, unidade_canônica)`` de '96 un' / '1.5 kg' / '1500 g'.

    Unidades conhecidas são convertidas para a forma canônica (g, ml, un);
    desconhecidas passam intactas (comparação downstream exige igualdade
    literal — conservador). ``None`` se não parseável.
    """
    if value is None:
        return None
    s = str(value).strip().lower()
    if not s or s == "not available":
        return None
    m = _QTY_RE.search(s)
    if not m:
        return None
    try:
        qty = float(m.group(1).replace(",", "."))
    except ValueError:
        return None
    unit = m.group(2)
    canon, factor = UNITS.get(unit, (unit, 1.0))
    return qty * factor, canon


def convert_unit(value: Any) -> str:
    """Normaliza strings de quantidade (ex: '1,5 KG' -> '1500 g')."""
    if not value or str(value).strip() == "":
        return "not available"
    try:
        raw = ascii_fold(str(value).replace(",", ".").replace(" ", "").lower().strip())
    except Exception:
        return "not available"
    if not raw:
        return "not available"
    if raw[0] == "z":
        raw = raw[1:]
    match = re.findall(r"(\d+\.?\d*)?(\D+)", raw)
    if not match:
        return "not available"
    numeric, unit = match[0]
    if not numeric:
        numeric = "1"
    if unit in UNITS:
        scale, converter = UNITS[unit]
        numeric = str(int(float(numeric) * converter)).strip()
        return f"{numeric} {scale}"
    return "not available"


# ---------------------------------------------------------------------------
# Parser de contagem de embalagem (pack size) a partir do PRODUCT_NAME.
# Usado como FALLBACK do quantity_norm quando quantity/quantityUnit do
# skus_metadata estão ausentes ou inválidos. Retorna a contagem TOTAL de
# unidades (n_packs * per_pack em multipacks).
# ---------------------------------------------------------------------------
_PACK_UNIT = r"(?:unidades?|unid|und|un|rolos?|fraldas?|tiras?)"
_PACK_PACK = r"(?:pacotes?|pcts?|pack|caixas?|fardos?)"


def parse_pack_size(name: Any) -> dict:
    """Extrai a contagem total de unidades de um nome de produto.

    Retorna ``dict(total, n_packs, per_pack, pattern, confidence)``;
    ``total = np.nan`` quando não infere. ``total == n_packs * per_pack``.
    A ordem das regras é deliberada: padrões de multiplicador (multipack)
    vêm ANTES da contagem simples, senão "24 Pacotes Com 7un" devolveria 7.
    """
    if not isinstance(name, str) or not name.strip():
        return dict(total=np.nan, n_packs=np.nan, per_pack=np.nan,
                    pattern="empty", confidence="none")
    s = name.lower().replace("×", "x")

    # Promoção "Leve N Pague M": a contagem que o cliente RECEBE é N, não M.
    m_leve = re.search(
        r"\bleve\s*(\d{1,3})\b(?!\s*(?:m\b|mts?\b|metros?\b|cm\b))", s
    )
    s = re.sub(r"\bpague\s*\d{1,3}\s*(?:unidades?|unid|und|un)?\b", " ", s)

    # 1. forma compacta NxM ("6x22", "4 x 42")
    m = re.search(r"(?<![\d.,])(\d{1,3})\s*x\s*(\d{1,3})(?![\d.,])", s)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return dict(total=a * b, n_packs=a, per_pack=b,
                    pattern="NxM", confidence="med")

    # 2. "N <pack> com M <unit>" ("24 pacotes com 7un cada")
    m = re.search(rf"(\d{{1,3}})\s*{_PACK_PACK}\s*com\s*(\d{{1,4}})\s*{_PACK_UNIT}", s)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return dict(total=a * b, n_packs=a, per_pack=b,
                    pattern="N_pack_com_M_un", confidence="high")

    # 3. "N <unit> de M <unit> cada" ("4 unidades de 42 tiras cada")
    m = re.search(rf"(\d{{1,3}})\s*{_PACK_UNIT}\s*de\s*(\d{{1,4}})\s*{_PACK_UNIT}\s*cada", s)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return dict(total=a * b, n_packs=a, per_pack=b,
                    pattern="N_un_de_M_cada", confidence="high")

    # 4. "M <unit> ... caixa N <pack>" ("12 unidades caixa 8 pacotes")
    m = re.search(rf"(\d{{1,4}})\s*{_PACK_UNIT}.*?{_PACK_PACK}.*?(\d{{1,3}})\s*{_PACK_PACK}", s)
    if m:
        b, a = int(m.group(1)), int(m.group(2))
        return dict(total=a * b, n_packs=a, per_pack=b,
                    pattern="M_un_caixa_N_pack", confidence="med")

    # 4b. promoção "leve N" sem estrutura de multipack: vale o que se LEVA.
    if m_leve is not None:
        v = int(m_leve.group(1))
        return dict(total=v, n_packs=1, per_pack=v,
                    pattern="leve_N", confidence="high")

    # 5. contagem simples: maior número colado num token de unidade
    cands = [int(x) for x in re.findall(rf"(\d{{1,4}})\s*{_PACK_UNIT}", s)]
    if cands:
        v = max(cands)
        return dict(total=v, n_packs=1, per_pack=v,
                    pattern="simple", confidence="high")

    return dict(total=np.nan, n_packs=np.nan, per_pack=np.nan,
                pattern="no_match", confidence="none")


# Extrator de massa/volume a partir do PRODUCT_NAME, para subcategorias cuja
# unidade de venda é peso/volume (leite em pó, creme, talco...) — NÃO contagem.
# Exige a unidade COLADA ao número para não capturar números de estágio/linha.
# Em múltiplas ocorrências usa a PRIMEIRA (conteúdo nominal).
_MASS_VOL_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(kg|kgs|g|gr|grs|mg|ml|mls|l|lt|lts|litros?)\b",
    re.IGNORECASE,
)


def parse_mass_volume(name: Any) -> str:
    """Massa/volume canônico ('400 g', '1000 g', '1500 ml') do nome, ou ''."""
    if name is None:
        return ""
    s = str(name)
    if not s.strip():
        return ""
    m = _MASS_VOL_RE.search(s)
    if not m:
        return ""
    num, unit = m.group(1), m.group(2)
    out = convert_unit(f"{num}{unit}")
    return "" if out == "not available" else out


# Extrator de METRAGEM (metros por rolo) do PRODUCT_NAME — eixo de QUANTIDADE
# real do papel higiênico que a contagem de rolos ignora (12x30m vs 12x60m).
# Exige a unidade 'm'/'mt'/'mts'/'metros' em fronteira de palavra — NÃO casa
# 'cm' nem 'mm' (largura do rolo).
#
# [FIX bge-m3-v1.6] O normalizer antigo definia DUAS _METRAGEM_RE; a segunda
# (com lookahead diferente e sem docstring correspondente) sombreava a que
# ``parse_metragem`` documentava. Mantida a semântica documentada (fronteira
# de palavra) + faixa de plausibilidade (5–600 m) herdada do extrator morto.
_METRAGEM_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(?:m\b|mts?\b|metros?\b)",
    re.IGNORECASE,
)

METRAGEM_PLAUSIBLE = (5.0, 600.0)


def parse_metragem(name: Any) -> float:
    """Metros por rolo extraídos do nome ('30m' -> 30.0), ou ``np.nan``.

    Usa a PRIMEIRA ocorrência PLAUSÍVEL (5–600 m) — comprimento nominal do
    rolo. Em '20m x 10cm' pega 20 (comprimento, não largura). Aceita vírgula
    decimal. Retorna float; o chamador arredonda.
    """
    if not isinstance(name, str) or not name.strip():
        return np.nan
    lo, hi = METRAGEM_PLAUSIBLE
    for m in _METRAGEM_RE.finditer(name):
        try:
            v = float(m.group(1).replace(",", "."))
        except ValueError:
            continue
        if lo <= v <= hi:
            return v
    return np.nan

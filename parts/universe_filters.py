# -*- coding: utf-8 -*-
"""Filtros de universo nomeados, aplicáveis por config (``universe_exclusions``).

Um filtro de universo remove itens de ORIGEM e CANDIDATO — diferente do
hard_filter, que só esconde o intruso como candidato mas deixa ele gerar uma
lista inteira ruim como origem. Antes eram blocos hard-coded (e comentados)
dentro do normalizer, gated por comparação de slug; agora a config declara:

.. code-block:: yaml

    leite_em_po__alimentacao_infantil:
      universe_exclusions: [nao_leite_em_po]

ATENÇÃO: listas acopladas a marca, frágeis por natureza — revisar com a
categoria antes de ativar em subcategoria nova. ``universe_exclusions`` entra
no ``config_hash`` quando não-vazio (muda resultados).
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List

import pandas as pd

# [LEITE EM PÓ] Itens que caem no subcategory_name de leite em pó mas NÃO são
# leite em pó de prateleira: fórmula infantil (miscategorização — circula aqui
# SEM as travas de segurança de formula_infantil) e suplemento/enteral.
# NÃO inclui composto lácteo (é leite em pó legítimo, já isolado por base_leite).
_NAO_LEITE_PATTERNS = {
    "formula_infantil": (r"\bnan\b|nestogeno|nestonutri|enfanutri|aptanutri|aptamil|"
                         r"enfamil|milupa|similac|nursoy|pregomin|pregestimil|"
                         r"alfar[ée]|althera|neocate|alfamino|puramino|nutramigen|"
                         r"\bpepti\b|f[óo]rmula\s*infantil"),
    "suplemento":       (r"sustagen|\bnutren\b|nutrini|infatrini|\bnidex\b|good\s*vit|"
                         r"nutrivita|pediasure|sustare"),
}

# [FÓRMULA] Itens que caem em "Fórmula Infantil" mas NÃO são fórmula
# (miscategorização upstream confirmada): mingau/cereal, nutrição enteral,
# suplemento, leite de vaca comum, não-alimento e placeholders. NÃO inclui
# composto lácteo (isolado por categoria_produto). Desligado por padrão —
# ativar via ``universe_exclusions: [nao_formula]`` após revisão com categoria.
_NAO_FORMULA_PATTERNS = {
    "mingau":       r"mucilon|mingau|neo\s*spoon|mistura\s*para\s*mingau",
    "enteral":      r"\bnutren\b|nutrini|infatrini|enteral|ketocal|pediasure|"
                    r"complemento\s*nutricional|\bascenda\b",
    "suplemento":   r"sustagen|sustain|susvita|sustup|sustare|\bsustan\b|sustap|"
                    r"\bustap\b|complemento\s*alimentar",
    "leite_vaca":   r"ninho\s*tradicional|\bregina\b|itamb[ée]|fortleite|"
                    r"a2\s*a2|leite\s+integral\b",
    "nao_alimento": r"munchkin|alimentador|mamadeira|chupeta|\bbico\b|\bcopo\b",
    "placeholder":  r"monuril|^\s*f[óo]rmula\s*[\d.,]+\s*\.?\s*$",
}


def _compile(patterns: Dict[str, str]) -> re.Pattern:
    return re.compile("|".join(f"(?:{p})" for p in patterns.values()), re.IGNORECASE)


# ---------------------------------------------------------------------------
# Exclusions da onda W4 (judge sobre a baseline) — padrões por TERMO, não por
# marca (mais estáveis). Cada uma remove intruso confirmado pelo judge:
# ---------------------------------------------------------------------------

# 108× "absorvente externo sugerido no lugar de tampão" (8.8% crítico).
_ABSORVENTE_EXTERNO = {
    "externo": r"com\s*abas|sem\s*abas|protetor\s*di[áa]rio|absorvente\s*noturno|"
               r"calcinha\s*absorvente|\bfralda\b",
}

# 15× "açúcar sugerido no lugar de adoçante (restrição glicêmica)".
_ACUCAR = {"acucar": r"\ba[çc][úu]car\b"}

# 13× "pastilha medicinal sugerida no lugar de bala de confeitaria".
_PASTILHA_MEDICINAL = {
    "medicinal": r"strepsils|benalet|flogoral|ciflogex|neopiridin|"
                 r"pastilhas?\s*(?:para|de)\s*(?:garganta|tosse)|propolis\s*spray",
}

# 7× "bebida sem álcool no lugar de bebida alcoólica" (Cerveja Sem Álcool
# tem subcategoria própria — é intruso aqui).
_SEM_ALCOOL = {"sem_alcool": r"sem\s*[áa]lcool|zero\s*[áa]lcool|0[.,]0\s*%"}

# 4× "bolsa de colostomia/coletora de urina no lugar de bolsa térmica".
_COLETOR_HOSPITALAR = {
    "coletor": r"colostomia|urostomia|coletor\s*(?:de)?\s*urina|\bsonda\b",
}

# 6× de 12 pares (!) "corticoide vs cosmético" em outros_dermocosmeticos.
_MEDICAMENTOSO_DERMO = {
    "corticoide": r"betametasona|dexametasona|hidrocortisona|corticoide|"
                  r"cetoconazol|clotrimazol|miconazol|\bmicosan\b|dipropionato",
}

# 4× "absorvente geriátrico no lugar de feminino" em absorvente_sem_abas —
# reusa o vocabulário do sintético `audience`.
_PRODUTO_GERIATRICO = {
    "geriatrico": r"geri[aá]t|incontin|\btena\b|bigfral|plenitud|\badult\b",
}

# W3 — intrusos de universo VALIDADOS por spot-check contra a baseline (só os
# que separam por keyword sem falso positivo; ver nota abaixo sobre os que NÃO
# entraram). Padrões conferidos em docs/lotes_toqan/ (0 falsos+ na amostra).

# 295× "geléia/mocotó não é cereal/aveia" em aveias_e_cereais. Palavras PURAS
# (\bgeléia\b|\bmocotó\b) não aparecem em barra de cereal/whey legítima —
# "goiabada"/"doce de leite" ficam FORA de propósito (são sabores de barra).
_NAO_CEREAL = {"geleia": r"\bgel[ée]ia\b|\bmocot[óo]\b"}

# 74× "água de coco vs água mineral" em agua. Água de Coco é subcategoria
# própria (agua_de_coco__bebidas) — intruso aqui. 0 falsos+ na amostra.
_AGUA_DE_COCO = {"agua_coco": r"[áa]gua\s*d[e]?\s*coco"}


# Filtros nomeados: nome -> regex sobre o PRODUCT_NAME (match ⇒ excluído).
UNIVERSE_FILTERS: Dict[str, re.Pattern] = {
    "nao_leite_em_po": _compile(_NAO_LEITE_PATTERNS),
    "nao_formula": _compile(_NAO_FORMULA_PATTERNS),
    "absorvente_externo": _compile(_ABSORVENTE_EXTERNO),
    "acucar": _compile(_ACUCAR),
    "pastilha_medicinal": _compile(_PASTILHA_MEDICINAL),
    "sem_alcool": _compile(_SEM_ALCOOL),
    "coletor_hospitalar": _compile(_COLETOR_HOSPITALAR),
    "medicamentoso_dermo": _compile(_MEDICAMENTOSO_DERMO),
    "produto_geriatrico": _compile(_PRODUTO_GERIATRICO),
    "nao_cereal": _compile(_NAO_CEREAL),
    "agua_de_coco": _compile(_AGUA_DE_COCO),
}

# ---------------------------------------------------------------------------
# W3 que NÃO viraram filtro (spot-check reprovou keyword) — deixados aqui como
# registro para não serem reintroduzidos por engano:
#   - acessorios_para_coloracao / acessorios_para_maquiagem: o intruso é a
#     maquiagem/tinta em si, mas os ACESSÓRIOS legítimos se chamam "Pincel
#     para Tintura", "Pincel para Batom" — keyword apagaria os corretos.
#     Precisa de sinal "ferramenta vs produto" (sintético futuro) ou reporte
#     à categorização, não universe_exclusion.
#   - "ração animal" (anticaspa, artigos_esportivos, autoteste...): ALUCINAÇÃO
#     do judge — 0 produtos pet reais na amostra dessas subcategorias (só em
#     mundo_pet). É QA do juiz, não config.
# ---------------------------------------------------------------------------

# [APLV] Exclusão de fórmulas terapêuticas de APLV grave (decisão médica, não
# de catálogo). Filtro por VALOR de coluna sintética, não por nome — aplicado
# via ``universe_exclusions: [aplv_terapeutica]`` quando o negócio decidir.
_APLV_TIPOS = frozenset({"aminoacido", "ext_hidrolisada"})

COLUMN_VALUE_FILTERS = {
    "aplv_terapeutica": ("tipo_formula", _APLV_TIPOS),
}

KNOWN_EXCLUSIONS = frozenset(UNIVERSE_FILTERS) | frozenset(COLUMN_VALUE_FILTERS)


def apply_universe_exclusions(
    df: pd.DataFrame, exclusions: Iterable[str]
) -> pd.DataFrame:
    """Remove linhas que casem os filtros nomeados em ``exclusions``.

    Filtros desconhecidos levantam ``ValueError`` (config inválida é melhor
    falhar alto do que silenciosamente não filtrar).
    """
    names: List[str] = [str(e).strip() for e in (exclusions or []) if str(e).strip()]
    if not names:
        return df
    unknown = [n for n in names if n not in KNOWN_EXCLUSIONS]
    if unknown:
        raise ValueError(
            f"universe_exclusions desconhecidas: {unknown} "
            f"(conhecidas: {sorted(KNOWN_EXCLUSIONS)})"
        )
    out = df
    for name in names:
        if name in UNIVERSE_FILTERS:
            pat = UNIVERSE_FILTERS[name]
            out = out[~out["PRODUCT_NAME"].map(lambda n: bool(pat.search(n or "")))]
        else:
            col, banned = COLUMN_VALUE_FILTERS[name]
            if col in out.columns:
                out = out[~out[col].isin(banned)]
    return out.reset_index(drop=True)

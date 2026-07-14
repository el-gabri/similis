# -*- coding: utf-8 -*-
"""LLM-as-judge para avaliar recomendações do Similis."""
from __future__ import annotations

import json
import os
import re
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

FLAT_TABLE = os.environ.get(
    "SIMILIS_JUDGE_FLAT_TABLE",
    "groceries_ops.similis.recommendations_flat_staging",
)
VERDICTS_TABLE = "groceries_ops.similis.judge_verdicts"
RANKING_TABLE = "groceries_ops.similis.judge_ranking_subcategoria"
N_ORIGENS_POR_SUBCAT = 20
TOP_K_SUGESTOES = 25
MAX_WORKERS = 8
MAX_RETRIES = 3

COL = {
    "subcategoria": "subcategoria",
    "origem_ean": "ean_origem",
    "origem_nome": "product_name_origem",
    "sugestao_ean": "ean_sugestao",
    "sugestao_nome": "product_name_sugestao",
    "rank": "rank",
    "relevance": "relevance",
}

LEGACY_LONG_COL = {
    "subcategoria": "subcategoria",
    "grupo": "_grupo",
    "role": "role",
    "ean": "ean",
    "nome": "PRODUCT_NAME",
    "rank": "rank",
    "relevance": "relevance",
}

ATRIBUTOS_CRITICOS = {
    "formula_infantil": ["estágio/faixa etária", "tipo terapêutico", "lactose"],
    "leite_em_po": ["base (vaca/soja/cabra)", "teor (integral/desnatado)", "lactose"],
}

MOTIVOS = {
    "categoria_diferente",
    "atributo_critico_divergente",
    "tamanho_incompativel",
    "funcao_diferente",
    "nao_e_produto",
}
SEVERIDADES = {"seguranca", "qualidade"}


def call_judge(prompt: str) -> str:
    """Recebe o prompt e devolve a resposta crua do LLM.

    Default não implementado: injete um cliente via parâmetro ``judge_fn``
    de ``run_judge``/``rodar_scan``/``calibrar`` (temperatura 0, resposta
    JSON) — assim o wiring do Toqan fica fora do repo e os testes passam
    um fake.
    """
    raise NotImplementedError("Conecte ao Toqan: retorne a string de resposta do LLM.")


def call_judge_with_retry(prompt: str, judge_fn=None) -> str:
    judge_fn = judge_fn or call_judge
    erro = None
    for tent in range(MAX_RETRIES):
        try:
            return judge_fn(prompt)
        except Exception as exc:  # noqa: BLE001
            erro = exc
            time.sleep(2 ** tent)
    return f"__ERRO__ {erro}"


def build_prompt(subcategoria, origem_nome, sugestoes, atributos_criticos=None):
    linhas = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(sugestoes))
    hint = ""
    if atributos_criticos:
        hint = (
            "\nNesta subcategoria, trate como CRÍTICOS (severidade=seguranca quando "
            f"divergirem): {', '.join(atributos_criticos)}."
        )
    return f"""Você audita recomendações de SUBSTITUTOS de um app de mercado/farmácia.
Um substituto é o que o cliente aceitaria NO LUGAR do produto de origem quando ele
está em falta: mesma função, atributos compatíveis, tamanho semelhante.

Subcategoria: {subcategoria}
Produto de ORIGEM: {origem_nome}{hint}

Para CADA sugestão abaixo, decida:
- veredito: "ok" ou "violacao"
- motivo (só se violacao): {sorted(MOTIVOS)}
- severidade (só se violacao): "seguranca" (cruza barreira dietética/médica/etária/
  dosagem, ou não é produto) ou "qualidade" (só um casamento pior)
- justificativa: até 12 palavras

REGRAS:
- Marca diferente NÃO é violação (substituição é entre marcas por natureza).
- Tamanho diferente só vira violacao se for drástico (>2-3x); severidade=qualidade.
- Sabor/variante diferente costuma ser "ok" (no máximo qualidade).
- Cruzar restrição dietética/médica (com/sem lactose, base vegetal vs animal,
  estágio de fórmula infantil, princípio ativo/dosagem) = atributo_critico_divergente,
  severidade=seguranca.
- Outra categoria de produto (ex.: mingau no lugar de fórmula) = categoria_diferente.
- Utensílio/placeholder/não-alimento = nao_e_produto, severidade=seguranca.
- Na dúvida sobre atributo de segurança, marque seguranca. NÃO penalize bons
  substitutos: item da mesma categoria e tamanho parecido é "ok".

Responda APENAS um array JSON, um objeto por sugestão na ordem, sem texto fora dele:
[{{"i":1,"veredito":"ok"}},{{"i":2,"veredito":"violacao","motivo":"...","severidade":"...","justificativa":"..."}}]

SUGESTÕES:
{linhas}"""


def parse_response(raw, n):
    txt = (raw or "").strip()
    txt = re.sub(r"^```(?:json)?|```$", "", txt, flags=re.MULTILINE).strip()
    m = re.search(r"\[.*\]", txt, flags=re.DOTALL)
    parsed = []
    if m:
        try:
            parsed = json.loads(m.group(0))
        except json.JSONDecodeError:
            parsed = []
    by_i = {}
    for o in parsed if isinstance(parsed, list) else []:
        if not isinstance(o, dict) or "i" not in o:
            continue
        try:
            idx = int(o["i"])
        except (ValueError, TypeError):
            continue
        ver = o.get("veredito")
        rec = {
            "veredito": ver if ver in ("ok", "violacao") else "erro_parse",
            "motivo": o.get("motivo") if o.get("motivo") in MOTIVOS else "",
            "severidade": o.get("severidade") if o.get("severidade") in SEVERIDADES else "",
            "justificativa": str(o.get("justificativa", ""))[:120],
        }
        if rec["veredito"] == "violacao" and not rec["severidade"]:
            rec["severidade"] = "qualidade"
        by_i[idx] = rec
    return [
        by_i.get(
            i,
            {
                "veredito": "erro_parse",
                "motivo": "",
                "severidade": "",
                "justificativa": "",
            },
        )
        for i in range(1, n + 1)
    ]


def _reshape_flat_writer_schema(pdf, top_k=TOP_K_SUGESTOES):
    registros = []
    required = {
        COL["subcategoria"],
        COL["origem_ean"],
        COL["origem_nome"],
        COL["sugestao_ean"],
        COL["sugestao_nome"],
        COL["rank"],
    }
    missing = required - set(pdf.columns)
    if missing:
        raise ValueError(f"recommendations_flat sem colunas esperadas: {sorted(missing)}")

    for (subcat, origem_ean), g in pdf.groupby([COL["subcategoria"], COL["origem_ean"]]):
        sug = g.sort_values(COL["rank"]).head(top_k)
        if sug.empty:
            continue
        registros.append(
            {
                "subcategoria": str(subcat),
                "origem_ean": str(origem_ean),
                "origem_nome": str(sug[COL["origem_nome"]].iloc[0]),
                "sug_eans": [str(e) for e in sug[COL["sugestao_ean"]].tolist()],
                "sug_nomes": [str(n) for n in sug[COL["sugestao_nome"]].tolist()],
                "sug_ranks": [int(r) for r in sug[COL["rank"]].tolist()],
            }
        )
    return registros


def _reshape_legacy_long_schema(pdf, top_k=TOP_K_SUGESTOES):
    c = LEGACY_LONG_COL
    registros = []
    for grupo, g in pdf.groupby(c["grupo"]):
        orig = g[g[c["role"]] == "ORIGEM"]
        sug = g[g[c["role"]] != "ORIGEM"].sort_values(c["rank"]).head(top_k)
        if orig.empty or sug.empty:
            continue
        subcat = (
            orig[c["subcategoria"]].iloc[0]
            if c["subcategoria"] in orig.columns
            else "DESCONHECIDA"
        )
        registros.append(
            {
                "subcategoria": str(subcat),
                "origem_ean": str(orig[c["ean"]].iloc[0]),
                "origem_nome": str(orig[c["nome"]].iloc[0]),
                "sug_eans": [str(e) for e in sug[c["ean"]].tolist()],
                "sug_nomes": [str(n) for n in sug[c["nome"]].tolist()],
                "sug_ranks": [int(r) for r in sug[c["rank"]].tolist()],
            }
        )
    return registros


def reshape_to_origins(pdf, top_k=TOP_K_SUGESTOES):
    if {COL["origem_ean"], COL["sugestao_ean"]}.issubset(pdf.columns):
        return _reshape_flat_writer_schema(pdf, top_k=top_k)
    if {LEGACY_LONG_COL["grupo"], LEGACY_LONG_COL["role"]}.issubset(pdf.columns):
        return _reshape_legacy_long_schema(pdf, top_k=top_k)
    raise ValueError(
        "Formato de flat não reconhecido. Esperava recommendations_flat "
        "(ean_origem/ean_sugestao) ou formato longo (_grupo/role)."
    )


def amostrar(registros, n_por_subcat=N_ORIGENS_POR_SUBCAT, seed=42):
    porsub = defaultdict(list)
    for r in registros:
        porsub[r["subcategoria"]].append(r)
    out = []
    for sc, regs in porsub.items():
        s = pd.DataFrame(regs)
        s = s.sample(min(n_por_subcat, len(s)), random_state=seed)
        out.extend(s.to_dict("records"))
    return out


def judge_origin(rec, judge_fn=None):
    sub = rec["subcategoria"]
    prompt = build_prompt(sub, rec["origem_nome"], rec["sug_nomes"], ATRIBUTOS_CRITICOS.get(sub))
    raw = call_judge_with_retry(prompt, judge_fn=judge_fn)
    veredictos = parse_response(raw, len(rec["sug_nomes"]))
    linhas = []
    for j, v in enumerate(veredictos):
        linhas.append(
            {
                "subcategoria": sub,
                "origem_ean": rec["origem_ean"],
                "origem_nome": rec["origem_nome"],
                "sugestao_ean": rec["sug_eans"][j],
                "sugestao_nome": rec["sug_nomes"][j],
                "rank": rec["sug_ranks"][j],
                "veredito": v["veredito"],
                "motivo": v["motivo"],
                "severidade": v["severidade"],
                "justificativa": v["justificativa"],
            }
        )
    return linhas


def run_judge(registros, judge_fn=None):
    linhas = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = [ex.submit(judge_origin, r, judge_fn) for r in registros]
        for k, fut in enumerate(as_completed(futs), 1):
            linhas.extend(fut.result())
            if k % 50 == 0:
                print(f"  julgadas {k}/{len(registros)} origens")
    return linhas


def aggregate(linhas):
    agg = defaultdict(lambda: {"n": 0, "viol": 0, "seg": 0, "erro": 0})
    motivos = defaultdict(lambda: defaultdict(int))
    for r in linhas:
        a = agg[r["subcategoria"]]
        a["n"] += 1
        if r["veredito"] == "violacao":
            a["viol"] += 1
            motivos[r["subcategoria"]][r["motivo"] or "sem_motivo"] += 1
            if r["severidade"] == "seguranca":
                a["seg"] += 1
        elif r["veredito"] == "erro_parse":
            a["erro"] += 1
    rank = []
    for sc, a in agg.items():
        n = max(a["n"], 1)
        top_motivo = max(motivos[sc].items(), key=lambda x: x[1])[0] if motivos[sc] else ""
        rank.append(
            {
                "subcategoria": sc,
                "sugestoes_avaliadas": a["n"],
                "taxa_violacao": round(a["viol"] / n, 4),
                "taxa_seguranca": round(a["seg"] / n, 4),
                "taxa_erro_parse": round(a["erro"] / n, 4),
                "motivo_dominante": top_motivo,
            }
        )
    rank.sort(key=lambda x: (-x["taxa_seguranca"], -x["taxa_violacao"]))
    return rank


def _display_spark_df(sdf):
    try:
        display(sdf)  # noqa: F821
    except NameError:
        sdf.show(truncate=False)


def rodar_scan(spark, filtro_subcategoria=None, judge_fn=None):
    sdf = spark.table(FLAT_TABLE)
    if filtro_subcategoria:
        sdf = sdf.filter(sdf[COL["subcategoria"]].isin(filtro_subcategoria))
    pdf = sdf.toPandas()
    print(f"Linhas do flat: {len(pdf)}")

    registros = reshape_to_origins(pdf)
    print(f"Origens reconstruídas: {len(registros)}")
    amostra = amostrar(registros)
    print(
        f"Origens amostradas p/ julgar: {len(amostra)} "
        f"(~{N_ORIGENS_POR_SUBCAT}/subcat)"
    )

    linhas = run_judge(amostra, judge_fn=judge_fn)
    print(f"Vereditos gerados: {len(linhas)}")

    sdf_v = spark.createDataFrame(pd.DataFrame(linhas))
    (
        sdf_v.write.mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(VERDICTS_TABLE)
    )

    ranking = aggregate(linhas)
    sdf_r = spark.createDataFrame(pd.DataFrame(ranking))
    (
        sdf_r.write.mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(RANKING_TABLE)
    )
    print(f"\nGravado: {VERDICTS_TABLE} e {RANKING_TABLE}")
    print("\n=== TOPO DA FILA (maior risco de segurança) ===")
    _display_spark_df(
        sdf_r.orderBy(
            sdf_r["taxa_seguranca"].desc(),
            sdf_r["taxa_violacao"].desc(),
        )
    )
    return ranking


def exportar_para_rotulagem(spark, subcats, n=10, caminho_saida=None):
    sdf = spark.table(FLAT_TABLE).filter(spark.table(FLAT_TABLE)[COL["subcategoria"]].isin(subcats))
    pdf = sdf.toPandas()
    amostra = amostrar(reshape_to_origins(pdf), n_por_subcat=n)
    rows = []
    for rec in amostra:
        for nome in rec["sug_nomes"]:
            rows.append(
                {
                    "subcategoria": rec["subcategoria"],
                    "origem_nome": rec["origem_nome"],
                    "sugestao_nome": nome,
                    "humano": "",
                }
            )
    df = pd.DataFrame(rows)
    out = caminho_saida or RANKING_TABLE + "_amostra_humana"
    spark.createDataFrame(df).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(out)
    print(f"Amostra p/ rotulagem em {out} ({len(df)} pares). Preencha a coluna 'humano'.")


def cohen_kappa(humano, juiz):
    pares = [
        (h, j)
        for h, j in zip(humano, juiz)
        if h in ("ok", "violacao") and j in ("ok", "violacao")
    ]
    if not pares:
        return None
    n = len(pares)
    po = sum(1 for h, j in pares if h == j) / n
    ph = sum(1 for h, _ in pares if h == "violacao") / n
    pj = sum(1 for _, j in pares if j == "violacao") / n
    pe = ph * pj + (1 - ph) * (1 - pj)
    kappa = 1.0 if pe == 1 else (po - pe) / (1 - pe)
    return {"kappa": round(kappa, 4), "concordancia": round(po, 4), "n": n}


def calibrar(spark, tabela_rotulada, judge_fn=None):
    pdf = spark.table(tabela_rotulada).toPandas()
    pdf = pdf[pdf["humano"].isin(["ok", "violacao"])]
    juiz_col = []
    for (sub, orig), g in pdf.groupby(["subcategoria", "origem_nome"]):
        nomes = g["sugestao_nome"].tolist()
        raw = call_judge_with_retry(
            build_prompt(sub, orig, nomes, ATRIBUTOS_CRITICOS.get(sub)),
            judge_fn=judge_fn,
        )
        ver = parse_response(raw, len(nomes))
        for v in ver:
            juiz_col.append(v["veredito"])
    res = cohen_kappa(pdf["humano"].tolist(), juiz_col)
    print(f"Calibração: {res}")
    print("Regra de bolso: kappa >= 0.6 = bom; >= 0.8 = ótimo. Abaixo, ajuste o prompt.")
    return res

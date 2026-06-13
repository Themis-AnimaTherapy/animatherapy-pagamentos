"""
db.py — camada de acesso ao Supabase.
Toda leitura e escrita passa por aqui.
O resto do código continua usando os mesmos nomes de coluna de sempre.
"""
import os
import pandas as pd
from supabase import create_client
from dotenv import load_dotenv

load_dotenv(override=True)

# ── Cliente Supabase (criado uma vez, reaproveitado) ──────────────────────────
_client = None

def _segredo(chave):
    """Lê um segredo: tenta st.secrets (Streamlit Cloud) e depois o .env (local)."""
    try:
        import streamlit as st
        return st.secrets[chave]
    except Exception:
        return os.environ.get(chave, "")

def _get():
    global _client
    if _client is None:
        _client = create_client(
            _segredo("SUPABASE_URL"),
            _segredo("SUPABASE_KEY"),
        )
    return _client

# ── Mapeamento: coluna no banco ↔ nome antigo (do CSV) ───────────────────────
_DB_PARA_CSV = {
    "mes":                "Mes",
    "ano":                "Ano",
    "data_atend":         "Data",
    "tutor":              "Tutor",
    "pet":                "Pet",
    "valor":              "Valor",
    "descontos":          "Descontos",
    "valor_liquido":      "ValorLiquido",
    "data_recebimento":   "DataRecebimento",
    "forma_pagamento":    "FormaPagamento",
    "status_atendimento": "Status_Atendimento",
    "status_pagamento":   "Status_Pagamento",
    "obs":                "OBS",
}
_CSV_PARA_DB = {v: k for k, v in _DB_PARA_CSV.items()}


def _para_csv(row):
    """Converte linha do banco em dict com os nomes antigos do CSV.
       Inclui '_id' (chave interna) para permitir atualizações por ID."""
    d = {"_id": row.get("id")}
    for db_col, csv_col in _DB_PARA_CSV.items():
        v = row.get(db_col)
        if v is None:
            d[csv_col] = ""
        elif db_col in ("valor", "descontos", "valor_liquido"):
            try:
                d[csv_col] = f"{float(v):.2f}"
            except (TypeError, ValueError):
                d[csv_col] = "0.00"
        else:
            d[csv_col] = str(v)
    return d


def _para_db(linha):
    """Converte dict CSV em dict para inserção no banco (sem '_id')."""
    d = {}
    for csv_col, db_col in _CSV_PARA_DB.items():
        v = linha.get(csv_col, "")
        if v == "" or v is None:
            v = None
        elif db_col == "ano":
            try:
                v = int(v)
            except (TypeError, ValueError):
                v = None
        elif db_col in ("valor", "descontos", "valor_liquido"):
            try:
                v = float(v)
            except (TypeError, ValueError):
                v = 0.0
        d[db_col] = v
    return d


# ── Funções públicas ──────────────────────────────────────────────────────────

def mes_ja_aberto(mes, ano):
    """True se já existem lançamentos desse mês no banco."""
    r = (_get().table("atendimentos")
              .select("id")
              .ilike("mes", mes.strip())
              .eq("ano", int(ano))
              .limit(1)
              .execute())
    return len(r.data) > 0


def carregar_linhas():
    """Retorna lista de dicts no mesmo formato de antes (+ '_id' interno)."""
    r = (_get().table("atendimentos")
              .select("*")
              .order("id")
              .execute())
    return [_para_csv(row) for row in r.data]


def inserir_linhas(linhas):
    """Insere novas linhas no banco (abrir mês / atendimento extra)."""
    records = [_para_db(l) for l in linhas]
    tamanho = 50
    for i in range(0, len(records), tamanho):
        _get().table("atendimentos").insert(records[i:i + tamanho]).execute()


def salvar_linha(row_id, updates_csv):
    """Atualiza campos de uma linha pelo ID interno do banco.
       'updates_csv' é dict com nomes no formato CSV (ex: 'Status_Pagamento')."""
    updates_db = {}
    for csv_col, valor in updates_csv.items():
        db_col = _CSV_PARA_DB.get(csv_col)
        if not db_col:
            continue
        if valor == "" or valor is None:
            updates_db[db_col] = None
        elif db_col in ("valor", "descontos", "valor_liquido"):
            try:
                updates_db[db_col] = float(valor)
            except (TypeError, ValueError):
                updates_db[db_col] = 0.0
        elif db_col == "ano":
            try:
                updates_db[db_col] = int(valor)
            except (TypeError, ValueError):
                updates_db[db_col] = None
        else:
            updates_db[db_col] = str(valor)
    _get().table("atendimentos").update(updates_db).eq("id", int(row_id)).execute()


def carregar_df():
    """Retorna DataFrame com os nomes de coluna originais."""
    linhas = carregar_linhas()
    if not linhas:
        return pd.DataFrame(columns=list(_DB_PARA_CSV.values()))
    df = pd.DataFrame(linhas)
    for col in ("Valor", "Descontos", "ValorLiquido"):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    df["Ano"] = pd.to_numeric(df["Ano"], errors="coerce").fillna(0).astype(int)
    for col in ("OBS", "DataRecebimento", "FormaPagamento"):
        df[col] = df[col].fillna("").astype(str)
    # Remove coluna interna _id (não faz parte do DataFrame original)
    if "_id" in df.columns:
        df = df.drop(columns=["_id"])
    return df

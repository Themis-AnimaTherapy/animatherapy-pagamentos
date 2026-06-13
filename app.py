# ==========================================================
#  App AnimaTherapy — versão 1 (painel de visão geral)
#  Abre no navegador. Lê o pagamentos.csv (nosso "banco de
#  dados") e mostra o resumo de cada mês de forma visual.
# ==========================================================

import os
from datetime import date

import difflib
import pandas as pd
import streamlit as st

from gestao import atualizar_status, adicionar_atendimento, abrir_mes
from conciliacao import conciliar, aplicar_conciliacao
import db

# Opções do "o que aconteceu" -> código do evento
EVENTOS = {
    "✅ Atendido": "atendido",
    "🚫 Eu cancelei (Themis)": "cancelado_themis",
    "🙅 Cliente cancelou": "cancelado_cliente",
    "♻️ Reposição": "reposicao",
    "🎉 Feriado": "feriado",
    "🏖️ Férias": "ferias",
}

MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
         "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
MES_NUM = {m.lower(): i + 1 for i, m in enumerate(MESES)}


def corrigir(nome, conhecidos, cutoff=0.85):
    """Se 'nome' for muito parecido com um já cadastrado, usa o existente
       (evita duplicado por erro de digitação). Devolve (nome, foi_corrigido)."""
    nome = (nome or "").strip()
    if not nome or nome in conhecidos:
        return nome, False
    parecidos = difflib.get_close_matches(nome, list(conhecidos), n=1, cutoff=cutoff)
    if parecidos:
        return parecidos[0], True
    return nome, False


def reais(valor):
    """Formata um número no padrão brasileiro: 1234.5 -> 'R$ 1.234,50'."""
    return "R$ " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def carregar():
    df = db.carregar_df()
    df["liq"] = pd.to_numeric(df["ValorLiquido"], errors="coerce").fillna(0.0)
    valor = pd.to_numeric(df["Valor"], errors="coerce").fillna(0.0)
    desc = pd.to_numeric(df["Descontos"], errors="coerce").fillna(0.0)
    # "potencial" = o que ela receberia (bruto menos a taxa). Usado para
    # mostrar quanto valem os cancelamentos e reposições.
    df["potencial"] = valor - desc
    # chave de ordenação por data (usa Mês+Ano; robusto a erros de ano na coluna Data)
    mnum = df["Mes"].str.strip().str.lower().map(MES_NUM).fillna(0).astype(int)
    dia = pd.to_numeric(df["Data"].str.split("/").str[0], errors="coerce").fillna(0).astype(int)
    ano = pd.to_numeric(df["Ano"], errors="coerce").fillna(0).astype(int)
    df["ordem"] = ano * 10000 + mnum * 100 + dia
    df["mnum"] = mnum   # número do mês (1-12)
    df["ano_n"] = ano   # ano como número
    return df


# ---------- Configuração da página ----------
st.set_page_config(page_title="AnimaTherapy", page_icon="🐾", layout="wide")


# ---------- Tela de login ----------
def tela_login():
    col_c, col_m, col_c2 = st.columns([1, 2, 1])
    with col_m:
        st.image("logo.png", use_container_width=True)
        st.title("Área Restrita 🔒")
        st.caption("Controle de Pagamentos — AnimaTherapy")
        senha = st.text_input("Senha", type="password", placeholder="Digite sua senha...")
        if st.button("Entrar  →", type="primary", use_container_width=True):
            if senha == st.secrets["senha"]:
                st.session_state["autenticada"] = True
                st.rerun()
            else:
                st.error("Senha incorreta. Tente novamente.")


if not st.session_state.get("autenticada"):
    tela_login()
    st.stop()


# ---------- Cabeçalho (só aparece após o login) ----------
col_logo, col_tit = st.columns([1, 3], vertical_alignment="center")
with col_logo:
    st.image("logo.png", use_container_width=True)
with col_tit:
    st.title("Controle de Pagamentos")
    st.caption("Terapia para cães e gatos 🐾")
    if st.button("Sair  🔓", key="logout"):
        st.session_state["autenticada"] = False
        st.rerun()

df = carregar()

# mensagem de sucesso que aparece DEPOIS de recarregar (ex: após gravar)
if "flash" in st.session_state:
    st.success(st.session_state.pop("flash"))

# ---------- Seletor de mês ----------
meses_disponiveis = [m for m in MESES if m in df["Mes"].values]
mes_atual = "Junho" if "Junho" in meses_disponiveis else meses_disponiveis[-1]
mes = st.selectbox("📅 Mês", meses_disponiveis,
                   index=meses_disponiveis.index(mes_atual))

dfm = df[df["Mes"] == mes]

# ---------- Barra lateral: registrar o que aconteceu ----------
with st.sidebar:
    st.header("✍️ Registrar atendimento")
    st.caption(f"Mês selecionado: **{mes}**")

    # Lista os atendimentos do mês (um por dia/tutor), em ordem de data
    dias = (dfm.sort_values("ordem")
            .drop_duplicates(subset=["Tutor", "Data"]))
    opcoes = {f"{r.Tutor} — {r.Data}  ({r.Status_Atendimento})": (r.Tutor, r.Data)
              for r in dias.itertuples()}

    if not opcoes:
        st.info("Nenhum atendimento neste mês ainda.")
    else:
        escolha = st.selectbox("Qual atendimento?", list(opcoes.keys()))
        evento_label = st.radio("O que aconteceu?", list(EVENTOS.keys()))

        if st.button("Registrar  ✅", use_container_width=True, type="primary"):
            tutor, data = opcoes[escolha]
            res = atualizar_status(tutor, data, EVENTOS[evento_label], confirmar=True)
            if res.get("ok"):
                msg = f"Registrado! {tutor} em {data} → {evento_label}"
                if res.get("reposicao"):
                    msg += "  ♻️ " + res["reposicao"]
                st.session_state["flash"] = msg
                st.rerun()   # recarrega o app com os dados novos
            else:
                st.error(res.get("msg", "Não consegui registrar."))

    # ----- Novo atendimento extra (avulso) -----
    st.divider()
    with st.expander("➕ Novo atendimento extra"):
        tutores = sorted(df["Tutor"].unique())
        pets_conhecidos = sorted(p for p in df["Pet"].unique() if p)
        with st.form("novo_atendimento", clear_on_submit=True):
            n_tutor_sel = st.selectbox("Cliente (escolha um existente)", ["—"] + tutores)
            n_tutor_novo = st.text_input("...ou digite um cliente NOVO")
            n_data = st.date_input("Data", value=date.today(), format="DD/MM/YYYY")
            n_pet = st.text_input("Pet(s)", help="Ex: Nina  ou  Lollie/Jazz/Rumi")
            n_valor = st.number_input("Valor bruto (R$)", min_value=0.0, step=10.0)
            n_desc = st.number_input("Desconto/Taxa (R$)", min_value=0.0, step=1.0)
            n_obs = st.text_input("Observação (opcional)")
            enviar = st.form_submit_button("Adicionar  ➕", type="primary",
                                           use_container_width=True)
        if enviar:
            tutor = n_tutor_novo.strip() or (n_tutor_sel if n_tutor_sel != "—" else "")
            if tutor and n_pet.strip():
                # rede de segurança contra duplicados por digitação
                tutor, tut_corr = corrigir(tutor, tutores)
                pet, pet_corr = corrigir(n_pet.strip(), pets_conhecidos)
                adicionar_atendimento(tutor, n_data.strftime("%d/%m/%y"),
                                      pet, n_valor, n_desc, n_obs.strip(), confirmar=True)
                msg = f"Adicionado: {tutor} ({pet}) em {n_data.strftime('%d/%m/%y')} — R$ {n_valor:.2f}"
                if tut_corr:
                    msg += f"  ✍️ (usei o cliente já cadastrado '{tutor}')"
                if pet_corr:
                    msg += f"  ✍️ (ajustei o pet para '{pet}')"
                st.session_state["flash"] = msg
                st.rerun()
            else:
                st.warning("Escolha/digite o Cliente e preencha o Pet.")

# ---------- Cartões de resumo (visão geral) ----------
recebido = dfm.loc[dfm["Status_Pagamento"] == "Pago", "liq"].sum()
a_receber = dfm.loc[dfm["Status_Pagamento"] == "Pendente", "liq"].sum()
previsto = dfm.loc[dfm["Status_Pagamento"] == "Previsto", "liq"].sum()

# quanto "deixou de ganhar": cancelamentos (sem cobrança) + reposições
perdido = dfm.loc[dfm["Status_Pagamento"] == "Sem cobrança", "potencial"].sum()
reposto = dfm.loc[dfm["Status_Pagamento"] == "Reposição", "potencial"].sum()
deixei_ganhar = perdido + reposto

# ----- acumulado do ano: mês corrente + meses anteriores -----
ano_sel = int(dfm["ano_n"].max()) if len(dfm) else 0
mnum_sel = MES_NUM.get(mes.lower(), 0)
acum = df[(df["ano_n"] == ano_sel) & (df["mnum"] <= mnum_sel)]
recebido_ac = acum.loc[acum["Status_Pagamento"] == "Pago", "liq"].sum()
areceber_ac = acum.loc[acum["Status_Pagamento"] == "Pendente", "liq"].sum()
previsto_ac = acum.loc[acum["Status_Pagamento"] == "Previsto", "liq"].sum()
deixei_ac = (acum.loc[acum["Status_Pagamento"] == "Sem cobrança", "potencial"].sum()
             + acum.loc[acum["Status_Pagamento"] == "Reposição", "potencial"].sum())

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("💰 Já recebido", reais(recebido))
    st.caption(f"📅 No ano: **{reais(recebido_ac)}**")
with c2:
    st.metric("⏳ A receber", reais(a_receber))
    st.caption(f"📅 No ano: **{reais(areceber_ac)}**")
with c3:
    st.metric("🔮 Ainda previsto", reais(previsto))
    st.caption(f"📅 No ano: **{reais(previsto_ac)}**")
with c4:
    st.metric("💸 Deixei de ganhar", reais(deixei_ganhar),
              help="Cancelamentos (sem cobrança) + reposições (atendi mas não cobrei, "
                   "pois já tinham sido pagas antes).")
    st.caption(f"📅 No ano: **{reais(deixei_ac)}**")

st.divider()

# ---------- Por situação: quantidade E valor ----------
st.subheader("📊 Por situação — quantos e quanto (R$)")


def resumo_por(coluna):
    g = (dfm.groupby(coluna)
            .agg(Qtd=("Pet", "size"), Valor=("potencial", "sum"))
            .reset_index()
            .sort_values("Qtd", ascending=False))
    g["Valor"] = g["Valor"].apply(reais)
    g.columns = ["Situação", "Qtd", "Valor (R$)"]
    return g


col_esq, col_dir = st.columns(2)
with col_esq:
    st.caption("💳 Status do Pagamento")
    st.table(resumo_por("Status_Pagamento"))
with col_dir:
    st.caption("🩺 Status do Atendimento")
    st.table(resumo_por("Status_Atendimento"))

st.divider()

# ---------- Tabela de atendimentos do mês ----------
st.subheader(f"📋 Atendimentos de {mes}")
tabela = dfm.sort_values("ordem")[["Data", "Tutor", "Pet", "Status_Atendimento",
                                    "Status_Pagamento", "ValorLiquido", "OBS"]].copy()
tabela.columns = ["Data", "Tutor", "Pet", "Atendimento", "Pagamento", "Líquido (R$)", "Obs."]
st.dataframe(tabela, use_container_width=True, hide_index=True)

st.caption(f"Total de {len(dfm)} atendimentos em {mes}. "
           "Fonte: Supabase (banco de dados na nuvem) ☁️")

st.divider()

# ================= AÇÕES DO MÊS =================
col_abrir, col_conc = st.columns(2)

# ---------- Abrir um novo mês ----------
with col_abrir:
    with st.expander("📅 Abrir um novo mês"):
        m_abrir = st.selectbox("Mês", MESES, key="m_abrir")
        a_abrir = st.number_input("Ano", value=2026, step=1, key="a_abrir")
        previa = abrir_mes(m_abrir, int(a_abrir), confirmar=False)   # só prévia
        if not previa["ok"]:
            st.warning(previa["msg"])
        else:
            st.caption(f"Prévia: **{previa['qtd']}** atendimentos serão criados (Previsto).")
            if st.button("Abrir mês  ✅", type="primary", key="bt_abrir"):
                r = abrir_mes(m_abrir, int(a_abrir), confirmar=True)
                st.session_state["flash"] = (f"Mês {m_abrir}/{int(a_abrir)} aberto: "
                                             f"{r['qtd']} atendimentos previstos.")
                st.rerun()

# ---------- Conciliar extrato ----------
with col_conc:
    with st.expander("🏦 Conciliar extrato bancário"):
        enviado = st.file_uploader("Envie o extrato do banco (arquivo .csv)",
                                   type=["csv"], key="up_extrato")
        if enviado is not None:
            with open("extrato-themis.csv", "wb") as f:
                f.write(enviado.getbuffer())
            st.success("Extrato recebido! ✅")

        if not os.path.exists("extrato-themis.csv"):
            st.caption("Baixe o extrato no app/site do banco (em CSV) e envie aqui em cima. 👆")
        elif st.button("Conferir extrato  🔎", key="bt_conc"):
            st.session_state["rel_conc"] = conciliar()

        if "rel_conc" in st.session_state:
            rel = st.session_state["rel_conc"]
            rotulos = {"conciliado": "✅ Pagou", "antecipado": "💳 Antecipado",
                       "sem_pendencias": "☑️ Já pago", "valor_nao_bateu": "⚠️ Não bateu",
                       "ignorado": "🚫 Ignorado", "nao_identificado": "❓ Conferir"}
            linhas_rel = []
            for r in rel:
                det = ""
                if r["status"] == "conciliado":
                    det = ", ".join(f"{a['pet']} {a['data']}" for a in r["atendimentos"])
                elif r["status"] in ("ignorado", "nao_identificado"):
                    det = r.get("pagador", "")
                linhas_rel.append([rotulos.get(r["status"], r["status"]), r["data"],
                                   r.get("cliente", ""), reais(r["valor"]), det])
            st.dataframe(pd.DataFrame(linhas_rel,
                         columns=["Situação", "Data", "Cliente", "Valor", "Detalhe"]),
                         hide_index=True, use_container_width=True)

            n_ok = sum(1 for r in rel if r["status"] == "conciliado")
            if n_ok:
                if st.button(f"Marcar {n_ok} pagamento(s) como Pago  ✅",
                             type="primary", key="bt_aplicar"):
                    res = aplicar_conciliacao(confirmar=True)
                    st.session_state.pop("rel_conc", None)
                    st.session_state["flash"] = f"{res['qtd']} atendimentos marcados como Pago!"
                    st.rerun()
            else:
                st.info("Nada para marcar como Pago neste extrato.")

# ==========================================================
#  Gestão dos atendimentos — "Abrir o mês" e atualizar status
#  Gera os atendimentos PREVISTOS e registra o que aconteceu.
# ==========================================================

from datetime import date, timedelta

# Reaproveita o cadastro e as regras de recorrência/feriado
from previsao_teste import PACIENTES, feriados_do_ano, ultima_data_real, NUM_MES, MESES

import db   # camada de acesso ao banco (Supabase)


def mes_ja_aberto(mes, ano):
    """Verifica se já existem lançamentos desse mês (pra não duplicar)."""
    return db.mes_ja_aberto(mes, ano)


def gerar_previstos(mes, ano):
    """Monta (sem gravar) as linhas previstas do mês, 1 por pet, pulando feriados."""
    num_mes = NUM_MES[mes.lower()]
    primeiro = date(ano, num_mes, 1)
    ultimo = (date(ano, 12, 31) if num_mes == 12
              else date(ano, num_mes + 1, 1) - timedelta(days=1))
    feriados = feriados_do_ano(ano)

    linhas = []
    for p in PACIENTES:
        ancora = ultima_data_real(p["match"])   # último atendimento real
        if not ancora:
            continue
        dt = ancora
        while dt < primeiro:                    # avança até o mês alvo
            dt += timedelta(days=p["freq"])
        while dt <= ultimo:
            if dt not in feriados:              # pula feriados
                liquido = p["valor"] - p["desconto"]
                for pet in p["pets_lista"]:     # uma linha por pet
                    linhas.append({
                        "Mes": mes, "Ano": ano, "Data": dt.strftime("%d/%m/%y"),
                        "Tutor": p["tutor"], "Pet": pet,
                        "Valor": f'{p["valor"]:.2f}', "Descontos": f'{p["desconto"]:.2f}',
                        "ValorLiquido": f'{liquido:.2f}',
                        "DataRecebimento": "", "FormaPagamento": "",
                        "Status_Atendimento": "Previsto", "Status_Pagamento": "Previsto",
                        "OBS": "",
                    })
            dt += timedelta(days=p["freq"])

    # ordena por data (ano, mês, dia)
    linhas.sort(key=lambda r: tuple(reversed(r["Data"].split("/"))))
    return linhas


def abrir_mes(mes, ano, confirmar=False):
    """Gera os previstos do mês. Só GRAVA se confirmar=True."""
    if mes_ja_aberto(mes, ano):
        return {"ok": False,
                "msg": f"O mês {mes}/{ano} já tem lançamentos — não vou duplicar."}

    linhas = gerar_previstos(mes, ano)

    if confirmar:
        db.inserir_linhas(linhas)

    return {"ok": True, "gravado": confirmar, "qtd": len(linhas), "linhas": linhas}


def _normaliza_data(d):
    """Aceita dd/mm/aaaa, dd/mm/aa ou dd/mm e devolve no formato dd/mm/aa."""
    partes = d.strip().split("/")
    dia = partes[0].zfill(2)
    mes = partes[1].zfill(2)
    ano = partes[2] if len(partes) > 2 else "26"
    if len(ano) == 4:
        ano = ano[2:]
    return f"{dia}/{mes}/{ano}"


def _e_antecipado(tutor):
    """Descobre se o tutor paga antecipado (Flor, Lucas)."""
    for p in PACIENTES:
        if p["match"].lower() in tutor.lower() or p["nome"].lower() in tutor.lower():
            return p["antecipado"]
    return False


def adicionar_atendimento(tutor, data, pet, valor, desconto=0.0, obs="", confirmar=False):
    """Adiciona um atendimento AVULSO (extra, fora da recorrência).
       Entra como Previsto/Previsto; depois você marca como Atendido."""
    data_n = _normaliza_data(data)
    dia, mes_num, ano2 = data_n.split("/")
    mes_nome = MESES[int(mes_num)]
    ano = 2000 + int(ano2)
    liquido = float(valor) - float(desconto)

    nova = {
        "Mes": mes_nome, "Ano": ano, "Data": data_n,
        "Tutor": tutor, "Pet": pet,
        "Valor": f"{float(valor):.2f}", "Descontos": f"{float(desconto):.2f}",
        "ValorLiquido": f"{liquido:.2f}",
        "DataRecebimento": "", "FormaPagamento": "",
        "Status_Atendimento": "Previsto", "Status_Pagamento": "Previsto",
        "OBS": obs or "Atendimento extra",
    }

    if confirmar:
        db.inserir_linhas([nova])

    return {"ok": True, "gravado": confirmar, "linha": nova}


def atualizar_status(tutor, data, evento, pet=None, confirmar=False):
    """Atualiza o status de um atendimento conforme o que aconteceu.
       evento: 'atendido', 'cancelado_themis', 'cancelado_cliente',
               'reposicao', 'feriado', 'ferias'.
       Para antecipados (Flor/Lucas), cancelamento gera reposição no mês seguinte."""
    data_n = _normaliza_data(data)

    linhas = db.carregar_linhas()

    # Acha as linhas do atendimento (um dia pode ter vários pets)
    alvos = [l for l in linhas
             if tutor.lower() in l["Tutor"].lower()
             and l["Data"] == data_n
             and (pet is None or pet.lower() == l["Pet"].lower())]
    if not alvos:
        return {"ok": False, "msg": f"Não encontrei atendimento de {tutor} em {data_n}."}

    antecip = _e_antecipado(tutor)
    mudancas = []
    linhas_a_salvar = list(alvos)   # começa com as linhas do atendimento principal

    for l in alvos:
        antes = f'{l["Status_Atendimento"]} / {l["Status_Pagamento"]}'
        if evento == "atendido":
            l["Status_Atendimento"] = "Atendido"
            l["Status_Pagamento"] = "Pago" if antecip else "Pendente"
        elif evento == "cancelado_themis":
            l["Status_Atendimento"] = "Cancelado Themis"
            if antecip:
                l["Status_Pagamento"] = "Pago"            # já tinha pago
            else:
                l["Status_Pagamento"] = "Sem cobrança"
                l["ValorLiquido"] = "0.00"
        elif evento == "cancelado_cliente":
            l["Status_Atendimento"] = "Cancelado Cliente"
            if antecip:
                l["Status_Pagamento"] = "Pago"
            else:
                l["Status_Pagamento"] = "Sem cobrança"
                l["ValorLiquido"] = "0.00"
        elif evento == "reposicao":
            # dia de reposição: atendido pra repor um cancelamento já pago.
            # Não há cobrança nova -> líquido R$ 0.
            l["Status_Atendimento"] = "Reposição"
            l["Status_Pagamento"] = "Reposição"
            l["ValorLiquido"] = "0.00"
        elif evento in ("feriado", "ferias"):
            l["Status_Atendimento"] = "Feriado" if evento == "feriado" else "Férias"
            l["Status_Pagamento"] = "Sem cobrança"
            l["ValorLiquido"] = "0.00"
        else:
            return {"ok": False, "msg": f"Evento desconhecido: {evento}"}
        depois = f'{l["Status_Atendimento"]} / {l["Status_Pagamento"]}'
        mudancas.append({"pet": l["Pet"], "antes": antes, "depois": depois})

    # Reposição: antecipado que cancelou (por você OU pelo cliente)
    reposicao = None
    if antecip and evento in ("cancelado_themis", "cancelado_cliente"):
        dia, mes, ano = data_n.split("/")
        m = int(mes)
        a = 2000 + int(ano)
        prox_m = 1 if m == 12 else m + 1
        prox_nome = MESES[prox_m]
        previstos = [l for l in linhas
                     if tutor.lower() in l["Tutor"].lower()
                     and l["Mes"].lower() == prox_nome.lower()
                     and l["Status_Atendimento"] == "Previsto"]
        previstos.sort(key=lambda r: tuple(reversed(r["Data"].split("/"))))
        n = len(alvos)
        if previstos:
            repos = previstos[:n]
            for l in repos:
                l["Status_Atendimento"] = "Reposição"
                l["Status_Pagamento"] = "Reposição"
                l["ValorLiquido"] = "0.00"
            linhas_a_salvar.extend(repos)   # inclui reposições para salvar
            reposicao = f"Marquei {min(n, len(previstos))} reposição(ões) em {prox_nome} (líquido R$ 0)."
        else:
            reposicao = (f"⚠️ {prox_nome} ainda não está aberto. Quando abrir, lembre de marcar "
                         f"{n} reposição(ões) da {tutor}.")

    if confirmar:
        campos = ["Status_Atendimento", "Status_Pagamento", "ValorLiquido"]
        for l in linhas_a_salvar:
            db.salvar_linha(l["_id"], {c: l[c] for c in campos})

    return {"ok": True, "gravado": confirmar, "tutor": tutor, "data": data_n,
            "evento": evento, "mudancas": mudancas, "reposicao": reposicao}


# ---- Demonstração: PRÉVIA de julho (não grava) ----
if __name__ == "__main__":
    res = abrir_mes("Julho", 2026, confirmar=False)
    if not res["ok"]:
        print("⚠️", res["msg"])
    else:
        print(f"PRÉVIA — {res['qtd']} atendimentos previstos para Julho (nada gravado ainda):")
        print("=" * 60)
        for l in res["linhas"]:
            print(f"  {l['Data']}  {l['Tutor']:24s} {l['Pet']:18s} líq R$ {l['ValorLiquido']}")

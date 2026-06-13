# ==========================================================
#  Conciliação bancária
#  Cruza o extrato (entradas) com os atendimentos PENDENTES,
#  casando por pagador + valor líquido. Pagamentos agrupados
#  são resolvidos por "soma de subconjunto".
# ==========================================================

import csv
from datetime import date

import db   # camada de acesso ao banco (Supabase)

EXTRATO = "extrato-themis.csv"

# DE-PARA: nome como aparece no banco -> apelido do cliente no controle
DE_PARA = {
    "CELSO PERIN": "Celso",
    "SIMONE JUBRAN": "Simone",
    "ADRIANA DUARTE": "Adriana",
    "ROLF ERIK HONGER": "Flor",      # marido da Flor faz o Pix
    "ADELE ZARZUR KHERLAKIAN": "Lucas",  # paga pelo Lucas
}

# Clientes que pagam antecipado (o depósito não casa com "pendência")
ANTECIPADOS = {"Flor", "Lucas"}

# Entradas que NÃO são pagamento de atendimento — ignorar na conciliação
# (transferências pessoais, resgates de aplicação, etc.)
IGNORAR = ["ROSICLER MALTA", "HENRIQUE PASSOS ALVALA", "RESGATE RDB"]


def _entradas(extrato):
    """Devolve só as ENTRADAS (valor > 0) do extrato."""
    with open(extrato, encoding="utf-8") as f:
        for l in csv.DictReader(f):
            try:
                v = float(l["Valor"])
            except (ValueError, KeyError):
                continue
            if v > 0:
                yield l["Data"], v, l["Descrição"]


def _identifica_cliente(descricao):
    """Acha o apelido do cliente pelo nome no extrato (de-para)."""
    d = descricao.upper()
    for nome_banco, apelido in DE_PARA.items():
        if nome_banco in d:
            return apelido
    return None


def _nome_pagador(descricao):
    """Tenta extrair o nome de quem pagou, pra mostrar nos não-identificados."""
    partes = descricao.split(" - ")
    return partes[1] if len(partes) > 1 else partes[0]


MES_NUM = {"janeiro": 1, "fevereiro": 2, "março": 3, "abril": 4, "maio": 5, "junho": 6,
           "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12}


def _data_atendimento(linha):
    """Monta a data do atendimento usando Mês + Ano (colunas confiáveis) e o
       dia da coluna Data — assim erros de digitação no ano da Data não atrapalham."""
    try:
        dia = int(linha["Data"].split("/")[0])
        mes = MES_NUM[linha["Mes"].strip().lower()]
        ano = int(linha["Ano"])
        return date(ano, mes, dia)
    except (ValueError, KeyError):
        return date(1900, 1, 1)   # se falhar, não bloqueia o casamento


def _parse_data(d):
    """Converte 'dd/mm/aa' ou 'dd/mm/aaaa' em date (ou None se não der)."""
    try:
        dia, mes, ano = d.split("/")
        ano = int(ano)
        if ano < 100:
            ano += 2000
        return date(ano, int(mes), int(dia))
    except (ValueError, AttributeError):
        return None


def _acha_subconjunto(itens, alvo_cent):
    """Acha um subconjunto de 'itens' [(idx, valor_cent)] que soma 'alvo_cent'.
       Usa programação dinâmica (trabalha em centavos, sem erro de arredondamento)."""
    alcancavel = {0: []}
    for idx, val in itens:
        novo = dict(alcancavel)
        for soma, combo in alcancavel.items():
            ns = soma + val
            if ns not in novo:
                novo[ns] = combo + [idx]
        alcancavel = novo
        if alvo_cent in alcancavel:
            break
    return alcancavel.get(alvo_cent)


def conciliar(extrato=EXTRATO, linhas=None):
    """Gera o relatório de conciliação (NÃO grava nada)."""
    if linhas is None:
        linhas = db.carregar_linhas()

    usados = set()      # índices de pendências já casadas
    relatorio = []

    for data, valor, desc in _entradas(extrato):
        # entradas que não são pagamento de cliente: ignorar
        if any(ig in desc.upper() for ig in IGNORAR):
            relatorio.append({"data": data, "valor": valor,
                              "pagador": _nome_pagador(desc), "status": "ignorado"})
            continue

        apelido = _identifica_cliente(desc)

        if apelido is None:
            relatorio.append({"data": data, "valor": valor,
                              "pagador": _nome_pagador(desc), "status": "nao_identificado"})
            continue

        # Um depósito só quita atendimentos com data ATÉ a data do depósito
        # (você recebe DEPOIS de atender; não dá pra pagar algo que ainda não aconteceu)
        corte_dep = _parse_data(data)

        # pendências disponíveis desse cliente (com valor > 0 e ainda não usadas)
        disp = [(i, round(float(linhas[i]["ValorLiquido"] or 0) * 100))
                for i, l in enumerate(linhas)
                if l["Status_Pagamento"] == "Pendente"
                and apelido.lower() in l["Tutor"].lower()
                and i not in usados
                and float(l["ValorLiquido"] or 0) > 0
                and (corte_dep is None or _data_atendimento(l) <= corte_dep)]

        achados = _acha_subconjunto(disp, round(valor * 100))

        if achados:
            usados.update(achados)
            relatorio.append({"data": data, "valor": valor, "cliente": apelido,
                              "status": "conciliado",
                              "idx": achados,
                              "atendimentos": [{"data": linhas[i]["Data"], "pet": linhas[i]["Pet"],
                                                "liq": linhas[i]["ValorLiquido"]} for i in achados]})
        elif not disp:
            relatorio.append({"data": data, "valor": valor, "cliente": apelido,
                              "status": "antecipado" if apelido in ANTECIPADOS else "sem_pendencias"})
        else:
            relatorio.append({"data": data, "valor": valor, "cliente": apelido,
                              "status": "valor_nao_bateu"})

    return relatorio


def aplicar_conciliacao(extrato=EXTRATO, confirmar=False):
    """Marca como Pago os atendimentos que a conciliação casou.
       Só GRAVA se confirmar=True."""
    linhas = db.carregar_linhas()

    rel = conciliar(extrato, linhas)   # usa a MESMA lista, índices batem
    mudancas = []
    linhas_modificadas = []

    for r in rel:
        if r["status"] != "conciliado":
            continue
        d = _parse_data(r["data"])
        data_rec = d.strftime("%d/%m/%y") if d else r["data"]
        for i in r["idx"]:
            linhas[i]["Status_Pagamento"] = "Pago"
            linhas[i]["DataRecebimento"] = data_rec
            linhas[i]["FormaPagamento"] = "Pix"
            linhas_modificadas.append(linhas[i])
            mudancas.append({"data": linhas[i]["Data"], "tutor": linhas[i]["Tutor"],
                             "pet": linhas[i]["Pet"], "liq": linhas[i]["ValorLiquido"],
                             "recebido_em": data_rec})

    if confirmar and mudancas:
        campos = ["Status_Pagamento", "DataRecebimento", "FormaPagamento"]
        for l in linhas_modificadas:
            db.salvar_linha(l["_id"], {c: l[c] for c in campos})

    return {"ok": True, "gravado": confirmar, "qtd": len(mudancas), "mudancas": mudancas}


# ---- Demonstração: relatório do extrato (não grava nada) ----
if __name__ == "__main__":
    rel = conciliar()
    print("RELATÓRIO DE CONCILIAÇÃO")
    print("=" * 60)
    for r in rel:
        if r["status"] == "conciliado":
            pets = ", ".join(f"{a['pet']} ({a['data']})" for a in r["atendimentos"])
            print(f"✅ {r['data']}  R$ {r['valor']:>8.2f}  {r['cliente']}: {pets}")
        elif r["status"] == "antecipado":
            print(f"💳 {r['data']}  R$ {r['valor']:>8.2f}  {r['cliente']}: pagamento antecipado (ok)")
        elif r["status"] == "sem_pendencias":
            print(f"☑️  {r['data']}  R$ {r['valor']:>8.2f}  {r['cliente']}: sem pendências (já estava pago)")
        elif r["status"] == "valor_nao_bateu":
            print(f"⚠️  {r['data']}  R$ {r['valor']:>8.2f}  {r['cliente']}: valor não bateu com pendências")
        elif r["status"] == "ignorado":
            print(f"🚫 {r['data']}  R$ {r['valor']:>8.2f}  ignorado (não é cliente): {r.get('pagador','?')}")
        else:
            print(f"❓ {r['data']}  R$ {r['valor']:>8.2f}  não identificado: {r.get('pagador','?')}")

# ==========================================================
#  Programa 3 — Chat com laço do agente
#  Agora é uma conversa contínua: o agente lembra do que
#  foi dito e pode usar ferramentas várias vezes sozinho.
# ==========================================================

import csv
import json
from datetime import date
from dotenv import load_dotenv
import anthropic

# Reaproveita as ferramentas que criamos nos outros arquivos
from previsao_teste import prever_faturamento
from gestao import abrir_mes, atualizar_status
from conciliacao import conciliar, aplicar_conciliacao

load_dotenv(override=True)
cliente = anthropic.Anthropic()

ARQUIVO = "pagamentos.csv"


# ----------------------------------------------------------
#  AS FERRAMENTAS (o trabalho de verdade)
# ----------------------------------------------------------

def consultar_pagamentos(status_pagamento=None, status_atendimento=None, tutor=None, mes=None):
    """Lista atendimentos, com filtros opcionais. Cada um tem 2 status."""
    with open(ARQUIVO, encoding="utf-8") as f:
        linhas = list(csv.DictReader(f))
    if status_pagamento:
        linhas = [l for l in linhas if l["Status_Pagamento"].lower() == status_pagamento.lower()]
    if status_atendimento:
        linhas = [l for l in linhas if l["Status_Atendimento"].lower() == status_atendimento.lower()]
    if tutor:
        linhas = [l for l in linhas if tutor.lower() in l["Tutor"].lower()]
    if mes:
        linhas = [l for l in linhas if l["Mes"].lower() == mes.lower()]
    return [
        {"data": l["Data"], "tutor": l["Tutor"], "pet": l["Pet"],
         "valor_liquido": l["ValorLiquido"],
         "atendimento": l["Status_Atendimento"], "pagamento": l["Status_Pagamento"],
         "obs": l["OBS"]}
        for l in linhas
    ]


def resumo_financeiro(mes=None):
    """Soma o líquido por status de PAGAMENTO e conta por status de ATENDIMENTO."""
    with open(ARQUIVO, encoding="utf-8") as f:
        linhas = list(csv.DictReader(f))
    if mes:
        linhas = [l for l in linhas if l["Mes"].lower() == mes.lower()]
    liquido_por_pagamento = {}
    qtd_por_atendimento = {}
    for l in linhas:
        sp = l["Status_Pagamento"]
        sa = l["Status_Atendimento"]
        valor = float(l["ValorLiquido"] or 0)
        liquido_por_pagamento[sp] = liquido_por_pagamento.get(sp, 0) + valor
        qtd_por_atendimento[sa] = qtd_por_atendimento.get(sa, 0) + 1
    return {"mes": mes or "todos",
            "liquido_por_status_pagamento": liquido_por_pagamento,
            "qtd_por_status_atendimento": qtd_por_atendimento,
            "qtd_total": len(linhas)}


# Pequenos "embrulhos" pra ano padrão e nomes de ferramenta
def prever(mes, ano=2026, reposicoes=None):
    return prever_faturamento(mes, ano, reposicoes)


def _abrir_mes(mes, ano=2026, confirmar=False):
    return abrir_mes(mes, ano, confirmar)


def _atualizar_status(tutor, data, evento, pet=None, confirmar=False):
    return atualizar_status(tutor, data, evento, pet, confirmar)


def _conciliar_extrato(extrato="extrato-themis.csv"):
    return conciliar(extrato)


def _aplicar_conciliacao(extrato="extrato-themis.csv", confirmar=False):
    return aplicar_conciliacao(extrato, confirmar)


# Uma "agenda" que liga o nome da ferramenta à função de verdade
FUNCOES = {
    "consultar_pagamentos": consultar_pagamentos,
    "resumo_financeiro": resumo_financeiro,
    "prever_faturamento": prever,
    "abrir_mes": _abrir_mes,
    "atualizar_status": _atualizar_status,
    "conciliar_extrato": _conciliar_extrato,
    "aplicar_conciliacao": _aplicar_conciliacao,
}


# ----------------------------------------------------------
#  AS ETIQUETAS (descrições para o Claude)
# ----------------------------------------------------------
FERRAMENTAS = [
    {
        "name": "consultar_pagamentos",
        "description": "Lista atendimentos individuais. Cada um tem DOIS status: "
                       "atendimento (Previsto, Atendido, Cancelado Themis, Cancelado Cliente, "
                       "Reposição, Feriado, Férias) e pagamento (Previsto, Pendente, Pago, "
                       "Reposição, Sem cobrança). Filtros todos opcionais.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status_pagamento": {"type": "string", "description": "Filtra pelo status do PAGAMENTO. Ex: Pago, Pendente, Reposição, Sem cobrança"},
                "status_atendimento": {"type": "string", "description": "Filtra pelo status do ATENDIMENTO. Ex: Atendido, Cancelado Themis, Cancelado Cliente, Reposição, Feriado, Férias"},
                "tutor": {"type": "string", "description": "Nome ou parte do nome do tutor"},
                "mes": {"type": "string", "description": "Ex: Janeiro, Fevereiro, Março, Abril, Maio"},
            },
            "required": [],
        },
    },
    {
        "name": "resumo_financeiro",
        "description": "Devolve o LÍQUIDO somado por status de PAGAMENTO (Pago, Pendente, etc.) "
                       "e a contagem por status de ATENDIMENTO. Use para totais/faturamento já "
                       "realizado (Pago = recebido; Pendente = a receber). Pode filtrar por mes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "mes": {"type": "string", "description": "Ex: Março. Se vazio, considera todos os meses."},
            },
            "required": [],
        },
    },
    {
        "name": "prever_faturamento",
        "description": "Faz a PREVISÃO de faturamento de um mês FUTURO, com base na recorrência "
                       "dos pacientes (dia da semana + frequência semanal/quinzenal). Gera as datas "
                       "reais e já EXCLUI os feriados. Use para perguntas como 'quanto devo receber "
                       "em agosto', 'previsão de julho', 'se todos vierem'. Retorna total_bruto e "
                       "total_liquido: destaque o LÍQUIDO, que é o que de fato fica após as taxas. "
                       "Por paciente retorna sessoes_atendidas, reposicoes e sessoes_cobradas: "
                       "reposição é um dia já pago (cliente que paga antecipado, como Flor e Lucas) "
                       "que será atendido SEM cobrar de novo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "mes": {"type": "string", "description": "Mês a prever. Ex: Junho, Julho, Agosto."},
                "ano": {"type": "integer", "description": "Ano. Se não informado, usa 2026."},
                "reposicoes": {
                    "type": "object",
                    "description": "Reposições a descontar da cobrança, por cliente. "
                                   "Ex: {\"Flor\": 1} = 1 atendimento da Flor neste mês é reposição "
                                   "(dia já pago), então será atendido mas não cobrado. "
                                   "Só faz sentido para quem paga antecipado (Flor, Lucas).",
                    "additionalProperties": {"type": "integer"},
                },
            },
            "required": ["mes"],
        },
    },
    {
        "name": "abrir_mes",
        "description": "Gera os atendimentos PREVISTOS de um mês (1 linha por pet), a partir da "
                       "recorrência dos pacientes. Não duplica mês já aberto. IMPORTANTE: chame "
                       "PRIMEIRO com confirmar=false para mostrar a prévia; só chame confirmar=true "
                       "depois que a usuária confirmar que pode gravar.",
        "input_schema": {
            "type": "object",
            "properties": {
                "mes": {"type": "string", "description": "Ex: Junho, Julho, Agosto."},
                "ano": {"type": "integer", "description": "Ano. Se não informado, usa 2026."},
                "confirmar": {"type": "boolean", "description": "false = só prévia (não grava); true = grava. Sempre prévia primeiro."},
            },
            "required": ["mes"],
        },
    },
    {
        "name": "atualizar_status",
        "description": "Atualiza o status de um atendimento quando a usuária conta o que aconteceu. "
                       "Mapeie a fala dela para o evento: atendi/atendido→atendido; eu cancelei/"
                       "cancelei→cancelado_themis; cliente/tutor cancelou→cancelado_cliente; "
                       "é reposição/foi reposição/repor→reposicao; feriado→feriado; férias→ferias. "
                       "Regras automáticas já aplicadas: atendido vira Pendente (ou Pago se antecipado "
                       "Flor/Lucas); cancelamento de antecipado gera reposição no mês seguinte; "
                       "reposicao deixa o atendimento e o pagamento como Reposição (líquido R$ 0, já "
                       "pago antes). IMPORTANTE: chame PRIMEIRO com confirmar=false (prévia), mostre o "
                       "que vai mudar, e só confirmar=true após o 'sim' dela.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tutor": {"type": "string", "description": "Nome do tutor. Ex: Adriana, Flor, Celso, Lucas, Simone."},
                "data": {"type": "string", "description": "Data do atendimento. Ex: 04/06/2026 ou 04/06."},
                "evento": {"type": "string",
                           "enum": ["atendido", "cancelado_themis", "cancelado_cliente", "reposicao", "feriado", "ferias"],
                           "description": "O que aconteceu com o atendimento."},
                "pet": {"type": "string", "description": "Opcional: nome do pet, se for só um. Vazio = todos os pets do dia."},
                "confirmar": {"type": "boolean", "description": "false = prévia; true = grava. Sempre prévia primeiro."},
            },
            "required": ["tutor", "data", "evento"],
        },
    },
    {
        "name": "conciliar_extrato",
        "description": "Lê o extrato bancário e gera o RELATÓRIO de conciliação (quem pagou o quê), "
                       "SEM gravar nada. Casa por pagador + valor líquido. Use quando a usuária pedir "
                       "pra conferir/conciliar o extrato. Mostra: conciliados (vão virar Pago), "
                       "antecipados (Flor/Lucas), sem pendências, valor não bateu, e não identificados "
                       "(que ela precisa conferir na mão).",
        "input_schema": {
            "type": "object",
            "properties": {
                "extrato": {"type": "string", "description": "Arquivo do extrato. Padrão: extrato-themis.csv"},
            },
            "required": [],
        },
    },
    {
        "name": "aplicar_conciliacao",
        "description": "MARCA como Pago (com data de recebimento e forma Pix) os atendimentos que a "
                       "conciliação casou no extrato. IMPORTANTE: rode conciliar_extrato primeiro pra "
                       "mostrar o relatório, e só chame aqui com confirmar=true depois que a usuária "
                       "confirmar. Com confirmar=false devolve a prévia do que será marcado.",
        "input_schema": {
            "type": "object",
            "properties": {
                "extrato": {"type": "string", "description": "Arquivo do extrato. Padrão: extrato-themis.csv"},
                "confirmar": {"type": "boolean", "description": "false = prévia; true = grava de verdade. Sempre prévia primeiro."},
            },
            "required": [],
        },
    },
]

# Uma instrução de "personalidade" pro agente
INSTRUCAO = (
    "Você é o assistente financeiro da AnimaTherapy (terapia para cães e gatos). "
    f"Hoje é {date.today().strftime('%d/%m/%Y')}. "
    "Responda em português do Brasil, de forma clara e simpática. Valores em reais (R$). "
    "Use as ferramentas para buscar dados reais antes de responder sobre pagamentos. "
    "Clientes que pagam ANTECIPADO: Flor e Lucas (os demais pagam por atendimento). "
    "REGRA DE SEGURANÇA: ao ESCREVER dados (abrir_mes, atualizar_status), SEMPRE faça a "
    "prévia primeiro (confirmar=false), mostre claramente o que vai mudar e PEÇA confirmação; "
    "só grave (confirmar=true) depois que a usuária responder que sim."
)


# ----------------------------------------------------------
#  O LAÇO DO AGENTE
#  Recebe a conversa, e fica usando ferramentas até terminar.
# ----------------------------------------------------------
def rodar_agente(mensagens):
    while True:
        resposta = cliente.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            system=INSTRUCAO,
            tools=FERRAMENTAS,
            messages=mensagens,
        )
        # Guarda o que o Claude disse/pediu
        mensagens.append({"role": "assistant", "content": resposta.content})

        # Se ele NÃO pediu ferramenta, terminou: devolve o texto
        if resposta.stop_reason != "tool_use":
            texto = "".join(b.text for b in resposta.content if b.type == "text")
            return texto, mensagens

        # Se pediu ferramentas, executamos TODAS e devolvemos os resultados
        resultados = []
        for bloco in resposta.content:
            if bloco.type == "tool_use":
                print(f"   🔧 (usando {bloco.name} {json.dumps(bloco.input, ensure_ascii=False)})")
                saida = FUNCOES[bloco.name](**bloco.input)
                resultados.append({
                    "type": "tool_result",
                    "tool_use_id": bloco.id,
                    "content": json.dumps(saida, ensure_ascii=False),
                })
        mensagens.append({"role": "user", "content": resultados})
        # volta ao topo do laço: o Claude vê os resultados e continua


# ----------------------------------------------------------
#  O CHAT (conversa contínua no terminal)
# ----------------------------------------------------------
print("=" * 55)
print("  💚 Assistente de Pagamentos AnimaTherapy")
print("  Pergunte o que quiser. Digite 'sair' para encerrar.")
print("=" * 55)

conversa = []  # a memória da conversa inteira

while True:
    try:
        pergunta = input("\nVocê: ").strip()
    except EOFError:
        break
    if pergunta.lower() in ("sair", "exit", "quit", ""):
        print("\nAté logo! 💚")
        break

    conversa.append({"role": "user", "content": pergunta})
    resposta, conversa = rodar_agente(conversa)
    print("\nAssistente:", resposta)

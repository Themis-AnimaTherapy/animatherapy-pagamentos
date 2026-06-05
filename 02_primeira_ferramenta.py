# ==========================================================
#  Programa 2 — A primeira ferramenta
#  O Claude vai PEDIR pra consultar os pagamentos, nós
#  executamos a consulta e devolvemos o resultado pra ele.
# ==========================================================

import csv
import json
from dotenv import load_dotenv
import anthropic

load_dotenv(override=True)
cliente = anthropic.Anthropic()


# ----------------------------------------------------------
#  PARTE A — A função de verdade (o "trabalho braçal")
#  Ela lê o CSV e devolve os atendimentos, podendo filtrar
#  por status (ex: "Pendente") e/ou por tutor.
# ----------------------------------------------------------
def consultar_pagamentos(status=None, tutor=None):
    with open("pagamentos.csv", encoding="utf-8") as f:
        linhas = list(csv.DictReader(f))

    # Aplica os filtros, se foram pedidos
    if status:
        linhas = [l for l in linhas if l["Status"].lower() == status.lower()]
    if tutor:
        linhas = [l for l in linhas if tutor.lower() in l["Tutor"].lower()]

    # Devolve uma versão enxuta, só com o que importa
    resultado = []
    for l in linhas:
        resultado.append({
            "data": l["Data"],
            "tutor": l["Tutor"],
            "pet": l["Pet"],
            "valor": l["ValorLiquido"],
            "status": l["Status"],
        })
    return resultado


# ----------------------------------------------------------
#  PARTE B — A "etiqueta" da ferramenta
#  É a DESCRIÇÃO que o Claude lê pra entender o que a
#  ferramenta faz e quais informações pode passar.
# ----------------------------------------------------------
ferramentas = [
    {
        "name": "consultar_pagamentos",
        "description": "Consulta a lista de atendimentos e pagamentos da AnimaTherapy. "
                       "Pode filtrar por status do pagamento e/ou por nome do tutor.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Filtrar por status. Ex: Pago, Pendente, "
                                   "Reposição, Cancelado Cliente, Cancelado Themis.",
                },
                "tutor": {
                    "type": "string",
                    "description": "Filtrar por nome (ou parte do nome) do tutor.",
                },
            },
            "required": [],
        },
    }
]


# ----------------------------------------------------------
#  PARTE C — A conversa
# ----------------------------------------------------------
pergunta = "Quem está com pagamento pendente? Some o total que falta receber."
print("VOCÊ:", pergunta, "\n")

# Começamos a lista de mensagens com a pergunta
mensagens = [{"role": "user", "content": pergunta}]

# 1ª chamada: mandamos a pergunta + a lista de ferramentas
resposta = cliente.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1000,
    tools=ferramentas,          # <- aqui entregamos as ferramentas ao Claude
    messages=mensagens,
)

# O Claude decidiu usar uma ferramenta?
if resposta.stop_reason == "tool_use":
    # Guardamos o pedido do Claude na conversa
    mensagens.append({"role": "assistant", "content": resposta.content})

    # Procuramos qual ferramenta ele pediu e com quais dados
    for bloco in resposta.content:
        if bloco.type == "tool_use":
            print(">> O Claude pediu a ferramenta:", bloco.name)
            print(">> Com os dados:", json.dumps(bloco.input, ensure_ascii=False), "\n")

            # NÓS executamos a função de verdade
            dados = consultar_pagamentos(**bloco.input)
            print(">> Encontramos", len(dados), "atendimentos. Devolvendo ao Claude...\n")

            # Devolvemos o resultado pro Claude (amarrado pelo tool_use_id)
            mensagens.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": bloco.id,
                    "content": json.dumps(dados, ensure_ascii=False),
                }],
            })

    # 2ª chamada: agora o Claude responde de verdade, já com os dados
    resposta_final = cliente.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        tools=ferramentas,
        messages=mensagens,
    )
    print("CLAUDE:", resposta_final.content[0].text)
else:
    # Caso ele responda direto, sem usar ferramenta
    print("CLAUDE:", resposta.content[0].text)

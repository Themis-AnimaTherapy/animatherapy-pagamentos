# ==========================================================
#  Migração: separar a coluna "Status" em DUAS:
#    - Status_Atendimento (o que rolou com a sessão)
#    - Status_Pagamento   (a situação do dinheiro)
#  Regras de valor líquido:
#    - Reposição / Sem cobrança / Feriado / Férias  ->  R$ 0,00
#  A coluna OBS é preservada.
# ==========================================================

import csv
import shutil

# De-para: status antigo (minúsculo) -> (Atendimento, Pagamento)
MAPA = {
    "pago":              ("Atendido",          "Pago"),
    "pendente":          ("Atendido",          "Pendente"),
    "reposição":         ("Reposição",         "Reposição"),
    "reposicao":         ("Reposição",         "Reposição"),
    "cancelado themis":  ("Cancelado Themis",  "Sem cobrança"),
    "cancelado cliente": ("Cancelado Cliente", "Sem cobrança"),
    "feriado":           ("Feriado",           "Sem cobrança"),
    "férias":            ("Férias",            "Sem cobrança"),
    "ferias":            ("Férias",            "Sem cobrança"),
    "previsto":          ("Previsto",          "Previsto"),
}

# Situações em que o líquido vira R$ 0,00
ZERA_LIQUIDO = {"Reposição", "Sem cobrança"}

# 1) Backup da planilha atual
shutil.copy("pagamentos.csv", "pagamentos_backup_status_unico.csv")
print("✅ Backup salvo em: pagamentos_backup_status_unico.csv")

# 2) Lê a planilha atual
with open("pagamentos.csv", encoding="utf-8") as f:
    linhas = list(csv.DictReader(f))

# 3) Monta as linhas novas, com as duas colunas
novas = []
for l in linhas:
    s = (l["Status"] or "").strip().lower()
    atendimento, pagamento = MAPA.get(s, ("Previsto", "Previsto"))
    liquido = l["ValorLiquido"]
    if pagamento in ZERA_LIQUIDO:
        liquido = "0.00"
    novas.append({
        "Mes": l["Mes"], "Ano": l["Ano"], "Data": l["Data"],
        "Tutor": l["Tutor"], "Pet": l["Pet"],
        "Valor": l["Valor"], "Descontos": l["Descontos"], "ValorLiquido": liquido,
        "DataRecebimento": l["DataRecebimento"], "FormaPagamento": l["FormaPagamento"],
        "Status_Atendimento": atendimento, "Status_Pagamento": pagamento,
        "OBS": l["OBS"],
    })

# 4) Grava a planilha nova (mesmo nome)
campos = ["Mes", "Ano", "Data", "Tutor", "Pet", "Valor", "Descontos", "ValorLiquido",
          "DataRecebimento", "FormaPagamento",
          "Status_Atendimento", "Status_Pagamento", "OBS"]
with open("pagamentos.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=campos)
    w.writeheader()
    w.writerows(novas)

print(f"✅ {len(novas)} atendimentos migrados para o formato de 2 colunas.")

# 5) Mostra um resumo do resultado
from collections import Counter
ca = Counter(n["Status_Atendimento"] for n in novas)
cp = Counter(n["Status_Pagamento"] for n in novas)
print("\nStatus do ATENDIMENTO:")
for k, v in ca.most_common():
    print(f"   {k:20s}: {v}")
print("\nStatus do PAGAMENTO:")
for k, v in cp.most_common():
    print(f"   {k:20s}: {v}")

# ==========================================================
#  Teste da ferramenta de PREVISÃO de faturamento
#  Projeta os atendimentos futuros com base na recorrência
#  de cada paciente (dia da semana + frequência).
# ==========================================================

import csv
from datetime import date, timedelta
import holidays   # peça que conhece os feriados nacionais do Brasil

ARQUIVO = "pagamentos.csv"

# --- Cadastro dos pacientes (confirmado por você) ---
# match  = parte do nome do tutor pra achar nos dados
# freq   = de quantos em quantos dias ele vem (7=semanal, 14=quinzenal)
# pets   = quantas cobranças por sessão
# valor  = valor por pet/cobrança
# valor = valor BRUTO por pet;  desconto = taxa por pet
# (o LÍQUIDO, que é o que de fato fica, é valor - desconto)
# antecipado = paga o mês inteiro ANTES de atender (Flor e Lucas)
PACIENTES = [
    {"nome": "Adriana", "match": "Adriana", "tutor": "Adriana Duarte Corrias",
     "pets_lista": ["Nina", "George"], "freq": 7,  "pets": 2, "valor": 200, "desconto": 10,   "antecipado": False},
    {"nome": "Flor",    "match": "Flor",    "tutor": "Flor Padilha",
     "pets_lista": ["Luna", "Kiara"], "freq": 7,  "pets": 2, "valor": 250, "desconto": 12.5, "antecipado": True},
    {"nome": "Lucas",   "match": "Lucas",   "tutor": "Lucas Curiati",
     "pets_lista": ["Maia", "Luna"], "freq": 7,  "pets": 2, "valor": 230, "desconto": 0,    "antecipado": True},
    {"nome": "Celso",   "match": "Celso",   "tutor": "Celso Perin",
     "pets_lista": ["Guga", "Serena"], "freq": 14, "pets": 2, "valor": 200, "desconto": 0,    "antecipado": False},
    {"nome": "Simone",  "match": "Simone",  "tutor": "Simone Jubran",
     "pets_lista": ["Lollie/Jazz/Rumi"], "freq": 14, "pets": 1, "valor": 380, "desconto": 0, "antecipado": False},
]

MESES = {1:"Janeiro",2:"Fevereiro",3:"Março",4:"Abril",5:"Maio",6:"Junho",
         7:"Julho",8:"Agosto",9:"Setembro",10:"Outubro",11:"Novembro",12:"Dezembro"}
NUM_MES = {v.lower(): k for k, v in MESES.items()}


def feriados_do_ano(ano):
    """Monta os feriados que VOCÊ escolheu excluir:
       nacionais oficiais + Carnaval (terça) + feriados de São Paulo.
       (Corpus Christi fica de fora: você atende nesse dia.)"""
    # 1) Nacionais oficiais (já vêm prontos)
    feriados = dict(holidays.Brazil(years=ano))

    # 2) Carnaval — segunda E terça (weekday 0 e 1)
    opcionais = holidays.Brazil(years=ano, categories=("optional",))
    for dia, nome in opcionais.items():
        if "Carnaval" in nome and dia.weekday() in (0, 1):
            feriados[dia] = "Carnaval"

    # 3) Feriados da cidade de São Paulo
    feriados[date(ano, 1, 25)] = "Aniversário de São Paulo"
    feriados[date(ano, 7, 9)] = "Revolução Constitucionalista (SP)"

    return feriados


def ultima_data_real(match):
    """Acha o atendimento mais recente (de 2026) de um paciente nos dados."""
    with open(ARQUIVO, encoding="utf-8") as f:
        linhas = list(csv.DictReader(f))
    datas = []
    for l in linhas:
        if match.lower() in l["Tutor"].lower():
            try:
                d, m, a = l["Data"].split("/")
                dt = date(2000 + int(a), int(m), int(d))
                if dt.year == 2026:          # ignora datas com erro de digitação
                    datas.append(dt)
            except Exception:
                pass
    return max(datas) if datas else None


def prever_faturamento(mes, ano, reposicoes=None):
    """Gera a previsão de atendimentos e receita de um mês futuro.
       reposicoes: dicionário {cliente: quantidade} de dias JÁ PAGOS que
       serão repostos neste mês — você atende, mas NÃO cobra."""
    num_mes = NUM_MES[mes.lower()]
    # primeiro e último dia do mês alvo
    primeiro = date(ano, num_mes, 1)
    if num_mes == 12:
        ultimo = date(ano, 12, 31)
    else:
        ultimo = date(ano, num_mes + 1, 1) - timedelta(days=1)

    feriados = feriados_do_ano(ano)   # feriados que você escolheu excluir

    resultado = {"mes": mes, "ano": ano, "pacientes": [],
                 "total_bruto": 0.0, "total_liquido": 0.0,
                 "feriados_pulados": []}

    for p in PACIENTES:
        ancora = ultima_data_real(p["match"])
        if not ancora:
            continue
        # avança a partir da âncora até cair no mês alvo
        dt = ancora
        while dt < primeiro:
            dt = dt + timedelta(days=p["freq"])
        datas_no_mes = []
        while dt <= ultimo:
            if dt in feriados:
                # caiu em feriado: não conta, mas anota pra mostrar
                resultado["feriados_pulados"].append(
                    f"{p['nome']}: {dt.strftime('%d/%m/%Y')} ({feriados[dt]})")
            else:
                datas_no_mes.append(dt)
            dt = dt + timedelta(days=p["freq"])

        n = len(datas_no_mes)                 # dias que ela vai ATENDER
        # quantas reposições (dias já pagos) descontar deste cliente
        repo = 0
        for k, v in (reposicoes or {}).items():
            if p["nome"].lower() in k.lower() or k.lower() in p["nome"].lower():
                repo += int(v)
        cobradas = max(0, n - repo)           # dias que ela vai COBRAR
        liquido_por_pet = p["valor"] - p["desconto"]
        sub_bruto = cobradas * p["pets"] * p["valor"]
        sub_liquido = cobradas * p["pets"] * liquido_por_pet
        resultado["total_bruto"] += sub_bruto
        resultado["total_liquido"] += sub_liquido
        resultado["pacientes"].append({
            "nome": p["nome"],
            "antecipado": p["antecipado"],
            "datas": [d.strftime("%d/%m/%Y") for d in datas_no_mes],
            "sessoes_atendidas": n,
            "reposicoes": repo,
            "sessoes_cobradas": cobradas,
            "subtotal_bruto": sub_bruto,
            "subtotal_liquido": sub_liquido,
        })
    return resultado


# ---- Demonstração: previsão de alguns meses ----
def mostrar(mes, ano, reposicoes=None):
    prev = prever_faturamento(mes, ano, reposicoes)
    print("=" * 56)
    print(f"  🔮 PREVISÃO DE FATURAMENTO — {prev['mes']}/{prev['ano']}")
    print("=" * 56)
    for p in prev["pacientes"]:
        cab = f"\n• {p['nome']}  ({p['sessoes_atendidas']} a atender"
        if p["reposicoes"]:
            cab += f", {p['reposicoes']} reposição → cobra {p['sessoes_cobradas']}"
        cab += ")"
        print(cab)
        print(f"    Datas: {', '.join(p['datas'])}")
        print(f"    Líquido: R$ {p['subtotal_liquido']:.2f}  (bruto R$ {p['subtotal_bruto']:.2f})")
    if prev["feriados_pulados"]:
        print("\n  🚫 Sessões puladas por feriado:")
        for f in prev["feriados_pulados"]:
            print(f"     - {f}")
    print("\n" + "-" * 56)
    print(f"  TOTAL LÍQUIDO previsto (o que fica): R$ {prev['total_liquido']:.2f}")
    print(f"  (total bruto seria R$ {prev['total_bruto']:.2f})")
    print("-" * 56 + "\n")

# Só roda a demonstração se este arquivo for executado direto
# (não roda quando o assistente o "importa" para reaproveitar a função).
if __name__ == "__main__":
    # Exemplo do seu caso: a Flor tem 1 reposição em junho (1 dia já pago em maio)
    mostrar("Junho", 2026, {"Flor": 1})
    mostrar("Julho", 2026)

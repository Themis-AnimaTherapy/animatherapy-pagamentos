# ==========================================================
#  Programa 1 — "Olá, Claude"
#  Objetivo: mandar uma pergunta pro Claude e ver a resposta
# ==========================================================

# 1) Importamos as "peças" que vamos usar
import os                          # pra ler a chave secreta do ambiente
from dotenv import load_dotenv     # pra carregar o arquivo .env
import anthropic                   # o conector com o Claude

# 2) Carrega a chave secreta do arquivo .env
#    override=True garante que a chave do arquivo vença qualquer
#    variável vazia que já exista no sistema.
load_dotenv(override=True)

# 3) Cria o "cliente" — é quem conversa com o Claude por nós.
#    Ele pega a chave automaticamente da variável ANTHROPIC_API_KEY.
cliente = anthropic.Anthropic()

# 4) Mandamos a pergunta e guardamos a resposta
print("Mandando pergunta pro Claude... aguarde um instante.\n")

resposta = cliente.messages.create(
    model="claude-sonnet-4-6",     # qual "cérebro" usar
    max_tokens=300,                # tamanho máximo da resposta
    messages=[
        {
            "role": "user",        # quem fala: o usuário (você)
            "content": "Olá! Me explique em uma frase curta o que é um agente de IA.",
        }
    ],
)

# 5) Mostra na tela só o texto da resposta
print("Claude respondeu:\n")
print(resposta.content[0].text)

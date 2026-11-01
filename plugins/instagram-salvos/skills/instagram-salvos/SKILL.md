---
name: instagram-salvos
description: >
  Transforma os posts SALVOS do Instagram do usuário numa base de conhecimento local e pesquisável:
  usa o login que já está no navegador (nunca pede senha), baixa os salvos, transcreve os vídeos com
  Whisper no próprio computador, resume cada post com título, tags e gancho, e mantém um INDEX.md leve.
  Use SEMPRE que o usuário quiser baixar, exportar, transcrever ou indexar os posts salvos do Instagram
  ("puxa meus salvos", "baixa meus salvos", "atualiza meus salvos"), ou quando perguntar algo sobre o que
  salvou ("o que eu salvei sobre X?", "tem algum salvo sobre Y?"). Para perguntas, vá direto para
  "Buscar na base". Feita pela Escale IA (escaleia.com).
---

# Instagram salvos → base de conhecimento

Você conduz o processo inteiro. O usuário pode nunca ter usado terminal: **explique cada passo em uma
frase simples, sem jargão, e diga o que cada comando faz antes de rodar**. O medo mais comum é o
Instagram bloquear a conta; trate isso com calma e transparência.

## Regras que não se quebram

1. **Nunca peça a senha do Instagram.** O login é o do navegador do próprio usuário.
2. **Antes de baixar qualquer coisa, mostre qual conta está logada e espere o usuário confirmar.**
3. **No máximo 50 posts por rodada.** Base grande se constrói em rodadas, em dias diferentes.
4. **Ao primeiro sinal de limite do Instagram, pare.** O script já para sozinho; não rode de novo antes
   de 30–60 minutos. Explique que é temporário e não é bloqueio.
5. Tudo fica no computador do usuário: a transcrição roda local, nada é enviado para servidor nenhum.

## Onde ficam as coisas

- Esta skill: a pasta onde está este `SKILL.md` (chame de `SKILL_DIR`). Script: `SKILL_DIR/scripts/salvos.py`.
- Dados: na pasta do projeto aberto, em `instagram-salvos/`:

```
instagram-salvos/
├── config.json     # preferências (criado na conversa inicial)
├── INDEX.md        # 1 linha por post: título, tags, autor (gerado pelo script)
└── posts/<data>_<autor>_<código>/
    ├── post.md     # legenda, transcrição e resumo
    └── midia/      # vídeo e imagens
```

- Ambiente Python isolado: `.venv-instagram-salvos/` na pasta do projeto. Chame o Python dele de `PY`:
  Windows `.venv-instagram-salvos\Scripts\python.exe`; Mac/Linux `.venv-instagram-salvos/bin/python`.

## 1. Conversa inicial

Se `instagram-salvos/config.json` existe, leia e pergunte só se quer mudar algo. Senão, pergunte uma
coisa por vez, em tom leve:

1. **Qual o @ da conta** cujos salvos vamos puxar. Diga: "o risco é baixo (só lemos os seus salvos,
   devagar), mas se tiver uma conta secundária com os mesmos salvos, é a opção mais tranquila".
2. **Quantos posts nesta rodada** (sugira 30; máximo 50) e explique o porquê em uma frase.
3. **Quais categorias** usar nas tags. Sugira 4–6 a partir do que a pessoa faz (ex.: `ganchos`,
   `vendas`, `ferramentas-ia`, `edicao-de-video`, `ideias-de-conteudo`). Poucas e fixas funcionam melhor.
4. **Manter os vídeos** depois de transcrever, ou apagar para economizar espaço (texto e imagens ficam).

Salve em `instagram-salvos/config.json`:

```json
{ "conta": "usuario", "max_por_rodada": 30, "categorias": ["ganchos", "vendas"], "manter_videos": false }
```

## 2. Preparar o computador (só na primeira vez)

Peça permissão antes de instalar e diga o que é cada coisa.

1. Python 3.10 a 3.13 (`python --version`, no Mac `python3`). Sem Python: Windows
   `winget install Python.Python.3.13`; Mac `brew install python@3.13` ou o instalador de python.org.
   Python 3.14 ainda não tem todas as peças da transcrição: use 3.13.
2. Ambiente isolado ("uma caixinha só para esta skill, não mexe no resto do computador"):
   `python -m venv .venv-instagram-salvos`
3. Dependências: `PY -m pip install -r SKILL_DIR/requirements.txt`
   (requests, faster-whisper e av na versão que funciona com ele; leva alguns minutos).
4. Não precisa de ffmpeg nem de yt-dlp.

## 3. Login (sem senha)

O caminho que funciona em Windows e Mac é o **Firefox**: o Chrome e o Edge no Windows criptografam o
login e não dá para reaproveitar.

1. Peça: "abra o Firefox (janela normal, não anônima), entre em instagram.com e veja se a conta ativa é
   a @CONTA". Sem Firefox: Windows `winget install Mozilla.Firefox`; Mac `brew install --cask firefox`
   ou firefox.com.
2. Rode `PY SKILL_DIR/scripts/salvos.py verificar`. Ele pergunta ao Instagram de quem é a sessão, sem
   baixar nada.
3. **Mostre a conta que apareceu e espere o "sim"** do usuário.

No Mac, quem prefere Chrome ou Safari pode usar `--navegador chrome` ou `--navegador safari` antes do
comando (precisa de `PY -m pip install browser_cookie3`; o Mac pede acesso ao Keychain: clicar em Permitir).

## 4. Puxar e transcrever

```
PY SKILL_DIR/scripts/salvos.py puxar --confirmo @CONTA --max N
```

- Baixa os salvos mais recentes que ainda não estão na base, depois transcreve os vídeos e gera o
  `INDEX.md`. Na segunda rodada em diante, para sozinho ao chegar nos que já foram baixados.
- Se `--confirmo` não bater com a conta logada, aborta sem baixar nada.
- Na primeira vez o Whisper baixa ~500 MB. Rode em segundo plano e avise que demora alguns minutos.
- Interrompeu no meio? É só rodar de novo: o que já foi baixado não se perde, e
  `PY SKILL_DIR/scripts/salvos.py transcrever` termina as transcrições pendentes.
- Vídeo só com música dá transcrição "(sem fala)": normal, resuma pela legenda.

## 5. Resumir e taguear (trabalho seu)

Rode `PY SKILL_DIR/scripts/salvos.py pendentes`. Para cada `post.md` da lista, leia legenda e
transcrição (em carrossel, olhe as imagens em `midia/`) e edite o próprio arquivo:

- `titulo:` até 8 palavras dizendo o que o post ensina ou mostra. Resuma, não copie a legenda.
- `tags:` 1 a 3 categorias do `config.json`, separadas por vírgula. Nenhuma serve? Use `outros` e
  conte ao usuário no final (talvez valha uma categoria nova).
- Seção **Resumo**: do que trata (1 frase), o gancho dos primeiros segundos (literal, quando houver
  fala) e o que dá para aproveitar.
- `status: novo` → `status: resumido`.

Depois rode `PY SKILL_DIR/scripts/salvos.py indice`.

## 6. Fechar a rodada

Diga quantos posts entraram, quais tags apareceram e destaque 2–3 posts que valem a pena. Lembre que
na próxima vez basta pedir "atualiza meus salvos".

## Buscar na base

Quando perguntarem "o que eu salvei sobre X?":

1. Leia só o `instagram-salvos/INDEX.md`.
2. Escolha as linhas cujo título ou tags combinam com a pergunta.
3. Abra apenas esses `post.md` e responda citando o @ do autor e o link. Não leia todos os posts: o
   índice existe para caber no contexto mesmo com centenas de salvos.

## Problemas comuns

| Sintoma | O que fazer |
|---|---|
| "Não achei o Instagram logado no Firefox" | Entrar em instagram.com no Firefox (janela normal) e rodar de novo. |
| "o Instagram pediu para esperar" / HTTP 429 | Parar. Esperar 30–60 min. Não é bloqueio. |
| "a sessão do navegador pode ter expirado" | Abrir instagram.com no navegador, confirmar que está logado, rodar `verificar` de novo. |
| Instagram pede para confirmar que foi você | O usuário aprova no próprio app/navegador e depois roda `verificar`. |
| Erro instalando `av` ou `faster-whisper` | Python 3.14 ou muito antigo: instalar o 3.13 e recriar o `.venv-instagram-salvos`. |
| Erro qualquer | Mostrar a mensagem ao usuário em linguagem simples e propor o próximo passo; nunca insistir contra o Instagram. |

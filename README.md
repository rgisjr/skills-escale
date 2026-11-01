# Skills da Escale IA para o Claude Code

Skills gratuitas que a [Escale IA](https://www.escaleia.com) usa no dia a dia, prontas para instalar
no seu Claude Code.

| Skill | O que faz |
|---|---|
| [instagram-salvos](plugins/instagram-salvos/skills/instagram-salvos/SKILL.md) | Transforma os seus posts salvos do Instagram numa base que o Claude consulta: baixa, transcreve no seu computador, resume e indexa. |

## Instalar

### Jeito mais fácil (Windows ou Mac, app do Claude ou terminal)

Abra o Claude Code e cole este pedido:

```
Instale a skill instagram-salvos da Escale IA no meu computador:
1. Baixe https://github.com/rgisjr/skills-escale/archive/refs/heads/main.zip
2. Copie a pasta plugins/instagram-salvos/skills/instagram-salvos de dentro do zip
   para a pasta de skills do Claude no meu usuário (~/.claude/skills/instagram-salvos).
3. Apague o zip baixado e me avise quando terminar.
```

Depois abra uma conversa nova, numa pasta de projeto, e peça:

> puxa meus salvos do instagram

### Pelo terminal (plugin)

```
/plugin marketplace add rgisjr/skills-escale
/plugin install instagram-salvos@escale-ia
```

## instagram-salvos

1. Usa o login que já está no seu navegador (Firefox). **Nunca pede senha.**
2. Mostra qual conta está logada e só baixa depois que você confirma.
3. Baixa os salvos em lotes de até 50, com pausas, e para sozinho se o Instagram pedir para esperar.
4. Transcreve os vídeos com Whisper **no seu computador**. Nada vai para servidor nenhum.
5. O Claude resume cada post (título, tags, gancho) e mantém um `INDEX.md` leve.

Depois é só perguntar:

> o que eu salvei sobre ganchos de Reels?

**Requisitos:** Windows, Mac ou Linux com Python 3.10 a 3.13 (o Claude instala se faltar) e o Firefox
logado no Instagram. No Mac também dá para usar o Chrome ou o Safari.

## Segurança

- Se puder, use uma conta secundária que tenha os mesmos salvos. O risco é baixo (a skill só lê os
  seus próprios salvos, devagar), mas conta reserva é tranquilidade.
- Os dados ficam numa pasta `instagram-salvos/` dentro do seu projeto.

---

Feito pela [Escale IA](https://www.escaleia.com): CRM, automação e IA para empresas venderem mais.
Licença MIT.

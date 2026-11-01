#!/usr/bin/env python3
"""Posts salvos do Instagram -> base de conhecimento local (skill instagram-salvos, Escale IA).

Usa o login que já está no navegador (nunca pede senha): o arquivo de cookies exportado do
Chrome pela extensão "Get cookies.txt LOCALLY" ou, se não houver, o login do Firefox. Lê a aba Salvos pela mesma
chamada que o instagram.com faz, baixa a mídia, transcreve os vídeos com Whisper
rodando no próprio computador e mantém um post.md por post + o INDEX.md.

Comandos (rode dentro da pasta do projeto; os dados ficam em ./instagram-salvos/):
  verificar                 mostra qual conta está logada no navegador (não baixa nada)
  puxar --confirmo @conta   baixa os salvos novos, transcreve e atualiza o índice
  transcrever               transcreve vídeos que ficaram sem transcrição
  pendentes                 lista os posts que o Claude ainda não resumiu
  indice                    regenera o INDEX.md a partir dos post.md
"""
import argparse
import json
import os
import platform
import sqlite3
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = Path.cwd() / 'instagram-salvos'
POSTS = BASE / 'posts'
INDEX = BASE / 'INDEX.md'
CONFIG = BASE / 'config.json'

MAX_PADRAO = 50             # teto recomendado por rodada
PARAR_APOS_CONHECIDOS = 5   # salvos já baixados em sequência = acabou o que é novo
PAUSA_PADRAO = 3            # segundos entre posts; evita limite do Instagram
MODELO_WHISPER = 'small'

URL_SALVOS = 'https://www.instagram.com/api/v1/feed/saved/posts/'
URL_CONTA = 'https://www.instagram.com/api/v1/accounts/edit/web_form_data/'
APP_ID_WEB = '936619743392459'  # id público do app web do Instagram
# O Instagram confere se o navegador da requisição é o mesmo da sessão: o User-Agent usa a versão instalada.
CHROME_PADRAO = '140.0.0.0'
FIREFOX_PADRAO = '140.0'
ARQUIVO_COOKIES = '*instagram.com_cookies.txt'  # nome que a extensão Get cookies.txt LOCALLY dá ao arquivo
TIPOS = {1: 'imagem', 2: 'reel', 8: 'carrossel'}
TRANSCRICAO_PENDENTE = '## Transcrição\n\n(pendente)'


class LimiteInstagram(Exception):
    """O Instagram pediu para esperar ou derrubou a sessão: parar na hora, sem insistir."""


# ---------- login do navegador ----------

def sistema_ua():
    return {'Windows': 'Windows NT 10.0; Win64; x64', 'Darwin': 'Macintosh; Intel Mac OS X 10_15_7'}.get(
        platform.system(), 'X11; Linux x86_64')


def versao_chrome():
    """Versão do Chrome instalado (para o User-Agent bater com o navegador de onde vieram os cookies)."""
    try:
        if platform.system() == 'Windows':
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Google\Chrome\BLBeacon') as chave:
                return winreg.QueryValueEx(chave, 'version')[0]
        if platform.system() == 'Darwin':
            import plistlib
            info = Path('/Applications/Google Chrome.app/Contents/Info.plist')
            return plistlib.loads(info.read_bytes())['CFBundleShortVersionString']
    except (OSError, KeyError, ValueError):
        pass
    return CHROME_PADRAO


def ua_chrome():
    major = versao_chrome().split('.')[0]
    return (f'Mozilla/5.0 ({sistema_ua()}) AppleWebKit/537.36 (KHTML, like Gecko) '
            f'Chrome/{major}.0.0.0 Safari/537.36')


def ua_firefox(perfil=None):
    versao = FIREFOX_PADRAO
    ini = perfil / 'compatibility.ini' if perfil else None
    if ini and ini.exists():
        for linha in ini.read_text(encoding='utf-8', errors='ignore').splitlines():
            if linha.startswith('LastVersion='):
                versao = linha.split('=', 1)[1].split('_')[0].split('.')[0] + '.0'
    sistema = sistema_ua().replace('Intel Mac OS X 10_15_7', 'Intel Mac OS X 10.15')
    return f'Mozilla/5.0 ({sistema}; rv:{versao}) Gecko/20100101 Firefox/{versao}'


def arquivo_de_cookies(caminho=None):
    """O cookies.txt exportado do Chrome: o informado, ou o mais recente na pasta atual ou em Downloads."""
    if caminho:
        arquivo = Path(caminho).expanduser()
        if not arquivo.exists():
            raise SystemExit(f'Não achei o arquivo de cookies {arquivo}.')
        return arquivo
    candidatos = [a for pasta in (Path.cwd(), Path.home() / 'Downloads') if pasta.exists()
                  for a in pasta.glob(ARQUIVO_COOKIES)]
    return max(candidatos, key=lambda a: a.stat().st_mtime) if candidatos else None


def cookies_do_arquivo(arquivo):
    """Lê o formato cookies.txt (Netscape): domínio, flag, caminho, seguro, validade, nome, valor."""
    cookies = {}
    for linha in arquivo.read_text(encoding='utf-8', errors='ignore').splitlines():
        if linha.startswith('#HttpOnly_'):
            linha = linha[len('#HttpOnly_'):]
        partes = linha.split('\t')
        if linha.startswith('#') or len(partes) < 7 or 'instagram.com' not in partes[0]:
            continue
        cookies[partes[5]] = partes[6].strip()
    if 'sessionid' not in cookies:
        raise SystemExit(f'O arquivo {arquivo.name} não tem o login do Instagram. Abra instagram.com no Chrome '
                         '(logado), clique na extensão Get cookies.txt LOCALLY e em "Export" de novo.')
    return cookies


def pastas_firefox():
    casa = Path.home()
    sistema = platform.system()
    if sistema == 'Windows':
        return [Path(os.environ.get('APPDATA', casa / 'AppData' / 'Roaming')) / 'Mozilla' / 'Firefox' / 'Profiles']
    if sistema == 'Darwin':
        return [casa / 'Library' / 'Application Support' / 'Firefox' / 'Profiles']
    return [casa / '.mozilla' / 'firefox', casa / 'snap' / 'firefox' / 'common' / '.mozilla' / 'firefox']


def cookies_firefox(obrigatorio=True):
    """Lê os cookies do Instagram direto do banco do Firefox (perfil mais recente que esteja logado)."""
    bancos = [b for pasta in pastas_firefox() if pasta.exists() for b in pasta.glob('*/cookies.sqlite')]
    for banco in sorted(bancos, key=lambda b: b.stat().st_mtime, reverse=True):
        # immutable=1 lê mesmo com o Firefox aberto, sem travar o arquivo
        conexao = sqlite3.connect(f'file:{banco.as_posix()}?immutable=1', uri=True)
        try:
            cookies = dict(conexao.execute(
                "SELECT name, value FROM moz_cookies WHERE host LIKE '%instagram.com'").fetchall())
        finally:
            conexao.close()
        if 'sessionid' in cookies:
            return cookies, banco.parent
    if obrigatorio:
        raise SystemExit('Não achei o Instagram logado no Firefox. Abra o Firefox, entre em instagram.com '
                         '(janela normal, não anônima) e rode de novo.')
    return None, None


def cookies_outro_navegador(nome):
    try:
        import browser_cookie3
    except ImportError:
        raise SystemExit(f'Para ler direto do {nome} instale o browser_cookie3 no ambiente da skill '
                         '(pip install browser_cookie3). No Windows use o arquivo exportado do Chrome.')
    try:
        jarra = getattr(browser_cookie3, nome)(domain_name='instagram.com')
    except Exception as e:  # cada navegador falha de um jeito (chave, keychain, banco travado)
        raise SystemExit(f'Não consegui ler o login do {nome} ({type(e).__name__}). '
                         'No Windows o Chrome/Edge criptografam os cookies: use o arquivo exportado '
                         'pela extensão Get cookies.txt LOCALLY.')
    cookies = {c.name: c.value for c in jarra}
    if 'sessionid' not in cookies:
        raise SystemExit(f'O {nome} não está logado no Instagram. Entre em instagram.com por ele e rode de novo.')
    return cookies


SEM_LOGIN = ('Não achei o login do Instagram. Jeito mais fácil (Chrome):\n'
             '  1. Instale a extensão "Get cookies.txt LOCALLY" na Chrome Web Store.\n'
             '  2. Abra instagram.com no Chrome, logado na sua conta.\n'
             '  3. Clique no ícone da extensão e em "Export". O arquivo vai para Downloads.\n'
             '  4. Rode de novo.')


def login(args):
    """Escolhe de onde vem o login e devolve (cookies, user_agent, origem)."""
    if args.navegador in ('auto', 'arquivo'):
        arquivo = arquivo_de_cookies(args.cookies)
        if arquivo:
            return cookies_do_arquivo(arquivo), ua_chrome(), f'arquivo {arquivo.name}, Chrome'
        if args.navegador == 'arquivo':
            raise SystemExit(SEM_LOGIN)
    if args.navegador in ('auto', 'firefox'):
        cookies, perfil = cookies_firefox(obrigatorio=args.navegador == 'firefox')
        if cookies:
            return cookies, ua_firefox(perfil), 'Firefox'
        raise SystemExit(SEM_LOGIN)
    if args.navegador == 'safari':
        ua = f'Mozilla/5.0 ({sistema_ua()}) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15'
    else:
        ua = ua_chrome()
    return cookies_outro_navegador(args.navegador), ua, args.navegador


def sessao_logada(args):
    cookies, user_agent, origem = login(args)
    sessao = requests.Session()
    sessao.cookies.update(cookies)
    sessao.headers.update({
        'User-Agent': user_agent,
        'X-IG-App-ID': APP_ID_WEB,
        'X-Requested-With': 'XMLHttpRequest',
        'X-CSRFToken': cookies.get('csrftoken', ''),
        'Referer': 'https://www.instagram.com/',
    })
    sessao.origem = origem
    return sessao


def pedir_json(sessao, url, **kwargs):
    resposta = sessao.get(url, timeout=30, **kwargs)
    eh_json = 'json' in resposta.headers.get('content-type', '')
    if resposta.status_code == 429 or (eh_json and 'wait a few minutes' in resposta.text.lower()):
        raise LimiteInstagram('o Instagram pediu para esperar alguns minutos')
    if resposta.status_code != 200 or not eh_json:
        raise LimiteInstagram(f'o Instagram não respondeu (HTTP {resposta.status_code}); '
                              'a sessão do navegador pode ter expirado')
    return resposta.json()


def conta_logada(sessao):
    """Pergunta ao próprio Instagram de quem é a sessão (a tela "Editar perfil" do site)."""
    conta = pedir_json(sessao, URL_CONTA).get('form_data', {}).get('username')
    if not conta:
        raise SystemExit('O login do navegador está incompleto. Saia e entre de novo no instagram.com.')
    return conta


# ---------- salvos ----------

@dataclass(frozen=True)
class Post:
    codigo: str
    autor: str
    tipo: str
    data: datetime
    legenda: str
    curtidas: object
    comentarios: object
    views: object
    midias: tuple  # ((url, extensão), ...)


def post_do_json(m):
    nos = m.get('carousel_media') or [m]
    midias = tuple((n['video_versions'][0]['url'], 'mp4') if n.get('video_versions')
                   else (n['image_versions2']['candidates'][0]['url'], 'jpg') for n in nos)
    return Post(
        codigo=m['code'], autor=m['user']['username'], tipo=TIPOS.get(m.get('media_type'), 'post'),
        data=datetime.fromtimestamp(m['taken_at'], tz=timezone.utc),
        legenda=(m.get('caption') or {}).get('text') or '',
        curtidas=m.get('like_count', ''), comentarios=m.get('comment_count', ''),
        views=m.get('play_count') or m.get('view_count') or '', midias=midias)


def salvos(sessao, pausa):
    """Mesma chamada que o instagram.com faz na aba Salvos, página por página."""
    cursor = None
    while True:
        dados = pedir_json(sessao, URL_SALVOS, params={'max_id': cursor} if cursor else {})
        for registro in dados.get('items', []):
            yield post_do_json(registro['media'])
        cursor = dados.get('next_max_id')
        if not dados.get('more_available') or not cursor:
            return
        time.sleep(pausa)


def codigos_baixados():
    return {ler_frontmatter(md).get('codigo') for md in POSTS.glob('*/post.md')}


def escrever_post_md(post, pasta):
    legenda = post.legenda.strip() or '(sem legenda)'
    (pasta / 'post.md').write_text(f"""---
codigo: {post.codigo}
autor: "@{post.autor}"
link: https://www.instagram.com/p/{post.codigo}/
tipo: {post.tipo}
publicado: {post.data:%Y-%m-%d}
baixado: {datetime.now():%Y-%m-%d}
curtidas: {post.curtidas}
comentarios: {post.comentarios}
views: {post.views}
titulo:
tags:
status: novo
---

# @{post.autor} · {post.tipo} · {post.data:%d/%m/%Y}

## Legenda

{legenda}

{TRANSCRICAO_PENDENTE}

## Resumo

- **Do que trata:**
- **Gancho (primeiros segundos):**
- **O que dá para aproveitar:**
""", encoding='utf-8')


def baixar(post):
    pasta = POSTS / f'{post.data:%Y-%m-%d}_{post.autor}_{post.codigo}'
    midia = pasta / 'midia'
    midia.mkdir(parents=True, exist_ok=True)
    # os links de mídia já vêm assinados pelo Instagram: o download não usa a sua conta
    for i, (url, ext) in enumerate(post.midias, 1):
        resposta = requests.get(url, timeout=120, headers={'User-Agent': ua_chrome()})
        resposta.raise_for_status()
        (midia / f'{post.codigo}_{i}.{ext}').write_bytes(resposta.content)
    escrever_post_md(post, pasta)
    return pasta


# ---------- transcrição e índice ----------

def transcrever(manter_videos=True):
    pendentes = [md for md in sorted(POSTS.glob('*/post.md'))
                 if TRANSCRICAO_PENDENTE in md.read_text(encoding='utf-8')]
    modelo = None
    for n, md in enumerate(pendentes, 1):
        videos = sorted((md.parent / 'midia').glob('*.mp4'))
        if not videos:
            transcricao = '(sem vídeo; veja as imagens em midia/)'
        else:
            if modelo is None:
                print(f'Carregando o Whisper "{MODELO_WHISPER}" (na primeira vez baixa ~500 MB)...')
                from faster_whisper import WhisperModel
                modelo = WhisperModel(MODELO_WHISPER, device='cpu', compute_type='int8')
            print(f'  [{n}/{len(pendentes)}] transcrevendo {md.parent.name}')
            partes = []
            for i, video in enumerate(videos, 1):
                segmentos, _ = modelo.transcribe(str(video), vad_filter=True)
                texto = ' '.join(s.text.strip() for s in segmentos).strip() or '(sem fala)'
                partes.append(f'**Vídeo {i}:** {texto}' if len(videos) > 1 else texto)
                if not manter_videos:
                    video.unlink()
            transcricao = '\n\n'.join(partes)
        md.write_text(md.read_text(encoding='utf-8').replace(
            TRANSCRICAO_PENDENTE, f'## Transcrição\n\n{transcricao}', 1), encoding='utf-8')


def ler_frontmatter(md):
    texto = md.read_text(encoding='utf-8')
    bloco = texto.split('---', 2)[1] if texto.startswith('---') else ''
    campos = {}
    for linha in bloco.strip().splitlines():
        chave, _, valor = linha.partition(':')
        campos[chave.strip()] = valor.strip().strip('"')
    return campos


def indice():
    linhas = []
    for md in sorted(POSTS.glob('*/post.md'), reverse=True):
        c = ler_frontmatter(md)
        rel = md.relative_to(BASE).as_posix()
        titulo = c.get('titulo') or '(ainda sem resumo)'
        tags = ' '.join(f'#{t.strip()}' for t in c.get('tags', '').split(',') if t.strip())
        linhas.append(f"- [{titulo}]({rel}) — {tags or '#sem-tag'} · {c.get('autor', '')} · {c.get('tipo', '')}")
    INDEX.write_text(
        '# Índice dos salvos do Instagram\n\n'
        '<!-- Gerado por salvos.py indice. Claude: leia este arquivo primeiro e abra só os post.md que '
        'interessam. Título e tags vêm do post.md; para mudar, edite lá e rode indice de novo. -->\n\n'
        f'{len(linhas)} posts · atualizado em {datetime.now():%d/%m/%Y %H:%M}\n\n'
        + '\n'.join(linhas) + '\n', encoding='utf-8')


def pendentes():
    for md in sorted(POSTS.glob('*/post.md')):
        if ler_frontmatter(md).get('status', 'novo') == 'novo':
            print(md.relative_to(Path.cwd()).as_posix())


# ---------- comandos ----------

def ler_config():
    return json.loads(CONFIG.read_text(encoding='utf-8')) if CONFIG.exists() else {}


def cmd_verificar(args):
    sessao = sessao_logada(args)
    try:
        conta = conta_logada(sessao)
    except LimiteInstagram as e:
        raise SystemExit(f'Não consegui confirmar a conta: {e}. Espere 30–60 minutos e tente de novo.')
    print('=' * 50)
    print(f'  CONTA LOGADA ({sessao.origem}): @{conta}')
    print('=' * 50)
    print('Nada foi baixado. Confirme se é a conta certa antes de puxar.')


def cmd_puxar(args):
    sessao = sessao_logada(args)
    confirmada = args.confirmo.lstrip('@').lower()
    novos, seguidos = 0, 0
    try:
        conta = conta_logada(sessao)
        if conta.lower() != confirmada:
            raise SystemExit(f'ABORTADO: o navegador está logado em @{conta}, não em @{confirmada}. Nada foi baixado.')
        sessao.headers['Referer'] = f'https://www.instagram.com/{conta}/saved/'
        conhecidos = codigos_baixados()
        for post in salvos(sessao, args.pausa):
            if post.codigo in conhecidos:
                seguidos += 1
                if seguidos >= PARAR_APOS_CONHECIDOS:
                    break
                continue
            seguidos = 0
            baixar(post)
            novos += 1
            print(f'  [{novos}] @{post.autor} · {post.tipo} · {post.codigo}')
            if novos >= args.max:
                break
            time.sleep(args.pausa)
    except LimiteInstagram as e:
        print(f'\nPAREI: {e}. Isso é temporário e não bloqueia a conta. '
              'O que já baixou está salvo; rode de novo em 30–60 minutos.')
    print(f'\n{novos} posts novos baixados.')
    transcrever(ler_config().get('manter_videos', True))
    indice()
    print(f'Índice atualizado: {INDEX}')


def main():
    for saida in (sys.stdout, sys.stderr):
        if hasattr(saida, 'reconfigure'):
            saida.reconfigure(encoding='utf-8')  # legendas com emoji quebram o console do Windows
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--navegador', default='auto',
                    choices=['auto', 'arquivo', 'firefox', 'chrome', 'edge', 'brave', 'safari'],
                    help='de onde vem o login (padrão auto: arquivo exportado do Chrome, senão Firefox)')
    ap.add_argument('--cookies', help='caminho do arquivo exportado (padrão: o mais recente em Downloads)')
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('verificar')
    p = sub.add_parser('puxar')
    p.add_argument('--confirmo', required=True, help='@ da conta que você confirmou no verificar')
    p.add_argument('--max', type=int, default=MAX_PADRAO, help=f'posts novos por rodada (padrão {MAX_PADRAO})')
    p.add_argument('--pausa', type=float, default=PAUSA_PADRAO, help='segundos entre posts')
    sub.add_parser('transcrever')
    sub.add_parser('pendentes')
    sub.add_parser('indice')
    args = ap.parse_args()
    POSTS.mkdir(parents=True, exist_ok=True)

    if args.cmd == 'verificar':
        cmd_verificar(args)
    elif args.cmd == 'puxar':
        cmd_puxar(args)
    elif args.cmd == 'transcrever':
        transcrever(ler_config().get('manter_videos', True))
        indice()
    elif args.cmd == 'pendentes':
        pendentes()
    else:
        indice()


if __name__ == '__main__':
    main()

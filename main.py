import os
import json
import asyncio
import pathlib
from io import BytesIO
import requests
from datetime import datetime, timezone
from typing import Optional
import html
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from PIL import Image, ImageDraw, ImageFont
import edge_tts

import models
from database import SessionLocal, engine

# Carrega as variáveis do arquivo .env
load_dotenv()

TELEGRAM_TOKEN =os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
API_SECRET_KEY = os.getenv("API_SECRET_KEY")
# --- ALTERAÇÃO 1: O sistema agora captura a URL do Netlify salva no seu .env ---
URL_MINI_APP = os.getenv("URL_MINI_APP")
# Sua tag de associado da Amazon (ex: seunome-20), cadastre no .env
AMAZON_AFFILIATE_TAG = os.getenv("AMAZON_AFFILIATE_TAG")
# Seu usuário e ID de ferramenta de afiliado do Mercado Livre (matt_word e
# matt_tool). Pra descobrir os seus: gere um link de afiliado de qualquer
# produto na Central de Afiliados, abra/expanda o link e veja esses dois
# parâmetros na URL completa.
MERCADOLIVRE_MATT_WORD = os.getenv("MERCADOLIVRE_MATT_WORD")
MERCADOLIVRE_MATT_TOOL = os.getenv("MERCADOLIVRE_MATT_TOOL")

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Meu Encurtador de Afiliados")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://statuesque-choux-9132e6.netlify.app",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
# ==========================================
# PROTEÇÃO DA API
# ==========================================
def verificar_chave_api(x_api_key: Optional[str] = Header(default=None)):
    chave_correta = os.getenv("API_SECRET_KEY")

    if not chave_correta:
        raise HTTPException(
            status_code=500,
            detail="API_SECRET_KEY não configurada no servidor."
        )

    if x_api_key != chave_correta:
        raise HTTPException(
            status_code=401,
            detail="Chave de API inválida."
        )

    return True
@app.get("/")
def read_root():
    return {"status": "ok", "mensagem": "O servidor FastAPI está a rodar perfeitamente na nuvem!"}

# ==========================================
# MODELOS PYDANTIC
# ==========================================
class ProdutoCreate(BaseModel):
    slug: str
    plataforma: str
    id_produto_original: str
    nome_produto: str
    preco_original: Optional[float] = None
    preco_oferta: float
    imagem_url: Optional[str] = None


# ==========================================
# DEPENDÊNCIAS
# ==========================================
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ==========================================
# FUNÇÕES DE SERVIÇO (LÓGICA ISOLADA)
# ==========================================
def montar_link_afiliado_amazon(link_ou_id: str) -> str:
    """
    A Amazon aceita duas formas de link de afiliado:
    1) um link amzn.to já pronto (gerado no site/app da Amazon, por
       produto) — nesse caso, usamos ele direto, sem mexer;
    2) qualquer outra URL de produto (ou só o ASIN) — nesse caso, dá pra
       automatizar 100% só adicionando '?tag=SUA_TAG'.
    """
    from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

    if not AMAZON_AFFILIATE_TAG:
        raise ValueError(
            "Defina AMAZON_AFFILIATE_TAG no seu .env com sua tag de associado "
            "da Amazon (ex: seunome-20) antes de publicar produtos da Amazon."
        )

    if link_ou_id.startswith("http"):
        host = urlparse(link_ou_id).netloc.lower()
        if "amzn.to" in host:
            # Já é um link de afiliado pronto — não mexe.
            return link_ou_id
        partes = urlparse(link_ou_id)
        query = parse_qs(partes.query)
        query["tag"] = [AMAZON_AFFILIATE_TAG]
        nova_query = urlencode(query, doseq=True)
        return urlunparse(partes._replace(query=nova_query))

    # Só o ASIN/ID foi colado: monta a URL padrão de produto da Amazon.
    asin = link_ou_id.strip("/")
    return f"https://www.amazon.com.br/dp/{asin}?tag={AMAZON_AFFILIATE_TAG}"


def montar_link_afiliado_mercadolivre(link_ou_id: str) -> str:
    """
    Descoberta nova: assim como a Amazon, o Mercado Livre aceita reaproveitar
    a mesma tag de afiliado (matt_word + matt_tool) em qualquer link de
    produto — não precisa mais gerar um link único por produto no site.
    """
    from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

    if not MERCADOLIVRE_MATT_WORD or not MERCADOLIVRE_MATT_TOOL:
        raise ValueError(
            "Defina MERCADOLIVRE_MATT_WORD e MERCADOLIVRE_MATT_TOOL no seu .env "
            "com os valores da sua tag de afiliado do Mercado Livre antes de "
            "publicar produtos dessa plataforma."
        )

    if link_ou_id.startswith("http"):
        partes = urlparse(link_ou_id)
        query = parse_qs(partes.query)
        query["matt_word"] = [MERCADOLIVRE_MATT_WORD]
        query["matt_tool"] = [MERCADOLIVRE_MATT_TOOL]
        nova_query = urlencode(query, doseq=True)
        return urlunparse(partes._replace(query=nova_query))

    # Só o ID do produto foi colado: monta a URL padrão do Mercado Livre.
    id_limpo = link_ou_id if link_ou_id.startswith("/") else f"/{link_ou_id}"
    return (
        f"https://www.mercadolivre.com.br{id_limpo}"
        f"?matt_word={MERCADOLIVRE_MATT_WORD}&matt_tool={MERCADOLIVRE_MATT_TOOL}"
    )


def gerar_novo_link_na_api(id_produto_original: str, plataforma: str) -> str:
    """Gera o link de afiliado e previne a duplicação de URLs."""
    plataforma_lower = plataforma.lower()
    id_limpo = id_produto_original.strip()

    if "amazon" in plataforma_lower:
        # Amazon é tratada à parte: injeta a tag automaticamente, seja num
        # link completo colado ou num ASIN puro.
        return montar_link_afiliado_amazon(id_limpo)

    if "mercado" in plataforma_lower or "livre" in plataforma_lower:
        # Mercado Livre também é tratado à parte agora: injeta matt_word e
        # matt_tool automaticamente, igual à Amazon.
        return montar_link_afiliado_mercadolivre(id_limpo)

    # Se o usuário já colou um link completo no formulário, não tenta montar de novo
    if id_limpo.startswith("http"):
        return id_limpo

    # Garante que tenha uma barra no começo para não quebrar a URL gerada
    if not id_limpo.startswith("/"):
        id_limpo = f"/{id_limpo}"

    if "shopee" in plataforma_lower:
        # A Shopee não tem tag reaproveitável (diferente de Amazon/Mercado
        # Livre): o link de afiliado é gerado por produto, no app/painel
        # deles ("Obter link"). Por isso é obrigatório colar o link
        # completo — não dá pra fabricar um a partir só do ID.
        raise ValueError(
            "Para Shopee, cole o link de afiliado completo "
            "(ex: https://shope.ee/XXXXXXX) gerado no app ou em "
            "affiliate.shopee.com.br — não é possível gerar esse link "
            "automaticamente a partir só do ID do produto."
        )

    elif "aliexpress" in plataforma_lower or "ali" in plataforma_lower:
        # Na prática, o link de afiliado do AliExpress já costuma vir pronto
        # (ex: https://s.click.aliexpress.com/e/_c3IJEhxP), então ele já cai
        # no "if id_limpo.startswith('http')" lá em cima. Este ramo é só um
        # reforço, caso um dia você cole apenas o ID do produto.
        return f"https://s.click.aliexpress.com{id_limpo}"

    return f"https://suaapi.com{id_limpo}"


def eh_link_de_afiliado(link: str, plataforma: str) -> bool:
    """
    Confere se um link colado pelo usuário bate com o domínio de afiliado
    esperado da plataforma escolhida. Usado só quando a pessoa cola um link
    completo (que não passa por gerar_novo_link_na_api) — pra evitar que um
    link direto do produto (sem comissão) seja postado sem ninguém perceber.
    """
    from urllib.parse import urlparse
    host = urlparse(link).netloc.lower()
    plataforma_lower = plataforma.lower()

    if "mercado" in plataforma_lower or "livre" in plataforma_lower:
        # Aceita tanto o link curto meli.la quanto um link de produto normal
        # já com matt_word/matt_tool (é isso que montar_link_afiliado_mercadolivre
        # gera automaticamente agora).
        return "meli.la" in host or ("matt_word" in link and "matt_tool" in link)

    elif "shopee" in plataforma_lower:
        return "shope.ee" in host or "s.shopee" in host

    elif "amazon" in plataforma_lower:
        # amzn.to é o encurtador de afiliado; se vier o link completo da
        # Amazon, exige o parâmetro "tag=" (seu ID de associado).
        return "amzn.to" in host or ("amazon." in host and "tag=" in link)

    elif "aliexpress" in plataforma_lower or "ali" in plataforma_lower:
        # Só s.click.aliexpress.com é de afiliado. aliexpress.com sozinho
        # é a página normal do produto (sem comissão).
        return "s.click.aliexpress.com" in host

    # Plataforma não reconhecida: não dá pra confirmar, então bloqueia.
    return False


async def aplicar_marca_dagua(url_imagem: str, texto_marca: str = "@SeuCanal") -> Optional[bytes]:
    """Baixa a imagem se disfarçando de navegador Chrome para evitar bloqueios 403."""
    try:
        # Cabeçalhos para simular um usuário real navegando
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
        }
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url_imagem, headers=headers)
            resp.raise_for_status()
    except Exception as e:
        print(f"Falha ao baixar imagem da loja: {e}")
        return None

    try:
        imagem = Image.open(BytesIO(resp.content)).convert("RGBA")
        camada_texto = Image.new("RGBA", imagem.size, (255, 255, 255, 0))
        desenho = ImageDraw.Draw(camada_texto)

        tamanho_fonte = max(18, imagem.width // 18)
        try:
            fonte = ImageFont.truetype("DejaVuSans-Bold.ttf", tamanho_fonte)
        except Exception:
            fonte = ImageFont.load_default()

        margem = 12
        bbox = desenho.textbbox((0, 0), texto_marca, font=fonte)
        x = imagem.width - (bbox[2] - bbox[0]) - margem
        y = imagem.height - (bbox[3] - bbox[1]) - margem

        desenho.text((x + 2, y + 2), texto_marca, font=fonte, fill=(0, 0, 0, 140))
        desenho.text((x, y), texto_marca, font=fonte, fill=(255, 255, 255, 200))

        resultado = Image.alpha_composite(imagem, camada_texto).convert("RGB")
        buffer = BytesIO()
        resultado.save(buffer, format="JPEG", quality=85)
        return buffer.getvalue()
    except Exception as e:
        print(f"Falha ao aplicar marca d'água: {e}")
        return None


async def enviar_voz_telegram(texto_fala: str):
    """Gera o áudio usando vozes neurais da Microsoft e envia para o Telegram."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return

    nome_arquivo_temp = f"oferta_{datetime.now().strftime('%H%M%S')}.ogg"

    try:
        # Voz masculina humanizada da Microsoft Azure.
        # Para voz feminina, mude para: "pt-BR-FranciscaNeural"
        voz_escolhida = "pt-BR-AntonioNeural"

        comunicador = edge_tts.Communicate(texto_fala, voz_escolhida)
        await comunicador.save(nome_arquivo_temp)

        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendVoice"
        async with httpx.AsyncClient(timeout=30) as client:
            with open(nome_arquivo_temp, "rb") as arquivo_voz:
                dados = {"chat_id": TELEGRAM_CHAT_ID}
                arquivos = {"voice": (nome_arquivo_temp, arquivo_voz, "audio/ogg")}
                resp = await client.post(url, data=dados, files=arquivos)
                resp.raise_for_status()

    except Exception as e:
        print(f"Falha ao enviar voz neural para o Telegram: {e}")
    finally:
        # Limpa o arquivo temporário do HD após o envio
        if os.path.exists(nome_arquivo_temp):
            os.remove(nome_arquivo_temp)


async def enviar_mensagem_telegram(texto: str, url_botao: str, imagem_bytes: Optional[bytes] = None):
    """Envia a oferta principal e exibe o detalhe do erro caso o Telegram recuse."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return

    # --- CORREÇÃO: botões do tipo "web_app" só funcionam em chat privado ---
    # com o bot. Em canais e grupos o Telegram rejeita a mensagem inteira.
    # Por isso o botão da Vitrine agora usa "url" normal, que funciona em
    # qualquer tipo de chat (e ainda assim abre como Mini App, se a URL
    # estiver registrada no BotFather).
    inline_keyboard = [
        [{"text": "🛒 Ir para a Loja", "url": url_botao}],
    ]
    if URL_MINI_APP:
        inline_keyboard.append(
            [{"text": "🛍️ Abrir Vitrine de Ofertas", "url": URL_MINI_APP}]
        )
    else:
        print("⚠️ URL_MINI_APP não definida no .env — botão da Vitrine não será enviado.")

    reply_markup = {"inline_keyboard": inline_keyboard}

    async with httpx.AsyncClient(timeout=20) as client:
        try:
            if imagem_bytes:
                legenda = texto if len(texto) <= 1024 else texto[:1021] + "..."
                url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
                dados = {
                    "chat_id": TELEGRAM_CHAT_ID,
                    "caption": legenda,
                    "parse_mode": "HTML",
                    "reply_markup": json.dumps(reply_markup),
                }
                arquivos = {"photo": ("produto.jpg", imagem_bytes, "image/jpeg")}
                response = await client.post(url, data=dados, files=arquivos)
            else:
                url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
                dados = {
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": texto,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                    "reply_markup": reply_markup,
                }
                response = await client.post(url, json=dados)

            response.raise_for_status()

        except httpx.HTTPStatusError as e:
            print(f"\n🚨 O TELEGRAM RECUSOU A POSTAGEM!")
            print(f"Código do erro: {e.response.status_code}")
            print(f"Motivo que a API devolveu: {e.response.text}\n")
        except Exception as e:
            print(f"Falha ao conectar com o Telegram: {e}")


# ==========================================
# ROTAS DA API
# ==========================================
@app.get("/formulario", response_class=HTMLResponse)
def formulario():
    """Serve o formulário HTML local."""
    caminho = pathlib.Path(__file__).parent / "formulario.html"
    if not caminho.exists():
        raise HTTPException(status_code=404, detail="formulario.html não encontrado.")
    return caminho.read_text(encoding="utf-8")

@app.get("/vitrine", response_class=HTMLResponse)
def pagina_vitrine():
    """Serve a página da vitrine localmente para testes, evitando bloqueios do Chrome."""
    caminho = pathlib.Path(__file__).parent / "index.html"
    if not caminho.exists():
         return "<h1>Arquivo index.html não encontrado na pasta! Coloque ele junto do main.py.</h1>"
    return caminho.read_text(encoding="utf-8")

@app.post("/produtos", dependencies=[Depends(verificar_chave_api)])
async def cadastrar_produto(produto: ProdutoCreate, db: Session = Depends(get_db)):
    """Recebe o produto, salva no banco e dispara foto e áudio para o Telegram."""
    link_existente = db.query(models.Link).filter(models.Link.slug == produto.slug).first()
    if link_existente:
        raise HTTPException(status_code=400, detail="Esse slug já está em uso.")

    try:
        link_final = gerar_novo_link_na_api(produto.id_produto_original, produto.plataforma)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Se a pessoa colou um link completo, ele passa direto sem transformação
    # (ver gerar_novo_link_na_api) — então aqui a gente confere se de fato é
    # um link de afiliado da plataforma escolhida, e bloqueia se não for.
    link_colado = produto.id_produto_original.strip()
    if link_colado.startswith("http") and not eh_link_de_afiliado(link_final, produto.plataforma):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Esse link não parece ser um link de afiliado da {produto.plataforma}. "
                "Cole o link de afiliado (o link curto/gerado no app ou painel da loja), "
                "não o link direto da página do produto."
            ),
        )

    # 1. Salva no banco de dados (Agora gravando os dados da vitrine!)
    novo_link = models.Link(
        slug=produto.slug,
        plataforma=produto.plataforma,
        id_produto_original=produto.id_produto_original,
        link_afiliado_cache=link_final,
        nome_produto=produto.nome_produto,      # NOVO
        imagem_url=produto.imagem_url,          # NOVO
        preco_oferta=produto.preco_oferta,      # NOVO
        gerado_em=datetime.now(timezone.utc),
    )
    db.add(novo_link)
    db.commit()
    db.refresh(novo_link)

    # ========================================================
    # FILTRO DE SEGURANÇA PARA AMAZON E SHOPEE
    # ========================================================
    titulo_limpo = produto.nome_produto

    # Se o nome for gigantesco, corta para não estourar o Telegram
    if len(titulo_limpo) > 150:
        titulo_limpo = titulo_limpo[:147] + "..."

    # Transforma símbolos perigosos (&, <, >) em texto seguro para HTML
    titulo_seguro = html.escape(titulo_limpo)
    # ========================================================

    # 2. Monta a string estruturada
    if produto.preco_original and produto.preco_original > produto.preco_oferta:
        economia = produto.preco_original - produto.preco_oferta
        desconto = (
            f"❌ De: <s>R$ {produto.preco_original:.2f}</s>\n"
            f"🔥 <b>Por apenas: R$ {produto.preco_oferta:.2f}</b>\n"
            f"💰 Você economiza: R$ {economia:.2f}\n"
        )
    else:
        desconto = f"🔥 <b>Por apenas: R$ {produto.preco_oferta:.2f}</b>\n"

    mensagem = (
        f"💥 <b>ACHADINHO BOMBANDO NA {produto.plataforma.upper()}!</b> 💥\n\n"
        f"📦 <b>{titulo_seguro}</b>\n\n"
        f"{desconto}\n"
        f"🛒 <b>Compre com segurança pelo link oficial abaixo 👇</b>\n\n"
        f"⚠️ <i>Preço sujeito a alteração a qualquer momento.</i>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )

    # 3. Processa a imagem
    imagem_bytes = None
    if produto.imagem_url:
        imagem_bytes = await aplicar_marca_dagua(produto.imagem_url, texto_marca="@SeuCanal")

    # 4. Dispara a imagem com texto
    await enviar_mensagem_telegram(mensagem, link_final, imagem_bytes)

    # 5. Dispara a narração em áudio
    texto_para_voz = produto.nome_produto if len(produto.nome_produto) < 80 else produto.nome_produto[:77] + "..."

    # Tratamento do preço para a inteligência artificial ler perfeitamente
    preco_str = f"{produto.preco_oferta:.2f}"
    reais, centavos = preco_str.split(".")

    if centavos == "00":
        # Se for um valor redondo (ex: 35.00), a voz fala apenas "35 reais"
        fala_preco = f"{reais} reais"
    else:
        # Se for quebrado (ex: 35.90), a voz fala "35 reais e 90 centavos"
        fala_preco = f"{reais} reais e {centavos} centavos"

    # Texto final reescrito com a direção correta do botão
    texto_para_leitura = (
        f"Atenção para esta super oferta! {texto_para_voz}. "
        f"Deixe de pagar caro, garanta o seu por apenas {fala_preco}. "
        f"O link oficial da loja está no botão logo abaixo da mensagem."
    )

    await enviar_voz_telegram(texto_para_leitura)

    return {"status": "sucesso", "produto": produto.nome_produto, "link": link_final}


# ==========================================
# ROTA DA VITRINE (NETLIFY)
# ==========================================
@app.get("/api/vitrine/{nome_plataforma}")
def buscar_produtos_vitrine(nome_plataforma: str, db: Session = Depends(get_db)):
    """
    Rota consumida pelo Netlify. Recebe o nome da plataforma, busca no 
    banco de dados e devolve as últimas 20 ofertas formatadas em JSON.
    """
    ofertas = db.query(models.Link).filter(models.Link.plataforma.ilike(nome_plataforma)).order_by(models.Link.id.desc()).limit(20).all()
    return ofertas


# ==========================================
# ROTA DE TESTE DA IA DE VOZ
# ==========================================
@app.post("/api/gerar-voz", tags=["IA de Voz - Edge TTS"])
async def gerar_voz_neural(texto_para_falar: str):
    """
    Recebe um texto, converte em voz neural realista usando o Edge TTS 
    e envia o áudio diretamente para o grupo do Telegram.
    """
    try:
        arquivo_audio = "voz_gerada.mp3"
        voz = "pt-BR-FranciscaNeural" 
        communicate = edge_tts.Communicate(texto_para_falar, voz)
        
        await communicate.save(arquivo_audio)
        
        token = os.getenv("TELEGRAM_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        
        if token and chat_id:
            url_telegram = f"https://api.telegram.org/bot{token}/sendAudio"
            with open(arquivo_audio, "rb") as arquivo:
                resposta = requests.post(
                    url_telegram, 
                    data={"chat_id": chat_id}, 
                    files={"audio": arquivo}
                )
            
            if os.path.exists(arquivo_audio):
                os.remove(arquivo_audio)
            
            return {"status": "Sucesso", "mensagem": "Áudio gerado e enviado ao Telegram!"}
        else:
            return {"status": "Erro", "mensagem": "Faltam credenciais no .env."}
            
    except Exception as e:
        return {"status": "Erro interno", "detalhe": str(e)}


# ==========================================
# REDIRECIONAMENTO DE AFILIADO
# ==========================================
@app.get("/{slug}")
def redirecionar_link(slug: str, db: Session = Depends(get_db)):
    """Recebe o clique do usuário e redireciona para a loja."""
    link_db = db.query(models.Link).filter(models.Link.slug == slug).first()

    if not link_db:
        raise HTTPException(status_code=404, detail="Link não encontrado")

    link_db.cliques += 1
    agora = datetime.now(timezone.utc)
    gerado_em = link_db.gerado_em

    if gerado_em is not None and gerado_em.tzinfo is None:
        gerado_em = gerado_em.replace(tzinfo=timezone.utc)

    horas_desde_geracao = (agora - gerado_em).total_seconds() / 3600 if gerado_em else 999

    if not link_db.link_afiliado_cache or horas_desde_geracao > 20:
        try:
            link_db.link_afiliado_cache = gerar_novo_link_na_api(
                link_db.id_produto_original, link_db.plataforma
            )
            link_db.gerado_em = agora
        except ValueError:
            # Não foi possível regenerar (ex: cadastro antigo de Mercado
            # Livre sem link completo) — mantém o que já está em cache em
            # vez de quebrar o clique de quem está comprando.
            pass

    db.commit()

    return RedirectResponse(url=link_db.link_afiliado_cache, status_code=302)

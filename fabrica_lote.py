import asyncio
import edge_tts
import random
import os
import re
from moviepy.editor import VideoFileClip, AudioFileClip

# Importações da nossa Base de Dados
from database import SessionLocal
from models import Link

# --- CONFIGURAÇÕES DA FÁBRICA ---
URL_BASE_RENDER = "https://glowing-garbanzo.onrender.com/"
VOZ = "pt-BR-AntonioNeural"
PASTA_ORIGINAIS = "videos_originais" # Onde os vídeos mudos vão ficar

# Garante que a pasta de vídeos originais existe no sistema
if not os.path.exists(PASTA_ORIGINAIS):
    os.makedirs(PASTA_ORIGINAIS)
    print(f"📁 Pasta '{PASTA_ORIGINAIS}' criada automaticamente para guardar os seus vídeos!")

# Ganchos de Copywriting
ganchos_escritos = [
    "🚨 OFERTA RELÂMPAGO! 🚨",
    "🔥 PREÇO QUE CAIU AGORA! 🔥",
    "⚡ SÓ HOJE COM ESSE DESCONTO! ⚡"
]

ganchos_falados = [
    "Atenção a este preço que caiu agora!",
    "Olha só esta oferta relâmpago que acabei de encontrar!",
    "Só hoje com esse desconto imperdível!"
]

async def processar_produtos():
    print("🔌 A conectar à base de dados Neon...")
    db = SessionLocal()
    
    produtos = db.query(Link).filter(Link.nome_produto.isnot(None)).all()
    db.close()
    
    if not produtos:
        print("⚠️ Nenhum produto encontrado com nome na base de dados!")
        return
        
    print(f"📦 Encontrados {len(produtos)} produtos. A iniciar a linha de produção!\n")
    print("=" * 50)
    
    for produto in produtos:
        print(f"\n🔄 A processar: {produto.nome_produto}")
        
        # 1. TRATAMENTO DO PREÇO
        preco_float = produto.preco_oferta or 0.0
        preco_formatado = f"R$ {preco_float:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
        
        if preco_float.is_integer():
            preco_falado = f"{int(preco_float)} reais"
        else:
            preco_falado = f"{str(preco_float).replace('.', ',')} reais"

        # 2. MONTAGEM DINÂMICA DA LEGENDA
        link_afiliado = f"{URL_BASE_RENDER}{produto.slug}"
        indice_sorteio = random.randint(0, 2)
        
        legenda_telegram = f"""{ganchos_escritos[indice_sorteio]}

O {produto.nome_produto} está por apenas {preco_formatado}! 😱

👉 Garanta o seu aqui: {link_afiliado}
"""
        texto_falado = f"{ganchos_falados[indice_sorteio]} O {produto.nome_produto} está por apenas {preco_falado}. Clique no link abaixo e garanta o seu!"
        
        print(f"📝 Legenda gerada:\n{legenda_telegram}")
        
        # 3. IDENTIFICAÇÃO DOS ARQUIVOS (O SEGREDO DA ORGANIZAÇÃO)
        nome_seguro = re.sub(r'[\\/*?:"<>|]', "", produto.slug)
        
        arquivo_audio = f"temp_audio_{nome_seguro}.mp3"
        arquivo_video_saida = f"post_pronto_{nome_seguro}.mp4"
        
        # A MUDANÇA ESTÁ AQUI: O Python agora procura o vídeo do produto específico DENTRO da pasta
        arquivo_video_base = f"{PASTA_ORIGINAIS}/{nome_seguro}.mp4"
        
        # Se o vídeo exato não existir na pasta, ele salta a renderização visual e avisa como resolver
        if not os.path.exists(arquivo_video_base):
            print(f"⚠️ VÍDEO AUSENTE: Para renderizar este produto, coloque um vídeo com o nome exato '{nome_seguro}.mp4' dentro da pasta '{PASTA_ORIGINAIS}'.")
            print("-" * 50)
            continue # Salta para o próximo produto sem dar erro
        
        # Se o vídeo existir, ele faz a magia!
        print("🎙️ A gravar a locução por IA...")
        comunicacao = edge_tts.Communicate(texto_falado, VOZ)
        await comunicacao.save(arquivo_audio)
        
        print(f"🎬 Encontrei o vídeo base '{arquivo_video_base}'! A montar com o áudio...")
        
        clip_video = VideoFileClip(arquivo_video_base)
        clip_audio = AudioFileClip(arquivo_audio)
        
        # Corta e cola o som
        video_editado = clip_video.subclip(0, clip_audio.duration).set_audio(clip_audio)
        video_editado.write_videofile(arquivo_video_saida, fps=24, codec="libx264", audio_codec="aac", logger=None)
        
        clip_video.close()
        clip_audio.close()
        video_editado.close()
            
        if os.path.exists(arquivo_audio):
            os.remove(arquivo_audio)
            
        print(f"✅ Concluído: '{arquivo_video_saida}' pronto para o Telegram!")
        print("-" * 50)

if __name__ == "__main__":
    asyncio.run(processar_produtos())
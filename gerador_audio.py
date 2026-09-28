import asyncio
import edge_tts
import random
import os
# A MUDANÇA: Agora trazemos o VideoFileClip (para ler movimento real)
from moviepy.editor import VideoFileClip, AudioFileClip

# 1. Ganchos escritos (Para a legenda do Telegram)
ganchos_escritos = [
    "🚨 OFERTA RELÂMPAGO! 🚨",
    "🔥 PREÇO QUE CAIU AGORA! 🔥",
    "⚡ SÓ HOJE COM ESSE DESCONTO! ⚡"
]

# 2. Ganchos falados (Para a voz da IA)
ganchos_falados = [
    "Atenção a este preço que caiu agora!",
    "Olha só esta oferta relâmpago que acabei de encontrar!",
    "Só hoje com esse desconto imperdível!"
]

indice_sorteio = random.randint(0, 2)

# Dados do produto (Ajustados para o POCO)
nome_produto = "POCO X7 Pro"
preco_texto = "R$ 1.500,00"
preco_falado = "1500 reais"
link_afiliado = "https://SEU_LINK_RENDER/poco-x7-pro"

legenda_telegram = f"""{ganchos_escritos[indice_sorteio]}

O {nome_produto} está por apenas {preco_texto}! 😱

👉 Garanta o seu aqui: {link_afiliado}
"""

texto_falado = f"{ganchos_falados[indice_sorteio]} O {nome_produto} está por apenas {preco_falado}. Clique no link abaixo e garanta o seu!"

# Ficheiros do projeto
VOZ = "pt-BR-AntonioNeural"
ARQUIVO_AUDIO = "audio_temporario.mp3"
ARQUIVO_VIDEO_ORIGINAL = "video_produto.mp4" # O vídeo real que acabou de renomear
ARQUIVO_VIDEO_FINAL = "post_pronto_telegram.mp4"

async def gerar_material():
    print("\n========== LEGENDA PARA O TELEGRAM ==========")
    print(legenda_telegram)
    print("=============================================\n")
    
    print("1. A gerar a locução por Inteligência Artificial...")
    comunicacao = edge_tts.Communicate(texto_falado, VOZ)
    await comunicacao.save(ARQUIVO_AUDIO)
    print("-> Áudio gravado com sucesso.")
    
    print("\n2. A editar o vídeo real e a sincronizar o áudio...")
    if not os.path.exists(ARQUIVO_VIDEO_ORIGINAL):
        print(f"⚠️ ERRO: Não encontrei o vídeo '{ARQUIVO_VIDEO_ORIGINAL}'. Renomeou-o corretamente?")
        return
        
    clip_video = VideoFileClip(ARQUIVO_VIDEO_ORIGINAL)
    clip_audio = AudioFileClip(ARQUIVO_AUDIO)
    
    # TRUQUE DE MESTRE: Corta o vídeo no tempo exato da voz e substitui o som original
    video_editado = clip_video.subclip(0, clip_audio.duration).set_audio(clip_audio)
    
    print("\n3. A renderizar o vídeo final (como tem movimento real, demora um pouco mais)...")
    # fps=24 garante que o movimento da mão fica fluido (padrão de cinema)
    video_editado.write_videofile(
        ARQUIVO_VIDEO_FINAL, 
        fps=24, 
        codec="libx264", 
        audio_codec="aac",
        logger=None
    )
    
    if os.path.exists(ARQUIVO_AUDIO):
        os.remove(ARQUIVO_AUDIO)
        
    print(f"\n✅ SUCESSO! O seu vídeo dobrado '{ARQUIVO_VIDEO_FINAL}' está pronto!")

if __name__ == "__main__":
    asyncio.run(gerar_material())
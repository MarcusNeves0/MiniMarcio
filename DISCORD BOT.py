import discord
from discord.ext import commands
import os
import random
import asyncio
import yt_dlp
from dotenv import load_dotenv
import aiohttp

# --- Configuração Inicial ---

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.members = True

bot = commands.Bot(command_prefix='$', intents=intents)

# --- Novas Variáveis para o Sistema de Música ---

# Dicionário para guardar a fila de músicas de cada servidor
song_queues = {}

# Modificando as opções do yt-dlp para NÃO ignorar playlists
yt_dlp_opts = {
    'format': 'bestaudio/best',
    'extract_flat': 'in_playlist',  # Extrai informações da playlist mais rápido
    'noplaylist': False  # ✅ MUDANÇA: Permite processar playlists
}
ytdl = yt_dlp.YoutubeDL(yt_dlp_opts)

ffmpeg_options = {
    'options': '-vn',
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
}


# --- Nova Função Auxiliar para Tocar a Próxima Música ---

def play_next(ctx):
    """Função chamada quando uma música termina para tocar a próxima da fila."""
    guild_id = ctx.guild.id
    if guild_id in song_queues and song_queues[guild_id]:
        # Pega a próxima música da fila
        song = song_queues[guild_id].pop(0)
        voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)

        if voice_client is None:
            return  # Se o bot foi desconectado, para de tocar

        # Extrai a URL de streaming da música novamente, pois elas expiram
        try:
            loop = asyncio.get_event_loop()
            data = loop.run_until_complete(ytdl.extract_info(song['url'], download=False))
            stream_url = data['url']
        except Exception as e:
            print(f"Erro ao re-extrair URL da música: {e}")
            play_next(ctx)  # Tenta a próxima música da fila
            return

        player = discord.FFmpegPCMAudio(stream_url, **ffmpeg_options)
        voice_client.play(player, after=lambda e: play_next(ctx))

        asyncio.run_coroutine_threadsafe(
            ctx.send(f'▶️ Tocando agora: **{song["title"]}**'),
            bot.loop
        )


# --- Eventos do Bot ---

@bot.event
async def on_ready():
    print(f'Bot conectado como {bot.user}')
    print('------')


# --- Comandos de Música (MODIFICADOS E NOVOS) ---

@bot.command(name='play', help='Toca uma música ou playlist, ou adiciona na fila.')
async def play(ctx, *, search: str):
    if not ctx.author.voice:
        await ctx.send("Você não está conectado a um canal de voz.")
        return

    channel = ctx.author.voice.channel
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)

    if voice_client is None:
        voice_client = await channel.connect()

    async with ctx.typing():
        try:
            # Busca a música ou playlist no YouTube
            data = await bot.loop.run_in_executor(None, lambda: ytdl.extract_info(search, download=False))

            # Garante que a fila para o servidor existe
            if ctx.guild.id not in song_queues:
                song_queues[ctx.guild.id] = []

            # Verifica se é uma playlist
            if 'entries' in data:
                # É uma playlist
                # Pega o número de músicas que serão adicionadas para a mensagem de confirmação
                num_songs_added = len(data['entries'])

                for entry in data['entries']:
                    # Adiciona cada música da playlist à fila
                    song_queues[ctx.guild.id].append({
                        'title': entry.get('title', 'Título desconhecido'),
                        'url': f"http://googleusercontent.com/youtube.com/9{entry.get('id')}"
                    })

                await ctx.send(f'✅ Adicionadas **{num_songs_added}** músicas da playlist à fila!')

            else:
                # É uma única música
                song = {
                    'title': data.get('title', 'Título desconhecido'),
                    'url': data.get('webpage_url', search)
                }
                song_queues[ctx.guild.id].append(song)
                await ctx.send(f'✅ Adicionado à fila: **{song["title"]}**')

            # ✅ A CORREÇÃO ESTÁ AQUI:
            # Após adicionar tudo, verifica se o bot está parado.
            # Se estiver, inicia a reprodução da fila.
            if not voice_client.is_playing():
                play_next(ctx)

        except Exception as e:
            await ctx.send("Ocorreu um erro ao buscar a música/playlist.")
            print(f"Erro no comando play: {e}")

@bot.command(name='skip', help='Pula para a próxima música da fila.')
async def skip(ctx):
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    if voice_client and voice_client.is_playing():
        voice_client.stop()  # Parar a música atual vai acionar a função play_next
        await ctx.send("⏭️ Música pulada!")
    else:
        await ctx.send("Não há nenhuma música tocando no momento.")


@bot.command(name='queue', help='Mostra a fila de músicas.')
async def queue(ctx):
    guild_id = ctx.guild.id
    if guild_id in song_queues and song_queues[guild_id]:
        embed = discord.Embed(title="Fila de Músicas", color=discord.Color.blue())

        # Lista as próximas 10 músicas da fila
        queue_list = ""
        for i, song in enumerate(song_queues[guild_id][:10]):
            queue_list += f"**{i + 1}.** {song['title']}\n"

        embed.description = queue_list
        if len(song_queues[guild_id]) > 10:
            embed.set_footer(text=f"... e mais {len(song_queues[guild_id]) - 10} músicas.")

        await ctx.send(embed=embed)
    else:
        await ctx.send("A fila de músicas está vazia!")


@bot.command(name='stop', help='Para a música, limpa a fila e desconecta o bot.')
async def stop(ctx):
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    guild_id = ctx.guild.id

    if guild_id in song_queues:
        song_queues[guild_id] = []

    if voice_client and voice_client.is_connected():
        await voice_client.disconnect()
        await ctx.send("⏹️ Fila limpa e bot desconectado.")


@bot.command(name='pause', help='Pausa a música atual.')
async def pause(ctx):
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    if voice_client and voice_client.is_playing():
        voice_client.pause()
        await ctx.send("⏸️ Música pausada.")


@bot.command(name='resume', help='Continua a música pausada.')
async def resume(ctx):
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    if voice_client and voice_client.is_paused():
        voice_client.resume()
        await ctx.send("▶️ Música retomada.")


# --- Seus outros comandos permanecem aqui ---
@bot.command(name='jokenpo', help='Joga Pedra, Papel ou Tesoura. Ex: $jokenpo pedra')
async def jokenpo(ctx, player_choice: str):
    # ... (código do jokenpo)
    pass


@bot.command(name='serverinfo', help='Mostra informações sobre o servidor.')
async def serverinfo(ctx):
    # ... (código do serverinfo)
    pass


@bot.command(name='pokedex', help='Mostra informações e a foto de um Pokémon. Ex: $pokedex pikachu')
async def pokedex(ctx, *, nome_pokemon: str):
    # ... (código do pokedex)
    pass


# --- Inicia o Bot ---
bot.run(TOKEN)
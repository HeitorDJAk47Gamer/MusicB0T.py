import disnake, os, asyncio, yt_dlp, random, urllib.parse, urllib.request, re
from disnake.ext import commands
from spotipy import Spotify
from spotipy.oauth2 import SpotifyClientCredentials


# Configurar as credenciais do Spotify
SPOTIFY_CLIENT_ID = "id"
SPOTIFY_CLIENT_SECRET = "token"
spotify = Spotify(client_credentials_manager=SpotifyClientCredentials(
    client_id=SPOTIFY_CLIENT_ID,
    client_secret=SPOTIFY_CLIENT_SECRET
))

client = commands.Bot(command_prefix=".", intents=disnake.Intents.all())

current_song = {}
queues = {}
voice_clients = {}
youtube_base_url = 'https://www.youtube.com/'
youtube_results_url = youtube_base_url + 'results?'
youtube_watch_url = youtube_base_url + 'watch?v='
yt_dl_options = {"format": "bestaudio[ext=webm]/bestaudio/best", "noplaylist": True,}
ytdl = yt_dlp.YoutubeDL(yt_dl_options)

ffmpeg_options = {"executable": 'C:\\ffmpeg\\bin\\ffmpeg.exe', 'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}

@client.event
async def on_ready():
    print(f'{client.user} Está on para usar!')

async def search_youtube(query):
    """Procura uma música no YouTube e retorna o link."""
    query_string = urllib.parse.urlencode({'search_query': query})
    content = urllib.request.urlopen(youtube_results_url + query_string)
    search_results = re.findall(r'/watch\?v=(.{11})', content.read().decode())
    if search_results:
        return youtube_watch_url + search_results[0]
    return None

async def play_song(ctx, song_data):
    """Função para tocar uma música específica."""
    try:
        player = disnake.FFmpegOpusAudio(song_data["url"], **ffmpeg_options)
        voice_clients[ctx.guild.id].play(
            player,
            after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), client.loop)
        )
        await ctx.send(f"Now playing: **{song_data['title']}**")
    except Exception as e:
        print(e)
        await ctx.send("An error occurred while trying to play the song.")

async def preload_next_song(ctx):
    """Pré-carrega a próxima música na fila."""
    try:
        # Verifica se há músicas na fila
        if queues[ctx.guild.id]:
            next_song_data = queues[ctx.guild.id][0]  # Próxima música na fila

            # Verifica se a música já foi pré-carregada
            if "url" not in next_song_data:
                query = next_song_data["title"]
                loop = asyncio.get_event_loop()
                data = await loop.run_in_executor(None, lambda: ytdl.extract_info(query, download=False))

                # Atualiza os dados da música com o link
                next_song_data["url"] = data["url"]
                next_song_data["title"] = data.get("title", "Unknown Title")
                print(f"Pré-carregada: {next_song_data['title']}")
    except Exception as e:
        print(f"Erro ao pré-carregar a próxima música: {e}")

async def play_next(ctx):
    """Toca a próxima música na fila."""
    if queues[ctx.guild.id]:
        next_song = queues[ctx.guild.id].pop(0)

        # Pré-carrega a próxima música enquanto esta toca
        asyncio.create_task(preload_next_song(ctx))

        await play_song(ctx, next_song)

@client.command(name="play")
async def play(ctx, *, query):
    try:
        # Conecta ao canal de voz, se ainda não estiver conectado
        if ctx.guild.id not in voice_clients or not voice_clients[ctx.guild.id].is_connected():
            voice_client = await ctx.author.voice.channel.connect()
            voice_clients[ctx.guild.id] = voice_client

        # Verifica se é um link do Spotify
        if "spotify.com" in query:
            if "track" in query:  # É uma música
                track_id = query.split("/")[-1].split("?")[0]
                track = spotify.track(track_id)
                query = f"{track['name']} {track['artists'][0]['name']}"  # Nome da música + artista

            elif "playlist" in query:  # É uma playlist
                playlist_id = query.split("/")[-1].split("?")[0]
                playlist = spotify.playlist(playlist_id)
                for item in playlist['tracks']['items']:
                    track = item['track']
                    track_query = f"{track['name']} {track['artists'][0]['name']}"
                    youtube_link = await search_youtube(track_query)

                    if ctx.guild.id not in queues:
                        queues[ctx.guild.id] = []
                    queues[ctx.guild.id].append({
                        "title": track_query,
                        "url": youtube_link
                    })
                embed_playlist = disnake.Embed(
                    title="Playlist Adicionada",
                    description=f"Playlist adicionada à fila com {len(playlist['tracks']['items'])} músicas!",
                    color=disnake.Color.blurple()
                )
                await ctx.send(embed=embed_playlist)
                return

        # Busca no YouTube se não for um URL
        youtube_link = await search_youtube(query)
        if not youtube_link:
            embed_notfound = disnake.Embed(
                title="Música não encontrada",
                description="Não consegui encontrar essa música no YouTube.",
                color=disnake.Color.red()
            )
            await ctx.send(embed=embed_notfound)
            return

        # Pré-processa a música (pega o título e o link de reprodução)
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(youtube_link, download=False))
        song_data = {
            "title": data.get("title", "Unknown Title"),
            "url": data["url"]
        }

        # Adiciona à fila, caso já esteja tocando algo
        if voice_clients[ctx.guild.id].is_playing():
            if ctx.guild.id not in queues:
                queues[ctx.guild.id] = []  # Cria a fila, se não existir
            queues[ctx.guild.id].append(song_data)
            embed_queue = disnake.Embed(
                title="Música Adicionada à Fila",
                description=f"Added to queue: **{song_data['title']}**",
                color=disnake.Color.green()
            )
            await ctx.send(embed=embed_queue)

            # Pré-carrega a próxima música
            asyncio.create_task(preload_next_song(ctx))
            return

        # Se não está tocando, inicia a reprodução
        await play_song(ctx, song_data)

    except Exception as e:
        print(e)
        embed_error = disnake.Embed(
            title="Erro ao Reproduzir Música",
            description="An error occurred while trying to play the song.",
            color=disnake.Color.red()
        )
        await ctx.send(embed=embed_error)


@client.command(name="skip")
async def skip(ctx):
    try:
        if ctx.guild.id in voice_clients and voice_clients[ctx.guild.id].is_playing():
            voice_clients[ctx.guild.id].stop()
            embed = disnake.Embed(
                title="⏭️ Música Pulada",
                description="A música atual foi pulada.",
                color=disnake.Color.orange()
            )
            await ctx.send(embed=embed)
            await play_next(ctx)
        else:
            embed = disnake.Embed(
                title="❌ Nenhuma Música Tocando",
                description="Não há música tocando no momento para pular.",
                color=disnake.Color.red()
            )
            await ctx.send(embed=embed)
    except Exception as e:
        print(e)
        embed = disnake.Embed(
            title="❌ Erro",
            description="Ocorreu um erro ao tentar pular a música.",
            color=disnake.Color.red()
        )
        await ctx.send(embed=embed)

@client.command(name="stop")
async def stop(ctx):
    """Para a música e desconecta o bot do canal de voz."""
    try:
        if ctx.guild.id in voice_clients:
            # Para a música e desconecta
            voice_clients[ctx.guild.id].stop()
            await voice_clients[ctx.guild.id].disconnect()
            del voice_clients[ctx.guild.id]

            # Limpa a fila
            if ctx.guild.id in queues:
                queues[ctx.guild.id].clear()

            embed = disnake.Embed(
                title="⏹️ Música Parada",
                description="A música foi parada e a fila foi limpa. O bot desconectou do canal de voz.",
                color=disnake.Color.red()
            )
            await ctx.send(embed=embed)
        else:
            embed = disnake.Embed(
                title="❌ Não estou conectado",
                description="O bot não está conectado a nenhum canal de voz.",
                color=disnake.Color.red()
            )
            await ctx.send(embed=embed)
    except Exception as e:
        print(e)
        await ctx.send("Ocorreu um erro ao tentar parar a música.")

@client.command(name="clearqueue")
async def clear_queue(ctx):
    """Limpa a fila de músicas."""
    try:
        if ctx.guild.id in queues and queues[ctx.guild.id]:
            queues[ctx.guild.id].clear()
            embed = disnake.Embed(
                title="🗑️ Fila Limpa",
                description="Todas as músicas foram removidas da fila.",
                color=disnake.Color.orange()
            )
            await ctx.send(embed=embed)
        else:
            embed = disnake.Embed(
                title="❌ Fila Vazia",
                description="Não há músicas na fila para limpar.",
                color=disnake.Color.red()
            )
            await ctx.send(embed=embed)
    except Exception as e:
        print(e)
        await ctx.send("Ocorreu um erro ao tentar limpar a fila.")

@client.command(name="pause")
async def pause(ctx):
    """Pausa a música atual."""
    try:
        if ctx.guild.id in voice_clients and voice_clients[ctx.guild.id].is_playing():
            voice_clients[ctx.guild.id].pause()
            embed = disnake.Embed(
                title="⏸️ Música Pausada",
                description="A reprodução da música foi pausada.",
                color=disnake.Color.blue()
            )
            await ctx.send(embed=embed)
        else:
            embed = disnake.Embed(
                title="❌ Nada tocando",
                description="Não há música tocando no momento para pausar.",
                color=disnake.Color.red()
            )
            await ctx.send(embed=embed)
    except Exception as e:
        print(e)
        await ctx.send("Ocorreu um erro ao tentar pausar a música.")

@client.command(name="resume")
async def resume(ctx):
    """Resume a música pausada."""
    try:
        if ctx.guild.id in voice_clients and voice_clients[ctx.guild.id].is_paused():
            voice_clients[ctx.guild.id].resume()
            embed = disnake.Embed(
                title="▶️ Música Resumida",
                description="A reprodução da música foi retomada.",
                color=disnake.Color.green()
            )
            await ctx.send(embed=embed)
        else:
            embed = disnake.Embed(
                title="❌ Nada pausado",
                description="Não há música pausada para retomar.",
                color=disnake.Color.red()
            )
            await ctx.send(embed=embed)
    except Exception as e:
        print(e)
        await ctx.send("Ocorreu um erro ao tentar retomar a música.")


queues = {}  # Dicionário que contém as filas de músicas por servidor

class QueueView(disnake.ui.View):
    """Classe para gerenciar a paginação da fila de músicas."""
    def __init__(self, ctx, queue, per_page=10):
        super().__init__(timeout=None)
        self.ctx = ctx
        self.queue = queue
        self.per_page = per_page
        self.current_page = 0
        self.total_pages = (len(queue) - 1) // per_page + 1

        # Atualizar os botões com base na página
        self.update_buttons()

    def update_buttons(self):
        """Ativa ou desativa os botões com base na página atual."""
        self.children[0].disabled = self.current_page == 0  # Botão Anterior
        self.children[1].disabled = self.current_page == self.total_pages - 1  # Botão Próximo

    async def send_embed(self, inter=None):
        """Envia ou atualiza o embed com a fila atual."""
        start = self.current_page * self.per_page
        end = start + self.per_page
        page_queue = self.queue[start:end]

        embed = disnake.Embed(
            title="Fila de Músicas",
            description="\n".join(
                [f"**{idx + start + 1}.** [{song['title']}]({song.get('url', 'https://www.youtube.com')})"
                 for idx, song in enumerate(page_queue)]
            ),
            color=disnake.Color.blurple()
        )
        embed.set_footer(text=f"Página {self.current_page + 1}/{self.total_pages}")

        if inter:
            await inter.response.edit_message(embed=embed, view=self)
        else:
            await self.ctx.send(embed=embed, view=self)

    @disnake.ui.button(label="Anterior", style=disnake.ButtonStyle.primary)
    async def previous_page(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        """Exibe a página anterior da fila."""
        self.current_page -= 1
        self.update_buttons()
        await self.send_embed(inter)

    @disnake.ui.button(label="Próximo", style=disnake.ButtonStyle.primary)
    async def next_page(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        """Exibe a próxima página da fila."""
        self.current_page += 1
        self.update_buttons()
        await self.send_embed(inter)


@client.command(name="queue")
async def queue(ctx):
    """Comando para exibir a fila de músicas."""
    guild_id = ctx.guild.id

    # Verifica se a fila está vazia
    if guild_id not in queues or not queues[guild_id]:
        embed_empty = disnake.Embed(
            title="Fila de Músicas",
            description="A fila está vazia.",
            color=disnake.Color.red()
        )
        await ctx.send(embed=embed_empty)
        return

    # Cria a view para paginação da fila
    queue_list = queues[guild_id]
    view = QueueView(ctx, queue_list)
    await view.send_embed()

@client.command(name="volume")
async def volume(ctx, volume: int):
    """Ajusta o volume do player."""
    try:
        if ctx.guild.id in voice_clients and voice_clients[ctx.guild.id].is_playing():
            if 0 <= volume <= 100:
                vc = voice_clients[ctx.guild.id]
                # Tenta ajustar o volume diretamente; se falhar, encapsula o source
                try:
                    vc.source.volume = volume / 100.0
                except AttributeError:
                    # Se o source não for do tipo PCMVolumeTransformer ou estiver com problema,
                    # encapsula-o novamente
                    source = vc.source
                    vc.source = disnake.PCMVolumeTransformer(source)
                    vc.source.volume = volume / 100.0
                await ctx.send(f"🔊 Volume ajustado para **{volume}%**")
            else:
                await ctx.send("❌ O volume deve estar entre **0 e 100**.")
        else:
            await ctx.send("❌ Nenhuma música está tocando no momento.")
    except Exception as e:
        print(e)
        await ctx.send("❌ Ocorreu um erro ao ajustar o volume.")

@client.command()
async def ping(ctx):
    calc = client.latency * 1000
    pong = round(calc)

    x = disnake.Embed(title='**Pong**', description=f'{pong} `ms`', color=0xff0000)

    y = disnake.Embed(title='**Pong**', description=f'{pong} `ms`', color=0xffff00)

    z = disnake.Embed(title='**Pong**', description=f'{pong} `ms`', color=0x008000)

    if pong > 160:
        msg = await ctx.send(embed=x)
        await msg.add_reaction('🏓')
    elif 80 <= pong <= 160:
        msg = await ctx.send(embed=y)
        await msg.add_reaction('🏓')
    elif pong < 80:
        msg = await ctx.send(embed=z)
        await msg.add_reaction('🏓')

        
client.run("TOKEN")

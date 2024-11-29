import disnake, os, asyncio, yt_dlp, random
from disnake.ext import commands
import urllib.parse, urllib.request, re


intents = disnake.Intents.default()
intents.message_content = True
client = commands.Bot(command_prefix=".", intents=intents)

current_song = {}
queues = {}
voice_clients = {}
youtube_base_url = 'https://www.youtube.com/'
youtube_results_url = youtube_base_url + 'results?'
youtube_watch_url = youtube_base_url + 'watch?v='
yt_dl_options = { "format": "bestaudio[ext=webm]/bestaudio/best", "noplaylist": True, "cookiefile": "cookies.txt"}
ytdl = yt_dlp.YoutubeDL(yt_dl_options)

ffmpeg_options = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5','options': '-vn'}

@client.event
async def on_ready():
    print(f'{client.user} Está on para usar!')

async def play_next(ctx):
    if queues[ctx.guild.id] != []:
        link = queues[ctx.guild.id].pop(0)
        await play(ctx, link=link)

@client.command(name="play")
async def play(ctx, *, link):
    try:
        # Conecta ao canal de voz, se ainda não estiver conectado
        if ctx.guild.id not in voice_clients or not voice_clients[ctx.guild.id].is_connected():
            voice_client = await ctx.author.voice.channel.connect()
            voice_clients[ctx.guild.id] = voice_client

        # Se o link não for um URL do YouTube, faz uma busca
        if youtube_base_url not in link:
            query_string = urllib.parse.urlencode({'search_query': link})
            content = urllib.request.urlopen(youtube_results_url + query_string)
            search_results = re.findall(r'/watch\?v=(.{11})', content.read().decode())
            link = youtube_watch_url + search_results[0]

        # Se o bot já está tocando, adiciona a música à fila
        if voice_clients[ctx.guild.id].is_playing():
            if ctx.guild.id not in queues:
                queues[ctx.guild.id] = []  # Cria a fila, se não existir
            queues[ctx.guild.id].append(link)
            await ctx.send(f"Added to queue: **{link}**")
            return

        # Se não está tocando, inicia a reprodução
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(link, download=False))
        song = data['url']
        title = data.get('title', 'Unknown Title')

        player = disnake.FFmpegOpusAudio(song, **ffmpeg_options)
        voice_clients[ctx.guild.id].play(
            player,
            after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), client.loop)
        )
        await ctx.send(f"Now playing: **{title}**")

    except Exception as e:
        print(e)
        await ctx.send("An error occurred while trying to play the song.")

@client.command(name="clearq")
async def clear_queue(ctx):
    if ctx.guild.id in queues:
        queues[ctx.guild.id].clear()
        await ctx.send("Fila limpa!")
    else:
        await ctx.send("Não há fila para limpar")

@client.command(name="pause")
async def pause(ctx):
    try:
        voice_clients[ctx.guild.id].pause()
    except Exception as e:
        print(e)

@client.command(name="resume")
async def resume(ctx):
    try:
        voice_clients[ctx.guild.id].resume()
    except Exception as e:
        print(e)

@client.command(name="stop")
async def stop(ctx):
    try:
        voice_clients[ctx.guild.id].stop()
        await voice_clients[ctx.guild.id].disconnect()
        del voice_clients[ctx.guild.id]
    except Exception as e:
        print(e)

queues = {}  # Dicionário que contém as filas de músicas por servidor

class QueueView(disnake.ui.View):
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
        self.children[0].disabled = self.current_page == 0  # Botão Anterior
        self.children[1].disabled = self.current_page == self.total_pages - 1  # Botão Próximo

    async def send_embed(self, inter=None):
        start = self.current_page * self.per_page
        end = start + self.per_page
        page_queue = self.queue[start:end]

        embed = disnake.Embed(
            title="Fila de Músicas",
            description="\n".join([f"**{idx + start + 1}.** [{url}]({url})" for idx, url in enumerate(page_queue)]),
            color=disnake.Color.blurple()
        )
        embed.set_footer(text=f"Página {self.current_page + 1}/{self.total_pages}")

        if inter:
            await inter.response.edit_message(embed=embed, view=self)
        else:
            await self.ctx.send(embed=embed, view=self)

    @disnake.ui.button(label="Anterior", style=disnake.ButtonStyle.primary)
    async def previous_page(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        self.current_page -= 1
        self.update_buttons()
        await self.send_embed(inter)

    @disnake.ui.button(label="Próximo", style=disnake.ButtonStyle.primary)
    async def next_page(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        self.current_page += 1
        self.update_buttons()
        await self.send_embed(inter)


@client.slash_command(name="queue", description="Exibe a fila de músicas atual")
async def view_queue(inter: disnake.ApplicationCommandInteraction):
    guild_id = inter.guild.id

    if guild_id not in queues or not queues[guild_id]:
        await inter.response.send_message("A fila está vazia.", ephemeral=True)
        return

    queue = queues[guild_id]
    view = QueueView(inter, queue)
    await view.send_embed()

@client.command(name="skip")
async def skip(ctx):
    try:
        if ctx.guild.id in voice_clients and voice_clients[ctx.guild.id].is_playing():
            # Recupera o título da próxima música, se existir
            next_song = None
            if queues[ctx.guild.id]:
                next_song_link = queues[ctx.guild.id][0]
                loop = asyncio.get_event_loop()
                data = await loop.run_in_executor(None, lambda: ytdl.extract_info(next_song_link, download=False))
                next_song = data.get('title', 'Unknown Title')
            
            # Para a música atual
            voice_clients[ctx.guild.id].stop()

            if next_song:
                await ctx.send(f"Skipping to the next song: **{next_song}**")
            else:
                await ctx.send("Skipping... No more songs in the queue.")
        else:
            await ctx.send("No music is currently playing.")
    except Exception as e:
        print(e)
        await ctx.send("An error occurred while trying to skip the song.")

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

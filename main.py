import disnake, os, asyncio, yt_dlp
from disnake.ext import commands
import urllib.parse, urllib.request, re


intents = disnake.Intents.default()
intents.message_content = True
client = commands.Bot(command_prefix=".", intents=intents)

queues = {}
voice_clients = {}
youtube_base_url = 'https://www.youtube.com/'
youtube_results_url = youtube_base_url + 'results?'
youtube_watch_url = youtube_base_url + 'watch?v='
yt_dl_options = { "format": "bestaudio[ext=webm]/bestaudio/best", "noplaylist": True, }
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
            await ctx.send(f"adicionado na fila: **{link}**")
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
        await ctx.send(f"Tocando agora: **{title}**")

    except Exception as e:
        print(e)
        await ctx.send("Ocorreu um erro ao tentar reproduzir a música.")

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

@client.command(name="queue")
async def view_queue(ctx):
    if ctx.guild.id in queues and queues[ctx.guild.id]:
        embed = disnake.Embed(
            title="🎶 Fila atual",
            description="Músicas na fila:",
            color=disnake.Color.blue()
        )
        for idx, url in enumerate(queues[ctx.guild.id], start=1):
            try:
                data = ytdl.extract_info(url, download=False)
                title = data.get('title', 'Título desconhecido')
                embed.add_field(
                    name=f"{idx}. {title}",
                    value=f"[Link]({url})",
                    inline=False
                )
            except Exception as e:
                print(f"Erro ao obter título: {e}")
                embed.add_field(
                    name=f"{idx}. Erro ao buscar título",
                    value=f"[Link]({url})",
                    inline=False
                )
        await ctx.send(embed=embed)
    else:
        await ctx.send("A fila está vazia.")

@client.command(name="skip")
async def skip(ctx):
    try:
        if ctx.guild.id in voice_clients and voice_clients[ctx.guild.id].is_playing():
            next_song = None
            if queues[ctx.guild.id]:
                next_song_link = queues[ctx.guild.id][0]
                loop = asyncio.get_event_loop()
                data = await loop.run_in_executor(None, lambda: ytdl.extract_info(next_song_link, download=False))
                next_song = data.get('title', 'Unknown Title')
            
            # Para a música atual
            voice_clients[ctx.guild.id].stop()

            if next_song:
                await ctx.send(f"Pulando para a próxima música: **{next_song}**")
            else:
                await ctx.send("Skipping... No more songs in the queue.")
        else:
            await ctx.send("Nenhuma música está sendo reproduzida no momento..")
    except Exception as e:
        print(e)
        await ctx.send("Ocorreu um erro ao tentar pular a música.") 

client.run("TOKEN")

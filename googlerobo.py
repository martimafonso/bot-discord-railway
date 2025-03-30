# Adicione isto no topo com os outros imports
import requests  # ← Importação faltando
import discord
from discord.ext import commands
from googleapiclient.discovery import build
from flask import Flask
from threading import Thread
import asyncio
import os
from discord.ext import commands
from dotenv import load_dotenv
from urllib.parse import quote_plus  # Para queries URL-safe

# Remova esta linha:
# load_dotenv()  # ← Comente ou delete

# Use diretamente os.getenv():
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

# Função para manter o bot vivo
app = Flask(__name__)

# ... (imports e configurações anteriores permanecem iguais)

# Adicione novas variáveis de ambiente no seu .env:
# DDG_API_URL = "https://api.duckduckgo.com/"
# BING_API_KEY = "sua_chave_bing"
# Adicione no topo com outros imports
import requests
from urllib.parse import quote_plus  # Para queries URL-safe

# ... (mantenha suas configurações existentes)

def serpapi_search(query, num_results=50):
    try:
        params = {
            'api_key': os.getenv('SERPAPI_KEY'),
            'engine': 'google',
            'q': query,
            'num': num_results,
            'gl': 'br',  # Resultados em português do Brasil
            'hl': 'pt'
        }
        
        response = requests.get('https://serpapi.com/search', params=params)
        response.raise_for_status()
        
        data = response.json()
        resultados = []
        
        for item in data.get('organic_results', []):
            if 'link' in item:
                resultados.append({
                    'title': item.get('title', 'Sem título')[:256],
                    'link': item['link']
                })
                if len(resultados) >= num_results:
                    break
                    
        return resultados
        
    except Exception as e:
        print(f"Erro no SerpAPI: {str(e)[:200]}")
        return []

def duckduckgo_search(query, num_results=50):
    try:
        # Tenta a versão HTML primeiro para termos sensíveis
        query_encoded = quote_plus(query)
        response = requests.get(
            f"https://html.duckduckgo.com/html/?q={query_encoded}",
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        
        if response.status_code == 200:
            return parse_ddg_html(response.text, num_results)
        else:
            return []  # Fallback para JSON se HTML falhar
            
    except Exception as e:
        print(f"Erro no DuckDuckGo: {str(e)[:200]}")
        return []

def parse_ddg_html(html, num_results):
    from bs4 import BeautifulSoup
    import urllib.parse
    
    soup = BeautifulSoup(html, 'html.parser')
    results = []
    
    for result in soup.select('.result__body'):
        link = result.select_one('.result__url')
        if link:
            # Extrai o link real do parâmetro 'uddg'
            raw_url = link['href']
            if 'uddg=' in raw_url:
                decoded_url = urllib.parse.unquote(raw_url.split('uddg=')[1])
                if decoded_url.startswith('https://') or decoded_url.startswith('http://'):
                    final_url = decoded_url.split('&rut=')[0]
                else:
                    final_url = f"https:{decoded_url.split('&rut=')[0]}"
            else:
                final_url = raw_url
            
            title = result.select_one('.result__title').text[:256]
            
            results.append({
                'title': title,
                'link': final_url
            })
            
            if len(results) >= num_results:
                break
                
    return results

def perform_search(query, num_results=50):
    # Tenta Google primeiro
    google_results = []
    try:
        GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
        CUSTOM_SEARCH_ENGINE_ID = os.getenv('CUSTOM_SEARCH_ENGINE_ID')
        
        if not GOOGLE_API_KEY or not CUSTOM_SEARCH_ENGINE_ID:
            raise ValueError("Credenciais do Google faltando")
            
        service = build("customsearch", "v1", developerKey=GOOGLE_API_KEY)
        google_results = []
        start_index = 1
        
        while len(google_results) < num_results:
            response = service.cse().list(
                q=query,
                cx=CUSTOM_SEARCH_ENGINE_ID,
                num=min(10, num_results - len(google_results)),
                start=start_index
            ).execute()
            
            items = response.get('items', [])
            if not items:
                break
                
            google_results.extend(items)
            start_index += len(items)
            
        return google_results
    
    except Exception as e:
        error_msg = str(e)
        if "Quota exceeded" in error_msg:
            print("Cota Google excedida. Usando fallback...")
        else:
            print(f"Erro crítico no Google: {error_msg[:200]}")
        
    # Fallback 1: DuckDuckGo
    ddg_results = duckduckgo_search(query, num_results)
    if ddg_results:
        return ddg_results
        
    # Fallback 2: SerpAPI
    serp_results = serpapi_search(query, num_results)
    if serp_results:
        return serp_results
        
    # Todos os fallbacks falharam
    return []


@app.route('/', methods=['GET', 'HEAD'])  # Aceita ambos os métodos
def home():
    return "O bot está vivo!"

def run():
    port = int(os.environ.get("PORT", 8080))  # ← Usando variável do Railway
    app.run(host='0.0.0.0', port=port)


def keep_alive():
  t = Thread(target=run)
  t.start()


# Configurações do Bot e da API
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=".", intents=intents)

@bot.command(name="google")
async def google(ctx, *, query: str):
    results = perform_search(query, num_results=50)
    
    if not results:
        await ctx.send("🚨 Todas as fontes de pesquisa falharam!")
        return

    current_index = 0

    def create_embed(index):
        embed = discord.Embed(
            title=f"Resultados {index * 5 + 1}-{min((index + 1) * 5, len(results))}",
            color=0x00ff00
        )
        
        start = index * 5
        end = start + 5
        
        for result in results[start:end]:
            # Garante que o link começa com http/https
            link = result['link']
            if not link.startswith(('http://', 'https://')):
                link = f"https://{link}"
            
            embed.add_field(
                name=result['title'],
                value=f"[Link]({link})",
                inline=False
            )
            
        return embed

    message = await ctx.send(embed=create_embed(current_index))
    
    # Controles de paginação (garanta que active_searches está definido)
    active_searches[message.id] = {
        "message": message,
        "results": results,
        "current_index": current_index,
        "user_id": ctx.author.id
    }
    

    def check(reaction, user):
        return (
            user.id == ctx.author.id and
            str(reaction.emoji) in ["⬅️", "➡️", "❌", "🔎"] and
            reaction.message.id == message.id
        )

    while True:
        try:
            reaction, user = await bot.wait_for("reaction_add",
                                              timeout=120.0,
                                              check=check)

            if str(reaction.emoji) == "➡️" and active_searches[
                message.id]["current_index"] < (len(results) - 1) // 5:
                active_searches[message.id]["current_index"] += 1
            elif str(reaction.emoji) == "⬅️" and active_searches[
                message.id]["current_index"] > 0:
                active_searches[message.id]["current_index"] -= 1
            elif str(reaction.emoji) == "🔎":
                await message.remove_reaction(reaction.emoji, user)
                prompt_message = await ctx.send("Para qual página você quer navegar?")

                def msg_check(m):
                    return m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit()

                try:
                    msg = await bot.wait_for("message", timeout=30.0, check=msg_check)
                    page = int(msg.content) - 1
                    await msg.delete()
                    await prompt_message.delete()
                    if 0 <= page <= (len(results) - 1) // 5:
                        active_searches[message.id]["current_index"] = page
                    else:
                        await ctx.send("Página inválida.", delete_after=5)
                except asyncio.TimeoutError:
                    await prompt_message.delete()
                    await ctx.send("Tempo esgotado para escolher a página.", delete_after=5)
            elif str(reaction.emoji) == "❌":
                await message.delete()
                await ctx.message.delete()
                del active_searches[message.id]
                break

            # Atualizar embed
            current_index = active_searches[message.id]["current_index"]
            await message.edit(embed=create_embed(current_index))
            await message.remove_reaction(reaction.emoji, user)

        except asyncio.TimeoutError:
            await message.clear_reactions()
            del active_searches[message.id]
            break

# ... (código posterior permanece igual)


if __name__ == "__main__":
  keep_alive()  # Mantém o servidor Flask ativo
  bot.run(os.environ['DISCORD_TOKEN'])  # Token via variável de ambiente

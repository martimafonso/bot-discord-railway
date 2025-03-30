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
    from bs4 import BeautifulSoup  # Adicione ao requirements.txt
    soup = BeautifulSoup(html, 'html.parser')
    results = []
    
    for result in soup.select('.result__body'):
        title = result.select_one('.result__title')
        link = result.select_one('.result__url')
        
        if title and link:
            results.append({
                'title': title.text[:256],
                'link': link['href']
            })
            if len(results) >= num_results:
                break
                
    return results

def perform_search(query, num_results=50):
    # Tenta Google
    google_results = []
    try:
        service = build("customsearch", "v1", developerKey=os.getenv('GOOGLE_API_KEY'))
        # ... (seu código existente do Google)
        return results
        
    except Exception as e:
        if "Quota exceeded" not in str(e):
            print(f"Erro crítico no Google: {e}")
            return []
            
    # Fallback 1: DuckDuckGo (HTML + JSON)
    ddg_results = duckduckgo_search(query, num_results)
    if ddg_results:
        return ddg_results
        
    # Fallback 2: SerpAPI (Premium)
    serp_results = serpapi_search(query, num_results)
    if serp_results:
        return serp_results
        
    return []  #Todos os fallbacks falharam


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


# ... (código anterior permanece igual)

@bot.command(name="google")
async def google(ctx, *, query: str):
    results = perform_search(query, num_results=50)
    
    if not results:
        await ctx.send("🚨 Todas as fontes de pesquisa falharam ou não retornaram resultados!")
        return

    current_index = 0

    # Função para criar o embed com base no índice atual (CORRIGIDO)
    def create_embed(index):
        embed = discord.Embed(
            title=f"Resultados {index * 5 + 1}-{min((index + 1) * 5, len(results))}/{len(results)}",
            color=discord.Color.blue()
        )
        for i in range(index * 5, min((index + 1) * 5, len(results))):
            result = results[i]
            embed.add_field(name=result['title'], value=result['link'], inline=False)
        return embed

    message = await ctx.send(embed=create_embed(current_index))

    # Adicionar reações para navegação (CORRIGIDO)
    await message.add_reaction("⬅️")
    await message.add_reaction("➡️")
    await message.add_reaction("❌")
    await message.add_reaction("🔎")

    # Salvar o estado da busca (CORRIGIDO)
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

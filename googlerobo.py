import discord
from discord.ext import commands
from googleapiclient.discovery import build
from flask import Flask
from threading import Thread
import asyncio
import os
from discord.ext import commands
from dotenv import load_dotenv

# Remova esta linha:
# load_dotenv()  # ← Comente ou delete

# Use diretamente os.getenv():
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

# Função para manter o bot vivo
app = Flask(__name__)


@app.route('/', methods=['GET', 'HEAD'])  # Aceita ambos os métodos
def home():
    return "O bot está vivo!"

def run():
  app.run(host='0.0.0.0', port=8080)  # Porta 8080 é obrigatória no Replit


def keep_alive():
  t = Thread(target=run)
  t.start()


# Configurações do Bot e da API
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=".", intents=intents)

# ... (imports e configurações anteriores permanecem iguais)

# Adicione novas variáveis de ambiente no seu .env:
# DDG_API_URL = "https://api.duckduckgo.com/"
# BING_API_KEY = "sua_chave_bing"

def duckduckgo_search(query, num_results=50):
    try:
        params = {
            'q': query,
            'format': 'json',
            'no_html': 1,
            'no_redirect': 1,
            't': 'discord_bot'
        }
        response = requests.get(os.getenv('DDG_API_URL'), params=params)
        response.raise_for_status()
        data = response.json()
        
        results = []
        for item in data.get('RelatedTopics', []):
            if 'FirstURL' in item:
                results.append({
                    'title': item.get('Text', 'Sem título'),
                    'link': item['FirstURL']
                })
            if len(results) >= num_results:
                break
        return results
    except Exception as e:
        print(f"Erro no DuckDuckGo: {e}")
        return []

def handle_google_error(e):
    if "Quota exceeded" in str(e):
        print("Cota do Google excedida! Usando fallback...")
        return True
    return False

def perform_search(query, num_results=50):
    # Tenta Google primeiro
    try:
        GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
        CUSTOM_SEARCH_ENGINE_ID = os.getenv('CUSTOM_SEARCH_ENGINE_ID')
        service = build("customsearch", "v1", developerKey=GOOGLE_API_KEY)
        
        results = []
        start_index = 1
        while len(results) < num_results:
            response = service.cse().list(
                q=query,
                cx=CUSTOM_SEARCH_ENGINE_ID,
                num=min(10, num_results - len(results)),
                start=start_index
            ).execute()
            
            items = response.get('items', [])
            if not items:
                break
                
            results.extend(items)
            start_index += len(items)
        return results
    
    except Exception as e:
        if handle_google_error(e):
            # Fallback 1: DuckDuckGo
            ddg_results = duckduckgo_search(query, num_results)
            if ddg_results:
                return ddg_results
            
            # Fallback 2: Adicione aqui outros serviços
            # bing_results = bing_search(query, num_results)
            # return bing_results
            
        print(f"Erro geral na busca: {e}")
        return []


# Função para buscar no Google
def google_search(query, num_results=50):
  GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')  # Adicione esta linha
  CUSTOM_SEARCH_ENGINE_ID = os.getenv('CUSTOM_SEARCH_ENGINE_ID')  # E esta
  service = build("customsearch", "v1", developerKey=GOOGLE_API_KEY)
  # ... restante do código ...
  results = []
  start_index = 1

  while len(results) < num_results:
    try:
      response = service.cse().list(q=query,
                                    cx=CUSTOM_SEARCH_ENGINE_ID,
                                    num=min(10, num_results - len(results)),
                                    start=start_index).execute()
      items = response.get('items', [])
      if not items:
        break
      results.extend(items)
      start_index += len(items)
    except Exception as e:
      print(f"Erro na busca: {e}")
      break

  return results


# Dicionário para armazenar buscas ativas
active_searches = {}


# Modifique o comando para usar a nova função:
@bot.command(name="google")
async def google(ctx, *, query: str):
    results = perform_search(query, num_results=50)  # Função modificada
    
    if not results:
        await ctx.send("🚨 Todas as fontes de pesquisa falharam ou não retornaram resultados!")
        return
    
    # Restante do código permanece igual...
    current_index = 0
    # ... (código de paginação e embed)

  # Função para criar o embed com base no índice atual
  def create_embed(index):
    embed = discord.Embed(
        title=
        f"Resultados {index * 5 + 1}-{min((index + 1) * 5, len(results))}/{len(results)}",
        color=discord.Color.blue())
    for i in range(index * 5, min((index + 1) * 5, len(results))):
      result = results[i]
      embed.add_field(name=result['title'], value=result['link'], inline=False)
    return embed

  message = await ctx.send(embed=create_embed(current_index))

  # Adicionar reações para navegação
  await message.add_reaction("⬅️")
  await message.add_reaction("➡️")
  await message.add_reaction("❌")
  await message.add_reaction("🔎")

  # Salvar o estado da busca
  active_searches[message.id] = {
      "message": message,
      "results": results,
      "current_index": current_index,
      "user_id": ctx.author.id
  }

  def check(reaction, user):
    return (user.id == ctx.author.id
            and str(reaction.emoji) in ["⬅️", "➡️", "❌", "🔎"]
            and reaction.message.id == message.id)

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
          return m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit(
          )

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
          await ctx.send("Tempo esgotado para escolher a página.",
                         delete_after=5)
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


if __name__ == "__main__":
  keep_alive()  # Mantém o servidor Flask ativo
  bot.run(os.environ['DISCORD_TOKEN'])  # Token via variável de ambiente

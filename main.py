import os
import asyncio
import aiohttp
import discord
import json
import time
import random
from discord.ext import tasks
from discord import app_commands
from dotenv import load_dotenv
import textwrap

# -------------------------------
# Load environment variables
# -------------------------------
load_dotenv(dotenv_path="/mnt/data/.env")
TOKEN = os.getenv("TOKEN")
JTOKEN = os.getenv("JTOKEN") or "jscajkghfpvj2xmyml5hnytds6hlwfa6"

# -------------------------------
# Discord Bot setup
# -------------------------------
ROPROXY_USERS = "https://users.roproxy.com"
ROPROXY_FRIENDS = "https://friends.roproxy.com"
ROPROXY_THUMB = "https://thumbnails.roproxy.com"

intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

global_limit = asyncio.Semaphore(20)
CACHE_DURATION = 300  # seconds
cache = {}  # uid -> {"data":..., "ts":...}

bot.session = None  # will be initialized on_ready

# -------------------------------
# Cache helpers
# -------------------------------
def get_cache(uid):
    entry = cache.get(uid)
    if not entry: 
        return None
    if time.time() - entry["ts"] > CACHE_DURATION:
        cache.pop(uid, None)
        return None
    return entry["data"]

def set_cache(uid, data):
    cache[uid] = {"data": data, "ts": time.time()}

# -------------------------------
# JSONHost helpers
# -------------------------------
async def jsonhost_get():
    url = "https://jsonhost.com/api/json/mason"
    headers = {"Authorization": JTOKEN}
    try:
        async with bot.session.get(url, headers=headers, timeout=10) as r:
            if r.status == 200:
                return await r.json()
    except Exception as e:
        print("JSONHost GET error:", e)
    return None

async def jsonhost_put(data):
    url = "https://jsonhost.com/api/json/mason"
    headers = {"Authorization": JTOKEN}
    try:
        async with bot.session.put(url, json=data, headers=headers, timeout=10) as r:
            return r.status == 200
    except Exception as e:
        print("JSONHost PUT error:", e)
    return False

# -------------------------------
# Roblox API fetchers
# -------------------------------
async def fetch_json(url, retries=3):
    headers = {"User-Agent": "Mozilla/5.0"}
    for _ in range(retries):
        try:
            async with bot.session.get(url, headers=headers, timeout=10) as r:
                if r.status == 200:
                    return await r.json()
        except Exception:
            await asyncio.sleep(1)
    return None

async def get_user_id(username):
    if username.isdigit(): 
        return int(username)
    payload = {"usernames": [username]}
    async with bot.session.post(f"{ROPROXY_USERS}/v1/usernames/users", json=payload) as r:
        if r.status != 200: 
            return None
        data = await r.json()
        try: 
            return data["data"][0]["id"]
        except:
            return None

async def get_full_user_data(uid):
    cached = get_cache(uid)
    if cached: 
        return cached

    online = await jsonhost_get() or {}
    if str(uid) in online:
        set_cache(uid, online[str(uid)])
        return online[str(uid)]

    user = await fetch_json(f"{ROPROXY_USERS}/v1/users/{uid}")
    friends = await fetch_json(f"{ROPROXY_FRIENDS}/v1/users/{uid}/friends/count")
    avatar = await fetch_json(f"{ROPROXY_THUMB}/v1/users/avatar-headshot?userIds={uid}&size=420x420&format=Png")

    if not user or not friends or not avatar: 
        return None

    result = {
        "name": user.get("name"),
        "displayName": user.get("displayName"),
        "userId": uid,
        "description": user.get("description"),
        "created": user.get("created"),
        "friendCount": friends.get("count", 0),
        "avatarUrl": avatar["data"][0]["imageUrl"]
    }

    set_cache(uid, result)
    online[str(uid)] = result
    await jsonhost_put(online)
    return result

# -------------------------------
# Cache cleaner
# -------------------------------
@tasks.loop(minutes=5)
async def clean_cache():
    now = time.time()
    expired = [k for k, v in cache.items() if now - v["ts"] > CACHE_DURATION]
    for k in expired: 
        cache.pop(k, None)

# -------------------------------
# Discord command
# -------------------------------
@tree.command(name="user", description="Search Roblox user")
async def roblox_user(interaction: discord.Interaction, username: str):
    async with global_limit:
        await interaction.response.defer()
        uid = await get_user_id(username)
        if not uid:
            await interaction.followup.send("❌ User not found.")
            return

        data = await get_full_user_data(uid)
        if not data:
            await interaction.followup.send("❌ API error or Cloudflare blocked.")
            return

        # Join date
        join_date = data["created"].split("T")[0] if data.get("created") else "N/A"

        # Premium check
        premium_data = await fetch_json(f"https://premiumfeatures.roproxy.com/v1/users/{uid}/validate-membership")
        is_premium = premium_data.get("isPremium") if premium_data else False
        premium_text = "● Premium Member" if is_premium else "○ Standard User"

        # Description
        desc = textwrap.shorten(data.get("description") or "_No description_", width=100, placeholder="…")

        # Embed
        embed = discord.Embed(
            title=f"{data['name']} — Roblox User",
            description=f"**{data['displayName']}**",
            color=discord.Color.from_rgb(235,245,255)
        )
        embed.set_thumbnail(url=data["avatarUrl"])
        embed.add_field(name="🌫 Description", value=desc, inline=False)
        embed.add_field(name="👥 Friends", value=str(data["friendCount"]), inline=True)
        embed.add_field(name="⭐ Status", value=premium_text, inline=True)
        embed.add_field(name="📅 Join Date", value=join_date, inline=True)
        embed.add_field(name="🆔 User ID", value=str(data["userId"]), inline=True)
        embed.set_footer(text="Cuslige Bot", icon_url=data["avatarUrl"])

        # Buttons
        class VisionButtons(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=60)
                self.add_item(discord.ui.Button(label="🌐 View Profile", style=discord.ButtonStyle.link,
                                               url=f"https://www.roblox.com/users/{uid}/profile"))
                self.add_item(discord.ui.Button(label="🖼 Avatar Image", style=discord.ButtonStyle.link,
                                               url=data["avatarUrl"]))
                self.add_item(discord.ui.Button(label="📋 Copy UserID", style=discord.ButtonStyle.secondary,
                                               disabled=True))

        await interaction.followup.send(embed=embed, view=VisionButtons())

# -------------------------------
# Background task: Random user fetch
# -------------------------------
SAMPLE_USERNAMES = [
    "builderman", "roblox", "noobmaster", "user123", "gamer456",
    "playerOne", "devTest", "exampleUser", "funnyCat", "coolDude"
]

async def random_user_search_task():
    await bot.wait_until_ready()
    while True:
        username = random.choice(SAMPLE_USERNAMES)
        async with global_limit:
            uid = await get_user_id(username)
            if uid:
                data = await get_full_user_data(uid)
                if data:
                    print(f"Auto-fetched: {username} ({uid})")
        await asyncio.sleep(100)  # 每 100 秒自動搜尋一次

# -------------------------------
# Bot ready
# -------------------------------
@bot.event
async def on_ready():
    print("Bot is ready.")
    bot.session = aiohttp.ClientSession()
    await tree.sync()
    clean_cache.start()
    bot.loop.create_task(random_user_search_task())

# -------------------------------
# Graceful shutdown
# -------------------------------
async def shutdown():
    if bot.session:
        await bot.session.close()

# -------------------------------
# Start bot
# -------------------------------
if __name__ == "__main__":
    try:
        bot.run(TOKEN)
    finally:
        asyncio.run(shutdown())

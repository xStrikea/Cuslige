import os
import subprocess
import shutil
import discord
import aiohttp
import asyncio
import json
import time
from discord.ext import tasks
from discord import app_commands
from dotenv import load_dotenv

# -------------------------------
# Load environment variables
# -------------------------------
load_dotenv()
TOKEN = os.getenv("TOKEN")
JTOKEN = os.getenv("JTOKEN") or "jscajkghfpvj2xmyml5hnytds6hlwfa6"

# -------------------------------
# Startup tasks
# -------------------------------
def update_pip():
    try:
        subprocess.run(["python3", "-m", "pip", "install", "--upgrade", "pip"], check=True)
    except:
        pass

def cleanup_files():
    folders = ["__pycache__", ".cache"]
    exts = [".log", ".tmp", ".bak"]
    for f in folders:
        if os.path.exists(f):
            try: shutil.rmtree(f)
            except: pass
    for file in os.listdir():
        for e in exts:
            if file.endswith(e):
                try: os.remove(file)
                except: pass

def install_requirements():
    try:
        subprocess.run(["python3", "-m", "pip", "install", "discord.py", "aiohttp", "python-dotenv"], check=True)
    except: pass

# -------------------------------
# Discord bot setup
# -------------------------------
ROPROXY_USERS = "https://users.roproxy.com"
ROPROXY_FRIENDS = "https://friends.roproxy.com"
ROPROXY_THUMB = "https://thumbnails.roproxy.com"

intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)
global_limit = asyncio.Semaphore(20)

cache = {}
CACHE_DURATION = 300

# -------------------------------
# Cache helpers
# -------------------------------
def encode_user_data(data): return json.dumps(data)
def decode_user_data(data): return json.loads(data)
def get_cache(uid):
    if uid not in cache: return None
    encoded, ts = cache[uid]
    if time.time() - ts > CACHE_DURATION:
        del cache[uid]; return None
    return decode_user_data(encoded)
def set_cache(uid, data): cache[uid] = (encode_user_data(data), time.time())

# -------------------------------
# JSONHost online storage
# -------------------------------
async def jsonhost_get():
    url = "https://jsonhost.com/api/json/mason"
    headers = {"Authorization": JTOKEN}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=headers) as r:
                return await r.json() if r.status == 200 else None
    except: return None

async def jsonhost_put(data):
    url = "https://jsonhost.com/api/json/mason"
    headers = {"Authorization": JTOKEN}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.put(url, json=data, headers=headers) as r:
                return r.status == 200
    except: return False

# -------------------------------
# Roblox API fetchers
# -------------------------------
async def fetch_json(session, url, retries=3):
    headers = {"User-Agent": "Mozilla/5.0"}
    for _ in range(retries):
        try:
            async with session.get(url, headers=headers, timeout=10) as r:
                if r.status == 200: return await r.json()
            await asyncio.sleep(1)
        except: await asyncio.sleep(1)
    return None

async def get_user_id(username):
    if username.isdigit(): return int(username)
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{ROPROXY_USERS}/v1/usernames/users", json={"usernames": [username]}) as r:
            if r.status != 200: return None
            data = await r.json()
            try: return data["data"][0]["id"]
            except: return None

async def get_full_user_data(uid):
    cached = get_cache(uid)
    if cached: return cached

    online = await jsonhost_get()
    if online and str(uid) in online:
        set_cache(uid, online[str(uid)])
        return online[str(uid)]

    async with aiohttp.ClientSession() as s:
        user = await fetch_json(s, f"{ROPROXY_USERS}/v1/users/{uid}")
        friends = await fetch_json(s, f"{ROPROXY_FRIENDS}/v1/users/{uid}/friends/count")
        avatar = await fetch_json(s, f"{ROPROXY_THUMB}/v1/users/avatar-headshot?userIds={uid}&size=420x420&format=Png")
        if not user or not friends or not avatar: return None

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
    online = online or {}
    online[str(uid)] = result
    await jsonhost_put(online)
    return result

# -------------------------------
# Cache cleaner
# -------------------------------
@tasks.loop(minutes=5)
async def clean_cache():
    now = time.time()
    expired = [k for k, (_, ts) in cache.items() if now - ts > CACHE_DURATION]
    for k in expired: del cache[k]

# -------------------------------
# VisionOS Improved Layout
# -------------------------------
@tree.command(name="user", description="Search Roblox user")
async def roblox_user(interaction: discord.Interaction, username: str):
    async with global_limit:
        await interaction.response.defer()
        uid = await get_user_id(username)
        if not uid: 
            await interaction.followup.send("❌ User not found."); return

        data = await get_full_user_data(uid)
        if not data: 
            await interaction.followup.send("❌ API error or Cloudflare blocked."); return

        # Format join date
        created = data["created"]
        join_date = created.split("T")[0] if created else "N/A"

        # Premium check
        async with aiohttp.ClientSession() as s:
            async with s.get(f"https://premiumfeatures.roproxy.com/v1/users/{uid}/validate-membership") as r:
                premium = await r.json() if r.status == 200 else {"isPremium": False}
        premium_text = "● Premium Member" if premium.get("isPremium") else "○ Standard User"

        # Truncate description if too long
        desc = data["description"] or "_No description_"
        if len(desc) > 100: desc = desc[:97] + "…"

        # -------------------------------
        # Embed Layout
        # -------------------------------
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
# Bot ready
# -------------------------------
@bot.event
async def on_ready():
    print("Bot is ready.")
    await tree.sync()
    clean_cache.start()

# -------------------------------
# Start
# -------------------------------
if __name__ == "__main__":
    update_pip()
    cleanup_files()
    install_requirements()
    bot.run(TOKEN)

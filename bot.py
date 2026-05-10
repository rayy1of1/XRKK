import subprocess
import sys

def _ensure(pkg, import_as=None):
    name = import_as or pkg
    try:
        __import__(name)
    except ImportError:
        print(f"{pkg} not found — installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"])

_ensure("PyNaCl", "nacl")
_ensure("davey")
_ensure("discord.py[voice]", "discord")

import discord
from discord.ext import commands
from discord import AuditLogAction
import asyncio
import aiohttp
import logging
import json
import os
import time
import ctypes


intents = discord.Intents.all()

bot = commands.Bot(command_prefix="x", intents=intents)

logging.basicConfig(level=logging.CRITICAL)
logging.getLogger().setLevel(logging.CRITICAL)
logging.getLogger('discord').setLevel(logging.CRITICAL)
logging.getLogger('discord.ext.commands').setLevel(logging.CRITICAL)

LOG_CHANNEL = 1501620158844899480

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WL_FILE = os.path.join(BASE_DIR, "whitelist.json")
WL_TXT  = os.path.join(BASE_DIR, "whitelist.txt")

stacker_bots: list = []


# ─── COLORS ───────────────────────────────────────────────────────────────────
class Colors:
    BLUE   = '\033[94m'
    CYAN   = '\033[96m'
    GREEN  = '\033[92m'
    YELLOW = '\033[93m'
    RED    = '\033[91m'
    PURPLE = '\033[95m'
    BOLD   = '\033[1m'
    END    = '\033[0m'

def clog(bot_name, message, color=Colors.BLUE):
    print(f"{Colors.BOLD}{Colors.CYAN}[{bot_name}]{Colors.END} {color}{message}{Colors.END}")


# ─── WHITELIST STORAGE ────────────────────────────────────────────────────────
def load_whitelist():
    if not os.path.exists(WL_FILE):
        return {}
    with open(WL_FILE, "r") as f:
        data = json.load(f)
    result = {}
    for gid, val in data.items():
        if isinstance(val, dict):
            result[gid] = {
                "users": set(val.get("users", [])),
                "bots":  set(val.get("bots",  [])),
            }
        else:
            result[gid] = {"users": set(val), "bots": set()}
    return result

def save_whitelist():
    data = {
        gid: {
            "users": list(entry["users"]),
            "bots":  list(entry["bots"]),
        }
        for gid, entry in WHITELIST.items()
    }
    with open(WL_FILE, "w") as f:
        json.dump(data, f, indent=4)

def save_whitelist_txt():
    with open(WL_TXT, "w") as f:
        f.write("=== XRK WHITELIST ===\n\n")
        for gid, entry in WHITELIST.items():
            f.write(f"Server ID: {gid}\n")
            f.write("  Users:\n")
            for uid in entry["users"]:
                f.write(f"    - {uid}\n")
            f.write("  Bots:\n")
            for uid in entry["bots"]:
                f.write(f"    - {uid}\n")
            f.write("\n")

WHITELIST = load_whitelist()

def _ensure_guild(guild_id):
    gid = str(guild_id)
    if gid not in WHITELIST:
        WHITELIST[gid] = {"users": set(), "bots": set()}
        save_whitelist()
    return gid

def get_wl(guild_id):
    gid = _ensure_guild(guild_id)
    return WHITELIST[gid]["users"] | WHITELIST[gid]["bots"]

def get_wl_users(guild_id):
    gid = _ensure_guild(guild_id)
    return WHITELIST[gid]["users"]

def get_wl_bots(guild_id):
    gid = _ensure_guild(guild_id)
    return WHITELIST[gid]["bots"]


# ─── DOWNLOAD HELPER ──────────────────────────────────────────────────────────
async def fetch_image_bytes(url):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.read()
    except Exception:
        pass
    return None


# ─── LOG EMBED ────────────────────────────────────────────────────────────────
async def send_log(guild, user_id, action, target=None):
    channel = guild.get_channel(LOG_CHANNEL)
    if not channel:
        return
    embed = discord.Embed(
        title="kupal ka ba",
        description=f"**A destructive action was blocked!**\n\n{action}",
        color=discord.Color.red()
    )
    embed.add_field(name="Attacker", value=f"<@{user_id}> ({user_id})", inline=False)
    if target:
        embed.add_field(name="Target", value=str(target), inline=False)
    embed.set_footer(text="Strict Anti-Nuke Module")
    await channel.send(embed=embed)


# ─── CORE BAN ─────────────────────────────────────────────────────────────────
async def ban_user(guild, user_id, reason, log_action=None, log_target=None):
    wl = get_wl(guild.id)
    if user_id in wl or user_id == guild.owner_id:
        print(f"[XRK] Skipped {user_id} — whitelisted or owner")
        return

    success = False

    try:
        await guild.ban(discord.Object(id=user_id), reason=reason, delete_message_days=0)
        print(f"[XRK] BANNED {user_id} — {reason}")
        success = True
    except discord.Forbidden:
        print(f"[XRK] Ban FAILED for {user_id} — bot role too low or missing BAN_MEMBERS permission")
    except discord.HTTPException as e:
        print(f"[XRK] Ban HTTP error for {user_id} — {e}")
    except Exception as e:
        print(f"[XRK] Ban unknown error for {user_id} — {e}")

    if not success:
        try:
            member = guild.get_member(user_id)
            if member is None:
                member = await guild.fetch_member(user_id)
            await member.kick(reason=reason)
            print(f"[XRK] KICKED {user_id} as fallback — {reason}")
            success = True
        except Exception as e:
            print(f"[XRK] Kick also FAILED for {user_id} — {e}")

    if success and log_action:
        await send_log(guild, user_id, log_action, log_target)


# ─── punish() wrapper ─────────────────────────────────────────────────────────
async def punish(guild, user, action, target=None):
    if not user or user.bot:
        return
    wl = get_wl(guild.id)
    if user.id in wl or user.id == guild.owner_id:
        return
    await ban_user(guild, user.id, f"Anti-Nuke: {action}", action, target)


# ─── AUDIT LOG HELPER ─────────────────────────────────────────────────────────
async def get_log(guild, action):
    async for e in guild.audit_logs(limit=1, action=action):
        return e
    for _ in range(6):
        await asyncio.sleep(0.05)
        async for e in guild.audit_logs(limit=1, action=action):
            return e
    return None


async def auto_delete_channel(channel):
    try:
        await channel.delete(reason="Anti-Nuke: Unauthorized Channel Creation")
    except Exception:
        pass


# ─── CHANNEL SNAPSHOT & AUTO-RESTORE ─────────────────────────────────────────
channel_snapshot: dict[int, dict[int, dict]] = {}
restore_queue: dict[int, list] = {}
restore_debounce_tasks: dict[int, asyncio.Task] = {}
_guilds_restoring: set[int] = set()


def _snapshot_channel(channel) -> dict:
    data = {
        "id": channel.id,
        "name": channel.name,
        "type": channel.type,
        "category_id": channel.category_id,
        "position": channel.position,
        "overwrites": channel.overwrites,
    }
    if isinstance(channel, discord.TextChannel):
        data["topic"] = channel.topic
        data["slowmode_delay"] = channel.slowmode_delay
        data["nsfw"] = channel.nsfw
    elif isinstance(channel, discord.VoiceChannel):
        data["bitrate"] = channel.bitrate
        data["user_limit"] = channel.user_limit
    elif isinstance(channel, discord.ForumChannel):
        data["topic"] = channel.topic
        data["slowmode_delay"] = channel.slowmode_delay
        data["nsfw"] = channel.nsfw
    return data


def snapshot_all_channels(guild):
    channel_snapshot[guild.id] = {}
    for ch in guild.channels:
        channel_snapshot[guild.id][ch.id] = _snapshot_channel(ch)
    print(f"[XRK] Snapshotted {len(guild.channels)} channels for guild {guild.id}")


async def _restore_single(guild, data: dict, category_map: dict) -> discord.abc.GuildChannel | None:
    category = None
    if data.get("category_id"):
        category = category_map.get(data["category_id"]) or guild.get_channel(data["category_id"])

    try:
        ch_type = data["type"]
        base_kwargs = {
            "name": data["name"],
            "overwrites": data.get("overwrites", {}),
            "position": data["position"],
            "reason": "Anti-Nuke: Auto-Restore Deleted Channel",
        }

        if ch_type == discord.ChannelType.category:
            new_ch = await guild.create_category(
                name=data["name"],
                overwrites=data.get("overwrites", {}),
                position=data["position"],
                reason="Anti-Nuke: Auto-Restore Deleted Category",
            )

        elif ch_type == discord.ChannelType.text:
            if category:
                base_kwargs["category"] = category
            new_ch = await guild.create_text_channel(
                topic=data.get("topic") or "",
                slowmode_delay=data.get("slowmode_delay", 0),
                nsfw=data.get("nsfw", False),
                **base_kwargs,
            )

        elif ch_type == discord.ChannelType.voice:
            if category:
                base_kwargs["category"] = category
            new_ch = await guild.create_voice_channel(
                bitrate=min(data.get("bitrate", 64000), 96000),
                user_limit=data.get("user_limit", 0),
                **base_kwargs,
            )

        elif ch_type == discord.ChannelType.forum:
            if category:
                base_kwargs["category"] = category
            new_ch = await guild.create_forum(
                topic=data.get("topic") or "",
                slowmode_delay=data.get("slowmode_delay", 0),
                nsfw=data.get("nsfw", False),
                **base_kwargs,
            )

        else:
            if category:
                base_kwargs["category"] = category
            new_ch = await guild.create_text_channel(**base_kwargs)

        print(f"[XRK] Restored: #{data['name']} ({ch_type})")
        return new_ch

    except Exception as e:
        print(f"[XRK] Restore failed for #{data['name']}: {e}")
        return None


async def _process_restore_queue(guild_id: int):
    await asyncio.sleep(2)

    guild = bot.get_guild(guild_id)
    if not guild:
        restore_queue.pop(guild_id, None)
        return

    queue = restore_queue.pop(guild_id, [])
    if not queue:
        return

    category_map: dict[int, discord.CategoryChannel] = {}

    _guilds_restoring.add(guild_id)
    try:
        categories = sorted(
            [d for d in queue if d["type"] == discord.ChannelType.category],
            key=lambda x: x["position"],
        )
        for data in categories:
            new_cat = await _restore_single(guild, data, category_map)
            if new_cat:
                category_map[data["id"]] = new_cat

        others = sorted(
            [d for d in queue if d["type"] != discord.ChannelType.category],
            key=lambda x: x["position"],
        )
        for data in others:
            await _restore_single(guild, data, category_map)
    finally:
        _guilds_restoring.discard(guild_id)

    snapshot_all_channels(guild)

    log_ch = guild.get_channel(LOG_CHANNEL)
    if log_ch and queue:
        names = "\n".join(f"• #{d['name']}" for d in queue[:20])
        if len(queue) > 20:
            names += f"\n…and {len(queue) - 20} more"
        embed = discord.Embed(
            title="Auto-Restore Complete",
            description=f"Restored **{len(queue)}** deleted channel(s).",
            color=discord.Color.green(),
        )
        embed.add_field(name="Channels Restored", value=names, inline=False)
        embed.set_footer(text="Anti-Nuke Auto-Restore Module")
        await log_ch.send(embed=embed)


def _queue_restore(guild_id: int, channel_data: dict):
    restore_queue.setdefault(guild_id, []).append(channel_data)

    existing = restore_debounce_tasks.get(guild_id)
    if existing and not existing.done():
        existing.cancel()

    task = asyncio.create_task(_process_restore_queue(guild_id))
    restore_debounce_tasks[guild_id] = task


# ─── EVENTS ───────────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    print(f"[XRK] Logged in as {bot.user} ({bot.user.id})")
    for guild in bot.guilds:
        snapshot_all_channels(guild)


@bot.event
async def on_guild_channel_delete(channel):
    saved_data = channel_snapshot.get(channel.guild.id, {}).pop(channel.id, None)

    entry = await get_log(channel.guild, AuditLogAction.channel_delete)
    if not entry:
        return

    deleter = entry.user
    wl = get_wl(channel.guild.id)

    if deleter.id in wl or deleter.id == channel.guild.owner_id:
        return

    await punish(channel.guild, deleter, "Deleted a channel", channel.name)

    if saved_data:
        _queue_restore(channel.guild.id, saved_data)


TRUSTED_BOTS = {472911936951156740}


@bot.event
async def on_guild_channel_create(channel):
    channel_snapshot.setdefault(channel.guild.id, {})[channel.id] = _snapshot_channel(channel)

    if channel.guild.id in _guilds_restoring:
        return

    wl = get_wl(channel.guild.id)
    entry = await get_log(channel.guild, AuditLogAction.channel_create)
    if not entry:
        return
    creator = entry.user
    if creator.id in wl or creator.id == channel.guild.owner_id:
        return
    if creator.bot:
        if creator.id not in TRUSTED_BOTS:
            await auto_delete_channel(channel)
        return
    await punish(channel.guild, creator, "Created a channel", channel.name)
    await auto_delete_channel(channel)


@bot.event
async def on_guild_channel_update(before, after):
    channel_snapshot.setdefault(after.guild.id, {})[after.id] = _snapshot_channel(after)

    wl = get_wl(after.guild.id)
    entry = await get_log(after.guild, AuditLogAction.channel_update)
    if not entry:
        return
    user = entry.user
    if user.bot or user.id in wl or user.id == after.guild.owner_id:
        return
    if before.name != after.name:
        await punish(after.guild, user, f"Renamed channel #{before.name} → #{after.name}", after.name)
        await asyncio.sleep(1)
        try:
            await after.edit(name=before.name, reason="Anti-Nuke: Unauthorized Rename")
        except Exception:
            pass


@bot.event
async def on_guild_update(before, after):
    wl = get_wl(after.id)
    entry = await get_log(after, AuditLogAction.guild_update)
    if not entry or entry.user.bot or entry.user.id in wl or entry.user.id == after.owner_id:
        return

    user = entry.user

    if before.name != after.name:
        await punish(after, user, f"Changed server name: {before.name} → {after.name}")
        try:
            await after.edit(name=before.name, reason="Anti-Nuke: Revert server name")
        except Exception:
            pass

    elif before.icon != after.icon:
        await punish(after, user, "Changed server icon")
        if before.icon:
            try:
                icon_url = before.icon.url if hasattr(before.icon, "url") else before.icon_url
                icon_bytes = await fetch_image_bytes(icon_url)
                if icon_bytes:
                    await after.edit(icon=icon_bytes, reason="Anti-Nuke: Revert server icon")
            except Exception:
                pass
        else:
            try:
                await after.edit(icon=None, reason="Anti-Nuke: Revert server icon")
            except Exception:
                pass

    elif before.banner != after.banner:
        await punish(after, user, "Changed server banner")
        if before.banner:
            try:
                banner_url = before.banner.url if hasattr(before.banner, "url") else before.banner_url
                banner_bytes = await fetch_image_bytes(banner_url)
                if banner_bytes:
                    await after.edit(banner=banner_bytes, reason="Anti-Nuke: Revert server banner")
            except Exception:
                pass
        else:
            try:
                await after.edit(banner=None, reason="Anti-Nuke: Revert server banner")
            except Exception:
                pass

    elif before.description != after.description:
        await punish(after, user, "Changed server description")
        try:
            await after.edit(description=before.description, reason="Anti-Nuke: Revert server description")
        except Exception:
            pass

    else:
        await punish(after, user, "Edited server settings")


baddie_cooldown = {}

WEBHOOK_DELETE_COOLDOWN_MS = 10000
webhook_delete_cooldown: dict[int, float] = {}


@bot.event
async def on_message(message):
    if message.author.bot and not message.webhook_id:
        return

    guild = message.guild
    if not guild:
        return

    content = message.content.lower()
    now = time.time()
    gid = guild.id

    if gid not in baddie_cooldown:
        baddie_cooldown[gid] = 0

    if "ARP" in content:
        if now - baddie_cooldown[gid] >= 20:
            await message.reply("POTANGINA MO")
            baddie_cooldown[gid] = now

    if message.webhook_id:
        wl = get_wl(guild.id)

        try:
            await message.delete()
        except discord.HTTPException:
            pass

        cooldown_seconds = WEBHOOK_DELETE_COOLDOWN_MS / 1000
        last_action = webhook_delete_cooldown.get(gid, 0)
        if now - last_action < cooldown_seconds:
            print(f"[XRK] Webhook spam in guild {gid} — rate-limited, skipping heavy actions "
                  f"({cooldown_seconds - (now - last_action):.1f}s remaining)")
            await bot.process_commands(message)
            return

        creator_id = None
        try:
            wh = await bot.fetch_webhook(message.webhook_id)
            if wh.user:
                uid = wh.user.id
                if uid not in wl and uid != guild.owner_id and not wh.user.bot:
                    creator_id = uid
                    print(f"[XRK] Webhook message creator found via fetch_webhook: {uid}")
        except Exception as e:
            print(f"[XRK] fetch_webhook failed: {e}")

        if not creator_id:
            entry = await get_log(guild, AuditLogAction.webhook_create)
            if entry:
                uid = entry.user.id
                if uid not in wl and uid != guild.owner_id and not entry.user.bot:
                    creator_id = uid
                    print(f"[XRK] Webhook creator found via audit log: {uid}")

        if creator_id:
            webhook_delete_cooldown[gid] = now

            await ban_user(guild, creator_id, "Anti-Nuke: Webhook Spam",
                           "Webhook Spam Detected", message.channel.name)

            try:
                webhooks = await guild.webhooks()
                await asyncio.gather(
                    *[wh.delete(reason="Anti-Nuke: Webhook Spam") for wh in webhooks],
                    return_exceptions=True
                )
            except Exception:
                pass

            try:
                await message.channel.purge(limit=200, check=lambda m: bool(m.webhook_id))
            except discord.HTTPException:
                pass
        else:
            print(f"[XRK] Could not identify webhook creator in guild {guild.id}")

    await bot.process_commands(message)


@bot.event
async def on_guild_role_update(before, after):
    wl = get_wl(after.guild.id)
    entry = await get_log(after.guild, AuditLogAction.role_update)
    if entry and not entry.user.bot and entry.user.id not in wl:
        await punish(after.guild, entry.user, "Updated a role", after.name)


@bot.event
async def on_guild_emojis_update(guild, before, after):
    wl = get_wl(guild.id)
    if len(after) < len(before):
        entry = await get_log(guild, AuditLogAction.emoji_delete)
        if entry and not entry.user.bot and entry.user.id not in wl:
            await punish(guild, entry.user, "Deleted an emoji")


@bot.event
async def on_member_join(member):
    if not member.bot:
        return
    guild = member.guild
    wl = get_wl(guild.id)
    entry = await get_log(guild, AuditLogAction.bot_add)
    if not entry:
        return
    user = entry.user
    if user.id in wl or user.id == guild.owner_id:
        return
    await punish(guild, user, "Added a bot", str(member))
    await ban_user(guild, member.id, "Anti-Nuke: Unauthorized Bot Add")


mass_kick_counter = {}


@bot.event
async def on_member_remove(member):
    guild = member.guild
    wl = get_wl(guild.id)
    entry = await get_log(guild, AuditLogAction.kick)
    if not entry:
        return
    user = entry.user
    if user.id in wl or user.bot or user.id == guild.owner_id:
        return
    mass_kick_counter[user.id] = mass_kick_counter.get(user.id, 0) + 1
    if mass_kick_counter[user.id] >= 2:
        await punish(guild, user, "Mass Kick Detected")
        mass_kick_counter[user.id] = 0


mass_ban_counter = {}


@bot.event
async def on_member_ban(guild, user):
    wl = get_wl(guild.id)
    entry = await get_log(guild, AuditLogAction.ban)
    if not entry:
        return
    executor = entry.user
    if executor.bot or executor.id in wl or executor.id == guild.owner_id:
        return
    mass_ban_counter[executor.id] = mass_ban_counter.get(executor.id, 0) + 1
    if mass_ban_counter[executor.id] >= 2:
        await punish(guild, executor, "Mass Ban Detected")
        mass_ban_counter[executor.id] = 0


@bot.event
async def on_webhooks_update(channel):
    guild = channel.guild
    wl = get_wl(guild.id)

    creator_id = None

    try:
        webhooks = await channel.webhooks()
        for wh in webhooks:
            if wh.user:
                uid = wh.user.id
                if uid not in wl and uid != guild.owner_id and not wh.user.bot:
                    creator_id = uid
                    print(f"[XRK] Webhook creator found via channel.webhooks(): {uid}")
                    break
    except discord.HTTPException as e:
        print(f"[XRK] channel.webhooks() failed: {e}")
        webhooks = []

    if not creator_id:
        print(f"[XRK] wh.user was None, trying audit log...")
        for attempt in range(8):
            await asyncio.sleep(0.5)
            try:
                async for entry in guild.audit_logs(limit=1, action=AuditLogAction.webhook_create):
                    uid = entry.user.id
                    if uid not in wl and uid != guild.owner_id and not entry.user.bot:
                        creator_id = uid
                        print(f"[XRK] Webhook creator found via audit log (attempt {attempt+1}): {uid}")
                    break
            except Exception as e:
                print(f"[XRK] Audit log error: {e}")
            if creator_id:
                break

    if not creator_id:
        print(f"[XRK] Could not identify webhook creator in #{channel.name}")
        return

    await ban_user(guild, creator_id, "Anti-Nuke: Unauthorized Webhook Creation",
                   "Unauthorized Webhook Creation", channel.name)

    try:
        all_webhooks = await guild.webhooks()
        await asyncio.gather(
            *[wh.delete(reason="Anti-Nuke: Unauthorized Webhook") for wh in all_webhooks],
            return_exceptions=True
        )
    except Exception:
        pass

    try:
        await channel.purge(limit=200, check=lambda m: bool(m.webhook_id))
    except discord.HTTPException:
        pass


# ─── COMMANDS ─────────────────────────────────────────────────────────────────

@bot.command(name="purge")
@commands.has_permissions(manage_messages=True)
async def purge(ctx, amount: int):
    if amount < 1 or amount > 100:
        return await ctx.reply("Please enter a number between 1 and 100.")
    await ctx.message.delete()
    deleted = await ctx.channel.purge(limit=amount)
    await ctx.send(f"Deleted {len(deleted)} messages.", delete_after=3)

@purge.error
async def purge_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.reply("Usage: `xpurge <amount>` (e.g. `xpurge 15`)")
    elif isinstance(error, commands.BadArgument):
        await ctx.reply("Please provide a valid number. Example: `xpurge 15`")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.reply("You need the **Manage Messages** permission to use this command.")


# ─── xwl — USERS ONLY ─────────────────────────────────────────────────────────
@bot.command(name="wl")
async def wl_cmd(ctx, member: discord.Member = None):
    if ctx.author.id != ctx.guild.owner_id and not ctx.author.guild_permissions.administrator:
        return await ctx.reply("You need to be an **Administrator** or the **Server Owner** to use this.")
    if member is None:
        return await ctx.reply("Usage: `xwl @user` — for **users only**. Use `xwlbot @bot` to whitelist a bot.")
    if member.bot:
        return await ctx.reply(
            f"**{member}** is a bot. Use `xwlbot @bot` to whitelist bots."
        )

    wl_users = get_wl_users(ctx.guild.id)

    if member.id in wl_users:
        wl_users.remove(member.id)
        save_whitelist()
        save_whitelist_txt()
        embed = discord.Embed(
            title="Whitelist Updated",
            description=f"Removed **{member}** from the user whitelist.",
            color=0x010101
        )
    else:
        wl_users.add(member.id)
        save_whitelist()
        save_whitelist_txt()
        embed = discord.Embed(
            title="Whitelist Updated",
            description=f"Added **{member}** to the user whitelist.",
            color=0x010101
        )

    await ctx.reply(embed=embed)

@wl_cmd.error
async def wl_error(ctx, error):
    if isinstance(error, commands.MemberNotFound):
        await ctx.reply("Could not find that user. Make sure to @mention them correctly.")


# ─── xwlbot — BOTS ONLY ───────────────────────────────────────────────────────
@bot.command(name="wlbot")
async def wlbot_cmd(ctx, member: discord.Member = None):
    if ctx.author.id != ctx.guild.owner_id and not ctx.author.guild_permissions.administrator:
        return await ctx.reply("You need to be an **Administrator** or the **Server Owner** to use this.")
    if member is None:
        return await ctx.reply("Usage: `xwlbot @bot` — for **bots only**. Use `xwl @user` to whitelist a user.")
    if not member.bot:
        return await ctx.reply(
            f"**{member}** is not a bot. Use `xwl @user` to whitelist users."
        )

    wl_bots = get_wl_bots(ctx.guild.id)

    if member.id in wl_bots:
        wl_bots.remove(member.id)
        save_whitelist()
        save_whitelist_txt()
        embed = discord.Embed(
            title="Bot Whitelist Updated",
            description=f"Removed **{member}** from the bot whitelist.",
            color=0x010101
        )
    else:
        wl_bots.add(member.id)
        save_whitelist()
        save_whitelist_txt()
        embed = discord.Embed(
            title="Bot Whitelist Updated",
            description=f"Added **{member}** to the bot whitelist.",
            color=0x010101
        )

    await ctx.reply(embed=embed)

@wlbot_cmd.error
async def wlbot_error(ctx, error):
    if isinstance(error, commands.MemberNotFound):
        await ctx.reply("Could not find that bot. Make sure to @mention it correctly.")


# ─── xshowlist ────────────────────────────────────────────────────────────────
@bot.command(name="showlist")
@commands.has_permissions(administrator=True)
async def showlist(ctx):
    wl_users = get_wl_users(ctx.guild.id)
    wl_bots  = get_wl_bots(ctx.guild.id)

    user_lines = []
    for uid in wl_users:
        member = ctx.guild.get_member(uid)
        if member is None:
            try:
                member = await ctx.guild.fetch_member(uid)
            except Exception:
                user_lines.append(f"`{uid}` *(not in server)*")
                continue
        user_lines.append(f"<@{member.id}> — `{member}` (`{member.id}`)")

    bot_lines = []
    for uid in wl_bots:
        member = ctx.guild.get_member(uid)
        if member is None:
            try:
                member = await ctx.guild.fetch_member(uid)
            except Exception:
                bot_lines.append(f"`{uid}` *(not in server)*")
                continue
        bot_lines.append(f"<@{member.id}> — `{member}` (`{member.id}`)")

    embed = discord.Embed(
        title="XRK COMMANDS — Whitelist",
        color=0x010101
    )

    embed.add_field(
        name="Whitelisted Users",
        value="\n".join(user_lines) if user_lines else "*No whitelisted users.*",
        inline=False
    )
    embed.add_field(
        name="Whitelisted Bots",
        value="\n".join(bot_lines) if bot_lines else "*No whitelisted bots.*",
        inline=False
    )
    await ctx.reply(embed=embed)

@showlist.error
async def showlist_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.reply("You need the **Administrator** permission to use this command.")


# ─── xhelpadmin ───────────────────────────────────────────────────────────────
@bot.command(name="helpadmin")
async def help_admin(ctx):
    wl = get_wl(ctx.guild.id)
    if ctx.author.id != ctx.guild.owner_id and ctx.author.id not in wl:
        return await ctx.reply("You are not whitelisted to use this command.")
    embed = discord.Embed(
        title="XRK COMMANDS — Admin Panel",
        description=(
            "**ADMIN & OWNER CONTROL CENTER**\n"
            "*All commands use the* `x` *prefix.*"
        ),
        color=0x010101
    )

    embed.add_field(
        name="Moderation",
        value=(
            "`xpurge <amount>` — Delete 1–100 messages\n"
            "`xlock [#channel]` — Lock a channel (blocks @everyone messages)\n"
            "`xunlock [#channel]` — Unlock a channel\n"
            "`xping` — Check bot latency\n"
            "`xrping @user` — Ping a specific user"
        ),
        inline=False
    )

    embed.add_field(
        name="Whitelist",
        value=(
            "`xwl @user` — Add/remove a **user** from the whitelist *(users only)*\n"
            "`xwlbot @bot` — Add/remove a **bot** from the whitelist *(bots only)*\n"
            "`xshowlist` — View all whitelisted users and bots separately"
        ),
        inline=False
    )

    embed.add_field(
        name="Anti-Nuke Protections",
        value=(
            "**Channel Protection**\n"
            "› Channel Create — auto-deleted + attacker banned\n"
            "› Channel Delete — attacker banned + **channel auto-restored**\n"
            "› Channel Rename — auto-reverted + attacker banned\n\n"
            "**Server Protection**\n"
            "› Server Name change — auto-reverted + attacker banned\n"
            "› Server Icon change — auto-reverted + attacker banned\n"
            "› Server Banner change — auto-reverted + attacker banned\n"
            "› Server Description change — auto-reverted + attacker banned\n"
            "› General server setting edit — attacker banned\n\n"
            "**Role & Emoji Protection**\n"
            "› Role update — attacker banned\n"
            "› Emoji delete — attacker banned\n\n"
            "**Webhook Protection**\n"
            "› Unauthorized webhook creation — instant ban + all webhooks deleted\n"
            "› Webhook spam messages — instant ban + purge + all webhooks deleted\n\n"
            "**Member Protection**\n"
            "› Unauthorized bot add — adder banned + bot banned\n"
            "› Mass Kick (2+ kicks) — attacker banned\n"
            "› Mass Ban (2+ bans) — attacker banned"
        ),
        inline=False
    )

    embed.add_field(
        name="Bot Stacker",
        value=(
            "`xspawnall [channel_id]` — Spawn ALL token bots into a VC at the same time\n"
            "`xdespawn` — Disconnect all token bots from VC"
        ),
        inline=False
    )

    embed.add_field(
        name="Notes",
        value=(
            "• Whitelisted users/bots and the **server owner** bypass ALL protections.\n"
            "• Use `xwl @user` for trusted admins, `xwlbot @bot` for trusted bots.\n"
            "• All blocked actions are logged to the designated log channel.\n"
            "• Mass channel deletes (nuke) are fully restored automatically — categories first, then channels."
        ),
        inline=False
    )

    await ctx.reply(embed=embed)

@help_admin.error
async def helpadmin_error(ctx, error):
    pass


# ─── xlock ────────────────────────────────────────────────────────────────────
@bot.command(name="lock")
@commands.has_permissions(manage_channels=True)
async def lock(ctx, channel: discord.TextChannel = None):
    channel = channel or ctx.channel
    overwrite = channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = False
    await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
    embed = discord.Embed(
        title="Channel Locked",
        color=0x010101
    )
    await ctx.reply(embed=embed)

@lock.error
async def lock_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.reply("You need the **Manage Channels** permission to use this command.")


# ─── xunlock ──────────────────────────────────────────────────────────────────
@bot.command(name="unlock")
@commands.has_permissions(manage_channels=True)
async def unlock(ctx, channel: discord.TextChannel = None):
    channel = channel or ctx.channel
    overwrite = channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = None
    await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
    embed = discord.Embed(
        title="Channel Unlocked",
        color=0x010101
    )
    await ctx.reply(embed=embed)

@unlock.error
async def unlock_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.reply("You need the **Manage Channels** permission to use this command.")


# ─── xping ────────────────────────────────────────────────────────────────────
@bot.command(name="ping")
async def ping(ctx):
    latency = round(bot.latency * 1000)
    embed = discord.Embed(
        title="Ping!",
        description=f"Ping! Latency: **{latency}ms**",
        color=0x010101
    )
    await ctx.reply(embed=embed)


# ─── xrping ───────────────────────────────────────────────────────────────────
@bot.command(name="rping")
async def rping(ctx, member: discord.Member = None):
    if member is None:
        return await ctx.reply("Usage: `xrping @user`")
    await ctx.reply(f"Hey {member.mention}! You've been pinged by {ctx.author.mention}!")

@rping.error
async def rping_error(ctx, error):
    if isinstance(error, commands.MemberNotFound):
        await ctx.reply("Could not find that user. Make sure to @mention them correctly.")


# ─── SPAWN HELPER ─────────────────────────────────────────────────────────────
async def _connect_stacker_to_channel(stacker, guild_id: int, channel):
    try:
        stacker_guild = stacker.get_guild(guild_id)
        if not stacker_guild:
            return False
        stacker_channel = stacker_guild.get_channel(channel.id)
        if not stacker_channel:
            return False
        existing_vc = None
        for v in stacker.voice_clients:
            if v.guild.id == guild_id:
                existing_vc = v
                break
        if existing_vc:
            await existing_vc.move_to(stacker_channel)
        else:
            await stacker_channel.connect(timeout=10.0, reconnect=True)
        clog(stacker.user.name, f"Joined: {channel.name}", Colors.CYAN)
        return True
    except Exception as e:
        clog(stacker.user.name if stacker.user else "Unknown", f"Spawn error: {e}", Colors.RED)
        return False


async def _resolve_voice_channel(ctx, channel_id):
    if channel_id:
        try:
            ch = ctx.guild.get_channel(channel_id) or await ctx.guild.fetch_channel(channel_id)
            return ch
        except Exception:
            await ctx.reply("Could not find that channel.")
            return None
    elif ctx.author.voice:
        return ctx.author.voice.channel
    return None


# ─── xspawnall ────────────────────────────────────────────────────────────────
@bot.command(name="spawnall")
async def spawnall_cmd(ctx, channel_id: int = None):
    wl = get_wl(ctx.guild.id)
    if ctx.author.id != ctx.guild.owner_id and ctx.author.id not in wl:
        return await ctx.reply("You are not whitelisted to use this command.")

    channel = await _resolve_voice_channel(ctx, channel_id)
    if not channel or not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
        return await ctx.reply("Please join a voice channel or provide a valid voice channel ID.")

    results = await asyncio.gather(
        *[_connect_stacker_to_channel(s, ctx.guild.id, channel) for s in stacker_bots],
        return_exceptions=True
    )
    spawned = sum(1 for r in results if r is True)

    await ctx.reply(f"Spawned **{spawned}** bot(s) into **{channel.name}**.")


# ─── xdespawn ─────────────────────────────────────────────────────────────────
@bot.command(name="despawn")
async def despawn_cmd(ctx):
    wl = get_wl(ctx.guild.id)
    if ctx.author.id != ctx.guild.owner_id and ctx.author.id not in wl:
        return await ctx.reply("You are not whitelisted to use this command.")

    despawned = 0
    for stacker in stacker_bots:
        for v in list(stacker.voice_clients):
            if v.guild.id == ctx.guild.id:
                try:
                    await v.disconnect()
                    clog(stacker.user.name, "Disconnected", Colors.YELLOW)
                    despawned += 1
                except Exception as e:
                    clog(stacker.user.name, f"Despawn error: {e}", Colors.RED)

    await ctx.reply(f"Despawned **{despawned}** bot(s) from voice.")


# ─── STACKER BOT CLASS ────────────────────────────────────────────────────────
class StackerBot(commands.Bot):
    def __init__(self, token):
        intents_s = discord.Intents.default()
        intents_s.message_content = True
        intents_s.voice_states = True

        super().__init__(command_prefix="\x00", intents=intents_s, help_command=None)
        self.token = token

    async def on_ready(self):
        clog(self.user.name, f"Online | {self.user.id}", Colors.GREEN)

    async def on_command_error(self, ctx, error):
        pass


async def start_stacker(token):
    b = StackerBot(token)
    stacker_bots.append(b)
    try:
        await b.start(token)
    except Exception as e:
        print(f"{Colors.RED}Stacker token failed: {token[:10]}... | {e}{Colors.END}")
    finally:
        if b in stacker_bots:
            stacker_bots.remove(b)


# ─── MAIN ─────────────────────────────────────────────────────────────────────
async def main():
    tokens_path = os.path.join(BASE_DIR, "tokens.txt")

    stacker_tokens = []
    if os.path.isfile(tokens_path):
        with open(tokens_path, "r", encoding="utf-8") as f:
            stacker_tokens = [t.strip() for t in f if t.strip() and not t.strip().startswith("#")]
        if stacker_tokens:
            print(f"{Colors.GREEN}Loaded {len(stacker_tokens)} stacker token(s){Colors.END}")
        else:
            print(f"{Colors.YELLOW}tokens.txt is empty — running without stacker bots{Colors.END}")
    else:
        print(f"{Colors.YELLOW}tokens.txt not found — place it next to bot.py, one token per line{Colors.END}")

    tasks = [bot.start("MTUwMTYzODgzMTQ1ODQ4ODQ2Mg.GNDtK2.R6vpWLmw96guxGrSJ-IjYk3CzfzFCyEvBA0AVE")]
    tasks += [start_stacker(t) for t in stacker_tokens]

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        print(f"\n{Colors.RED}[FATAL ERROR] {e}{Colors.END}")
        input("\nPress Enter to close...")
        sys.exit(1)
# ===============================================
# coded by ray

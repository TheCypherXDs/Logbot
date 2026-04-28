import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import aiohttp
from datetime import datetime
from typing import Literal, Optional

class BackupView(discord.ui.View):
    def __init__(self, cog, filename, mode, interaction):
        super().__init__(timeout=60)
        self.cog = cog
        self.filename = filename
        self.mode = mode
        self.interaction = interaction

    @discord.ui.button(label="Подтвердить восстановление", style=discord.ButtonStyle.red)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.interaction.user.id:
            return await interaction.response.send_message("Это не ваше меню.", ephemeral=True)
        self.stop()
        await interaction.response.edit_message(content="🔄 Начинаю процесс восстановления (Импорт)...", view=None)
        await self.cog.run_restore(self.interaction, self.filename, self.mode)

    @discord.ui.button(label="Отмена", style=discord.ButtonStyle.grey)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(content="❌ Восстановление отменено.", view=None)

class BackupCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.backup_dir = "backups"
        if not os.path.exists(self.backup_dir):
            try: os.makedirs(self.backup_dir)
            except: pass

    def log_error(self, error_msg):
        with open("errors.log", "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat()}] {error_msg}\n")

    async def log_backup_action(self, guild, title, description, color=discord.Color.blue()):
        logger = self.bot.get_cog("LoggerCog")
        if logger:
            await logger.send_log(guild, "server", title, description, color)

    @app_commands.command(name="backup_upload", description="Загрузить JSON файл бэкапа")
    @app_commands.default_permissions(administrator=True)
    async def backup_upload(self, interaction: discord.Interaction, attachment: discord.Attachment):
        if not attachment.filename.endswith(".json"):
            return await interaction.response.send_message("❌ Файл должен быть в формате .json", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        try:
            content = await attachment.read()
            data = json.loads(content)
            
            # Валидация структуры
            required_keys = ["name", "roles", "categories", "timestamp"]
            if not all(key in data for key in required_keys):
                return await interaction.followup.send("❌ Некорректная структура бэкапа.")

            filename = f"upload_{interaction.guild.id}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.json"
            filepath = os.path.join(self.backup_dir, filename)
            
            with open(filepath, "wb") as f:
                f.write(content)

            embed = discord.Embed(title="✅ Бэкап загружен", color=discord.Color.green())
            embed.add_field(name="Источник (Сервер)", value=data.get("name", "Неизвестно"), inline=False)
            embed.add_field(name="Дата создания", value=data.get("timestamp", "??"), inline=True)
            embed.add_field(name="Ролей", value=len(data.get("roles", [])), inline=True)
            embed.add_field(name="Категорий", value=len(data.get("categories", [])), inline=True)
            embed.set_footer(text=f"ID файла: {filename}")
            
            await interaction.followup.send(embed=embed)
            await self.log_backup_action(interaction.guild, "📥 Загружен внешний бэкап", f"Файл: `{filename}`\nИсточник: `{data['name']}`")
        except Exception as e:
            self.log_error(f"Upload error: {e}")
            await interaction.followup.send(f"❌ Ошибка при загрузке: {e}")

    @app_commands.command(name="protocol_backup", description="Создать локальный бэкап")
    @app_commands.default_permissions(administrator=True)
    async def protocol_backup(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        try:
            backup_data = {
                "name": guild.name,
                "roles": [],
                "categories": [],
                "timestamp": datetime.now().isoformat()
            }
            # Сохраняем старый ID ролей для маппинга
            for role in sorted(guild.roles, key=lambda r: r.position, reverse=True):
                if role.is_default() or role.managed: continue
                backup_data["roles"].append({
                    "id": role.id,
                    "name": role.name,
                    "color": role.color.value,
                    "permissions": role.permissions.value,
                    "hoist": role.hoist,
                    "mentionable": role.mentionable
                })

            for category in guild.categories:
                cat_data = {"id": category.id, "name": category.name, "position": category.position, "overwrites": {}, "channels": []}
                for target, ov in category.overwrites.items():
                    allow, deny = ov.pair()
                    cat_data["overwrites"][str(target.id)] = {"allow": allow.value, "deny": deny.value, "type": "role" if isinstance(target, discord.Role) else "member"}
                
                for channel in category.channels:
                    chan_data = {"id": channel.id, "name": channel.name, "type": str(channel.type), "position": channel.position, "overwrites": {}}
                    for target, ov in channel.overwrites.items():
                        allow, deny = ov.pair()
                        chan_data["overwrites"][str(target.id)] = {"allow": allow.value, "deny": deny.value, "type": "role" if isinstance(target, discord.Role) else "member"}
                    if isinstance(channel, discord.TextChannel):
                        chan_data.update({"topic": channel.topic, "slowmode": channel.slowmode_delay})
                    cat_data["channels"].append(chan_data)
                backup_data["categories"].append(cat_data)

            filename = f"backup_{guild.id}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.json"
            with open(os.path.join(self.backup_dir, filename), "w", encoding="utf-8") as f:
                json.dump(backup_data, f, indent=4, ensure_ascii=False)

            await interaction.followup.send(f"✅ Бэкап создан: `{filename}`")
        except Exception as e:
            self.log_error(f"Backup error: {e}")
            await interaction.followup.send(f"❌ Ошибка: {e}")

    async def filename_autocomplete(self, interaction: discord.Interaction, current: str):
        if not os.path.exists(self.backup_dir): return []
        files = [f for f in os.listdir(self.backup_dir) if f.endswith(".json")]
        return [app_commands.Choice(name=f, value=f) for f in files if current.lower() in f.lower()][:25]

    @app_commands.command(name="backup_info", description="Информация о бэкапе")
    @app_commands.autocomplete(filename=filename_autocomplete)
    @app_commands.default_permissions(administrator=True)
    async def backup_info(self, interaction: discord.Interaction, filename: str):
        filepath = os.path.join(self.backup_dir, filename)
        if not os.path.exists(filepath): return await interaction.response.send_message("Нет файла.", ephemeral=True)
        try:
            with open(filepath, "r", encoding="utf-8") as f: data = json.load(f)
            embed = discord.Embed(title=f"📋 Инфо: {filename}", color=discord.Color.blue())
            embed.add_field(name="Сервер", value=data.get("name", "??"), inline=False)
            embed.add_field(name="Ролей", value=len(data.get("roles", [])), inline=True)
            embed.add_field(name="Категорий", value=len(data.get("categories", [])), inline=True)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e: await interaction.response.send_message(f"Ошибка: {e}", ephemeral=True)

    @app_commands.command(name="backup_restore", description="Восстановить из файла")
    @app_commands.autocomplete(filename=filename_autocomplete)
    @app_commands.default_permissions(administrator=True)
    async def backup_restore(self, interaction: discord.Interaction, filename: str, mode: Literal['safe', 'overwrite', 'full']):
        filepath = os.path.join(self.backup_dir, filename)
        if not os.path.exists(filepath): return await interaction.response.send_message("Файл не найден.", ephemeral=True)
        view = BackupView(self, filename, mode, interaction)
        await interaction.response.send_message(content=f"⚠️ Восстановить сервер из `{filename}` (Режим: {mode})?", view=view, ephemeral=True)

    async def run_restore(self, interaction, filename, mode):
        guild = interaction.guild
        filepath = os.path.join(self.backup_dir, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            role_mapping = {} # old_id -> new_role_obj
            my_top_role = guild.me.top_role

            # 1. Roles
            for r_data in data["roles"]:
                role = discord.utils.get(guild.roles, name=r_data["name"])
                if not role:
                    try:
                        role = await guild.create_role(name=r_data["name"], color=discord.Color(r_data["color"]), permissions=discord.Permissions(r_data["permissions"]))
                    except: continue
                elif mode == 'overwrite' and role < my_top_role and not role.managed:
                    try: await role.edit(color=discord.Color(r_data["color"]), permissions=discord.Permissions(r_data["permissions"]))
                    except: pass
                role_mapping[str(r_data["id"])] = role

            # 2. Categories & Channels
            for cat_data in data["categories"]:
                category = discord.utils.get(guild.categories, name=cat_data["name"])
                if not category:
                    category = await guild.create_category(name=cat_data["name"])
                
                # Overwrites (Category)
                for old_id, ow_data in cat_data.get("overwrites", {}).items():
                    target = role_mapping.get(old_id)
                    if not target and ow_data["type"] == "member":
                        target = guild.get_member(int(old_id))
                    if target:
                        ow = discord.PermissionOverwrite.from_pair(discord.Permissions(ow_data["allow"]), discord.Permissions(ow_data["deny"]))
                        try: await category.set_permissions(target, overwrite=ow)
                        except: pass

                for chan_data in cat_data["channels"]:
                    channel = discord.utils.get(category.channels, name=chan_data["name"])
                    if not channel:
                        if chan_data["type"] == "text":
                            channel = await category.create_text_channel(name=chan_data["name"], topic=chan_data.get("topic"))
                        elif chan_data["type"] == "voice":
                            channel = await category.create_voice_channel(name=chan_data["name"])
                    
                    if channel:
                        for old_id, ow_data in chan_data.get("overwrites", {}).items():
                            target = role_mapping.get(old_id)
                            if not target and ow_data["type"] == "member":
                                target = guild.get_member(int(old_id))
                            if target:
                                ow = discord.PermissionOverwrite.from_pair(discord.Permissions(ow_data["allow"]), discord.Permissions(ow_data["deny"]))
                                try: await channel.set_permissions(target, overwrite=ow)
                                except: pass

            # 3. Full Mode: Delete extra
            if mode == 'full':
                backup_role_names = [r["name"] for r in data["roles"]]
                for role in guild.roles:
                    if not role.is_default() and not role.managed and role < my_top_role and role.name not in backup_role_names:
                        try: await role.delete()
                        except: pass
                
                backup_chan_names = []
                for cat in data["categories"]: backup_chan_names.extend([c["name"] for c in cat["channels"]])
                for chan in guild.channels:
                    if chan.name not in backup_chan_names and not isinstance(chan, discord.CategoryChannel):
                        try: await chan.delete()
                        except: pass

            await interaction.followup.send("✅ Перенос структуры завершен!")
            await self.log_backup_action(guild, "♻️ Импорт бэкапа", f"Модератор {interaction.user.mention} успешно импортировал структуру из `{filename}`")
        except Exception as e:
            self.log_error(f"Restore error: {e}")
            await interaction.followup.send(f"❌ Ошибка при импорте: {e}")

async def setup(bot):
    await bot.add_cog(BackupCog(bot))

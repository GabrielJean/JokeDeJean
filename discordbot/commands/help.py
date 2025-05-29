import discord
from discord import app_commands
from history import log_command

async def setup(bot):
    @bot.tree.command(name="help", description="Affiche la liste des commandes disponibles")
    async def help_command(interaction: discord.Interaction):
        log_command(interaction.user, "help", {}, guild=interaction.guild)
        embed = discord.Embed(
            title="Aide - Commandes du bot",
            color=0x00bcff,
            description="La plupart des commandes vocales acceptent `voice_channel` (optionnel)."
        )
        embed.add_field(
            name="/joke",
            value="Joue une blague Reddit en vocal.\nParams: voice_channel",
            inline=False)
        embed.add_field(
            name="/jokeqc",
            value="Blague québécoise .mp3.\nParams: voice_channel",
            inline=False)
        embed.add_field(
            name="/penis",
            value="Joue un son spécial.\nParams: voice_channel",
            inline=False)
        embed.add_field(
            name="/say-vc",
            value="Lecture TTS personnalisée.\nParams: message, instructions, sauvegarder_instructions, voice_channel",
            inline=False)
        embed.add_field(
            name="/gpt",
            value="GPT-4o Q&A, réponse lue.\nParams: query, lecture_vocale, prompt, sauvegarder_prompt",
            inline=False
        )
        embed.add_field(
            name="/roast",
            value="Roast fun, accent québécois !\nParams: cible, intensite, details, voice_channel",
            inline=False
        )
        embed.add_field(
            name="/compliment",
            value="Compliment drôle/style québécois.\nParams: cible, details, voice_channel",
            inline=False
        )
        embed.add_field(
            name="/bloque",
            value="Bloque le bot pendant 2h de rejoindre ton salon vocal actuel.",
            inline=False
        )
        embed.add_field(
            name="/debloque",
            value="Débloque le bot de rejoindre ton salon vocal actuel.",
            inline=False
        )
        embed.add_field(
            name="/leave",
            value="Fait quitter le salon vocal au bot.",
            inline=False)
        embed.add_field(
            name="/say-tc",
            value="Affiche le texte dans le salon texte. Param: message",
            inline=False)
        embed.add_field(
            name="/reset-prompts",
            value="Reset les prompts/instructions TTS.",
            inline=False
        )
        embed.add_field(
            name="/history",
            value="Affiche les 15 dernières commandes (éphémère).",
            inline=False
        )
        embed.add_field(
            name="/help",
            value="Affiche cette aide détaillée.",
            inline=False
        )
        embed.set_footer(text="Besoin d’être dans un vocal OU d'utiliser voice_channel=...  Utilisez /bloque pour être tranquille!")
        await interaction.response.send_message(embed=embed, ephemeral=True)
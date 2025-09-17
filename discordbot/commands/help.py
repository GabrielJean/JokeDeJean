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
            inline=False
        )
        embed.add_field(
            name="/jokeqc",
            value="Blague québécoise .mp3.\nParams: voice_channel",
            inline=False
        )
        embed.add_field(
            name="/penis",
            value="Joue un son spécial.\nParams: voice_channel",
            inline=False
        )
        embed.add_field(
            name="/say-vc",
            value="Lecture TTS personnalisée.\nParams: message, instructions, sauvegarder_instructions, voice_channel",
            inline=False
        )
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
            inline=False
        )
        embed.add_field(
            name="/say-tc",
            value="Affiche le texte dans le salon texte. Param: message",
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
        embed.add_field(
            name="/yt",
            value="Joue l'audio d'une vidéo YouTube dans le vocal.\nParams: url, voice_channel, loop",
            inline=False
        )
        embed.add_field(
            name="/ytsearch",
            value="Recherche une vidéo YouTube et joue l'audio dans le vocal.\nParams: query, voice_channel\nUI: permet de choisir la lecture en boucle.",
            inline=False
        )
        embed.add_field(
            name="/suno",
            value="Lit l'audio d'une chanson Suno via un lien (ex: https://suno.com/song/...).\nParams: url, voice_channel, loop",
            inline=False
        )
        embed.add_field(
            name="/skip",
            value="Passe au prochain message TTS en vocal (skip la lecture actuelle).\nParams: voice_channel",
            inline=False
        )
        embed.add_field(
            name="/music",
            value="Joue une catégorie de musique YouTube en rotation aléatoire.\nParams: category, voice_channel (optionnels)\nCatégories dans music_sources.json",
            inline=False
        )
        embed.add_field(
            name="/settings",
            value="Réglages TTS (UI si aucun paramètre).\nParams: target, tts_instructions, reset\nTargets: global | say-vc | roast | compliment",
            inline=False
        )

        embed.set_footer(text="Besoin d’être dans un vocal OU d'utiliser voice_channel=...  Utilisez /bloque pour être tranquille!")

        await interaction.response.send_message(embed=embed, ephemeral=True)
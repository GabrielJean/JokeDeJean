import discord
from discord import app_commands
try:
    from ..history import log_command
except ImportError:  # script fallback
    from history import log_command  # type: ignore
from discord.ext import commands

# Map command names to a short help description; dynamic embed will only show
# commands that are actually registered on the bot instance.
COMMAND_DESCRIPTIONS = {
    "joke": "Joue une blague Reddit en vocal. Params: voice_channel",
    "jokeqc": "Blague québécoise .mp3. Params: voice_channel",
    "penis": "Joue un son spécial. Params: voice_channel",
    "say-vc": "Lecture TTS personnalisée. Params: message, instructions, sauvegarder_instructions, voice_channel",
    "gpt": "GPT-4o Q&A, réponse lue. Params: query, lecture_vocale, prompt, sauvegarder_prompt",
    "roast": "Roast fun, accent québécois ! Params: cible, intensite, details, voice_channel",
    "compliment": "Compliment drôle/style québécois. Params: cible, details, voice_channel",
    "bloque": "Bloque le bot pendant 2h de rejoindre ton salon vocal actuel.",
    "debloque": "Débloque le bot de rejoindre ton salon vocal actuel.",
    "leave": "Fait quitter le salon vocal au bot.",
    "say-tc": "Affiche le texte dans le salon texte. Param: message",
    "history": "Affiche les 15 dernières commandes (éphémère).",
    "yt": "Joue l'audio d'une vidéo YouTube. Params: url, voice_channel, loop",
    "ytsearch": "Recherche une vidéo YouTube et joue l'audio. Params: query, voice_channel",
    "suno": "Lit l'audio d'une chanson Suno (https://suno.com/song/...). Params: url, voice_channel, loop",
    "skip": "Passe au prochain message TTS en vocal (skip actuel). Params: voice_channel",
    "music": "Musique YouTube rotation aléatoire. Params: category, voice_channel",
    "settings": "Réglages TTS (UI si aucun paramètre). Params: target, tts_instructions, reset",
}

async def setup(bot):
    @bot.tree.command(name="help", description="Affiche la liste des commandes disponibles")
    async def help_command(interaction: discord.Interaction):
        log_command(interaction.user, "help", {}, guild=interaction.guild)

        embed = discord.Embed(
            title="Aide - Commandes du bot",
            color=0x00bcff,
            description="La plupart des commandes vocales acceptent `voice_channel` (optionnel)."
        )

        # Determine which slash commands are actually registered.
        tree: discord.app_commands.CommandTree = interaction.client.tree  # type: ignore
        registered = {cmd.name for cmd in tree.walk_commands()}
        # Always show /help first if present
        ordered = ["help"] + sorted(c for c in registered if c != "help")
        for name in ordered:
            desc = COMMAND_DESCRIPTIONS.get(name, "(Pas de description disponible)")
            # Keep each field small; Discord limit 1024
            if len(desc) > 1000:
                desc = desc[:1000] + "…"
            embed.add_field(name=f"/{name}", value=desc, inline=False)

        embed.set_footer(text="Liste filtrée selon les modules chargés pour CE bot.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
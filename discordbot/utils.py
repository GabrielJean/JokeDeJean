import discord

def build_safely_embed_for_sayvc(message, current_instructions, display_name):
    max_overall = 6000
    max_title = 256
    max_footer = 2048
    max_field = 1024
    max_fields = 25
    cuts = []  # texte splitté
    to_split = message or ""
    while to_split:
        cuts.append(to_split[:950])
        to_split = to_split[950:]
    fields = []
    total_chars = 0
    for idx, part in enumerate(cuts[:max_fields]):
        label = "Message" if idx == 0 else f"…suite {idx}"
        value = part
        if len(value) > max_field:
            value = value[:max_field - 3] + "..."
        fields.append((label, value))
        total_chars += len(label) + len(value)
        if total_chars > max_overall:
            break
    embed = discord.Embed(
        title="💬 Texte prononcé en vocal"[:max_title],
        color=0x00bcff,
    )
    if len(message) <= 950 and (len(message) + len(embed.title)) < (max_overall - 128):
        embed.description = message
    for label, value in fields:
        embed.add_field(name=label, value=value, inline=False)
    cut_total = sum(len(x[1]) for x in fields)
    if cut_total < len(message):
        embed.add_field(name="…", value="(Texte coupé : trop long pour Discord embed !)", inline=False)
    if current_instructions:
        val = current_instructions if len(current_instructions) < max_field else (current_instructions[:max_field-3] + "...")
        embed.add_field(name="Style", value=val, inline=False)
    embed.set_footer(text=f"Demandé par {display_name}"[:max_footer])
    return embed

def build_gpt_embed(query, reply, interaction):
    max_overall = 6000
    max_chunk = 950
    max_field = 1024
    max_fields = 25
    max_title = 256
    max_footer = 2048
    reply_cuts = []
    to_split = reply or ""
    while to_split:
        reply_cuts.append(to_split[:max_chunk])
        to_split = to_split[max_chunk:]
    embed = discord.Embed(title="Réponse GPT-4o"[:max_title], color=0x00bcff, description=f"**Q :** {query[:800]}")
    total_chars = len(embed.title or "") + len(embed.description or "")
    for idx, chunk in enumerate(reply_cuts[:max_fields]):
        name = "Réponse" if idx == 0 else f"(suite {idx})"
        field_val = chunk if len(chunk) < max_field else (chunk[:max_field-3] + "...")
        embed.add_field(name=name, value=field_val, inline=False)
        total_chars += len(name) + len(field_val)
        if total_chars > max_overall:
            break
    if sum(len(x) for x in reply_cuts) > max_chunk * max_fields:
        embed.add_field(name="Info", value="(réponse tronquée, trop longue !)", inline=False)
    return embed
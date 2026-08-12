import os
import discord
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_PICKS"))

intents = discord.Intents.default()
client = discord.Client(intents=intents)


@client.event
async def on_ready():
    print(f"Logged in as {client.user}")

    channel = client.get_channel(CHANNEL_ID)

    if channel is None:
        print("Channel not found.")
    else:
        await channel.send("Hello! MLB Model is connected successfully.")

    await client.close()


client.run(TOKEN)

import discord
from discord import app_commands
from discord.ui import View, Button
import asyncio
import os
import whisper
from datetime import datetime
from discord.ext import voice_recv

TOKEN = ''

discord.opus.load_opus("/opt/homebrew/lib/libopus.dylib")

class MyClient(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.messages = True
        intents.voice_states = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()  # Sync commands

    async def on_ready(self):
        print(f'Logged in as {self.user}')


client = MyClient()
process = None
model = whisper.load_model("turbo")

recording_sessions = {}


# RecordingSession class
class RecordingSession:
    def __init__(self, guild_id: int, user_id: int):
        self.guild_id = guild_id
        self.user_id = user_id
        self.filename = self._generate_filename()
        self.sink = None
        self.datetime = datetime.now()

    def _generate_filename(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"recording_g{self.guild_id}_u{self.user_id}_{timestamp}.wav"

    def get_start_time(self):
        return self.datetime

    def start(self, voice_client):
        if self.sink is None:
            if not os.path.exists("recordings"):
                os.makedirs("recordings")
            file_path = os.path.join("recordings", self.filename)
            self.sink = voice_recv.WaveSink(file_path)
            voice_client.listen(self.sink)

    def stop(self, voice_client):
        if self.sink:
            voice_client.stop_listening()
        return self.filename

    def cleanup(self):
        self.sink = None


class RecordView(View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.blurple, custom_id="candidature_button", row=0)
    async def stop_recording(self, interaction: discord.Interaction, button: Button):
        self.clear_items()
        await interaction.message.edit(view=self)
        await end(interaction)


# Join voice channel
@client.tree.command(name="join", description="Bot joins your voice channel")
async def join(interaction: discord.Interaction):
    if interaction.user.voice:
        channel = interaction.user.voice.channel
        await interaction.response.defer()
        await channel.connect(cls=voice_recv.VoiceRecvClient)
        await interaction.followup.send("Bot has joined the voice channel!")
        await record(interaction)
    else:
        await interaction.response.send_message("You're not in a voice channel!")


# Record Audio Using FFmpeg
#@client.tree.command(name="record", description="Start recording audio")
async def record(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    user_id = interaction.user.id
    vc = interaction.guild.voice_client
    if vc and isinstance(vc, voice_recv.VoiceRecvClient):
        if guild_id in recording_sessions:
            await interaction.response.send_message("A recording is already in progress in this server!")
            return
        session = RecordingSession(guild_id, user_id)
        session.start(vc)
        recording_sessions[guild_id] = session
        await interaction.followup.send(
            f"Recording started for <@{user_id}>! Saving to `{session.filename}`.", view=RecordView()
        )
    else:
        await interaction.response.send_message("Bot is not connected to a voice channel!")


# Stop Recording
@client.tree.command(name="stop", description="Stop recording audio")
async def stop(interaction: discord.Interaction):
    await end(interaction)


async def end(interaction):
    guild_id = interaction.guild.id
    vc = interaction.guild.voice_client
    if vc and guild_id in recording_sessions:
        await interaction.response.defer()
        session = recording_sessions.pop(guild_id)  # Retrieve and remove the session
        start = session.get_start_time()
        now = datetime.now()
        diff = now - start
        await asyncio.sleep(diff.total_seconds() + 1)
        filename = session.stop(vc)
        session.cleanup()
        await interaction.followup.send("Transcribing the recording...")
        text = await transcribe(filename)
        if len(text) > 2000:
            filepath = os.path.join("recordings", "transcription.txt")
            with open(filepath, "w") as file:
                file.write(text)
            await interaction.followup.send(file=discord.File(filepath))
        else:
            await interaction.followup.send(f"Transcription:\n{text}")
        await vc.disconnect()
        #await interaction.response.send_message("Bot has left the voice channel.")
    else:
        await interaction.response.send_message("No recording in progress.")


# Leave Voice Channel
@client.tree.command(name="leave", description="Bot leaves the voice channel")
async def leave(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc:
        await vc.disconnect()
        await interaction.response.send_message("Bot has left the voice channel.")
    else:
        await interaction.response.send_message("Bot is not connected to any voice channel.")


async def transcribe(filename):
    result = model.transcribe(os.path.join("recordings", filename))
    return result["text"]


@client.event
async def on_ready():
    print(f'We have logged in as {client.user}')

client.run(TOKEN)

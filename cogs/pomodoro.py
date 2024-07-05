# Copyright © Krypton 2019-2023 - https://github.com/kkrypt0nn (https://krypton.ninja)

# Version: 6.1.0

# Modified by Y.Ozaki - https://github.com/mttk1528


import asyncio
import math
import os
import subprocess
from collections import defaultdict
from datetime import datetime

import discord
from discord.ext import commands
from discord.ext.commands import Context


class Pomodoro(commands.Cog, name="pomodoro"):
    def __init__(self, bot) -> None:
        """
        Initialize the Pomodoro cog.

        :param bot: The Discord bot instance.
        """
        self.bot = bot
        # Server-specific dictionaries for managing multiple servers
        self.server_to_voice_client = defaultdict(lambda: None)
        self.server_to_if_connected = defaultdict(lambda: False)
        self.server_to_text_channel = defaultdict(lambda: None)
        self.server_to_expected_disconnection = defaultdict(lambda: None)

        self.server_to_pomodoro_count = defaultdict(lambda: 0)
        # Pomodoro timer management
        self.server_to_pomodoro_timer = defaultdict(lambda: None)  # type: dict[int, tuple[datetime, int, str]]
        self.server_to_pomodoro_status = defaultdict(lambda: False)

        # Default Pomodoro settings
        self.server_to_pomodoro_work_time = defaultdict(lambda: 25)
        self.server_to_pomodoro_short_break_time = defaultdict(lambda: 5)
        self.server_to_pomodoro_long_break_time = defaultdict(lambda: 15)
        self.server_to_pomodoro_long_break_interval = defaultdict(lambda: 4)

        # Start the Pomodoro loop
        self.bot.loop.create_task(self.pomodoro_loop())

        self.audio_path = f"{os.path.realpath(os.path.dirname(__file__))}/audio.mp3"

    def format_time(self, minutes: float) -> str:
        """
        Convert minutes to mm:ss format.

        :param minutes: Time in minutes (can be float)
        :return: Formatted time string in mm:ss format
        """
        total_seconds = math.floor(minutes * 60)
        minutes, seconds = divmod(total_seconds, 60)
        return f"{minutes:02d}:{seconds:02d}"

    async def pomodoro_loop(self):
        while True:
            for guild_id, status in self.server_to_pomodoro_status.items():
                if status:
                    timer_data = self.server_to_pomodoro_timer[guild_id]
                    if timer_data:
                        start_time, pomodoro_count, current_phase = timer_data
                        elapsed_time = (datetime.now() - start_time).total_seconds() / 60

                        if current_phase == "work":
                            if elapsed_time >= self.server_to_pomodoro_work_time[guild_id]:
                                await self.start_break(guild_id)
                        elif current_phase == "break":
                            if pomodoro_count % self.server_to_pomodoro_long_break_interval[guild_id] == 0:
                                break_time = self.server_to_pomodoro_long_break_time[guild_id]
                            else:
                                break_time = self.server_to_pomodoro_short_break_time[guild_id]

                            if elapsed_time >= break_time:
                                await self.start_work(guild_id)

            await asyncio.sleep(1)

    async def start_break(self, guild_id: int):
        self.server_to_pomodoro_count[guild_id] += 1
        pomodoro_count = self.server_to_pomodoro_count[guild_id]

        if pomodoro_count % self.server_to_pomodoro_long_break_interval[guild_id] == 0:
            break_type = "休憩(長)"
            break_time = self.server_to_pomodoro_long_break_time[guild_id]
        else:
            break_type = "休憩(短)"
            break_time = self.server_to_pomodoro_short_break_time[guild_id]

        self.server_to_pomodoro_timer[guild_id] = (datetime.now(), pomodoro_count, "break")

        channel = self.server_to_text_channel[guild_id]
        break_time_formatted = self.format_time(break_time)
        await channel.send(f"作業セッション完了！{break_type}の時間です（{break_time_formatted}）")

        await self.play_sound(guild_id, self.audio_path)

    async def start_work(self, guild_id: int):
        timer_data = self.server_to_pomodoro_timer[guild_id]
        if timer_data:
            _, pomodoro_count, _ = timer_data
            self.server_to_pomodoro_timer[guild_id] = (datetime.now(), pomodoro_count, "work")

        channel = self.server_to_text_channel[guild_id]
        work_time = self.server_to_pomodoro_work_time[guild_id]
        work_time_formatted = self.format_time(work_time)
        await channel.send(f"休憩時間終了！作業に戻りましょう！（{work_time_formatted}）")

        await self.play_sound(guild_id, self.audio_path)

    async def play_sound(self, guild_id: int, sound_file: str):
        """
        Play a sound in the voice channel.

        :param guild_id: The ID of the Discord server.
        :param sound_file: The filename of the sound to play.
        """
        voice_client = self.server_to_voice_client[guild_id]
        if voice_client and voice_client.is_connected():
            ffmpeg_options = {
                'options': '-vn -ac 2',
                'stderr': subprocess.DEVNULL
            }
            source = discord.FFmpegPCMAudio(self.audio_path, **ffmpeg_options)
            voice_client.play(source)

    @commands.hybrid_command(
        name="pomodoro",
        description="ポモドーロタイマーを開始します",
    )
    async def pomodoro(self, context: Context) -> None:
        guild_id = context.guild.id

        if self.server_to_voice_client[guild_id] is None or not self.server_to_voice_client[guild_id].is_connected():
            join_success = await self.__join(context)
            if not join_success:
                embed = discord.Embed(
                    description="このコマンドを使用するには、ボイスチャンネルに参加している必要があります。", color=0xE02B2B
                )
                await context.reply(embed=embed)
                return

        if self.server_to_pomodoro_status[guild_id] is True:
            embed = discord.Embed(
                description="ポモドーロセッションはすでに進行中です。", color=0xE02B2B
            )
            await context.reply(embed=embed)
            return

        self.server_to_pomodoro_status[guild_id] = True
        self.server_to_pomodoro_timer[guild_id] = (datetime.now(), 0, "work")
        self.server_to_pomodoro_count[guild_id] = 0  # ポモドーロカウントをリセット

        work_time_formatted = self.format_time(self.server_to_pomodoro_work_time[guild_id])
        embed = discord.Embed(
            description=f"ポモドーロタイマーを開始しました。作業時間: {work_time_formatted}", color=0x00FF00
        )
        await context.reply(embed=embed)

    @commands.hybrid_command(
        name="pomoend",
        description="現在のポモドーロセッションを終了します。",
    )
    async def pomoend(self, context: Context) -> None:
        guild_id = context.guild.id

        if self.server_to_pomodoro_status[guild_id] is False:
            embed = discord.Embed(
                description="終了するアクティブなポモドーロセッションがありません。", color=0xE02B2B
            )
            await context.reply(embed=embed)
            return

        pomodoro_timer = self.server_to_pomodoro_timer[guild_id]
        self.server_to_pomodoro_status[guild_id] = False

        if pomodoro_timer:
            start_time, pomodoro_count, _ = pomodoro_timer
            elapsed_time = datetime.now() - start_time
            elapsed_time_str = self.format_time(elapsed_time.total_seconds() / 60)

            embed = discord.Embed(
                description=f"ポモドーロセッションが終了しました。\n合計時間: {elapsed_time_str}\n完了したポモドーロ: {pomodoro_count}", color=0x00FF00
            )
        else:
            embed = discord.Embed(
                description="ポモドーロセッションが終了しました。詳細な情報は利用できません。", color=0x00FF00
            )

        await context.reply(embed=embed)

        self.server_to_pomodoro_count[guild_id] = 0
        self.server_to_pomodoro_timer[guild_id] = None

    @commands.hybrid_command(
        name="pomostatus",
        description="現在のポモドーロセッションの状況を表示します。",
    )
    async def pomostatus(self, context: Context) -> None:
        guild_id = context.guild.id

        if self.server_to_pomodoro_status[guild_id] is False:
            embed = discord.Embed(
                description="アクティブなポモドーロセッションはありません。", color=0xE02B2B
            )
            await context.reply(embed=embed)
            return

        timer_data = self.server_to_pomodoro_timer[guild_id]
        if timer_data:
            start_time, pomodoro_count, current_phase = timer_data
            elapsed_time = (datetime.now() - start_time).total_seconds() / 60

            if current_phase == "work":
                time_left = self.server_to_pomodoro_work_time[guild_id] - elapsed_time
                phase_name = "作業"
            else:
                if pomodoro_count % self.server_to_pomodoro_long_break_interval[guild_id] == 0:
                    break_time = self.server_to_pomodoro_long_break_time[guild_id]
                else:
                    break_time = self.server_to_pomodoro_short_break_time[guild_id]
                time_left = break_time - elapsed_time
                phase_name = "休憩"

            time_left_formatted = self.format_time(time_left)

            embed = discord.Embed(
                title="現在の状況",
                description=f"現在のフェーズ: {phase_name}\n"
                            f"残り時間: {time_left_formatted}\n"
                            f"完了済みポモドーロ: {pomodoro_count}",
                color=0x00FF00
            )
            await context.reply(embed=embed)

    @commands.hybrid_command(
        name="setting",
        description="ポモドーロタイマーの設定をカスタマイズします",
    )
    async def setting(
        self, context: Context,
        work_time: str, short_break_time: str,
        long_break_time: str, long_break_interval: str
    ) -> None:
        guild_id = context.guild.id

        try:
            work_time = float(work_time)
            short_break_time = float(short_break_time)
            long_break_time = float(long_break_time)
            long_break_interval = int(long_break_interval)

            if work_time <= 0 or short_break_time <= 0 or long_break_time <= 0 or long_break_interval <= 0:
                raise ValueError("すべての値は正の数でなければなりません。")

            if work_time > 120 or short_break_time > 30 or long_break_time > 60:
                raise ValueError("時間設定が長すぎます。適切な範囲内で設定してください。")

        except ValueError as e:
            embed = discord.Embed(
                title="設定エラー",
                description=f"無効な入力: {str(e)}",
                color=0xE02B2B
            )
            await context.reply(embed=embed)
            return

        self.server_to_pomodoro_work_time[guild_id] = work_time
        self.server_to_pomodoro_short_break_time[guild_id] = short_break_time
        self.server_to_pomodoro_long_break_time[guild_id] = long_break_time
        self.server_to_pomodoro_long_break_interval[guild_id] = long_break_interval

        settings = f"作業時間: {self.format_time(work_time)}\n" \
                   f"休憩(短): {self.format_time(short_break_time)}\n" \
                   f"休憩(長): {self.format_time(long_break_time)}\n" \
                   f"長休憩までの間隔: {long_break_interval} ポモドーロ"

        embed = discord.Embed(
            title="設定を更新しました",
            description=settings,
            color=0x00FF00
        )
        await context.reply(embed=embed)

    async def __join(self, context: Context) -> bool:
        user = context.author

        if user.voice is None:
            return False

        if self.server_to_voice_client[context.guild.id] is not None:
            if self.server_to_voice_client[context.guild.id].is_connected():
                self.server_to_expected_disconnection[context.guild.id] = True
                await self.server_to_voice_client[context.guild.id].disconnect()
                self.server_to_voice_client[context.guild.id] = None

        self.server_to_text_channel[context.guild.id] = context.channel
        self.server_to_voice_client[context.guild.id] = await user.voice.channel.connect()
        self.server_to_if_connected[context.guild.id] = True

        return True

    @commands.hybrid_command(
        name="disconnect",
        description="ボットをボイスチャンネルから切断します。",
    )
    async def disconnect(self, context: Context) -> None:
        voice_client = self.server_to_voice_client[context.guild.id]
        if voice_client is None:
            embed = discord.Embed(
                description="ポモドーロボットはボイスチャンネルに接続されていません。", color=0xE02B2B
            )
            await context.reply(embed=embed)
            return
        else:
            embed = discord.Embed(
                description=f"{voice_client.channel.mention}から退出します 👋", color=0xE02B2B
            )
            await context.send(embed=embed)
            self.server_to_expected_disconnection[context.guild.id] = True
            await voice_client.disconnect()

            self.server_to_voice_client[context.guild.id] = None
            self.server_to_if_connected[context.guild.id] = False
            self.server_to_text_channel[context.guild.id] = None

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after) -> None:
        if member.id == self.bot.user.id:
            guild_id = member.guild.id
            if before.channel is not None and after.channel is None:
                if self.server_to_expected_disconnection[guild_id]:
                    self.bot.logger.info("通常の切断を検出しました。")
                    self.server_to_expected_disconnection[guild_id] = False
                else:
                    self.bot.logger.info("予期せぬ切断を検出しました。再接続を試みます。")
                    try:
                        self.server_to_voice_client[guild_id] = await before.channel.connect()
                        self.bot.logger.info("ボイスチャンネルに正常に再接続しました。")
                    except Exception as e:
                        self.bot.logger.error(f"ボイスチャンネルへの再接続に失敗しました: {str(e)}")


async def setup(bot) -> None:
    await bot.add_cog(Pomodoro(bot))

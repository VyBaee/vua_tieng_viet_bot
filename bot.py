import discord
from discord.ext import commands
import json
import asyncio
import os
import random
import aiohttp
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

CHANNEL_FILE = "channel.json"

# Link file từ ngữ online (.txt) - mỗi dòng là 1 từ 2 âm tiết
WORD_FILE_PATH = "D:/TeraBoxDownload/Backup/Tuna/Study/Coding/Bot Discord/vua_tieng_viet/words_2_syllables.txt"

# Lấy kênh mặc định từ file nếu có
default_channel_id = None
if os.path.exists(CHANNEL_FILE):
    with open(CHANNEL_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        default_channel_id = data.get("id")

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ===== Biến trạng thái game =====
game_active = False  # Kiểm soát game đang chạy hay không

# ===== Hàm hỗ trợ =====
async def fetch_words():
    """Lấy danh sách từ từ file local"""
    if os.path.exists(WORD_FILE_PATH):
        with open(WORD_FILE_PATH, "r", encoding="utf-8") as f:
            words = [line.strip() for line in f.readlines() if line.strip()]
        return words
    else:
        print(f"❌ Không tìm thấy file {WORD_FILE_PATH}")
        return []

def shuffle_word(word: str):
    """Đảo vị trí chữ cái, đảm bảo không trùng với từ gốc"""
    chars = list(word.replace(" ", ""))  # bỏ dấu cách
    shuffled = chars[:]
    while True:
        random.shuffle(shuffled)
        shuffled_word = "".join(shuffled)
        if shuffled_word.lower() != "".join(chars).lower():
            break
    return "/".join(shuffled)

# ===== Lệnh setchannel =====
@bot.command()
@commands.has_permissions(administrator=True)
async def setchannel(ctx):
    global default_channel_id
    default_channel_id = ctx.channel.id
    with open(CHANNEL_FILE, "w", encoding="utf-8") as f:
        json.dump({"id": default_channel_id}, f)
    await ctx.send(f"✅ Đã đặt kênh mặc định là {ctx.channel.mention}")

# ===== Lệnh stop =====
@bot.command()
@commands.has_permissions(administrator=True)
async def stop(ctx):
    global game_active
    if not game_active:
        await ctx.send("⚠️ Không có trò chơi nào đang diễn ra!")
        return
    game_active = False
    await ctx.send("🛑 Đang tổng hợp bảng xếp hạng...")

# ===== Lệnh start =====
@bot.command(name="start")  # giữ lệnh !start, tên hàm khác để tránh xung đột
async def start_cmd(ctx):
    global game_active
    if default_channel_id is None:
        await ctx.send("❌ Chưa có kênh mặc định! Dùng `!setchannel` trước.")
        return
    if ctx.channel.id != default_channel_id:
        await ctx.send(f"⚠️ Trò chơi chỉ được chơi ở {bot.get_channel(default_channel_id).mention}")
        return
    if game_active:
        await ctx.send("⚠️ Trò chơi đang diễn ra!")
        return

    words = await fetch_words()
    if not words:
        await ctx.send("❌ Không thể tải danh sách từ! Kiểm tra link hoặc file online.")
        return

    game_active = True
    await start_game(ctx.channel, words)

# ===== Hàm chạy game =====
async def start_game(channel, words):
    global game_active
    consecutive_fails = 0
    scores = {}
    question_count = 0  # Số câu đã chơi

    intro_embed = discord.Embed(
        title="🎯 VUA TIẾNG VIỆT 🎯",
        description=(
            "Luật chơi:\n"
            "- Bot sẽ đưa ra một từ **2 âm tiết** đã bị xáo trộn chữ cái (ngăn cách bằng /)\n"
            "- Bạn có 60 giây để đoán từ gốc\n"
            "- Ai trả lời đúng **đầu tiên** sẽ +1 điểm\n"
            "- Nếu **3 câu liên tiếp** không ai đúng → trò chơi kết thúc\n"
            "- Quản trị viên có thể dùng `!stop` để dừng ngay và vẫn hiện bảng xếp hạng"
        ),
        color=discord.Color.gold()
    )
    await channel.send(embed=intro_embed)
    await asyncio.sleep(2)

    while consecutive_fails < 3 and game_active:
        question_count += 1
        original_word = random.choice(words)
        scrambled = shuffle_word(original_word)

        # Thông tin hiển thị thêm
        char_count = len(original_word.replace(" ", ""))  # số ký tự (không tính khoảng trắng)

        time_left = 60
        question_embed = discord.Embed(
            title=f"📝 Câu hỏi mới!",
            description=(
                "**Từ bị xáo trộn:**\n"
                f"```{scrambled}``` • {char_count} ký tự\n"
                f"⏳ Thời gian còn lại: **{time_left} giây**"
            ),
            color=discord.Color.blue()
        )
        question_embed.set_footer(text=f"Câu #{question_count}.")
        question_embed.add_field(name="Độ dài", value=f"{char_count} ký tự", inline=True)

        question_message = await channel.send(embed=question_embed)

        winner_id = None  # Lưu ID người thắng câu này

        def check(m):
            return m.channel == channel and not m.author.bot

        while time_left > 0 and game_active:
            try:
                msg = await bot.wait_for("message", timeout=1.0, check=check)

                if msg.content.strip().lower() == original_word.lower():
                    if winner_id is None:  # Chưa ai thắng câu này
                        winner_id = msg.author.id
                        scores[winner_id] = scores.get(winner_id, 0) + 1
                        await channel.send(f"✅ {msg.author.mention} là người trả lời đúng đầu tiên! (+1 điểm)")
                        break  # Dừng câu hỏi hiện tại, sang câu mới
                else:
                    try:
                        await msg.add_reaction("❌")  # phản hồi sai
                    except discord.HTTPException:
                        pass
            except asyncio.TimeoutError:
                pass

            time_left -= 1
            # Cập nhật đếm ngược
            question_embed.description = (
                "**Từ bị xáo trộn:**\n"
                f"```{scrambled}```\n"
                f"⏳ Thời gian còn lại: **{time_left} giây**"
            )
            await question_message.edit(embed=question_embed)

        if not game_active:
            # Bị dừng bởi !stop → thoát vòng while lớn để in leaderboard
            break

        if winner_id is not None:
            await channel.send(f"⏱ Hết giờ! Đáp án là **{original_word}**")
            consecutive_fails = 0
        else:
            await channel.send(f"⏱ Hết giờ! Không ai trả lời đúng. Đáp án là **{original_word}**")
            consecutive_fails += 1

    # Bảng xếp hạng
    if scores:
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        leaderboard = "\n".join([f"<@{uid}>: **{score}** điểm" for uid, score in sorted_scores])
    else:
        leaderboard = "Không có ai ghi điểm."
        
    # Thông báo lý do kết thúc
    if not game_active:
        await channel.send("🏁 Trò chơi đã được dừng bởi quản trị viên. Trò chơi kết thúc!")
    else:
        await channel.send("🛑 Đang tổng hợp bảng xếp hạng...")
        await channel.send("🏁 Sau 3 lần liên tiếp không có ai trả lời đúng. Trò chơi kết thúc!")

    leaderboard_embed = discord.Embed(
        title="🏆 Bảng xếp hạng",
        description=leaderboard,
        color=discord.Color.green()
    )
    await channel.send(embed=leaderboard_embed)

    game_active = False

bot.run(TOKEN)

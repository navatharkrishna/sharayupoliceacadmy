#!/usr/bin/env python3
"""
Telegram Quiz Bot — Bulk Upload All Questions from CSV to Group/Channel
"""

import asyncio
import csv
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
import os

from telegram import Update
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, ContextTypes
)

# ---------------- CONFIG ----------------
CSV_PATH = Path("data/quiz.csv")  # Relative path
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")  # Load from GitHub Secrets
BATCH_SIZE = 100
DELAY_BETWEEN_POLLS = 2
DELAY_BETWEEN_BATCHES = 10
CHANNEL_ID = os.environ.get("TELEGRAM_CHANNELID")  # e.g., "-1002796750436"
# -----------------------------------------

if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is missing! Set it in GitHub Secrets.")

if not CHANNEL_ID:
    raise RuntimeError("TELEGRAM_CHANNELID is missing! Set it in GitHub Secrets.")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logging.info(f"Loaded CHANNEL_ID: {CHANNEL_ID}")

@dataclass
class QuizItem:
    question_no: str
    question: str
    options: List[str]
    correct_option_id: int
    description: Optional[str] = None
    reference: Optional[str] = None

class QuestionBank:
    def __init__(self) -> None:
        self.items: List[QuizItem] = []

    def load_csv(self, path: Path) -> int:
        if not path.exists():
            raise FileNotFoundError(f"CSV file not found: {path}")

        with path.open(encoding="utf-8") as f:
            reader = csv.DictReader(f)
            required = {
                "question_no", "question", "option1", "option2",
                "option3", "option4", "correct_answer", "description", "reference"
            }
            if not required.issubset(set(reader.fieldnames or [])):
                raise ValueError(f"CSV missing columns. Required: {required}. Found: {reader.fieldnames}")

            for row in reader:
                if not row.get("question"):
                    continue

                options = [
                    (row.get("option1") or "").strip(),
                    (row.get("option2") or "").strip(),
                    (row.get("option3") or "").strip(),
                    (row.get("option4") or "").strip()
                ]
                options = [opt for opt in options if opt]

                correct_raw = (row.get("correct_answer") or "").strip()

                # Default to 0 if no exact match found
                cid = None
                if correct_raw.isdigit():
                    cid = int(correct_raw) - 1
                elif correct_raw in options:
                    cid = options.index(correct_raw)
                else:
                    normalized = [opt.strip() for opt in options]
                    if correct_raw.strip() in normalized:
                        cid = normalized.index(correct_raw.strip())
                    else:
                        logging.warning(
                            f"⚠️ Correct answer mismatch at Q{row.get('question_no')}: "
                            f"'{correct_raw}' not in {options}. Defaulting to first option."
                        )
                        cid = 0  # Fallback

                self.items.append(
                    QuizItem(
                        question_no=row.get("question_no", ""),
                        question=row["question"],
                        options=options,
                        correct_option_id=cid if 0 <= cid < len(options) else 0,
                        description=row.get("description") or None,
                        reference=row.get("reference") or None
                    )
                )
        return len(self.items)

QBANK = QuestionBank()
loaded_count = QBANK.load_csv(CSV_PATH)
logging.info(f"Loaded {loaded_count} questions from CSV")

HELP_TEXT = (
    "नमस्कार! मी Bulk Quiz Bot आहे.\n\n"
    "Commands:\n"
    "/uploadall — CSV मधील सर्व प्रश्न (चॅटमध्ये) पाठवा\n"
    "/uploadchannel — सर्व प्रश्न चॅनेलवर पाठवा\n"
    "/count — एकूण प्रश्न संख्या दाखवा"
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"👋 Hi {update.effective_user.first_name or ''}!\n" + HELP_TEXT)

async def count(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"📚 Total questions loaded: {len(QBANK.items)}")

async def send_quiz_batch(context: ContextTypes.DEFAULT_TYPE, chat_id: str, to_channel: bool = False):
    """Send quiz batch to chat or channel."""
    for start_idx in range(0, len(QBANK.items), BATCH_SIZE):
        batch = QBANK.items[start_idx:start_idx + BATCH_SIZE]

        for idx, item in enumerate(batch, 1):
            try:
                poll_question = f"{item.question_no}) {item.question}"
                if item.reference:
                    poll_question += f"\n{item.reference}"

                await context.bot.send_poll(
                    chat_id=chat_id,
                    question=poll_question[:300],
                    options=item.options[:10],
                    type="quiz",
                    correct_option_id=item.correct_option_id,
                    explanation=(item.description or "")[:200],
                    is_anonymous=True  # Always anonymous for channels
                )
                await asyncio.sleep(DELAY_BETWEEN_POLLS)
            except Exception as e:
                logging.error(f"Failed to send question {start_idx + idx}: {e}")

        await asyncio.sleep(DELAY_BETWEEN_BATCHES)

async def upload_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not QBANK.items:
        await update.message.reply_text("❌ No questions found in CSV.")
        return
    await update.message.reply_text(f"🚀 Uploading {len(QBANK.items)} questions to this chat...")
    await send_quiz_batch(context, update.effective_chat.id, to_channel=False)
    await update.message.reply_text("🎉 All questions uploaded successfully!")

async def upload_channel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not QBANK.items:
        await update.message.reply_text("❌ No questions found in CSV.")
        return
    await update.message.reply_text(f"📢 Uploading {len(QBANK.items)} questions to channel {CHANNEL_ID}...")
    try:
        await send_quiz_batch(context, CHANNEL_ID, to_channel=True)
        await update.message.reply_text("✅ All questions uploaded to channel!")
    except Exception as e:
        logging.error(f"Upload to channel failed: {e}")
        await update.message.reply_text(f"❌ Failed to upload to channel: {e}")

async def main() -> None:
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    await application.bot.delete_webhook(drop_pending_updates=True)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("count", count))
    application.add_handler(CommandHandler("uploadall", upload_all))
    application.add_handler(CommandHandler("uploadchannel", upload_channel))

    await application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    try:
        import nest_asyncio
        nest_asyncio.apply()
    except ImportError:
        pass
    asyncio.run(main())

#!/usr/bin/env python3
"""
Telegram Quiz Bot — Bulk Upload All Questions from CSV
"""

import asyncio
import csv
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List
import os
import requests

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
AUTO_UPLOAD = True
# -----------------------------------------

@dataclass
class QuizItem:
    question_no: str
    question: str
    options: List[str]
    correct_option_id: int
    description: str | None = None
    reference: str | None = None  # Reference column

class QuestionBank:
    def __init__(self) -> None:
        self.items: List[QuizItem] = []

    def load_csv(self, path: Path) -> int:
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
                    row.get("option1", ""), row.get("option2", ""),
                    row.get("option3", ""), row.get("option4", "")
                ]
                options = [opt.strip() for opt in options if opt.strip()]
                try:
                    cid = options.index(row.get("correct_answer", "").strip())
                except Exception:
                    continue
                if not (0 <= cid < len(options)):
                    continue

                self.items.append(
                    QuizItem(
                        row.get("question_no", ""),
                        row["question"].strip(),
                        options,
                        cid,
                        row.get("description") or None,
                        row.get("reference") or None  # Load reference
                    )
                )
        return len(self.items)

QBANK = QuestionBank()
QBANK.load_csv(CSV_PATH)

HELP_TEXT = (
    "नमस्कार! मी Bulk Quiz Bot आहे.\n\n"
    "Commands:\n"
    "/uploadall — CSV मधील सर्व प्रश्न बॅचेस मध्ये पाठवा\n"
    "/count — एकूण प्रश्न संख्या दाखवा"
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"👋 Hi {update.effective_user.first_name or ''}!\n" + HELP_TEXT)

async def count(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"📚 Total questions loaded: {len(QBANK.items)}")

async def upload_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not QBANK.items:
        await update.message.reply_text("❌ No questions found in CSV.")
        return

    chat_id = update.effective_chat.id
    await update.message.reply_text(f"🚀 Uploading {len(QBANK.items)} questions in batches of {BATCH_SIZE}...")

    for start_idx in range(0, len(QBANK.items), BATCH_SIZE):
        batch = QBANK.items[start_idx:start_idx+BATCH_SIZE]
        await update.message.reply_text(f"📦 Sending batch {start_idx//BATCH_SIZE+1} of {len(batch)} questions...")

        for idx, item in enumerate(batch, 1):
            try:
                # Format question exactly as requested
                poll_question = f"{item.question_no}) {item.question}\n\n"
                if item.reference:
                    poll_question += f"{item.reference}\n"

                # Send poll with options (Telegram handles buttons)
                await context.bot.send_poll(
                    chat_id=chat_id,
                    question=poll_question[:300],
                    options=item.options[:10],  # Keep original options
                    type="quiz",
                    correct_option_id=item.correct_option_id,
                    explanation=(item.description or "")[:200],
                    is_anonymous=False,  # Change to True for channel posting
                )
                await asyncio.sleep(DELAY_BETWEEN_POLLS)
            except Exception as e:
                logging.error(f"Failed to send question {start_idx+idx}: {e}")

        await update.message.reply_text("✅ Batch sent. Waiting before next batch...")
        await asyncio.sleep(DELAY_BETWEEN_BATCHES)

    await update.message.reply_text("🎉 All questions uploaded successfully!")

async def auto_upload_on_start(app: Application) -> None:
    await asyncio.sleep(5)
    updates = await app.bot.get_updates()
    if updates and updates[-1].message:
        fake_update = Update(update_id=updates[-1].update_id, message=updates[-1].message)
        await upload_all(fake_update, ContextTypes.DEFAULT_TYPE)

async def main() -> None:
    # Remove webhook to avoid conflicts
    requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

    builder = ApplicationBuilder().token(BOT_TOKEN)
    if AUTO_UPLOAD:
        builder = builder.post_init(auto_upload_on_start)

    application = builder.build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("count", count))
    application.add_handler(CommandHandler("uploadall", upload_all))

    await application.run_polling()

if __name__ == "__main__":
    try:
        import nest_asyncio
        nest_asyncio.apply()
    except ImportError:
        pass
    import asyncio
    asyncio.run(main())

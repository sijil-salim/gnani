"""
Appointment-booking voice agent (happy path only), built on LiveKit Agents.

Flow:  caller speaks a date  ->  Gnani Prisma (STT)  ->  LLM extracts the date and
       calls `book_slot`  ->  slot is allotted and saved  ->  LLM writes the
       confirmation  ->  Gnani Timbre (TTS) speaks it back.

Configuration lives in .env:
  - GNANI_* settings for speech (language, model, voice)
  - LLM_BASE_URL / LLM_API_KEY / LLM_MODEL for any OpenAI-compatible LLM
    (currently Groq; can point to Gnani Evon)
"""

import logging
import os
from datetime import date, datetime

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    RunContext,
    WorkerOptions,
    cli,
    function_tool,
)
# Plugins must be imported at the top of the file (LiveKit registers them on startup)
from livekit.plugins import gnani, openai, silero

from calendar_store import allot_and_book

load_dotenv()
logger = logging.getLogger("booking-agent")

# ---------------------------------------------------------------------------
# The agent
# ---------------------------------------------------------------------------
class BookingAgent(Agent):
    def __init__(self) -> None:
        today = date.today()
        super().__init__(
            instructions=(
                "You are a friendly appointment-booking assistant on a phone call. "
                f"Today is {today:%A, %d %B %Y}. "
                "Ask the caller which date they would like to book. "
                "When they say a date (including relative dates like 'next Monday' or "
                "'tomorrow'), convert it to YYYY-MM-DD and call the book_slot tool. "
                "Then confirm the booking out loud: the date, the time slot, and the "
                "booking ID, spelled out clearly. "
                "Keep every reply to one or two short sentences. Plain spoken text only: "
                "no lists, symbols, emojis or markdown, because your words are read aloud."
            )
        )

    @function_tool
    async def book_slot(self, context: RunContext, booking_date: str) -> str:
        """Book the allotted appointment slot for the caller on the requested date.

        Args:
            booking_date: The date the caller asked for, in YYYY-MM-DD format.
        """
        booking = allot_and_book(booking_date)  # saved to bookings.json
        logger.info("Booked: %s", booking)
        spoken_date = datetime.strptime(booking_date, "%Y-%m-%d").strftime("%A, %d %B")
        return (
            f"Booking confirmed for {spoken_date} at {booking['slot']}. "
            f"Booking ID is {booking['booking_id']}."
        )


# ---------------------------------------------------------------------------
# Speech — Gnani Prisma (STT) and Gnani Timbre (TTS), via Gnani's LiveKit plugin
# ---------------------------------------------------------------------------
def build_stt():
    return gnani.STT(
        language=os.getenv("GNANI_STT_LANGUAGE", "en-IN"),
        sample_rate=16000,
    )


def build_tts():
    return gnani.TTS(
        model=os.getenv("GNANI_TTS_MODEL", "timbre-v2.5"),
        voice=os.getenv("GNANI_TTS_VOICE", "Kaveri"),
        language=os.getenv("GNANI_TTS_LANGUAGE", "en-IN"),
        sample_rate=16000,
    )


# ---------------------------------------------------------------------------
# LLM — any OpenAI-compatible endpoint (currently Groq; can point to Gnani Evon).
# To switch, just change the three LLM_* values in .env.
# ---------------------------------------------------------------------------
def build_llm():
    return openai.LLM(
        base_url=os.getenv("LLM_BASE_URL"),
        api_key=os.getenv("LLM_API_KEY"),
        model=os.getenv("LLM_MODEL"),
    )


# ---------------------------------------------------------------------------
# Entrypoint: wire STT + LLM + TTS into a LiveKit session
# ---------------------------------------------------------------------------
async def entrypoint(ctx: JobContext) -> None:
    await ctx.connect()
    logger.info("Speech: Gnani Prisma + Timbre | LLM: %s", os.getenv("LLM_MODEL"))

    session = AgentSession(
        stt=build_stt(),
        llm=build_llm(),
        tts=build_tts(),
        vad=silero.VAD.load(),
    )

    await session.start(room=ctx.room, agent=BookingAgent())
    await session.generate_reply(
        instructions="Greet the caller briefly and ask which date they would like to book."
    )


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
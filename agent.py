"""
Appointment-booking voice agent (happy path only), built on LiveKit Agents.

Flow:  caller speaks a date  ->  STT  ->  LLM extracts the date and calls `book_slot`
       ->  slot is allotted and saved  ->  LLM writes the confirmation  ->  TTS speaks it.

Providers are configured in .env:
  - SPEECH_PROVIDER = deepgram (current) | gnani (Gnani Prisma STT + Timbre TTS)
  - LLM_BASE_URL / LLM_API_KEY / LLM_MODEL = any OpenAI-compatible endpoint
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
from livekit.plugins import deepgram, gnani, openai, silero

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
# Speech providers — switch with SPEECH_PROVIDER in .env ("deepgram" or "gnani")
# ---------------------------------------------------------------------------
SPEECH_PROVIDER = os.getenv("SPEECH_PROVIDER", "deepgram").lower()


def build_stt():
    if SPEECH_PROVIDER == "deepgram":
        return deepgram.STT(model="nova-3", language="en")
    return gnani.STT(
        language=os.getenv("GNANI_STT_LANGUAGE", "en-IN"),
        sample_rate=16000,
    )


def build_tts():
    if SPEECH_PROVIDER == "deepgram":
        return deepgram.TTS()
    return gnani.TTS(
        voice=os.getenv("GNANI_TTS_VOICE", "Pranav"),
        model=os.getenv("GNANI_TTS_MODEL", "timbre-v2.0"),
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
    logger.info("Speech provider: %s | LLM: %s", SPEECH_PROVIDER, os.getenv("LLM_MODEL"))

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
"""
Calendar store.

- Daily slots are read from slots.json.
- Bookings are saved to bookings.json so they can be viewed during a demo.

Commands:
  python calendar_store.py                    show the calendar
  python calendar_store.py clear              delete all bookings
  python calendar_store.py clear 2026-10-12   delete bookings for one date
"""

import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
SLOTS_FILE = HERE / "slots.json"
BOOKINGS_FILE = HERE / "bookings.json"


def load_slots() -> list[str]:
    """Read the list of daily slots from slots.json."""
    return json.loads(SLOTS_FILE.read_text())["daily_slots"]


def load_bookings() -> dict:
    """Read all bookings from bookings.json ({} if no bookings yet)."""
    if BOOKINGS_FILE.exists():
        return json.loads(BOOKINGS_FILE.read_text())
    return {}


def save_bookings(bookings: dict) -> None:
    """Write all bookings back to bookings.json, sorted by date."""
    BOOKINGS_FILE.write_text(json.dumps(dict(sorted(bookings.items())), indent=2))


def allot_and_book(booking_date: str) -> dict:
    """Allot the first free slot on the given date (YYYY-MM-DD) and save the booking."""
    bookings = load_bookings()
    taken = {b["slot"] for b in bookings.get(booking_date, [])}
    free = [s for s in load_slots() if s not in taken]
    if not free:  # outside the happy path, but fail clearly rather than crash
        raise RuntimeError(f"No free slots on {booking_date}")

    booking = {
        "booking_id": f"BK-{uuid.uuid4().hex[:6].upper()}",
        "slot": free[0],
        "booked_at": datetime.now().isoformat(timespec="seconds"),
    }
    bookings.setdefault(booking_date, []).append(booking)
    save_bookings(bookings)
    return {"date": booking_date, **booking}


def clear_bookings(booking_date: str | None = None) -> None:
    """Delete all bookings, or only the bookings for one date."""
    if booking_date is None:
        BOOKINGS_FILE.unlink(missing_ok=True)
        print("All bookings cleared.")
        return
    bookings = load_bookings()
    if bookings.pop(booking_date, None) is None:
        print(f"No bookings found for {booking_date}.")
        return
    save_bookings(bookings)
    print(f"Bookings for {booking_date} cleared.")


def show_calendar() -> None:
    """Print every booked date with each slot marked as booked or free."""
    bookings = load_bookings()
    if not bookings:
        print("No bookings yet.")
        return
    slots = load_slots()
    for day, day_bookings in bookings.items():
        pretty = datetime.strptime(day, "%Y-%m-%d").strftime("%A, %d %B %Y")
        print(f"\n{pretty}")
        by_slot = {b["slot"]: b for b in day_bookings}
        for slot in slots:
            b = by_slot.get(slot)
            status = f"BOOKED  {b['booking_id']}" if b else "free"
            print(f"  {slot:>8}   {status}")
    print()


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "clear":
        clear_bookings(args[1] if len(args) > 1 else None)
    else:
        show_calendar()

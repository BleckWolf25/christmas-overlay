# src/advent.py
import datetime

from win32 import get_work_area_for_point

class AdventCalendar:
    """A small gift icon in the corner. Hover for 800 ms during Dec 1–25 to reveal the day's note."""

    MESSAGES = [
        "Peace on Earth starts with a cup of hot chocolate.",
        "Today's forecast: 100% chance of joy.",
        "Don't forget to water your Christmas tree.",
        "Wrap a gift for someone who won't expect it.",
        "Play your favourite carol really loud today.",
        "Call someone you miss. It'll make their day.",
        "Snowflakes are just winter's confetti.",
        "Add extra marshmallows. It's the law.",
        "Pine needles are temporary. Joy is forever.",
        "Bake something. Anything. Even toast.",
        "Leave cookies out — even if only for you.",
        "Wear the ugly sweater. It's a badge of honour.",
        "A warm fire is 90% about the company.",
        "Believe in the magic of small moments.",
        "The best gifts aren't always wrapped.",
        "Take a walk. Look up. Smile at the cold.",
        "Watch a classic Christmas movie tonight.",
        "Write a note to someone who needs it.",
        "Hum your favourite carol while washing up.",
        "Forgive someone. Even if it's yourself.",
        "Give a stranger an unexpected compliment.",
        "Homemade is always the right size.",
        "Fill the room with whatever smells like Christmas.",
        "Rest. You've earned it.",
        "Merry Christmas!",
    ]

    def __init__(self, canvas, vx: int, vy: int):
        self.canvas = canvas
        self.vx, self.vy = vx, vy
        _, _, wr, wb = get_work_area_for_point(0, 0)
        self._gift_pos = (wr - 46 - vx, wb - 62 - vy)
        self._items: list = []
        self._gift_bounds = None
        self._message_tag: str | None = None
        self._message_until = 0
        self._hover_start = 0
        self._last_day_opened: int | None = None
        self._active = self._is_active()
        if self._active:
            self._draw_gift(opened=False)

    @staticmethod
    def _is_active() -> bool:
        today = datetime.date.today()
        return today.month == 12 and 1 <= today.day <= 25

    def _draw_gift(self, opened: bool) -> None:
        for item in self._items:
            self.canvas.delete(item)
        self._items = []
        gx, gy = self._gift_pos
        c = self.canvas

        self._items.append(c.create_rectangle(gx - 12, gy - 6, gx + 12, gy + 12, fill="#B91C1C", outline="#5A0E0E"))
        self._items.append(c.create_rectangle(gx - 12, gy + 1, gx + 12, gy + 4, fill="#FCD34D", outline=""))
        self._items.append(c.create_rectangle(gx - 2, gy - 6, gx + 2, gy + 12, fill="#FCD34D", outline=""))

        if opened:
            self._items.append(c.create_rectangle(gx - 12, gy - 16, gx + 12, gy - 8, fill="#991B1B", outline="#5A0E0E"))
            self._items.append(c.create_rectangle(gx - 12, gy - 13, gx + 12, gy - 11, fill="#FCD34D", outline=""))
        else:
            self._items.append(c.create_rectangle(gx - 13, gy - 8, gx + 13, gy - 4, fill="#991B1B", outline="#5A0E0E"))
            self._items.append(c.create_rectangle(gx - 13, gy - 6, gx + 13, gy - 5, fill="#FCD34D", outline=""))
            self._items.append(c.create_oval(gx - 8, gy - 12, gx - 2, gy - 6, fill="#FCD34D", outline="#92400E"))
            self._items.append(c.create_oval(gx + 2, gy - 12, gx + 8, gy - 6, fill="#FCD34D", outline="#92400E"))

        self._gift_bounds = (gx - 14, gy - 18, gx + 14, gy + 14)

    def update(self, tick: int, cx: float, cy: float) -> None:
        if not self._active:
            return

        if self._message_tag is not None and tick >= self._message_until:
            self.canvas.delete(self._message_tag)
            self._message_tag = None

        if self._gift_bounds is None:
            return
        x1, y1, x2, y2 = self._gift_bounds
        if x1 <= cx <= x2 and y1 <= cy <= y2:
            if self._hover_start == 0:
                self._hover_start = tick
            elif self._message_tag is None and tick - self._hover_start >= 24:  # ~800 ms
                self._show_message(tick)
        else:
            self._hover_start = 0

    def _show_message(self, tick: int) -> None:
        today = datetime.date.today()
        if today.month != 12 or not (1 <= today.day <= 25):
            return

        msg = self.MESSAGES[(today.day - 1) % len(self.MESSAGES)]
        if self._last_day_opened != today.day:
            self._draw_gift(opened=True)
            self._last_day_opened = today.day

        gx, gy = self._gift_pos
        tag = f"advent_{tick}"
        text = self.canvas.create_text(
            gx, gy - 42, text=msg, fill="#FEF3C7",
            font=("Segoe UI", 11, "bold"), width=280, anchor="s", justify="right",
        )
        self.canvas.addtag_withtag(tag, text)
        bbox = self.canvas.bbox(text)
        if bbox:
            pad = 6
            bg = self.canvas.create_rectangle(
                bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad,
                fill="#0F172A", outline="#FBBF24", width=1,
            )
            self.canvas.tag_raise(text)
            self.canvas.addtag_withtag(tag, bg)

        self._message_tag = tag
        self._message_until = tick + 6 * 30
        self._hover_start = 0
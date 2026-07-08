from jarvis_core.domain import Command


class Planner:
    def plan(self, text):
        normalized = text.strip().lower()
        if "time" in normalized or "hora" in normalized:
            return Command(name="time.now", args={}, source="cli")
        return Command(name="unknown", args={"text": text}, source="cli")

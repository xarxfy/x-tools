"""The few colours tags, categories and groups can have (the UI shows them with fixed shades)."""

COLORS = ("gray", "blue", "green", "orange", "red", "purple", "pink", "teal")
DEFAULT = "gray"
COLOR_PATTERN = "^(" + "|".join(COLORS) + ")$"

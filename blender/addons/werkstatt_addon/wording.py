"""How the game shows an upgrade node (model.Vehicle.in_game) in the panel's words. Pure Python, like model.py."""

# The toolsets a definition's toolNodes names (the save's VehicleItem.ToolsetIDs).
TOOLS = {2317836723: "the portable winch", 3771754783: "the portable plank"}
# The list's short words, which fit the sidebar's default width; note() says more in the item box.
MARKS = {"never": "Not in game", "always": "Always shown", "tool": "With tool"}


def note(how, tools):
    """A sentence on how the game shows a node; "" for one that shows with its item alone."""
    names = " and ".join(TOOLS.get(t, f"tool {t}") for t in tools)
    if how == "never":
        return "Not shown in game"
    if how == "always":
        return "Always shown"
    if how == "tool":
        return f"Shown with {names}"
    return f"Shown with its item and {names}" if tools else ""


def mark(how, tools):
    """The list's mark for a node ("never", "always" or "tool", a key of MARKS), or None for one that shows with its
    item alone."""
    return "tool" if tools else how if how in MARKS else None

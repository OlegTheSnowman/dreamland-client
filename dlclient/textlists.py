"""List commands the client opens as a list window.

The rows always come from the server's "list" frame (framelists.py). The
client does not read lists out of the game's text: when the server sends no
frame for a command, the game's own text is shown instead.

kind: (default command, parser, title key, keys help key). The parser slot is
always None now; it stays so the table keeps its shape for the code reading it.
"""

PARSERS = {
    "shop": ("list", None, "tl.shop", "tl.shopkeys"),
    "services": ("service", None, "tl.services", "tl.servicekeys"),
    "training": ("train", None, "tl.training", "tl.trainkeys"),
    "skills": ("practice", None, "tl.skills", "tl.skillkeys"),
    "skilltable": ("skills", None, "tl.skills", "tl.skillkeys"),
    "questshop": ("quest list", None, "tl.questshop", "tl.questshopkeys"),
    "questrequest": ("quest request", None, "tl.questrequest", "tl.questrequestkeys"),
    "zonequests": ("quest", None, "tl.zonequests", "tl.zonequestkeys"),
    "areas": ("areas", None, "tl.areas", "tl.areakeys"),
    "notes": ("note list", None, "tl.notes", "tl.notekeys"),
    "helpmatches": ("help", None, "tl.helpmatches", "tl.helpkeys"),
    "glist": ("glist", None, "tl.glist", "tl.glistkeys"),
    "socials": ("socials", None, "tl.socials", "tl.socialkeys"),
    "commands": ("commands", None, "tl.commands", "tl.commandkeys"),
    "linked": ("vault", None, "tl.linked", "tl.linkedkeys"),
}

PAGER = ("Press Enter to continue", "Нажмите клавишу Enter для продолжения", "Натисни Enter, щоб продовжити")


def is_pager(text):
    return any(p in text for p in PAGER)

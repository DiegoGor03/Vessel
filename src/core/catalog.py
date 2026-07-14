"""App catalog helpers: categorization and cross-distro grouping.

This module turns the flat, per-distro Package/ContainerApp lists produced by
PackageManager into a "store-like" catalog: one AppGroup per piece of
software, merging the matching entries found across containers/distros, with
a best-effort category and icon so the UI can render a GNOME
Software / Bazaar style grid.

The categorization and name-matching here are heuristic (keyword / alias
based) rather than driven by real AppStream metadata, since apt/dnf/pacman
don't expose that uniformly. It's good enough to group and sort a software
store view, but it isn't perfect — e.g. a package with an unusual name and
no recognizable keywords in its description will land in "Altro".
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)


# Category key -> (display label, icon name)
# Icon names follow the freedesktop icon-naming-spec "applications-*"
# categories, which are shipped by the Adwaita/hicolor icon themes on any
# GNOME system, so they render even when we have no real app icon.
CATEGORIES: Dict[str, tuple] = {
    "internet": ("Internet & Comunicazione", "applications-internet"),
    "multimedia": ("Audio & Video", "applications-multimedia"),
    "grafica": ("Grafica & Design", "applications-graphics"),
    "ufficio": ("Ufficio & Produttività", "applications-office"),
    "sviluppo": ("Sviluppo", "applications-development"),
    "giochi": ("Giochi", "applications-games"),
    "sistema": ("Sistema & Utilità", "applications-system"),
    "altro": ("Altro", "application-x-executable"),
}

# Keyword lists checked (in this order) against "name description" lowercase.
# First category whose keyword matches wins.
_CATEGORY_KEYWORDS: List[tuple] = [
    ("giochi", [
        "game", "gaming", "steam", "lutris", "emulator", "chess", "arcade",
        "minecraft", "wine-", "playonlinux",
    ]),
    ("sviluppo", [
        "ide", "compiler", "debugger", " git", "git-", "sdk", "programming",
        "development", "code editor", "vim", "emacs", "docker", "podman",
        "database", "postgresql", "mysql", "sqlite", "gcc", "clang",
        "python3-", "nodejs", "rust", "golang", "jdk", "java-", "editor for",
    ]),
    ("grafica", [
        "image", "photo", "graphic", "design", "gimp", "inkscape", "blender",
        "draw", "paint", "krita", "scanner", "vector graphics", "3d model",
        "icon theme",
    ]),
    ("multimedia", [
        "audio", "video", "music", "media player", "player for", "codec",
        "mp3", "ffmpeg", "obs", "vlc", "mpv", "spotify", "rhythmbox",
        "sound", "recorder", "streaming", "podcast", "radio",
    ]),
    ("ufficio", [
        "office", "document", "pdf", "spreadsheet", "presentation", "note",
        "notes", "calendar", "libreoffice", "writer", "word processor",
        "task manager", "todo", "finance", "accounting",
    ]),
    ("internet", [
        "browser", "mail client", "e-mail", "email", "chat", "messenger",
        "telegram", "discord", " irc", "ftp client", "torrent", "vpn",
        "network client", "web browser", "rss", "slack", "zoom", "video call",
        "remote desktop", "ssh client",
    ]),
    ("sistema", [
        "system monitor", "disk", "backup", "utilit", "terminal emulator",
        "file manager", "archive manager", "system settings", "package",
        "firewall", "partition", "driver", "hardware", "bluetooth",
    ]),
]

# Cross-distro name normalization: packages that are "the same" software
# but named differently by different package managers.
_NAME_ALIASES: Dict[str, str] = {
    "firefox-esr": "firefox",
    "chromium-browser": "chromium",
    "chromium-freeworld": "chromium",
    "gimp2": "gimp",
    "code": "visual-studio-code",
    "vscode": "visual-studio-code",
    "libreoffice-fresh": "libreoffice",
    "libreoffice-still": "libreoffice",
    "thunderbird-esr": "thunderbird",
}

# Suffixes distro packaging conventions commonly append that don't change
# what the software fundamentally is.
# NOTE: packages like `audacity-data` are separate from `audacity`, so we
# avoid stripping suffixes that often denote distinct helper/data packages.
_STRIP_SUFFIXES: Sequence[str] = (
    "-bin", "-git", "-app", "-stable",
)


def normalize_name(name: str) -> str:
    """Return a distro-agnostic grouping key for a package/app name."""
    key = name.lower().strip()
    for suffix in _STRIP_SUFFIXES:
        if key.endswith(suffix) and len(key) > len(suffix) + 1:
            key = key[: -len(suffix)]
    return _NAME_ALIASES.get(key, key)


def categorize(name: str, description: str = "") -> str:
    """Best-effort category key for a package, based on name + description."""
    haystack = f"{name} {description}".lower()
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(kw in haystack for kw in keywords):
            return category
    return "altro"


@dataclass
class AppGroup:
    """One software entry in the catalog, merged across distros/containers."""
    key: str
    display_name: str
    category: str
    description: str = ""
    candidates: List[object] = field(default_factory=list)  # Package | ContainerApp

    @property
    def category_label(self) -> str:
        return CATEGORIES.get(self.category, CATEGORIES["altro"])[0]

    @property
    def category_icon(self) -> str:
        return CATEGORIES.get(self.category, CATEGORIES["altro"])[1]

    @property
    def icon_name(self) -> str:
        """Prefer a real icon (from a ContainerApp's .desktop Icon=) if any
        candidate has one; otherwise fall back to the category icon."""
        for c in self.candidates:
            real_icon = getattr(c, "icon", "") or ""
            if real_icon:
                return real_icon
        return self.category_icon

    @property
    def distros(self) -> List[str]:
        return sorted({c.distro for c in self.candidates})

    @property
    def is_multi_distro(self) -> bool:
        return len(self.distros) > 1

    def candidate_for(self, distro: str) -> Optional[object]:
        for c in self.candidates:
            if c.distro == distro:
                return c
        return None


def group_packages(items: Sequence[object]) -> List[AppGroup]:
    """Group a flat list of Package/ContainerApp objects into AppGroups.

    Works for both PackageManager.search_packages_all_containers() results
    (Package objects) and get_apps_all_containers() results (ContainerApp
    objects) — both expose .name, .distro, .container attributes.
    """
    groups: Dict[str, AppGroup] = {}

    for item in items:
        key = normalize_name(item.name)
        description = getattr(item, "description", "") or ""

        group = groups.get(key)
        if group is None:
            group = AppGroup(
                key=key,
                display_name=item.name,
                category=categorize(item.name, description),
                description=description,
            )
            groups[key] = group
        elif not group.description and description:
            group.description = description

        group.candidates.append(item)

    return sorted(groups.values(), key=lambda g: g.display_name.lower())


def category_counts(groups: Sequence[AppGroup]) -> Dict[str, int]:
    """Count how many app groups fall into each category (for the sidebar)."""
    counts: Dict[str, int] = {}
    for group in groups:
        counts[group.category] = counts.get(group.category, 0) + 1
    return counts
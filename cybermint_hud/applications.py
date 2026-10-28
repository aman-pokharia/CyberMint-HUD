"""Desktop application discovery, search and launch helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class ApplicationEntry:
    name: str
    keywords: tuple[str, ...]
    app_info: Any


def enumerate_applications(app_info_api: Any | None = None) -> list[ApplicationEntry]:
    if app_info_api is None:
        import gi

        gi.require_version("Gio", "2.0")
        from gi.repository import Gio

        app_info_api = Gio.AppInfo

    entries = []
    for app_info in app_info_api.get_all():
        if not app_info.should_show():
            continue
        name = (app_info.get_name() or "").strip()
        if not name:
            continue
        try:
            raw_keywords = app_info.get_keywords() or ()
        except (AttributeError, TypeError):
            raw_keywords = ()
        keywords = tuple(str(word).strip() for word in raw_keywords if str(word).strip())
        entries.append(ApplicationEntry(name, keywords, app_info))
    return sorted(entries, key=lambda item: item.name.casefold())


def filter_applications(apps: Iterable[ApplicationEntry], query: str) -> list[ApplicationEntry]:
    terms = query.casefold().split()
    if not terms:
        return list(apps)
    matches = []
    for app in apps:
        searchable = " ".join((app.name, *app.keywords)).casefold()
        if all(term in searchable for term in terms):
            matches.append(app)
    return matches


def launch_application(entry: ApplicationEntry) -> tuple[bool, str]:
    try:
        launched = entry.app_info.launch([], None)
        if launched is False:
            return False, f"{entry.name} did not start"
        return True, ""
    except Exception as exc:
        return False, str(exc) or exc.__class__.__name__

"""The power right-click menu in the owner's words, 2026-10-20.

- "unshare doesnt sound correct": a shared circuit offers "Remove 3fer"
  (named by its ways), the batch "Remove 3fers from this screen".
- The tray's distro unplugs read "Unplug multi" / "Unplug circuit"
  (tests/test_hardware_dock.py pins those).
- Tab steps circuits in the Power view, so the menu says "Previous
  Circuit" / "Next Circuit" there.
- "when i click to redraw a circuit and it is highlighted we need to make
  sure it stays highlighted until after it has been redrawn": the run open
  for redrawing keeps its highlight after Alt is let go, until Esc.

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_power_menu_wording.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_nfer_custom_rulings import (  # noqa: E402,F401 - fixtures
    _guard, page, landed, make, pt, alt_click,
)

MENU_TEXT_JS = """() => [...document.querySelectorAll('#context-menu .menu-option')]
    .filter(e => e.offsetParent !== null).map(e => e.textContent.trim())"""


def _menu(page, p):
    page.evaluate("() => window.app.hideContextMenu()")
    page.mouse.click(p['x'], p['y'], button='right')
    landed(page)
    return page.evaluate(MENU_TEXT_JS)


def test_a_3fer_offers_remove_3fer_and_the_screen_remove_3fers(page):
    (wall,) = make(page, [{'name': 'Wall', 'columns': 10}])
    items = _menu(page, pt(page, wall, 2, 1))
    assert 'Remove 3fer' in items, items
    assert 'Remove 3fers from this screen' in items, items
    assert not any('Un-share' in t for t in items), items


def test_the_tab_items_say_circuit_in_the_power_view(page):
    (wall,) = make(page, [{'name': 'Wall', 'columns': 10}])
    items = _menu(page, pt(page, wall, 2, 1))
    assert any(t.startswith('Previous Circuit') for t in items), items
    assert any(t.startswith('Next Circuit') for t in items), items
    assert not any(t.startswith('Next Port') for t in items), items


def test_the_circuit_being_redrawn_stays_lit_until_esc(page):
    (wall,) = make(page, [{'name': 'Wall', 'columns': 10}])
    page.evaluate("() => window.app.hideContextMenu()")
    alt_click(page, pt(page, wall, 0, 4))
    away = pt(page, wall, 4, 9)
    page.mouse.move(away['x'], away['y'])
    landed(page)
    lit = """(id) => window.canvasRenderer._runUnderlayLit(window.__nf.layer(id), 2)"""
    assert page.evaluate("() => window.app._overrideHover") is None
    assert page.evaluate(lit, wall), 'the circuit being redrawn stays lit'
    page.keyboard.press('Escape')
    landed(page)
    assert not page.evaluate(lit, wall), 'Esc ends the redraw and its highlight'

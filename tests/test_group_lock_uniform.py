"""A group is locked or unlocked as ONE thing.

The owner's ruling, 2026-10-19: "if a screen is locked and becomes part of
a group then ask if want to lock the whole thing or unlock it. since cant
be both."

- Group Screens (or Add to Group) over locked AND unlocked screens asks
  once: "Lock the whole group" or "Unlock it"; Cancel groups nothing. The
  choice lands on every member inside the grouping's one history entry.
  (Before: the grouping was refused outright, naming the locked screen.)
- Locking or unlocking any member locks or unlocks the whole group.
- An old file whose group is half locked opens unchanged; the first lock
  toggle on that group asks the same question.
- A selection of screens that are ALL locked still groups nothing - every
  screen in it is locked, so nothing may change - and names them.

Run locally:
    python -m pytest tests/test_group_lock_uniform.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_nfer_custom_rulings import (  # noqa: E402,F401 - fixtures
    _guard, page, landed, make, history,
)


def two(page, a_locked=False, b_locked=False, grouped=False, extra=None):
    specs = [{'name': 'A', 'columns': 3, 'props': {'locked': a_locked}},
             {'name': 'B', 'columns': 3, 'x': 800, 'props': {'locked': b_locked}}]
    if extra:
        specs.append(extra)
    ids = make(page, specs, group=grouped)
    page.evaluate("""() => { window.__nf.errors = [];
        window.app._showLockedError = (ls) => { if (ls && ls.length)
            window.__nf.errors.push(ls.map(l => l.name)); }; }""")
    return ids


def select(page, *ids):
    page.evaluate("""(ids) => {
        const app = window.app;
        app.selectedLayerIds = new Set(ids);
        app.currentLayer = window.__nf.layer(ids[0]);
        app.lastSelectedLayerId = ids[0];
    }""", list(ids))


def state(page, ids):
    return page.evaluate("""(ids) => ({
        locked: ids.map(id => !!window.__nf.layer(id).locked),
        groups: ids.map(id => window.__nf.layer(id).group_id || null),
        errors: window.__nf.errors,
    })""", list(ids))


def lock_dialog(page):
    return page.evaluate("""() => {
        const m = document.getElementById('group-lock-modal');
        if (!m || m.style.display === 'none') return null;
        return { text: m.textContent.replace(/\\s+/g, ' ').trim(),
                 buttons: [...m.querySelectorAll('button')].map(b => b.textContent.trim()) };
    }""")


def start(page, js):
    """Start an async app verb without waiting for it (a dialog may hold
    it), and wait until it has either finished or put the dialog up."""
    page.evaluate("""(js) => {
        window.__done = false;
        Promise.resolve((0, eval)(js)).finally(() => { window.__done = true; });
    }""", js)
    page.wait_for_function("""() => window.__done || (() => {
        const m = document.getElementById('group-lock-modal');
        return !!m && m.style.display !== 'none'; })()""")


def finish(page):
    page.wait_for_function("() => window.__done === true")
    landed(page)


def test_grouping_locked_and_unlocked_screens_asks_and_locks_the_group(page):
    a, b = two(page, b_locked=True)
    select(page, a, b)
    h0 = len(history(page))
    start(page, "window.app.groupSelectedLayers()")
    dlg = lock_dialog(page)
    assert dlg, 'grouping a locked and an unlocked screen must ask'
    assert dlg['buttons'] == ['Cancel', 'Unlock it', 'Lock the whole group'], dlg
    assert 'B' in dlg['text'], dlg
    page.locator('#group-lock-lock').click()
    finish(page)
    out = state(page, [a, b])
    assert out['locked'] == [True, True], out
    assert out['groups'][0] and out['groups'][0] == out['groups'][1], out
    assert history(page)[h0:] == ['Group Screens'], history(page)
    saved = page.evaluate("""async (ids) => {
        const p = await (await fetch('/api/project')).json();
        return ids.map(id => !!p.layers.find(l => l.id === id).locked);
    }""", [a, b])
    assert saved == [True, True], saved


def test_grouping_with_unlock_it_unlocks_every_member(page):
    a, b = two(page, a_locked=True)
    select(page, a, b)
    start(page, "window.app.groupSelectedLayers()")
    page.locator('#group-lock-unlock').click()
    finish(page)
    out = state(page, [a, b])
    assert out['locked'] == [False, False], out
    assert out['groups'][0] and out['groups'][0] == out['groups'][1], out


def test_cancel_groups_nothing_and_changes_nothing(page):
    a, b = two(page, b_locked=True)
    select(page, a, b)
    h0 = len(history(page))
    start(page, "window.app.groupSelectedLayers()")
    page.locator('#group-lock-cancel').click()
    finish(page)
    out = state(page, [a, b])
    assert out['locked'] == [False, True] and out['groups'] == [None, None], out
    assert len(history(page)) == h0


def test_adding_a_locked_screen_to_an_unlocked_group_asks(page):
    a, b, c = two(page, grouped=True, extra={'name': 'C', 'columns': 3, 'x': 1600,
                                            'props': {'locked': True}})
    page.evaluate("""(ids) => {
        const app = window.app;
        const C = window.__nf.layer(ids[2]);
        C.group_id = null;
        app.project.groups[0].layer_ids = [ids[0], ids[1]];
    }""", [a, b, c])
    select(page, c)
    start(page, "window.app.addSelectedToGroup(window.app.project.groups[0].id)")
    assert lock_dialog(page), 'joining a locked screen to an unlocked group must ask'
    page.locator('#group-lock-lock').click()
    finish(page)
    out = state(page, [a, b, c])
    assert out['locked'] == [True, True, True], out
    assert len(set(out['groups'])) == 1 and out['groups'][0], out


def test_locking_one_member_locks_the_whole_group(page):
    a, b = two(page, grouped=True)
    select(page, a)
    h0 = len(history(page))
    start(page, "window.app.toggleLockOnSelected()")
    finish(page)
    assert state(page, [a, b])['locked'] == [True, True]
    assert history(page)[h0:] == ['Lock Layers'], history(page)
    select(page, b)
    start(page, "window.app.toggleLockOnSelected()")
    finish(page)
    assert state(page, [a, b])['locked'] == [False, False]


def test_an_old_half_locked_group_opens_unchanged_and_asks_on_the_first_toggle(page):
    a, b = two(page, b_locked=True, grouped=True)
    assert state(page, [a, b])['locked'] == [False, True]
    select(page, a)
    start(page, "window.app.toggleLockOnSelected()")
    assert lock_dialog(page), 'a half-locked group must ask which way'
    page.locator('#group-lock-unlock').click()
    finish(page)
    assert state(page, [a, b])['locked'] == [False, False]

    a, b = two(page, b_locked=True, grouped=True)
    start(page, "window.app.toggleGroupLock(window.app.project.groups[0].id)")
    assert lock_dialog(page)
    page.locator('#group-lock-lock').click()
    finish(page)
    assert state(page, [a, b])['locked'] == [True, True]


def test_grouping_screens_that_are_all_locked_is_refused(page):
    a, b = two(page, a_locked=True, b_locked=True)
    select(page, a, b)
    start(page, "window.app.groupSelectedLayers()")
    assert lock_dialog(page) is None
    finish(page)
    out = state(page, [a, b])
    assert out['groups'] == [None, None], out
    assert ['A', 'B'] in out['errors'], out

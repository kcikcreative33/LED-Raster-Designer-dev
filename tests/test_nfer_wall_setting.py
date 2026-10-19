"""A grouped wall shares ONE splitter setting.

The owner's rulings, 2026-10-19, from a three-screen group show built on
1.5.3-beta.1 (the shape is rebuilt here in generic form: three members,
150 W cabinets on 208 V x 20 A, a half-height top row, the first member
with sharing off and the other two with it on, and old circuits that are
each ONE run covering three columns):

1. In a group, "Share circuits via splitters" - the enabled flag AND the
   splitter size - is ONE setting for the whole wall, in auto and custom:
   "when grouped they should be sharing that setting". Ticking or
   changing it on any member writes every member in one history entry,
   and the sidebar shows the wall's value whichever member is selected.
   Members that disagree (an old file) read the first member's setting;
   the file is not rewritten until the setting is touched. A locked
   member blocks the change for the whole wall and is named.
   (Before: the box wrote only the selected screens and showed the
   selected screen's own flag, while the custom fill read the wall
   owner's - so a member showing "on" filled one 15-cabinet run.)

Run locally:
    python -m pytest tests/test_nfer_wall_setting.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_nfer_custom_rulings import (  # noqa: E402,F401 - fixtures
    _guard, page, landed, make, pt, alt_click, alt_sweep, menu_at, take,
    fill, circuits, gangs, manual, history,
)


# Old-file shape: three members, A (6 columns) owns circuit 1, B holds
# circuits 2-6 drawn across all three screens - each a single run of three
# columns snaking top-down, except circuit 4, one column - and C holds
# nothing. All custom. Top row half height when `half` is set.
OLD_WALL_JS = """async ([a, b, c, half]) => {
    const app = window.app;
    if (half) {
        // Half-height cabinets are the server's geometry: set them there.
        await app._layerSavesSettled();
        const p = await window.__nf.j('GET', '/api/project');
        p.layers.forEach(l => { if ([a, b, c].includes(l.id)) l.panels.forEach(q => {
            if (q.row === 0) q.halfTile = 'height'; }); });
        await window.__nf.j('PUT', '/api/project', p);
        const fresh = await window.__nf.j('GET', '/api/project');
        fresh.layers.forEach(fl => { const l = window.__nf.layer(fl.id);
            if (l) l.panels = fl.panels; });
    }
    const A = window.__nf.layer(a), B = window.__nf.layer(b), C = window.__nf.layer(c);
    const snake = (cols, lid) => cols.flatMap((col, i) => {
        const rows = i % 2 ? [4, 3, 2, 1, 0] : [0, 1, 2, 3, 4];
        return rows.map(r => Object.assign({ row: r, col }, lid ? { layerId: lid } : {}));
    });
    [A, B, C].forEach(l => {
        l.powerFlowPattern = 'custom';
        l.lastPowerFlowPattern = 'tl-v';
    });
    A.powerCustomPaths = { 1: snake([0, 1, 2]) };
    A.powerCustomIndex = 1;
    B.powerCustomPaths = { 2: snake([3, 4, 5], a), 3: snake([0, 1, 2]),
                           4: snake([3]), 5: snake([0, 1, 2], c),
                           6: snake([3, 4, 5], c) };
    B.powerCustomIndex = 6;
    C.powerCustomPaths = {};
    app._circuitTailCache = null;
    app.updateLayers([A, B, C]);
    app.renderLayers();
    app.resetHistory('Old file');
}"""

SHARING_OFF = {'powerSplitters': {'enabled': False, 'maxWays': 3,
                                  'manual': {'merge': [], 'split': []}}}


def three(page, a_props=None, b_props=None, c_props=None):
    """A three-member group: A (6 columns, sharing OFF), B (4 columns) and
    C (6 columns), both sharing on."""
    close_menu(page)
    return make(page, [
        {'name': 'A', 'columns': 6, 'props': dict(SHARING_OFF, **(a_props or {}))},
        {'name': 'B', 'columns': 4, 'x': 1200, 'props': b_props or {}},
        {'name': 'C', 'columns': 6, 'x': 2000, 'props': c_props or {}},
    ], group=True)


def old_wall(page, half=True, **kw):
    ids = three(page, **kw)
    page.evaluate(OLD_WALL_JS, [*ids, half])
    landed(page)
    return ids


def close_menu(page):
    """A menu left open by the test before must not catch this one's clicks."""
    page.evaluate("() => window.app.hideContextMenu()")


def select(page, *ids):
    page.evaluate("""(ids) => {
        const app = window.app;
        const l = window.__nf.layer(ids[0]);
        app.currentLayer = l;
        app.selectedLayerIds = new Set(ids);
        app.lastSelectedLayerId = ids[0];
        app.loadLayerToInputs();
        app.refreshSplitterPanel();
        app.updateCustomPowerUI && app.updateCustomPowerUI();
    }""", list(ids))
    landed(page)


def raw(page, ids):
    """Each member's STORED splitter setting, not the wall's read."""
    return page.evaluate("""(ids) => ids.map(id => {
        const s = window.__nf.layer(id).powerSplitters || {};
        return [!!s.enabled, s.maxWays];
    })""", list(ids))


def box(page):
    return page.evaluate("""() => {
        const en = document.getElementById('power-splitters-enabled');
        const mw = document.getElementById('power-splitters-maxways');
        return { checked: en.checked, ways: mw.value };
    }""")


def catch_locked(page):
    page.evaluate("""() => { window.__nf.errors = [];
        window.app._showLockedError = (ls) => { if (ls && ls.length)
            window.__nf.errors.push(ls.map(l => l.name)); }; }""")


# ── 1. one splitter setting per wall ──────────────────────────────────────

def test_the_wall_reads_its_first_members_setting(page):
    """The old file: A sharing off, B and C on. Whichever member is
    selected, the box shows the wall's value - A's, off - and the app
    reads it so; nothing is rewritten by opening or selecting."""
    a, b, c = old_wall(page)
    for m in (a, b, c):
        select(page, m)
        assert box(page)['checked'] is False, (
            f'member {m} must show the wall setting (off): {box(page)}')
        assert page.evaluate("(id) => window.app.getPowerSplitters("
                             "window.__nf.layer(id)).enabled", m) is False
    assert raw(page, [a, b, c]) == [[False, 3], [True, 3], [True, 3]], (
        'an old file opens unchanged until the setting is touched')


def test_ticking_the_box_on_one_member_sets_the_whole_wall(page):
    """B alone selected, the box ticked: all three members share - one
    history entry, saved to the server. The size picked on C reaches A
    and B; one undo puts the size back on every member."""
    a, b, c = old_wall(page)
    select(page, b)
    h0 = len(history(page))
    page.locator('#power-splitters-enabled').click()
    landed(page)
    assert raw(page, [a, b, c]) == [[True, 3]] * 3, raw(page, [a, b, c])
    assert history(page)[h0:] == ['Change Splitter Packing'], history(page)
    saved = page.evaluate("""async (ids) => {
        await window.app._layerSavesSettled();
        const p = await (await fetch('/api/project')).json();
        return ids.map(id => !!(p.layers.find(l => l.id === id)
            .powerSplitters || {}).enabled);
    }""", [a, b, c])
    assert saved == [True, True, True], saved

    select(page, c)
    page.evaluate("""() => {
        const mw = document.getElementById('power-splitters-maxways');
        mw.value = '2';
        mw.dispatchEvent(new Event('change', { bubbles: true }));
    }""")
    landed(page)
    assert raw(page, [a, b, c]) == [[True, 2]] * 3, raw(page, [a, b, c])
    select(page, a)
    assert box(page) == {'checked': True, 'ways': '2'}, box(page)
    page.evaluate("() => window.app.undo()")
    landed(page)
    assert raw(page, [a, b, c]) == [[True, 3]] * 3, raw(page, [a, b, c])


def test_a_locked_member_blocks_the_wall_setting(page):
    """C locked, its own flag off: ticking the box on B would change C, so
    no member changes, C is named, and the box snaps back to the wall's
    value. A locked member already holding the new value blocks nothing."""
    a, b, c = old_wall(page, c_props=dict(SHARING_OFF, locked=True))
    catch_locked(page)
    select(page, b)
    h0 = len(history(page))
    page.locator('#power-splitters-enabled').click()
    landed(page)
    assert raw(page, [a, b, c]) == [[False, 3], [True, 3], [False, 3]], (
        raw(page, [a, b, c]))
    assert len(history(page)) == h0, history(page)
    assert ['C'] in page.evaluate("() => window.__nf.errors")
    assert box(page)['checked'] is False

    a, b, c = old_wall(page, c_props={'locked': True})
    catch_locked(page)
    select(page, b)
    page.locator('#power-splitters-enabled').click()
    landed(page)
    assert raw(page, [a, b, c]) == [[True, 3]] * 3, raw(page, [a, b, c])
    assert page.evaluate("() => window.__nf.errors") == []


def test_a_custom_fill_on_a_member_follows_the_box_it_shows(page):
    """Custom group, nothing drawn, A sharing off: B selected shows the
    box off; ticked there, a three-column fill on B is ONE 3fer of three
    column runs (it used to tick B only, and the fill - which reads the
    wall's owner, A - poured one 15-cabinet run)."""
    a, b, c = three(page)
    page.evaluate("""(ids) => {
        const app = window.app;
        ids.forEach(id => { const l = window.__nf.layer(id);
            l.powerFlowPattern = 'custom'; });
        app.updateLayers(ids.map(id => window.__nf.layer(id)));
        app.resetHistory('Custom');
    }""", [a, b, c])
    landed(page)
    select(page, b)
    assert box(page)['checked'] is False, box(page)
    page.locator('#power-splitters-enabled').click()
    landed(page)
    assert fill(page, [(b, 0, 2)])
    out = circuits(page, a)
    assert [(c_['num'], c_['runs']) for c_ in out] == [(1, [5, 5, 5])], out
    assert out[0]['on'] == [b], out
    assert gangs(page, a) == [{'num': 1, 'ways': 3, 'over': False}]


def test_an_auto_group_packs_every_member_by_the_wall_setting(page):
    """An auto group of two wattages (each member packs alone): A sharing
    off, B on. B packs by the wall's setting - plain circuits - and
    ticking the box on B shares both."""
    a, b = make(page, [{'name': 'A', 'columns': 4, 'props': SHARING_OFF},
                       {'name': 'B', 'columns': 4, 'x': 1000,
                        'props': {'panelWatts': 100}}], group=True)
    assert all(len(c_['runs']) == 1 for c_ in circuits(page, b)), (
        f'B must follow the wall (sharing off): {circuits(page, b)}')
    select(page, b)
    page.locator('#power-splitters-enabled').click()
    landed(page)
    assert any(len(c_['runs']) > 1 for c_ in circuits(page, a)), circuits(page, a)
    assert any(len(c_['runs']) > 1 for c_ in circuits(page, b)), circuits(page, b)


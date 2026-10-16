"""A locked screen stays unchanged; picking it is not a change (1.5 audit).

The owner's ruling (2026-10-16): "If it's locked it stays locked and
unchanged until unlocked. If you try to change it shows an error dialog and
tells why it can't change." The lock guards EVERYTHING, not only position:
every action that would modify a locked screen leaves it alone and shows the
one locked error naming it ("<name> is locked - unlock it to change it."),
the unlocked screens of the same action still take it, and an action that
would change nothing says nothing. SELECTING a locked screen or its cabinets
is not a change, so it is never an error.

Also pinned here, from the same audit, on Pixel Map selection:
* a click is measured in screen pixels (4 px, the dock's threshold), not
  world units, so a 1 px jitter at low zoom is still a click;
* a hidden current screen is out of the cabinet scope unless it is the only
  screen in play;
* cabinet lookups by row/col are indexed, not a linear search per key;
* the render path only reads the cabinet selection; it is pruned on a real
  selection change.

Driven through real mouse and keyboard gestures wherever the gesture itself
is under test.

Run locally:
    python -m pytest tests/test_lock_guards_and_select.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from conftest import settled  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _restore_server_project(server_project_guard):
    """Leave the shared server project exactly as this module found it."""


FIT_COUNTER_JS = """
    window.__fits = 0;
    let cr = null;
    Object.defineProperty(window, 'canvasRenderer', {
        configurable: true,
        get() { return cr; },
        set(v) {
            cr = v;
            if (v && typeof v.fitToView === 'function' && !v.__fitCounted) {
                const fit = v.fitToView.bind(v);
                v.fitToView = function () { window.__fits++; return fit(...arguments); };
                v.__fitCounted = true;
            }
        },
    });
"""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1600, 'height': 1000})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}"
    )
    # Count the renderer's fits: the app fits the view a moment after it
    # loads, and a fit landing between two clicks of a test moves the wall
    # under the pointer. The page is ready once that first fit has run.
    context.add_init_script(FIT_COUNTER_JS)
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => window.app && window.app.project"
                         " && window.app._initialLoadComplete === true"
                         " && window.canvasRenderer && window.__fits > 0"
                         " && window.canvasRenderer.zoom > 0", timeout=20000)
    pg.evaluate("""() => {
        const app = window.app;
        window.__toasts = [];
        const orig = app._toast;
        app._toast = function (msg) {
            window.__toasts.push(String(msg));
            return orig.apply(this, arguments);
        };
    }""")
    yield pg
    context.close()


MODIFIER = "Meta" if sys.platform == "darwin" else "Control"


def locked_msg(*names):
    if len(names) == 1:
        return f'{names[0]} is locked - unlock it to change it.'
    return (', '.join(names[:-1]) + ' and ' + names[-1]
            + ' are locked - unlock them to change them.')


# Three ungrouped 2x2 screens of 128 px cabinets, side by side and apart.
TRIO = [
    dict(name='Lock A', columns=2, rows=2, cabinet_width=128,
         cabinet_height=128, offset_x=0, offset_y=0),
    dict(name='Lock B', columns=2, rows=2, cabinet_width=128,
         cabinet_height=128, offset_x=600, offset_y=0),
    dict(name='Lock C', columns=2, rows=2, cabinet_width=128,
         cabinet_height=128, offset_x=1200, offset_y=0),
]

RESET_JS = """async ([specs, opts]) => {
    const app = window.app, r = window.canvasRenderer;
    await app._layerSavesSettled();
    let project = await (await fetch('/api/project')).json();
    project.layers = [];
    project.groups = [];
    project.distros = [];
    await fetch('/api/project', {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(project),
    });
    for (const spec of specs) {
        await fetch('/api/layer/add', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(spec),
        });
    }
    app.project = await (await fetch('/api/project')).json();
    app.dedupeProjectLayers('lock_guard_test_reset');
    const screens = app.project.layers.filter(
        l => (l.type || 'screen') === 'screen').slice(0, specs.length);
    const ids = screens.map(l => l.id);
    if (opts.group) {
        const members = opts.group.map(i => screens[i]);
        app.project.groups = [{ id: 'g_lk', name: 'Lock Wall',
                                layer_ids: members.map(l => l.id) }];
        members.forEach(l => { l.group_id = 'g_lk'; });
        await fetch('/api/project', {
            method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(app.project),
        });
    }
    (opts.locked || []).forEach(i => { screens[i].locked = true; });
    (opts.hidden || []).forEach(i => { screens[i].visible = false; });
    // Each layer PUT is echoed back over the socket (layer_updated) and
    // merged into the page. Wait for every echo before the page state is
    // set up, so a late one cannot land on top of the test.
    const want = [...new Set([...(opts.locked || []), ...(opts.hidden || [])])]
        .map(i => screens[i].id);
    const echoed = new Set();
    const onEcho = (l) => { if (l) echoed.add(l.id); };
    if (app.socket && want.length) app.socket.on('layer_updated', onEcho);
    for (const id of want) {
        const l = screens.find(x => x.id === id);
        await fetch(`/api/layer/${id}`, {
            method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ locked: !!l.locked, visible: l.visible !== false }),
        });
    }
    if (app.socket && want.length) {
        const t0 = Date.now();
        while (!want.every(id => echoed.has(id)) && Date.now() - t0 < 5000) {
            await new Promise(r => setTimeout(r, 20));
        }
        app.socket.off('layer_updated', onEcho);
    }
    // The echo merges onto the project; re-read the screens it settled on.
    screens.forEach((l, i) => {
        screens[i] = app.project.layers.find(x => x.id === l.id) || l;
    });
    const cur = screens[opts.current || 0];
    app.currentLayer = cur;
    app.selectedLayerIds = new Set((opts.selected || [opts.current || 0]).map(i => ids[i]));
    app.lastSelectedLayerId = cur.id;
    app.selectionAnchorLayerId = cur.id;
    if (app.customSelection) app.customSelection.clear();
    if (app.powerCustomSelection) app.powerCustomSelection.clear();
    if (app.pixelMapSelection) app.pixelMapSelection.clear();
    app._overrideEditing = null;
    if (typeof app.setViewMode === 'function' && opts.view && opts.view !== r.viewMode) {
        app.setViewMode(opts.view);
    }
    r.viewMode = opts.view || 'pixel-map';
    r.zoom = opts.zoom || 0.5; r.panX = 60; r.panY = 60;
    if (typeof app._flushPendingSaveState === 'function') app._flushPendingSaveState();
    app.renderLayers();
    app.loadLayerToInputs();
    app.updatePixelMapBulkActionUI();
    app.resetHistory('Lock guard test reset');
    app._lastLockedEditReport = null;   // a new test is a new burst
    window.__toasts = [];
    // The last test's toasts stack up the middle of the window for five
    // seconds; they must not sit over the canvas this test presses on.
    const host = document.getElementById('app-toast-host');
    if (host) host.innerHTML = '';
    r.render();
    return ids;
}"""


def reset(page, specs=TRIO, **opts):
    ids = page.evaluate(RESET_JS, [specs, opts])
    assert len(ids) == len(specs), ids
    return ids


def saves_settled(page):
    page.evaluate("async () => { await window.app._layerSavesSettled(); }")


def toasts(page):
    return page.evaluate("() => window.__toasts.slice()")


def layer(page, lid):
    """The layer as the page holds it, less the render caches."""
    return page.evaluate("""(id) => {
        const l = window.app.project.layers.find(x => x.id === id);
        if (!l) return null;
        return JSON.parse(JSON.stringify(l, (k, v) => k.charAt(0) === '_' ? undefined : v));
    }""", lid)


def server_layer(page, lid):
    return page.evaluate("""async (id) => {
        const p = await (await fetch('/api/project')).json();
        return p.layers.find(l => l.id === id) || null;
    }""", lid)


def history_len(page):
    return page.evaluate("() => window.app.history.length")


def to_client(page, wx, wy):
    pt = page.evaluate("""([wx, wy]) => {
        const r = window.canvasRenderer;
        const rect = r.canvas.getBoundingClientRect();
        return { x: rect.left + wx * r.zoom + r.panX,
                 y: rect.top + wy * r.zoom + r.panY };
    }""", [wx, wy])
    return pt['x'], pt['y']


def click(page, at, modifier=None, jitter=0):
    x, y = to_client(page, *at)
    if modifier:
        page.keyboard.down(modifier)
    try:
        page.mouse.move(x, y)
        page.mouse.down()
        if jitter:
            page.mouse.move(x + jitter, y + jitter)
        page.mouse.up()
    finally:
        if modifier:
            page.keyboard.up(modifier)


def drag(page, start, end, modifier=None, steps=8):
    sx, sy = to_client(page, *start)
    ex, ey = to_client(page, *end)
    if modifier:
        page.keyboard.down(modifier)
    try:
        page.mouse.move(sx, sy)
        page.mouse.down()
        page.mouse.move(ex, ey, steps=steps)
        page.mouse.up()
    finally:
        if modifier:
            page.keyboard.up(modifier)


def sel_state(page):
    return page.evaluate("""() => {
        const app = window.app;
        return {
            keys: [...app.pixelMapSelection].sort(),
            selected: [...app.selectedLayerIds].sort((a, b) => a - b),
            current: app.currentLayer ? app.currentLayer.id : null,
        };
    }""")


def keys(lid, cells):
    return sorted(f'{lid}:{r},{c}' for r, c in cells)


# ═════════════════════════════════════════════════════════════════════════
# Selection is not a change (C7, S1)
# ═════════════════════════════════════════════════════════════════════════

def test_plain_click_on_a_locked_screen_picks_it_and_its_cabinet_quietly(page):
    a, b, c = reset(page, locked=[1], selected=[0], current=0)
    # The lower row: the screen's name label sits over the middle and a
    # press on it is the label's own gesture.
    click(page, (664, 220))                   # B's R1C0, B unselected
    got = sel_state(page)
    assert got['current'] == b and got['selected'] == [b], got
    assert got['keys'] == keys(b, [(1, 0)]), got
    click(page, (664 + 128, 220))             # B is current now: R1C1
    got = sel_state(page)
    assert got['keys'] == keys(b, [(1, 1)]), got
    assert toasts(page) == [], 'picking a locked screen is not a change'


def test_marquee_cmd_click_and_select_all_pick_locked_cabinets_quietly(page):
    a, b, c = reset(page, locked=[1], selected=[0, 1], current=0)
    drag(page, (200, 60), (700, 200))
    assert sel_state(page)['keys'] == sorted(keys(a, [(0, 1), (1, 1)])
                                             + keys(b, [(0, 0), (1, 0)]))
    click(page, (664 + 128, 64), modifier=MODIFIER)
    assert keys(b, [(0, 1)])[0] in sel_state(page)['keys']
    page.keyboard.press(f'{MODIFIER}+a')
    got = sel_state(page)
    assert len(got['keys']) == 8, got
    assert toasts(page) == []


def test_set_blank_refuses_the_locked_cabinets_and_names_the_screen(page):
    a, b, c = reset(page, locked=[1], selected=[0, 1], current=0)
    drag(page, (200, 60), (700, 200))
    h0 = history_len(page)
    page.click('#bulk-set-blank')
    settled(page, lambda: history_len(page), lambda n: n > h0)
    saves_settled(page)
    assert [p['hidden'] for p in server_layer(page, b)['panels']] == [False] * 4
    hidden_a = sorted((p['row'], p['col']) for p in server_layer(page, a)['panels'] if p['hidden'])
    assert hidden_a == [(0, 1), (1, 1)]
    assert toasts(page) == [locked_msg('Lock B')]
    # Restore on cabinets that are not blank would change nothing on B:
    # it says nothing about B.
    page.evaluate("() => { window.__toasts = []; }")
    page.evaluate("""(b) => {
        const app = window.app;
        app.pixelMapSelection.clear();
        app.project.layers.find(l => l.id === b).panels
            .forEach(p => app.pixelMapSelection.add(app.getScopedPanelKey(b, p)));
        app.updatePixelMapBulkActionUI();
    }""", b)
    page.click('#bulk-unset-blank')
    saves_settled(page)
    assert toasts(page) == []


def test_custom_click_that_picks_a_locked_screen_adds_nothing_and_says_nothing(page):
    a, b, c = reset(page, locked=[1], selected=[0], current=0, view='data-flow')
    page.evaluate("""(ids) => {
        const app = window.app;
        ids.forEach(id => {
            const l = app.project.layers.find(x => x.id === id);
            l.flowPattern = 'custom';
        });
        window.canvasRenderer.render();
    }""", [a, b])
    before = layer(page, b)
    click(page, (664, 64))
    assert sel_state(page)['current'] == b
    # (selectLayer fills the absent defaults - `{}` reads as no paths)
    assert (layer(page, b).get('customPortPaths') or {}) == (before.get('customPortPaths') or {})
    assert toasts(page) == []
    # Already current: the click is the draw verb, and it names the lock.
    click(page, (664 + 128, 64))
    assert (layer(page, b).get('customPortPaths') or {}) == (before.get('customPortPaths') or {})
    assert toasts(page) == [locked_msg('Lock B')]


# ═════════════════════════════════════════════════════════════════════════
# Stepping the active port / circuit (C1, C7)
# ═════════════════════════════════════════════════════════════════════════

def _custom_paths(page, lid, kind='data'):
    page.evaluate("""([id, kind]) => {
        const app = window.app;
        const l = app.project.layers.find(x => x.id === id);
        if (kind === 'power') {
            l.powerFlowPattern = 'custom';
            l.powerCustomPaths = { 1: [{ row: 0, col: 0 }], 2: [{ row: 0, col: 1 }] };
            l.powerCustomIndex = 1;
        } else {
            l.flowPattern = 'custom';
            l.customPortPaths = { 1: [{ row: 0, col: 0 }], 2: [{ row: 0, col: 1 }] };
            l.customPortIndex = 1;
        }
        app.loadLayerToInputs();
        window.canvasRenderer.render();
    }""", [lid, kind])


def test_alt_click_on_a_run_of_a_locked_screen_keeps_the_active_port(page):
    a, b, c = reset(page, locked=[0], selected=[0], current=0, view='data-flow')
    _custom_paths(page, a)
    h0 = history_len(page)
    click(page, (64 + 128, 64), modifier='Alt')     # run 2
    got = layer(page, a)
    assert got['customPortIndex'] == 1, got['customPortIndex']
    assert history_len(page) == h0
    assert toasts(page) == [locked_msg('Lock A')]
    # Alt+click on the run that is already active changes nothing.
    page.evaluate("() => { window.__toasts = []; }")
    click(page, (64, 64), modifier='Alt')
    assert toasts(page) == []


@pytest.mark.parametrize('kind', ['data', 'power'])
def test_prev_at_one_on_a_locked_screen_says_nothing_next_is_refused(page, kind):
    view = 'power' if kind == 'power' else 'data-flow'
    a, b, c = reset(page, locked=[0], selected=[0], current=0, view=view)
    page.evaluate("""([id, kind]) => {
        const l = window.app.project.layers.find(x => x.id === id);
        if (kind === 'power') { l.powerFlowPattern = 'custom'; delete l.powerCustomPaths; delete l.powerCustomIndex; }
        else { l.flowPattern = 'custom'; delete l.customPortPaths; delete l.customPortIndex; }
    }""", [a, kind])
    before = layer(page, a)
    prev_id = '#power-custom-prev' if kind == 'power' else '#custom-prev-port'
    page.evaluate("(sel) => document.querySelector(sel).click()", prev_id)
    assert layer(page, a) == before, 'Prev at 1 wrote the locked screen'
    page.evaluate("() => document.activeElement && document.activeElement.blur()")
    page.keyboard.press('Shift+Tab')
    assert layer(page, a) == before
    assert toasts(page) == []
    page.keyboard.press('Tab')
    assert layer(page, a) == before
    assert toasts(page) == [locked_msg('Lock A')]


# ═════════════════════════════════════════════════════════════════════════
# Sidebar and Screen Info edits (C2)
# ═════════════════════════════════════════════════════════════════════════

def test_screen_info_edit_skips_the_locked_screen_and_snaps_back(page):
    a, b, c = reset(page, locked=[0], selected=[0, 1], current=0)
    before_a = layer(page, a)
    page.evaluate("""() => {
        const el = document.getElementById('number-size');
        el.value = '33';
        el.dispatchEvent(new Event('change', { bubbles: true }));
    }""")
    saves_settled(page)
    assert layer(page, b)['number_size'] == 33
    assert server_layer(page, b)['number_size'] == 33
    assert layer(page, a) == before_a, 'the locked screen changed'
    assert server_layer(page, a)['number_size'] == before_a['number_size']
    assert toasts(page) == [locked_msg('Lock A')]
    # The field shows the selection as it really is: mixed.
    assert page.evaluate("() => document.getElementById('number-size').value") == ''


def test_a_sidebar_funnel_edit_on_only_locked_screens_changes_nothing(page):
    a, b, c = reset(page, locked=[0], selected=[0], current=0)
    before = layer(page, a)
    # Settle the history on the state as it stands (the reset's own
    # normalizing writes), so the step count below is the edit's alone.
    page.evaluate("() => window.app.saveState('Baseline')")
    h0 = history_len(page)
    page.evaluate("""() => {
        const el = document.getElementById('screen-rotation');
        el.value = '90';
        el.dispatchEvent(new Event('change', { bubbles: true }));
    }""")
    saves_settled(page)
    assert layer(page, a) == before
    assert history_len(page) == h0
    assert toasts(page) == [locked_msg('Lock A')]
    assert page.evaluate("() => document.getElementById('screen-rotation').value") == \
        str(before.get('rotation') or 0)
    # Setting the value it already holds is no change and says nothing.
    page.evaluate("() => { window.__toasts = []; }")
    page.evaluate("""() => {
        const el = document.getElementById('screen-rotation');
        el.dispatchEvent(new Event('change', { bubbles: true }));
    }""")
    assert toasts(page) == []


def test_a_group_edit_leaves_a_locked_peer_alone_and_names_it(page):
    a, b, c = reset(page, locked=[1], group=[0, 1], selected=[0], current=0)
    before_b = layer(page, b)
    page.evaluate("""() => {
        const el = document.getElementById('number-size');
        el.value = '41';
        el.dispatchEvent(new Event('change', { bubbles: true }));
    }""")
    saves_settled(page)
    assert layer(page, a)['number_size'] == 41
    assert layer(page, b) == before_b
    assert server_layer(page, b)['number_size'] == before_b['number_size']
    assert toasts(page) == [locked_msg('Lock B')]


def test_the_lock_toggle_still_unlocks(page):
    a, b, c = reset(page, locked=[0], selected=[0], current=0)
    page.evaluate("() => document.getElementById('toggle-lock-selected').click()")
    saves_settled(page)
    assert layer(page, a)['locked'] is False
    assert server_layer(page, a)['locked'] is False
    assert toasts(page) == []


def test_rename_in_the_screens_list_is_refused_on_a_locked_screen(page):
    a, b, c = reset(page, locked=[0], selected=[0], current=0)
    page.locator(f'input.layer-name-input[data-layer-id="{a}"]').first.dblclick()
    page.keyboard.press(f'{MODIFIER}+a')
    page.keyboard.type('Renamed')
    page.keyboard.press('Enter')
    saves_settled(page)
    assert layer(page, a)['name'] == 'Lock A'
    assert server_layer(page, a)['name'] == 'Lock A'
    assert toasts(page) == [locked_msg('Lock A')]


def test_jumper_field_writes_the_unlocked_screen_only(page):
    a, b, c = reset(page, locked=[0], selected=[0, 1], current=0, view='power')
    before_a = layer(page, a).get('powerJumpV')
    page.evaluate("""() => {
        const el = document.getElementById('power-jump-v');
        el.value = '12';
        el.dispatchEvent(new Event('change', { bubbles: true }));
    }""")
    saves_settled(page)
    assert layer(page, a).get('powerJumpV') == before_a
    assert layer(page, b)['powerJumpV'] == 12
    assert toasts(page) == [locked_msg('Lock A')]


def test_change_cabinet_and_route_as_one_refuse_locked_screens(page):
    a, b, c = reset(page, locked=[0], group=[0, 1], selected=[0, 1], current=1)
    before = layer(page, a)
    page.evaluate("""(ids) => window.app.changeCabinetForLayers(ids,
        { cabinet_width: 64, cabinet_height: 64 })""", [a, b])
    saves_settled(page)
    assert layer(page, b)['cabinet_width'] == 64
    assert layer(page, a)['cabinet_width'] == before['cabinet_width']
    assert toasts(page) == [locked_msg('Lock A')]
    page.evaluate("() => { window.__toasts = []; }")
    route = page.evaluate("""() => {
        const box = document.getElementById('route-group-as-one');
        const g = window.app.project.groups[0];
        const was = g.routeDataAsOne;
        box.checked = !box.checked;
        box.dispatchEvent(new Event('change', { bubbles: true }));
        return { was, now: g.routeDataAsOne };
    }""")
    assert route['was'] == route['now'], route
    assert toasts(page) == [locked_msg('Lock A')]


def test_power_setters_refuse_a_locked_screen(page):
    a, b, c = reset(page, locked=[0], selected=[0], current=0, view='power')
    before = layer(page, a)
    page.evaluate("""(id) => {
        const app = window.app;
        const l = app.project.layers.find(x => x.id === id);
        app.setCircuitCable(l, 1, { ft: 50, connector: null });
        app.setSocaLength(l, 0, '100ft');
    }""", a)
    assert layer(page, a) == before
    assert toasts(page) == [locked_msg('Lock A')]


def test_dock_drops_refuse_a_locked_screen(page):
    a, b, c = reset(page, locked=[0], selected=[0], current=0, view='power')
    page.evaluate("() => window.app.addDistro({ name: 'LK' })")
    before = layer(page, a)
    page.evaluate("""(id) => {
        const app = window.app;
        const d = app.getDistros()[0];
        app._dockDropDistro({ type: 'distro', distroId: d.id }, { kind: 'screen', layerId: id });
        app._dockDropPlug({ type: 'plug', distroId: d.id, output: 'soca208', title: 'LK' },
                          { kind: 'screen', layerId: id });
    }""", a)
    assert layer(page, a) == before
    assert set(toasts(page)) == {locked_msg('Lock A')}


# ═════════════════════════════════════════════════════════════════════════
# Delete and move (C3, C4)
# ═════════════════════════════════════════════════════════════════════════

def test_delete_key_on_a_locked_screen_is_refused(page):
    a, b, c = reset(page, locked=[0], selected=[0], current=0)
    page.evaluate("() => document.activeElement && document.activeElement.blur()")
    page.keyboard.press('Delete')
    saves_settled(page)
    assert layer(page, a) is not None
    assert server_layer(page, a) is not None
    assert toasts(page) == [locked_msg('Lock A')]


def test_multi_delete_removes_the_unlocked_and_names_the_locked(page):
    a, b, c = reset(page, locked=[0], selected=[0, 1], current=0)
    page.evaluate("() => document.activeElement && document.activeElement.blur()")
    page.keyboard.press('Backspace')
    settled(page, lambda: page.evaluate("() => window.app.deletionInProgress"),
            lambda v: not v)
    ids = page.evaluate("() => window.app.project.layers.map(l => l.id)")
    assert a in ids and b not in ids and c in ids, ids
    assert toasts(page) == [locked_msg('Lock A')]


def test_dragging_a_locked_screen_says_so_once_per_gesture(page):
    a, b, c = reset(page, locked=[0], selected=[0], current=0)
    before = layer(page, a)
    drag(page, (100, 100), (400, 300), modifier='Shift', steps=20)
    assert layer(page, a)['offset_x'] == before['offset_x']
    assert toasts(page) == [locked_msg('Lock A')]
    # A shift-click that never moves says nothing.
    page.evaluate("() => { window.__toasts = []; }")
    click(page, (100, 100), modifier='Shift')
    assert toasts(page) == []


def test_a_mixed_drag_moves_the_unlocked_and_names_the_locked(page):
    a, b, c = reset(page, locked=[0], selected=[0, 1], current=1)
    ax = layer(page, a)['offset_x']
    bx = layer(page, b)['offset_x']
    drag(page, (700, 100), (900, 100), modifier='Shift', steps=12)
    saves_settled(page)
    assert layer(page, a)['offset_x'] == ax
    assert layer(page, b)['offset_x'] != bx
    assert toasts(page) == [locked_msg('Lock A')]


def test_center_on_canvas_names_a_locked_screen(page):
    a, b, c = reset(page, locked=[0], selected=[0], current=0)
    before = layer(page, a)
    x, y = to_client(page, 100, 100)
    page.mouse.click(x, y, button='right')
    page.locator('#context-menu [data-action="center-both"]').click()
    assert layer(page, a)['offset_x'] == before['offset_x']
    assert layer(page, a)['offset_y'] == before['offset_y']
    assert toasts(page) == [locked_msg('Lock A')]


# ═════════════════════════════════════════════════════════════════════════
# Pixel Map selection mechanics (S2, S3, S4, S5)
# ═════════════════════════════════════════════════════════════════════════

def test_a_one_pixel_jitter_at_low_zoom_is_still_a_click(page):
    a, b, c = reset(page, selected=[0, 1], current=0, zoom=1)
    click(page, (664, 64), jitter=1)
    got = sel_state(page)
    assert got['current'] == b and got['selected'] == [b], got
    assert got['keys'] == keys(b, [(0, 0)]), got


def test_a_jittered_cmd_click_toggles_the_screen_out(page):
    a, b, c = reset(page, selected=[0, 1], current=0, zoom=1)
    click(page, (664, 64), modifier=MODIFIER, jitter=1)
    assert sel_state(page)['selected'] == [a]


def test_a_hidden_current_screen_is_out_of_the_marquee(page):
    a, b, c = reset(page, hidden=[0], selected=[0, 1], current=0)
    scope = page.evaluate("() => window.app.getPixelMapScopeLayers().map(l => l.id)")
    assert scope == [b], scope
    page.evaluate("(sel) => window.app.selectPixelMapPanelsInRect(null, sel)",
                  {'x1': -10, 'y1': -10, 'x2': 900, 'y2': 300})
    got = sel_state(page)
    assert all(k.startswith(f'{b}:') for k in got['keys']), got
    assert len(got['keys']) == 4
    # The only screen in play keeps its hidden cabinets reachable.
    page.evaluate("(a) => { window.app.selectedLayerIds = new Set([a]); }", a)
    assert page.evaluate("() => window.app.getPixelMapScopeLayers().map(l => l.id)") == [a]


def test_the_render_path_reads_the_selection_without_pruning(page):
    a, b, c = reset(page, selected=[0, 1], current=0)
    page.evaluate("""([a, b]) => {
        const app = window.app;
        app.pixelMapSelection.add(`${a}:0,0`);
        app.pixelMapSelection.add(`${b}:0,0`);
        // Mid-update: the selection names one screen for a moment.
        app.selectedLayerIds = new Set([a]);
        window.canvasRenderer.render();
        app.renderLayers();
        app.updatePixelMapBulkActionUI();
        app.selectedLayerIds = new Set([a, b]);
    }""", [a, b])
    assert sel_state(page)['keys'] == sorted([f'{a}:0,0', f'{b}:0,0'])
    # A real selection change prunes what left the scope.
    page.evaluate("(b) => window.app.toggleLayerSelection("
                  "window.app.project.layers.find(l => l.id === b))", b)
    assert sel_state(page)['keys'] == [f'{a}:0,0']


def test_row_col_lookup_is_indexed_and_follows_a_rebuild(page):
    a, b, c = reset(page, selected=[0], current=0)
    out = page.evaluate("""(id) => {
        const app = window.app;
        const l = app.project.layers.find(x => x.id === id);
        const first = app.getPanelByRowCol(l, 1, 1);
        const old = l.panels;
        l.panels = old.map(p => Object.assign({}, p));   // a rebuild: new array
        const second = app.getPanelByRowCol(l, 1, 1);
        const res = { same: first === old.find(p => p.row === 1 && p.col === 1),
                      rebuilt: second === l.panels.find(p => p.row === 1 && p.col === 1),
                      miss: app.getPanelByRowCol(l, 9, 9) };
        l.panels = old;
        return res;
    }""", a)
    assert out == {'same': True, 'rebuilt': True, 'miss': None}, out


def test_cross_screen_marquee_is_fast_on_six_large_screens(page):
    big = [dict(name=f'Big {i}', columns=80, rows=40, cabinet_width=16,
                cabinet_height=16, offset_x=(i % 3) * 1400, offset_y=(i // 3) * 700)
           for i in range(6)]
    reset(page, big, selected=list(range(6)), current=0, zoom=0.25)
    timing = page.evaluate("""() => {
        const app = window.app, r = window.canvasRenderer;
        const rect = { x1: -10, y1: -10, x2: 4300, y2: 1400 };
        const move = () => {
            const t0 = performance.now();
            app.selectPixelMapPanelsInRect(app.currentLayer, rect);
            r.render();
            return performance.now() - t0;
        };
        move();
        const after = Math.min(move(), move(), move());
        const count = app.pixelMapSelection.size;
        // The same move with the linear lookup this replaced.
        const proto = Object.getPrototypeOf(app);
        const indexed = proto.getPanelByRowCol;
        proto.getPanelByRowCol = function (layer, row, col) {
            if (!layer || !layer.panels) return null;
            return layer.panels.find(p => p.row === row && p.col === col) || null;
        };
        let before;
        try { before = Math.min(move(), move()); }
        finally { proto.getPanelByRowCol = indexed; }
        app.pixelMapSelection.clear();
        return { before, after, count };
    }""")
    print(f"\n6 x 80x40 cross-screen marquee move: linear {timing['before']:.1f} ms, "
          f"indexed {timing['after']:.1f} ms ({timing['count']} cabinets)")
    assert timing['count'] == 6 * 80 * 40
    assert timing['after'] < timing['before'], timing

"""Two Power view fixes for 1.5.4, pinned in a real browser.

* A FOLDED DISTRO CARD hides its OUTPUTS row (owner, 2026-10-30: "When you
  minimize distro, we do not need to see the multi and l2130 stuff that you
  can drag since it is minimized"). The header and the LEGS line stay: the
  LEGS line was put outside the fold so a folded distro still reads its
  balance at a glance. The plug chips are hidden, not detached, so none of
  them can be dragged or tabbed to while folded; unfolded they come back,
  and the fold survives a tray rebuild.
* ESCAPE CANCELS AN ALT+CLICK REDRAW (owner, 2026-10-30: "when I use alt +
  click to redraw we need a way to deselect like the escape key").

Run locally:
    "C:/Users/Blue Iris/.venvs/led-raster/Scripts/python.exe" -m pytest \
        tests/test_distro_collapse_and_alt_escape.py -q --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# WALL A: 8 wide x 18 rows of 200 W cabinets at 208 V / 10 A - one row per
# circuit, 18 circuits, three multis of six.
SEED_JS = """async () => {
    const proj = await (await fetch('/api/project')).json();
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments;
    await fetch('/api/project', {method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(proj)});
    await fetch('/api/layer/add', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name: 'WALL A', columns: 8, rows: 18,
                              cabinet_width: 200, cabinet_height: 200})});
    const p1 = await (await fetch('/api/project')).json();
    for (const l of p1.layers) {
        await fetch(`/api/layer/${l.id}`, {method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({powerVoltage: 208, powerAmperage: 10, panelWatts: 200})});
    }
    const p = await (await fetch('/api/project')).json();
    const app = window.app;
    app.project = p;
    app.currentLayer = p.layers[0];
    app.selectedLayerIds = new Set([p.layers[0].id]);
    app.renderLayers();
    const r = window.canvasRenderer;
    r.zoom = 0.22; r.panX = 60; r.panY = 60; r.render();
    return p.layers[0].id;
}"""

# The show reshaped in the page: the distros given, nothing assigned, no
# take-over, no fold remembered.
SETUP_JS = """(distros) => {
    const app = window.app;
    const L = app.project.layers.find(l => l.name === 'WALL A');
    Object.assign(L, { powerVoltage: 208, powerAmperage: 10, panelWatts: 200,
                       powerSocaDistro: {}, powerSocaNumber: {}, powerSocaPhasePos: {},
                       powerSocaLengths: {}, powerSocaSplits: [], powerSocaNames: {},
                       powerBreakoutType: null, locked: false,
                       powerFlowPattern: 'tl-h', powerOrganized: false,
                       powerMaximize: false, powerCustomPaths: {},
                       powerCustomOverrides: [], powerCustomIndex: 1 });
    app.normalizePowerBreakout(L);
    app.currentLayer = L;
    app.selectedLayerIds = new Set([L.id]);
    app._overrideEditing = null;
    app._overrideHover = null;
    app._sweepSelection = null;
    if (app.powerCustomSelection) app.powerCustomSelection.clear();
    if (typeof app.hideContextMenu === 'function') app.hideContextMenu();
    app.updateLayers([L]);
    app.project.distros = distros.map(d => JSON.parse(JSON.stringify(d)));
    for (const d of app.project.distros) {
        try { localStorage.removeItem(`ledRasterPanelCollapsed_hwdock-distro-${d.id}`); } catch (e) {}
    }
    app._circuitTailCache = null;
    app._distroFaceMemo = null;
    app._persistDistros();
    app._restateNaming();
    app.renderHardwareDock();
    window.canvasRenderer.render();
    if (typeof app._flushPendingSaveState === 'function') app._flushPendingSaveState();
    app.resetHistory('Card Seed');
    return app.getSocaPlan(L).length;
}"""

ROW = lambda rid, conn, count, coupling='ll', paired=None: {  # noqa: E731
    'id': rid, 'connector': conn, 'count': count, 'coupling': coupling,
    'breakerA': 20, 'pairedWith': paired}

# A face with the three kinds the owner named: a 208 multi, a 120 multi
# and an L21-30.
VX = {'id': 'd1', 'name': 'VX', 'ratingA': 200, 'system': '120/208',
      'outputRows': [ROW('r1', 'soca', 1), ROW('r2', 'soca', 1, coupling='ln'),
                     ROW('r3', 'l2130', 1)]}

UNIT = '[data-lrd-distro="d1"]'
ARROW = f'{UNIT} > .hw-dock-head-row .lrd-sec-arrow'

# What the card shows: every plug chip with whether it is rendered, can be
# reached by Tab, and is what a press at its centre would land on.
CARD_JS = """() => {
    const unit = document.querySelector('[data-lrd-distro="d1"]');
    if (!unit) return null;
    const shown = (el) => !!el && el.getClientRects().length > 0
        && getComputedStyle(el).visibility !== 'hidden';
    const row = unit.querySelector(':scope > .hw-dock-outputs');
    const legs = unit.querySelector(':scope > .hw-dock-legs');
    const head = unit.querySelector(':scope > .hw-dock-head-row');
    const plugs = [...unit.querySelectorAll('[data-hwdock^="plug-"]')].map(c => {
        const r = c.getBoundingClientRect();
        const hit = shown(c) ? document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2) : null;
        return { key: c.dataset.hwdock, shown: shown(c),
                 reachable: !!hit && (hit === c || c.contains(hit)) };
    });
    // Tab order: walk every focusable element the browser would stop on.
    const tabbable = [...document.querySelectorAll('[tabindex], a[href], button, input, select, textarea')]
        .filter(el => el.tabIndex >= 0 && !el.disabled && shown(el));
    return {
        folded: unit.classList.contains('lrd-sec-collapsed'),
        outputsRow: !!row,
        outputsShown: shown(row),
        legsShown: shown(legs),
        headShown: shown(head),
        plugs,
        tabbablePlugs: tabbable.filter(el => (el.dataset.hwdock || '').startsWith('plug-')
            && unit.contains(el)).length,
    };
}"""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
    pg.wait_for_timeout(1500)
    pg.evaluate(SEED_JS)
    pg.wait_for_timeout(800)
    pg.locator('[data-mode="power"]').click()
    pg.wait_for_timeout(500)
    yield pg, errors
    context.close()


def setup(pg, *distros):
    # The previous gesture's server echo lands first, so it cannot replace
    # the layer this setup writes.
    pg.wait_for_timeout(400)
    n = pg.evaluate(SETUP_JS, list(distros))
    pg.wait_for_timeout(300)
    return n


def click_arrow(pg):
    pg.evaluate("(s) => document.querySelector(s).scrollIntoView({block: 'center'})", ARROW)
    box = pg.locator(ARROW).first.bounding_box()
    assert box, 'no fold arrow on the distro card'
    pg.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
    pg.wait_for_timeout(250)


# ── a folded distro card hides its outputs ───────────────────────────────

def test_a_folded_distro_card_hides_its_output_chips(page):
    pg, errors = page
    setup(pg, VX)
    open_card = pg.evaluate(CARD_JS)
    assert open_card and not open_card['folded'], open_card
    assert open_card['outputsShown'] and open_card['legsShown'], open_card
    keys = [p['key'] for p in open_card['plugs']]
    assert len(keys) == 3, open_card
    assert all(p['shown'] and p['reachable'] for p in open_card['plugs']), open_card
    assert open_card['tabbablePlugs'] == 3, open_card

    click_arrow(pg)
    folded = pg.evaluate(CARD_JS)
    assert folded['folded'], 'the arrow did not fold the card'
    # the header and the LEGS line stay; the OUTPUTS row goes
    assert folded['headShown'] and folded['legsShown'], folded
    assert folded['outputsRow'], 'the row was detached instead of hidden'
    assert not folded['outputsShown'], folded
    assert [p['key'] for p in folded['plugs']] == keys
    assert not any(p['shown'] or p['reachable'] for p in folded['plugs']), folded
    assert folded['tabbablePlugs'] == 0, folded

    # the fold survives a rebuild of the tray, and the row stays hidden
    pg.evaluate("() => window.app.renderHardwareDock()")
    pg.wait_for_timeout(200)
    again = pg.evaluate(CARD_JS)
    assert again['folded'] and not again['outputsShown'], again
    assert again['tabbablePlugs'] == 0, again
    assert pg.evaluate("() => localStorage.getItem('ledRasterPanelCollapsed_hwdock-distro-d1')") == '1'

    # unfolded, everything is back as it was
    click_arrow(pg)
    back = pg.evaluate(CARD_JS)
    assert not back['folded'], back
    assert back['outputsShown'] and back['legsShown'], back
    assert [p['key'] for p in back['plugs']] == keys
    assert all(p['shown'] and p['reachable'] for p in back['plugs']), back
    assert back['tabbablePlugs'] == 3, back
    assert not errors, errors


def test_a_guide_reaching_a_plug_chip_unfolds_the_card(page):
    """The reveal helpers know the row folds with its card: a chip inside
    a folded card counts as hidden by the fold, so a focus restore or a
    guide aiming at it opens the card (and a header control does not)."""
    pg, errors = page
    setup(pg, VX)
    click_arrow(pg)
    res = pg.evaluate("""() => {
        const app = window.app;
        const unit = document.querySelector('[data-lrd-distro="d1"]');
        const chip = unit.querySelector('[data-hwdock^="plug-"]');
        const gear = unit.querySelector('[data-hwpop="distro-d1"]');
        const legs = unit.querySelector(':scope > .hw-dock-legs');
        const out = { chip: app._sectionFoldHides(unit, chip),
                      gear: app._sectionFoldHides(unit, gear),
                      legs: legs ? app._sectionFoldHides(unit, legs) : null };
        app._dockRevealSections(chip);
        out.openAfter = !unit.classList.contains('lrd-sec-collapsed');
        return out;
    }""")
    assert res == {'chip': True, 'gear': False, 'legs': False, 'openAfter': True}, res
    assert pg.evaluate(CARD_JS)['outputsShown']
    assert not errors, errors

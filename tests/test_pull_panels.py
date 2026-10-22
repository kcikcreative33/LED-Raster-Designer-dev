"""Panel counts on the pull sheet (owner, 2026-10-22: "we need to have the
pull sheet include panel counts").

  * One row per panel type a screen hangs, EA, under the screen's own
    position and labelled with its name; TOTALS add them up across the
    show. Two screens of one type on one position (a group's members)
    merge into one row, "WALL-A, WALL-B".
  * The type is the panel library's name for the cabinet, found by its
    size and weight ("ROE Black Quartz 3.9 Full Tile"); a cabinet the
    library cannot name is its size in the show's unit ('19.7" × 19.7"
    panel' in a feet show, "500 × 500 mm panel" in a meters one).
  * A half tile is a row of its own: the library's matching half where it
    has one, else "<name> half"; a square cabinet's two halves are one
    cabinet turned, any other's are told apart by their sizes.
  * Blank and hidden cabinets, and hidden screens, count none.
  * The rows are side 'panel': on the pull sheet, its TOTALS, the xlsx,
    the GEAR LIST and the binder's pull pages (a Panels block), never on a
    screen's CABLES THIS SCREEN table or a hardware pull list. A pull-sheet
    edit (hide, count) works on them like any other row.

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_pull_panels.py -v --browser chromium
"""

import io
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))
sys.path.insert(0, HERE)

openpyxl = pytest.importorskip('openpyxl', reason='openpyxl not installed')
pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# QUARTZ: the library's ROE Black Quartz 3.9 Full Tile (500 x 1000 mm,
# 128 x 256 px, 22 kg - no other model has those figures), 4 x 3, its last
# row half tiles halved in height (the library's Half Tile), one cabinet
# halved in width (no library match: "<name> half" with its size), one
# blank and one hidden cabinet. WALL-A (3 x 2) and WALL-B (2 x 2) are a
# group of 500 x 500 mm cabinets the library cannot name, WALL-B with one
# half tile; FLOOR (2 x 1) the same cabinet on its own; GHOST a hidden
# screen.
SEED_JS = """async () => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.pullSheetEdits;
    delete proj.cableUnit; delete proj.beaches;
    await j('PUT', '/api/project', proj);
    const add = (body) => j('POST', '/api/layer/add', body);
    const plain = {cabinet_width: 128, cabinet_height: 128, panel_width_mm: 500, panel_height_mm: 500,
                   panel_weight: 20, weight_unit: 'kg', powerVoltage: 208, powerAmperage: 20, panelWatts: 100};
    await add({name: 'QUARTZ', columns: 4, rows: 3, cabinet_width: 128, cabinet_height: 256,
               panel_width_mm: 500, panel_height_mm: 1000, panel_weight: 22, weight_unit: 'kg',
               halfLastRow: true, powerVoltage: 208, powerAmperage: 20, panelWatts: 100});
    await add({name: 'WALL-A', columns: 3, rows: 2, ...plain});
    await add({name: 'WALL-B', columns: 2, rows: 2, ...plain});
    await add({name: 'FLOOR', columns: 2, rows: 1, ...plain});
    await add({name: 'GHOST', columns: 2, rows: 2, ...plain});
    let p = await j('GET', '/api/project');
    const byName = (n) => p.layers.find(l => l.name === n);
    p.groups = [{id: 'g1', name: 'SR Beach', layer_ids: [byName('WALL-A').id, byName('WALL-B').id]}];
    byName('GHOST').visible = false;
    await j('PUT', '/api/project', p);
    p = await j('GET', '/api/project');
    app.project = p;
    app.dedupeProjectLayers('pull_panels_setup');
    const L = (n) => app.project.layers.find(l => l.name === n);
    const at = (l, r, c) => l.panels.find(x => x.row === r && x.col === c);
    at(L('QUARTZ'), 0, 3).halfTile = 'width';
    at(L('QUARTZ'), 0, 0).blank = true;
    at(L('QUARTZ'), 1, 0).hidden = true;
    at(L('WALL-B'), 1, 1).halfTile = 'height';
    await app.pullPanelCatalogReady();
    app.renderLayers();
    app.resetHistory('Pull Panels Seed');
    return {quartz: L('QUARTZ').id, a: L('WALL-A').id, b: L('WALL-B').id, floor: L('FLOOR').id,
            ghost: L('GHOST').id,
            halves: L('QUARTZ').panels.filter(x => x.halfTile === 'height').length};
}"""

LIST_JS = """() => {
    const app = window.app;
    app._circuitTailCache = null;
    return JSON.parse(JSON.stringify(app.buildPullList()));
}"""

SHEET_JS = """() => {
    const app = window.app;
    app._circuitTailCache = null;
    return JSON.parse(JSON.stringify(app.buildPullSheet()));
}"""

FULL = 'ROE Black Quartz 3.9 Full Tile'
HALF = 'ROE Black Quartz 3.9 Half Tile'
SIDE_HALF = 'ROE Black Quartz 3.9 Full Tile half (9.8" × 39.4")'
PLAIN = '19.7" × 19.7" panel'
PLAIN_HALF = '19.7" × 9.8" half panel'


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
    ids = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(800)
    assert ids['halves'] == 4, f'fixture: QUARTZ\'s last row is half tiles: {ids}'
    yield pg, ids, errors
    context.close()


def _clear_edits(pg):
    pg.evaluate("""async () => {
        const app = window.app;
        delete app.project.pullSheetEdits;
        await fetch('/api/project', {method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({pullSheetEdits: {positions: {}}})});
    }""")


@pytest.fixture()
def seeded(page):
    """The seeded page with no pull-sheet edits after the test."""
    yield page
    _clear_edits(page[0])


def _panels(rows):
    return [(r['type'], r['length'], r['qty'], r['label'], r['notes'])
            for r in rows if r.get('side') == 'panel']


def test_each_screen_counts_its_panels_by_type_under_its_own_position(seeded):
    pg, ids, errors = seeded
    out = pg.evaluate(LIST_JS)
    by = {p['name']: p for p in out['positions']}
    # GHOST is hidden: no position, no panels
    assert sorted(by) == ['FLOOR', 'QUARTZ', 'SR Beach'], sorted(by)
    # 12 cabinets: 4 half tiles (height), 1 halved in width, 1 blank and
    # 1 hidden - 5 full ones hang
    assert _panels(by['QUARTZ']['rows']) == [
        (FULL, 'EA', 5, 'QUARTZ', ''),
        (SIDE_HALF, 'EA', 1, 'QUARTZ', ''),
        (HALF, 'EA', 4, 'QUARTZ', ''),
    ]
    # the group: both members' cabinets of one type on one row, the
    # screens in the label; WALL-B's half tile its own row
    # (the sheet's natural sort: 9.8" before 19.7")
    assert _panels(by['SR Beach']['rows']) == [
        (PLAIN_HALF, 'EA', 1, 'WALL-B', ''),
        (PLAIN, 'EA', 9, 'WALL-A, WALL-B', ''),
    ]
    assert _panels(by['FLOOR']['rows']) == [(PLAIN, 'EA', 2, 'FLOOR', '')]
    # TOTALS add them up across the show
    assert _panels(out['totals']) == [
        (PLAIN_HALF, 'EA', 1, 'WALL-B', ''),
        (PLAIN, 'EA', 11, 'WALL-A, WALL-B, FLOOR', ''),
        (FULL, 'EA', 5, 'QUARTZ', ''),
        (SIDE_HALF, 'EA', 1, 'QUARTZ', ''),
        (HALF, 'EA', 4, 'QUARTZ', ''),
    ]
    # the screens' own readings (CABLES THIS SCREEN) and the hardware pull
    # lists carry no panel row
    for scr in out['byScreen'].values():
        assert not [r for r in scr['rows'] + scr['rowsOn'] if r.get('side') == 'panel'], scr['name']
    for h in out['hardware']:
        assert not [r for r in h['rows'] if r.get('side') == 'panel'], h['name']
    assert errors == []


def test_a_square_cabinets_halves_are_one_type_and_the_library_names_its_half(seeded):
    pg, ids, _ = seeded
    got = pg.evaluate("""(ids) => {
        const app = window.app;
        const L = (id) => app.project.layers.find(l => l.id === id);
        return {quartz: app.pullPanelTypes(L(ids.quartz)), wall: app.pullPanelTypes(L(ids.a)),
                ruby: app.pullPanelTypes({panel_width_mm: 500, panel_height_mm: 500, cabinet_width: 256,
                                          cabinet_height: 256, panel_weight: 9.2, weight_unit: 'kg'}),
                bp2: app.pullPanelTypes({panel_width_mm: 500, panel_height_mm: 500, cabinet_width: 176,
                                         cabinet_height: 176, panel_weight: 9.35, weight_unit: 'kg'}),
                typed: app.pullPanelTypes({panel_width_mm: 600, panel_height_mm: 337.5, cabinet_width: 192,
                                           cabinet_height: 108, panel_weight: 9, weight_unit: 'kg'})};
    }""", ids)
    assert got['quartz'] == {'none': FULL, 'height': HALF, 'width': SIDE_HALF}, got['quartz']
    assert got['wall'] == {'none': PLAIN, 'height': PLAIN_HALF, 'width': PLAIN_HALF}, got['wall']
    # a square library model with no half in the library: "<name> half",
    # one row whichever way it is halved
    assert got['ruby'] == {'none': 'ROE Ruby 1.9B V2', 'height': 'ROE Ruby 1.9B V2 half',
                           'width': 'ROE Ruby 1.9B V2 half'}, got['ruby']
    # figures four library models share (BP2, BP2V2, ...) name none of them
    assert got['bp2'] == {'none': PLAIN, 'height': PLAIN_HALF, 'width': PLAIN_HALF}, got['bp2']
    # a cabinet typed by hand, not square: its halves differ
    assert got['typed'] == {'none': '23.6" × 13.3" panel', 'height': '23.6" × 6.6" half panel',
                            'width': '11.8" × 13.3" half panel'}, got['typed']


def test_a_meters_show_says_the_size_in_mm(seeded):
    pg, ids, _ = seeded
    got = pg.evaluate("""(ids) => {
        const app = window.app;
        const was = app.project.cableUnit;
        app.project.cableUnit = 'm';
        try {
            app._circuitTailCache = null;
            const list = JSON.parse(JSON.stringify(app.buildPullList()));
            return list.positions.find(p => p.name === 'SR Beach').rows;
        } finally {
            if (was === undefined) delete app.project.cableUnit; else app.project.cableUnit = was;
        }
    }""", ids)
    assert _panels(got) == [
        ('500 × 250 mm half panel', 'EA', 1, 'WALL-B', ''),
        ('500 × 500 mm panel', 'EA', 9, 'WALL-A, WALL-B', ''),
    ]


def test_an_edit_on_a_panel_row_reaches_the_sheet_and_its_totals(seeded):
    pg, ids, _ = seeded
    sheet = pg.evaluate("""([ids, plain, half]) => {
        const app = window.app;
        const engine = app.buildPullList();
        const sr = engine.positions.find(p => p.name === 'SR Beach');
        const row = sr.rows.find(r => r.type === plain);
        app.setPullSheetRowEdit(app.pullPositionKey(sr), app.pullRowKey(row), {qty: 12}, row);
        const q = engine.positions.find(p => p.name === 'QUARTZ');
        app.removePullSheetRow(app.pullPositionKey(q), `${half}|EA`);
        app._circuitTailCache = null;
        return JSON.parse(JSON.stringify(app.buildPullSheet()));
    }""", [ids, PLAIN, HALF])
    by = {p['name']: p for p in sheet['positions']}
    assert _panels(by['SR Beach']['rows'])[1] == (PLAIN, 'EA', 12, 'WALL-A, WALL-B', '')
    assert HALF not in [r['type'] for r in by['QUARTZ']['rows']]
    totals = {r['type']: r for r in sheet['totals'] if r.get('side') == 'panel'}
    assert totals[PLAIN]['qty'] == 14 and HALF not in totals, totals
    # the screens' readings are untouched by it
    for scr in sheet['byScreen'].values():
        assert not [r for r in scr['rows'] if r.get('side') == 'panel']
    # the edit is the user's: undo takes it back
    pg.evaluate("() => window.app.undo()")
    pg.evaluate("() => window.app.undo()")
    back = pg.evaluate(SHEET_JS)
    totals = {r['type']: r['qty'] for r in back['totals'] if r.get('side') == 'panel'}
    assert totals[PLAIN] == 11 and totals[HALF] == 4, totals


def test_a_free_row_naming_a_panel_lands_on_the_panel_side(seeded):
    pg, _, _ = seeded
    got = pg.evaluate("""([full, plain]) => {
        const app = window.app;
        return [full, full.toUpperCase(), plain, 'Spare panel', 'Half tile', 'Socapex panel',
                'Cat6 Barrel', 'Shackle'].map(t => app.pullGuessSide(t));
    }""", [FULL, PLAIN])
    assert got == ['panel', 'panel', 'panel', 'panel', 'panel', 'power', 'data', 'power'], got


def test_the_xlsx_and_its_gear_list_carry_the_panel_rows(seeded, e2e_server):
    """The workbook is the edited sheet: the panel rows in their positions'
    blocks with an edit on one, and every written panel type appended to
    the GEAR LIST's Cable Type column."""
    pg, _, _ = seeded
    import urllib.request
    sheet = pg.evaluate("""([plain]) => {
        const app = window.app;
        const engine = app.buildPullList();
        const f = engine.positions.find(p => p.name === 'FLOOR');
        const row = f.rows.find(r => r.type === plain);
        app.setPullSheetRowEdit(app.pullPositionKey(f), app.pullRowKey(row), {qty: 3, notes: 'one spare'}, row);
        app._circuitTailCache = null;
        return JSON.parse(JSON.stringify(app.buildPullSheet()));
    }""", [PLAIN])
    body = json.dumps({'project_name': 'Panels', 'pull_list': sheet}).encode('utf-8')
    req = urllib.request.Request(f'{e2e_server}/api/export/pull-sheet', data=body,
                                 headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req) as r:
        data = r.read()
    wb = openpyxl.load_workbook(io.BytesIO(data))
    ws = wb['Pull Sheet']
    import pull_sheet
    blocks = {}
    for col in pull_sheet.BLOCK_COLS:
        name = ws.cell(5, col).value
        rows = []
        for r in range(7, 67):
            t = ws.cell(r, col).value
            if t is None:
                continue
            rows.append(tuple(ws.cell(r, col + k).value for k in range(5)))
        blocks[name] = rows
    assert (PLAIN, 'EA', 3, 'FLOOR', 'one spare') in blocks['FLOOR'], blocks['FLOOR']
    assert (FULL, 'EA', 5, 'QUARTZ', None) in blocks['QUARTZ'], blocks['QUARTZ']
    assert (HALF, 'EA', 4, 'QUARTZ', None) in blocks['QUARTZ'], blocks['QUARTZ']
    assert (PLAIN, 'EA', 9, 'WALL-A, WALL-B', None) in blocks['SR Beach'], blocks['SR Beach']
    gear = [wb['GEAR LIST'].cell(r, 1).value for r in range(4, 201)]
    for t in (FULL, HALF, SIDE_HALF, PLAIN, PLAIN_HALF):
        assert t in gear, t


def test_the_binder_pull_page_prints_a_panels_block(seeded):
    """The pull pages mirror the pull sheet: a Panels block beside the
    hardware, one row per type with its count and screens."""
    pg, _, errors = seeded
    got = pg.evaluate("""() => {
        const app = window.app;
        const o = app.readBinderOptions();
        const plan = app.planBinder(o);
        return plan.map((p, i) => ({ title: p.title, kind: p.kind,
                                     texts: app.renderBinderPage(o, i, { bitmaps: false }).texts }));
    }""")
    pulls = [p for p in got if str(p['title']).startswith('Pull')]
    assert pulls, [p['title'] for p in got]
    flat = [t for p in pulls for t in p['texts']]
    assert 'PANELS' in flat and 'PANEL' in flat, flat
    assert FULL in flat and HALF in flat and PLAIN in flat, flat
    # the screens' own sheets say nothing of the panel types
    others = [t for p in got if not str(p['title']).startswith('Pull') and 'all positions' not in str(p['title'])
              for t in p['texts']]
    assert FULL not in others and PLAIN not in others
    assert errors == []

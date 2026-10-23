"""A favorite panel picks the library as it is now.

A favorite in Add Screen (and Change cabinet) is a snapshot of the panel's
figures, kept in localStorage when it was hearted. Picking it:

  * looks the model up in the loaded library by manufacturer and name and
    uses the library's CURRENT figures and model id, so a correction to
    the library (ROE's Graphite weights and watts, 1.5.4) reaches it;
  * a model the library renamed in this release ("Graphite 2.6 (4 in 1)"
    is "Graphite GP2.6 (4 in 1)") is found under its new name;
  * a model the library no longer has keeps the snapshot's figures and
    saves NO model id and no halves, so the screen never names a library
    model that isn't there.

The favorites list and the picker's summary show the same: the library's
name and figures today, so the list matches what a pick makes.

Each case starts from a favorite as 1.5.3 saved it.

Run locally:
    ~/.venvs/led-raster-designer/bin/python -m pytest tests/test_panel_favorites.py -v --browser chromium
"""

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


# Favorites as 1.5.3 hearted them: _toggleCatalogFavorite's snapshot of
# the catalog row of the day.
OLD_GRAPHITE_HALF = {
    '_mfr': 'ROE', 'name': 'Graphite 2.6 (4 in 1) Half Tile',
    'width_mm': 500, 'height_mm': 500, 'pixels_w': 192, 'pixels_h': 192,
    'weight_kg': 5.2, 'watts_max': 160, 'source': 'roevisual graphite.pdf',
}
OLD_GP39_FULL = {
    '_mfr': 'ROE', 'name': 'Graphite GP3.9 Full Tile',
    'width_mm': 500, 'height_mm': 1000, 'pixels_w': 128, 'pixels_h': 256,
    'weight_kg': 8.5, 'watts_max': 320, 'source': 'roevisual graphite.pdf',
}
GONE = {
    '_mfr': 'ROE', 'name': 'Retired Test Tile',
    'width_mm': 600, 'height_mm': 337.5, 'pixels_w': 240, 'pixels_h': 135,
    'weight_kg': 7.25, 'watts_max': 180, 'source': 'a spec sheet',
}


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
    pg.wait_for_timeout(1000)
    pg.evaluate("""(favs) => {
        localStorage.removeItem('panelCatalog.cached');
        window.app.setAddLayerFavorites(favs);
    }""", [OLD_GRAPHITE_HALF, OLD_GP39_FULL, GONE])
    yield pg, errors
    pg.evaluate("() => window.app.setAddLayerFavorites([])")
    context.close()


# Pick favorite `name` the way a person does: open + Add Screen, click its
# row, click Add Screen. Returns the new screen's cabinet and saved panel.
PICK_JS = """async (name) => {
    const app = window.app;
    const before = app.project.layers.length;
    app.openPresetPicker();
    let row = null;
    for (let i = 0; i < 100 && !row; i++) {
        row = [...document.querySelectorAll('#preset-picker-list .preset-picker-row[data-kind="favorite"]')]
            .find(r => r.dataset.key === 'ROE|' + name) || null;
        if (!row) await new Promise(r => setTimeout(r, 50));
    }
    if (!row) return { error: 'no favorite row for ' + name };
    row.click();
    document.getElementById('preset-picker-add').click();
    for (let i = 0; i < 100 && app.project.layers.length === before; i++) await new Promise(r => setTimeout(r, 50));
    const l = app.project.layers[app.project.layers.length - 1];
    if (app.project.layers.length === before) return { error: 'no screen was added' };
    const kg = l.weight_unit === 'lb' ? +(Number(l.panel_weight) / 2.20462).toFixed(2) : Number(l.panel_weight);
    const out = { id: l.panelModelId ?? null, name: l.panelModelName ?? null,
                  halves: l.panelModelHalves ?? null, kg, watts: Number(l.panelWatts),
                  w: l.cabinet_width, h: l.cabinet_height,
                  wmm: l.panel_width_mm, hmm: l.panel_height_mm };
    await fetch('/api/layer/' + l.id, { method: 'DELETE' });
    app.project.layers = app.project.layers.filter(x => x.id !== l.id);
    return out;
}"""


def test_a_renamed_favorite_picks_the_new_name_and_its_figures(page):
    pg, errors = page
    got = pg.evaluate(PICK_JS, OLD_GRAPHITE_HALF['name'])
    assert 'error' not in got, got
    # ROE's own name and figures today: 5.1 kg and 125 W, not the 5.2 kg
    # and 160 W the favorite was saved with
    assert got['id'] == 'ROE|Graphite GP2.6 (4 in 1) Half Tile', got
    assert got['name'] == 'ROE Graphite GP2.6 (4 in 1) Half Tile', got
    assert (got['kg'], got['watts']) == (5.1, 125), got
    assert (got['w'], got['h'], got['wmm'], got['hmm']) == (192, 192, 500, 500), got
    assert not errors, errors


def test_a_favorite_picks_the_librarys_current_figures(page):
    pg, errors = page
    got = pg.evaluate(PICK_JS, OLD_GP39_FULL['name'])
    assert 'error' not in got, got
    assert got['id'] == 'ROE|Graphite GP3.9 Full Tile', got
    assert got['name'] == 'ROE Graphite GP3.9 Full Tile', got
    # 9.0 kg in the library now, 8.5 kg in the favorite
    assert (got['kg'], got['watts']) == (9.0, 320), got
    assert got['halves'] == {'height': 'ROE Graphite GP3.9 Half Tile', 'width': None}, got
    assert not errors, errors


def test_a_favorite_the_library_no_longer_has_saves_no_model(page):
    pg, errors = page
    got = pg.evaluate(PICK_JS, GONE['name'])
    assert 'error' not in got, got
    # the snapshot's figures, under its name, but no model id and no halves
    assert got['id'] is None and got['halves'] is None, got
    assert got['name'] == 'ROE Retired Test Tile', got
    assert (got['kg'], got['watts']) == (7.25, 180), got
    assert (got['w'], got['h']) == (240, 135), got
    assert not errors, errors


def test_the_rename_map_only_names_models_the_library_has(page):
    """Every new name in this release's rename map is a model in the
    bundled library, and no old name still is."""
    pg, _ = page
    got = pg.evaluate("""async () => {
        const app = window.app;
        await app._ensurePanelCatalogData();
        const old = { _mfr: 'ROE', name: 'Graphite 2.6 (4 in 1) Full Tile' };
        const lib = app._libraryPanelFor(old);
        const stillThere = (app._panelCatalog.ROE || []).some(p => p.name === old.name);
        return { name: lib && lib.name, mfr: lib && lib._mfr, stillThere };
    }""")
    assert got == {'name': 'Graphite GP2.6 (4 in 1) Full Tile', 'mfr': 'ROE', 'stillThere': False}, got


# The favorites list and the picker's summary show what a pick makes: the
# library's name and figures today, not the snapshot's (owner, round 5).
ROWS_JS = """async () => {
    const app = window.app;
    app.openPresetPicker();
    const rows = () => [...document.querySelectorAll('#preset-picker-list .preset-picker-row[data-kind="favorite"]')];
    for (let i = 0; i < 100 && !(app._panelCatalog && rows().length === 3 && !app._pickerFavsFromSnapshot); i++) {
        await new Promise(r => setTimeout(r, 50));
    }
    await new Promise(r => setTimeout(r, 200));
    const read = (r) => {
        const divs = r.firstElementChild.children;
        return { key: r.dataset.key, label: divs[0].textContent, sub: divs[1].textContent };
    };
    const out = { rows: rows().map(read), summaries: {} };
    for (const r of rows()) {
        r.click();
        out.summaries[r.dataset.key] = document.getElementById('preset-picker-summary').textContent;
    }
    app.closePresetPicker();
    return out;
}"""


def test_the_favorites_list_and_summary_show_the_librarys_panel(page):
    pg, errors = page
    got = pg.evaluate(ROWS_JS)
    rows = {r['key']: r for r in got['rows']}
    s = got['summaries']
    # renamed: ROE's name today, its 125 W and 5.1 kg
    old = 'ROE|Graphite 2.6 (4 in 1) Half Tile'
    assert rows[old]['label'] == 'ROE Graphite GP2.6 (4 in 1) Half Tile', rows[old]
    assert '125W/panel' in rows[old]['sub'] and '160W' not in rows[old]['sub'], rows[old]
    assert s[old] == 'Panel: ROE Graphite GP2.6 (4 in 1) Half Tile, 500×500mm · 192×192px · 5.1kg · 125W', s
    # corrected: 9.0 kg in the library, 8.5 kg in the snapshot
    gp39 = 'ROE|Graphite GP3.9 Full Tile'
    assert rows[gp39]['label'] == 'ROE Graphite GP3.9 Full Tile', rows[gp39]
    assert s[gp39] == 'Panel: ROE Graphite GP3.9 Full Tile, 500×1000mm · 128×256px · 9kg · 320W', s
    # gone from the library: the snapshot, as a pick makes it
    gone = 'ROE|Retired Test Tile'
    assert rows[gone]['label'] == 'ROE Retired Test Tile', rows[gone]
    assert s[gone] == 'Panel: ROE Retired Test Tile, 600×337.5mm · 240×135px · 7.25kg · 180W', s
    assert not errors, errors

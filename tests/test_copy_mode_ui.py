"""Mirror screens, copy boxes and the per-port card-or-box choice in the
browser (owner's rulings, 2026-10-30).

"You pick the screen to copy; the copy screen's port map follows the first
automatically and can't be drawn separately. A mismatch in size or panel is
refused." - Screen Info's "Mirror a screen" row sets it; the mirror's data
controls refuse out loud; its runs land on the copy box (H_4xfiber Copy mode:
"OPT 3 copies the output on OPT 1", H15 Video Wall Splicer Specifications
V1.15.0 p.36) and print on the pull sheet and in the tray like any run.

An MX40 Pro box going on OPT 3 in 20-port mode asks Mirror or Backup (User
Manual V1.5.0 p.9: "OPT 3 is the copy channel of OPT 1"; owner: "Either, you
pick"), and each of its ports 1-20 plugs in at the unit's RJ45 or at the box
("You can use the optical port alongside the physical Ethernet port").

Run locally:
    python -m pytest tests/test_copy_mode_ui.py -v --browser chromium
"""
import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


SEED_JS = """async () => {
    const proj = await (await fetch('/api/project')).json();
    proj.layers = [];
    proj.groups = [];
    proj.processors = [];
    proj.distros = [];
    delete proj.port_assignments;
    await fetch('/api/project', {method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(proj)});
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)})
        .then(r => r.json());
    const add = (name, columns) => j('POST', '/api/layer/add', {name,
        columns, rows: 3, cabinet_width: 256, cabinet_height: 256,
        offset_x: name === 'SL' ? 0 : (name === 'SR' ? 1100 : 2200)});
    await add('SL', 4); await add('SR', 4); await add('WIDE', 5);
    let st = await j('POST', '/api/processors', {deviceId: 'novastar-h9'});
    const pid = st.processors[0].id;
    st = await j('PUT', `/api/processors/${pid}/slots/0`,
                 {deviceId: 'novastar-card-h-4xfiber'});
    const cid = st.processors[0].slots[0].card.id;
    await j('PUT', `/api/processors/${pid}/cards/${cid}`, {mode: 'copy'});
    for (let i = 0; i < 4; i++) {
        await j('POST', `/api/processors/${pid}/cards/${cid}/cvts`,
                {deviceId: 'novastar-cvt10', pair: false});
    }
    const app = window.app;
    app.project = await (await fetch('/api/project')).json();
    await app.refreshProcessors();
    app.renderLayers();
    const byName = (n) => app.project.layers.find(l => l.name === n);
    const sl = byName('SL'), sr = byName('SR'), wide = byName('WIDE');
    await app.refreshPortAssignment();
    for (let i = 0; i < 2; i++) {
        await app._assignmentRequest('/api/port-assignments/place', 'POST',
            {layerId: String(sl.id), index: i, cardId: cid, port: i + 1},
            null, 'Place Port');
    }
    app.resetHistory('Mirror Seed');
    return {pid, cid, sl: sl.id, sr: sr.id, wide: wide.id};
}"""

SHOW_JS = """async (id) => {
    const app = window.app;
    const layer = app.project.layers.find(l => l.id === id);
    app.selectLayer(layer);
    app.updatePortCapacityDisplay();
    await new Promise(r => setTimeout(r, 50));
    const sel = document.getElementById('mirror-screen');
    const note = document.getElementById('mirror-screen-note');
    return {options: [...sel.options].map(o => o.textContent),
            value: sel.value, disabled: sel.disabled,
            note: note.style.display === 'none' ? '' : note.textContent,
            rowShown: document.getElementById('mirror-screen-row')
                .style.display !== 'none'};
}"""

PICK_JS = """async (value) => {
    const sel = document.getElementById('mirror-screen');
    sel.value = String(value);
    sel.dispatchEvent(new Event('change', {bubbles: true}));
    await new Promise(r => setTimeout(r, 700));
    await window.app.refreshPortAssignment();
    return true;
}"""

TOASTS_JS = """() => {
    if (!window.__toasts) {
        window.__toasts = [];
        const orig = window.app._toast.bind(window.app);
        window.app._toast = (msg, err, ms) => {
            window.__toasts.push({msg: String(msg), err: !!err});
            return orig(msg, err, ms);
        };
    }
    const out = window.__toasts.slice();
    window.__toasts.length = 0;
    return out;
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
    pg.wait_for_timeout(2000)
    ids = pg.evaluate(SEED_JS)
    pg.wait_for_timeout(600)
    pg.locator('[data-mode="data-flow"]').click()
    pg.wait_for_timeout(400)
    pg.evaluate(TOASTS_JS)
    yield pg, ids, errors
    context.close()


def test_the_mirror_row_sets_the_mirror_and_its_runs_land_on_the_copy_box(page):
    pg, ids, errors = page
    shown = pg.evaluate(SHOW_JS, ids['sr'])
    assert shown['rowShown'] and shown['value'] == ''
    assert shown['options'] == ['None', 'SL', 'WIDE']
    pg.evaluate(PICK_JS, ids['sl'])
    shown = pg.evaluate(SHOW_JS, ids['sr'])
    assert shown['value'] == str(ids['sl'])
    assert shown['note'].startswith('Port map follows SL.'), shown
    out = pg.evaluate("""(ids) => {
        const app = window.app;
        const sr = app.project.layers.find(l => l.id === ids.sr);
        const sl = app.project.layers.find(l => l.id === ids.sl);
        const scr = app._assignment.screens
            .find(s => s.layerId === String(ids.sr));
        return {mirrorOf: sr.dataMirrorOf, flow: [sr.flowPattern, sl.flowPattern],
                ports: scr ? scr.ports.map(p => [p.port, p.source]) : null,
                occ: app._portOccupants(ids.cid, 17).map(o => o.name),
                slNote: null};
    }""", ids)
    assert out['mirrorOf'] == ids['sl']
    assert out['flow'][0] == out['flow'][1]
    assert out['ports'][:2] == [[17, 'mirror'], [18, 'mirror']], out
    assert out['occ'] == ['SR']
    # the source names its mirror
    assert pg.evaluate(SHOW_JS, ids['sl'])['note'] == 'Mirrored by SR.'
    assert errors == []


def test_a_mismatched_screen_is_refused_and_the_pick_snaps_back(page):
    pg, ids, errors = page
    pg.evaluate(TOASTS_JS)
    pg.evaluate(SHOW_JS, ids['wide'])
    pg.evaluate(PICK_JS, ids['sl'])
    toasts = pg.evaluate(TOASTS_JS)
    assert any(t['err'] and t['msg'].startswith(
        'WIDE is 5 x 3 cabinets and SL is 4 x 3') for t in toasts), toasts
    shown = pg.evaluate(SHOW_JS, ids['wide'])
    assert shown['value'] == ''
    assert pg.evaluate("""(id) => window.app.project.layers
        .find(l => l.id === id).dataMirrorOf""", ids['wide']) is None
    assert errors == []


def test_the_mirrors_data_map_is_read_only_and_says_why(page):
    pg, ids, errors = page
    pg.evaluate(SHOW_JS, ids['sr'])
    pg.evaluate(TOASTS_JS)
    before = pg.evaluate("""(id) => window.app.project.layers
        .find(l => l.id === id).flowPattern""", ids['sr'])
    btn = pg.locator('.flow-pattern-btn[data-pattern="tr-v"]').first
    btn.scroll_into_view_if_needed()
    btn.click(force=True)
    pg.wait_for_timeout(200)
    toasts = pg.evaluate(TOASTS_JS)
    assert any(t['err'] and t['msg'].startswith(
        "SR mirrors SL - its data port map follows SL's") for t in toasts), \
        toasts
    after = pg.evaluate("""(id) => window.app.project.layers
        .find(l => l.id === id).flowPattern""", ids['sr'])
    assert after == before
    assert btn.evaluate("el => el.style.opacity") == '0.45'
    # the tray: a placement of the mirror's own ports is refused out loud
    pg.evaluate("""(ids) => window.app._assignmentRequest(
        '/api/port-assignments/place', 'POST',
        {layerId: String(ids.sr), index: 0, cardId: ids.cid, port: 5},
        null, 'Place Port')""", ids)
    toasts = pg.evaluate(TOASTS_JS)
    assert any(t['err'] and 'SR mirrors SL' in t['msg'] for t in toasts)
    assert errors == []


def test_the_mirror_follows_the_sources_map(page):
    pg, ids, errors = page
    out = pg.evaluate("""async (ids) => {
        const app = window.app;
        const sl = app.project.layers.find(l => l.id === ids.sl);
        const sr = app.project.layers.find(l => l.id === ids.sr);
        sl.flowPattern = 'bl-v';
        app.saveState('Change Flow');
        return [sl.flowPattern, sr.flowPattern];
    }""", ids)
    assert out == ['bl-v', 'bl-v']
    assert errors == []


def test_the_pull_sheet_and_the_box_show_the_mirrors_runs(page):
    pg, ids, errors = page
    out = pg.evaluate("""(ids) => {
        const app = window.app;
        const pull = app.buildPullList();
        const sr = pull.byScreen[ids.sr];
        const sl = pull.byScreen[ids.sl];
        const card = app._dockFindCard(ids.cid).card;
        const mirrorBox = card.cvts[2];
        return {sr: sr ? sr.ports.slice(0, 2).map(p => p.box) : null,
                sl: sl ? sl.ports.slice(0, 2).map(p => p.box) : null,
                title: app.pullBoxTitle(mirrorBox),
                taken: app.socketsTaken(ids.cid, mirrorBox.id)};
    }""", ids)
    assert out['sr'] == [out['title'], out['title']], out
    assert out['sl'][0] != out['title']
    assert out['taken']['taken'] == 2, out
    assert errors == []


MX40_JS = """async (mode) => {
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)})
        .then(r => r.json());
    const st = await j('POST', '/api/processors', {deviceId: 'novastar-mx40-pro'});
    const proc = st.processors[st.processors.length - 1];
    const cid = proc.slots[0].card.id;
    await j('PUT', `/api/processors/${proc.id}/cards/${cid}`, {mode});
    await window.app.refreshProcessors();
    window.app.renderHardwareDock();
    return {pid: proc.id, cid};
}"""


def test_an_mx40_pro_box_on_opt3_asks_mirror_or_backup(page):
    pg, ids, errors = page
    mx = pg.evaluate(MX40_JS, '20-port')
    pg.evaluate("(mx) => window.app._dockAddBox(mx.cid, 'novastar-cvt10')", mx)
    pg.wait_for_timeout(300)
    modal = pg.locator('#copy-role-modal')
    assert modal.is_visible()
    assert 'OPT 3 copies OPT 1' in pg.locator('#copy-role-text').inner_text()
    pg.locator('#copy-role-mirror').click()
    pg.wait_for_timeout(600)
    boxes = pg.evaluate("""(mx) => window.app._dockFindCard(mx.cid).card.cvts
        .map(b => [b.trunkTitle, b.copyRole, b.firstPort])""", mx)
    assert boxes == [['OPT 1', None, 1], ['OPT 3', 'mirror', 21]], boxes
    # the box gear flips it to Backup
    pg.evaluate("""(mx) => {
        const app = window.app;
        const found = app._dockFindCard(mx.cid);
        const cvt = found.card.cvts[1];
        const el = app._buildBoxCopyRoleStrip(found.proc, cvt);
        el.querySelector('[data-level="backup"]').click();
    }""", mx)
    pg.wait_for_timeout(600)
    box = pg.evaluate("""(mx) => window.app._dockFindCard(mx.cid).card.cvts[1]
        .firstPort""", mx)
    assert box == 1
    # Cancel adds nothing
    pg.evaluate("(mx) => window.app._dockAddBox(mx.cid, 'novastar-cvt10')", mx)
    pg.wait_for_timeout(300)
    pg.locator('#copy-role-cancel').click()
    pg.wait_for_timeout(400)
    assert pg.evaluate("(mx) => window.app._dockFindCard(mx.cid).card.cvts"
                       ".length", mx) == 2
    assert errors == []


def test_an_mx40_pro_port_plugs_in_at_the_unit_or_the_box(page):
    pg, ids, errors = page
    mx = pg.evaluate(MX40_JS, '40-port')
    pg.evaluate("""async (mx) => {
        await fetch(`/api/processors/${mx.pid}/cards/${mx.cid}/cvts`, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({deviceId: 'novastar-cvt10'})});
        await window.app.refreshProcessors();
    }""", mx)
    out = pg.evaluate("""async (mx) => {
        const app = window.app;
        let found = app._dockFindCard(mx.cid);
        const port = found.card.ports.find(p => p.number === 3);
        const strip = app._buildPortPlugStrip(found.proc, found.card, port);
        const segs = [...strip.querySelectorAll('[data-level]')]
            .map(s => [s.dataset.level, s.textContent,
                       s.classList.contains('hw-pop-seg-on')]);
        strip.querySelector('[data-level="card"]').click();
        for (let i = 0; i < 40; i++) {
            await new Promise(r => setTimeout(r, 50));
            found = app._dockFindCard(mx.cid);
            if (found.card.ports.find(p => p.number === 3).plug === 'card') break;
        }
        const home = app._bPortHome(mx.cid, 3);
        const rows = app._buildCardPlugRows(found.proc, found.card);
        return {segs, plug: found.card.ports.find(p => p.number === 3).plug,
                box: home.box ? home.box.id : null,
                owner: app._dataPortOwner(mx.cid, 3).kind,
                rows: rows ? rows.textContent : ''};
    }""", mx)
    assert out['segs'] == [['card', 'Processor RJ45', False],
                           ['box', 'Breakout box', True]], out
    assert out['plug'] == 'card' and out['box'] is None
    assert out['owner'] == 'card'
    assert 'OPT 1: ports 1-10 (1 at the RJ45)' in out['rows'], out
    assert errors == []

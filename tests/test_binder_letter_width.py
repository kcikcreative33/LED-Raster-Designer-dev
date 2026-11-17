"""Nothing on a binder sheet runs out of the drawing area into the title
block - at letter and A4 above all, where the drawing area is narrowest.

The owner, 2026-11-17, on a letter Header/Footer sheet of a wide, short
wall: the view bubble's name ("SCREEN G - FOH - SWITCH · HEADER/FOOTER ·
REAR VIEW") was drawn at the sheet's fill scale with nothing holding it to
the drawing's width, so it and its rule ran across the revisions - "need
to look at this horizontal scaling for 8.5 x 11 on all sheets".

Pinned here, on a synthetic show (a 20 x 6 wall with a long name and
ten double header bars, a second small screen), drawn from the rear: on every sheet of the binder, at
every sheet size, title block on and off, every text, rule, box and line
that starts left of the title block ends before it (or before the border,
with the block off). The view bubble's name may shrink, then be cut, but
never leaves the drawing area.

Run locally:
    python3 -m pytest tests/test_binder_letter_width.py -v --browser chromium
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


LONG = 'SCREEN G - FOH - SWITCH'

SEED_JS = """async (name) => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const proj = await j('GET', '/api/project');
    proj.layers = []; proj.groups = []; proj.processors = []; proj.distros = [];
    delete proj.port_assignments; delete proj.pullSheet; delete proj.binder;
    delete proj.fiberCables; delete proj.pullSheetEdits;
    await j('PUT', '/api/project', proj);
    const add = (body) => j('POST', '/api/layer/add', body);
    const common = {powerVoltage: 208, powerAmperage: 20, panelWatts: 200,
                    powerFlowPattern: 'tl-v', powerOrganized: true, flowPattern: 'tl-h',
                    processorType: 'novastar-armor'};
    await add({...common, name, columns: 20, rows: 6, cabinet_width: 500, cabinet_height: 500});
    await add({...common, name: 'IMAG LEFT', columns: 4, rows: 3, cabinet_width: 500,
               cabinet_height: 500, offset_x: 12000});
    let p = await j('GET', '/api/project');
    const wall = p.layers.find(l => l.name === name);
    wall.riggingBars = Array(10).fill(2);
    p.layers.find(l => l.name === 'IMAG LEFT').riggingBars = [2, 2];
    await j('PUT', '/api/project', p);
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('letter_width_setup');
    app.renderLayers();
    window.canvasRenderer.render();
    app.resetHistory('Letter Width Seed');
    return app.project.layers.map(l => l.name);
}"""

# Every sheet of the binder painted; for each, the ops that start left of
# `edge` (page units) and end past it, the border frame aside.
OVER_JS = """([opts, edge, pad]) => {
    const app = window.app;
    const plan = app.planBinder(opts);
    const mc = document.createElement('canvas').getContext('2d');
    const widthOf = (o) => {
        mc.font = `${o.weight || 400} ${o.size}px Helvetica, Arial, sans-serif`;
        return mc.measureText(o.text).width;
    };
    const out = [];
    let bubbles = [];
    for (let i = 0; i < plan.length; i++) {
        const r = app.renderBinderPage(opts, i);
        const bad = [];
        for (const o of (r.record ? r.record.ops : [])) {
            let x0, x1, what;
            if (o.op === 'text') {
                if (!String(o.text).trim() || o.rotate) continue;
                const w = widthOf(o);
                x0 = o.align === 'center' ? o.x - w / 2 : o.align === 'right' ? o.x - w : o.x;
                x1 = x0 + w;
                what = 'text ' + o.text;
            } else if (o.op === 'rect' || o.op === 'image') {
                // the border frame: from the page's pad all the way across
                if (o.x <= pad + 1 && o.w > edge - pad) continue;
                x0 = o.x; x1 = o.x + o.w; what = o.op;
            } else if (o.op === 'line') {
                const xs = (o.points || []).map(p => p[0]);
                if (!xs.length) continue;
                x0 = Math.min(...xs); x1 = Math.max(...xs); what = 'line';
                if (x0 <= pad + 1 && x1 - x0 > edge - pad) continue;
            } else continue;
            if (x0 < edge - 1 && x1 > edge + 1) bad.push({what, x0: Math.round(x0), x1: Math.round(x1)});
        }
        if (r.bubble) bubbles.push({title: plan[i].title, name: r.bubble.name});
        out.push({n: plan[i].number, title: plan[i].title, kind: plan[i].kind, bad});
    }
    return {sheets: out, bubbles};
}"""

SHEETS = ('letter', 'a4', 'tabloid')
SHEET_IN = {'letter': (11, 8.5), 'a4': (11.69, 8.27), 'tabloid': (17, 11)}
PX_IN, PAD, TB_W = 200, 50, 480


def _opts(**kw):
    o = {'sheet': 'letter', 'palette': 'colour', 'sides': {'power': True, 'data': True},
         'scope': {'kind': 'show'}, 'cover': True, 'pull': True, 'hardware': True,
         'wiring': True, 'rigging': True, 'titleBlock': True, 'view': 'rear'}
    o.update(kw)
    return o


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
    names = pg.evaluate(SEED_JS, LONG)
    pg.wait_for_timeout(600)
    assert LONG in names, names
    yield pg, errors
    context.close()


@pytest.mark.parametrize('sheet', SHEETS)
@pytest.mark.parametrize('tb', (True, False), ids=('block', 'noblock'))
def test_nothing_runs_out_of_the_drawing_area(page, sheet, tb):
    pg, errors = page
    w, _h = SHEET_IN[sheet]
    W = w * PX_IN
    edge = W - PAD - (TB_W if tb else 0)
    res = pg.evaluate(OVER_JS, [_opts(sheet=sheet, titleBlock=tb), edge, PAD])
    kinds = {s['kind'] for s in res['sheets']}
    assert {'power', 'data', 'wiring', 'rigging'} <= kinds, kinds
    bad = [(s['n'], s['title'], s['bad']) for s in res['sheets'] if s['bad']]
    assert not bad, bad
    assert not errors, errors


def test_the_header_footer_bubble_still_names_the_sheet_at_letter(page):
    """Held to the drawing's width, the name shrinks before it is cut: at
    letter the Header/Footer bubble still reads the whole sheet title."""
    pg, _errors = page
    res = pg.evaluate(OVER_JS, [_opts(sheet='letter'), 11 * PX_IN - PAD - TB_W, PAD])
    rig = [b for b in res['bubbles'] if 'Header/Footer' in b['title'] and LONG in b['title']]
    assert rig, res['bubbles']
    assert all(b['name'] == LONG + ' · HEADER/FOOTER · REAR VIEW' for b in rig), rig

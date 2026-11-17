"""Nothing on a binder sheet runs past the drawing area into the title
block, on the small sheets as on the big ones (owner, 2026-11-17, a
Header/Footer sheet at letter whose view title "SCREEN G - FOH - SWITCH ·
HEADER/FOOTER · REAR VIEW" ran on under the Revisions table: "need to look
at this horizontal scaling for 8.5 x 11 on all sheets").

Every sheet of three shows - the binder's own (screens, wiring, pull,
distro, processor), a fiber show and a grouped header/footer show - is
painted at letter, A4 and tabloid, and every text, rule, line and bitmap
it records left of the title block must end before it.

Run locally:
    python3 -m pytest tests/test_binder_letter_fit.py -v --browser chromium
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(__file__))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

from test_binder import SEED_JS as BINDER_SEED_JS  # noqa: E402
from test_binder_fiber_page import MANY_JS  # noqa: E402
from test_group_header_footer_sheets import SEED_JS as HF_SEED_JS  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    yield pg, errors
    context.close()


def _opts(sheet, tb=True):
    return {'sheet': sheet, 'palette': 'colour', 'sides': {'power': True, 'data': True},
            'scope': {'kind': 'show'}, 'cover': True, 'pull': True, 'hardware': True,
            'wiring': True, 'rigging': True, 'fiber': True, 'titleBlock': tb}


# Every sheet painted, and every mark it recorded that starts left of the
# title block and ends past it (the sheet's own border and the block's own
# rules apart).
AUDIT_JS = """(opts) => {
    const app = window.app;
    const plan = app.planBinder(opts);
    const ctx = document.createElement('canvas').getContext('2d');
    const bad = [];
    plan.forEach((p, i) => {
        const r = app.renderBinderPage(opts, i);
        const rec = r.record;
        if (!rec) return;
        const geo = app._bGeo(r.sheet, opts.titleBlock !== false);
        const edge = geo.titleBlock ? geo.tb.x : geo.W - 50;
        const left = geo.border.x + 1, right = geo.border.x + geo.border.w - 1;
        const over = (a, b, what) => {
            if (a < edge - 2 && b > edge + 2) bad.push({ sheet: p.title, what, a: Math.round(a), b: Math.round(b), edge });
        };
        for (const o of rec.ops) {
            if (o.op === 'text') {
                if (o.rotate) continue;
                ctx.font = `${o.weight || 400} ${o.size}px Arial`;
                const w = ctx.measureText(o.text).width;
                const a = o.align === 'center' ? o.x - w / 2 : (o.align === 'right' || o.align === 'end') ? o.x - w : o.x;
                over(a, a + w, 'text "' + o.text + '"');
            } else if (o.op === 'rect') {
                if (o.x <= left && o.x + o.w >= right) continue;          // the sheet / border
                over(o.x, o.x + o.w, 'rect');
            } else if (o.op === 'line') {
                const xs = o.points.map(q => q[0]);
                const a = Math.min(...xs), b = Math.max(...xs);
                if (a <= left && b >= right) continue;                      // the border
                over(a, b, 'line');
            } else if (o.op === 'image') {
                over(o.x, o.x + o.w, 'image');
            }
        }
    });
    return { sheets: plan.length, bad };
}"""


LONG_NAMES_JS = """async () => {
    const app = window.app;
    const j = (method, url, body) => fetch(url, {method,
        headers: {'Content-Type': 'application/json'},
        body: body === undefined ? undefined : JSON.stringify(body)}).then(r => r.json());
    const p = await j('GET', '/api/project');
    p.layers.forEach((l, i) => { l.name = 'SCREEN ' + String.fromCharCode(65 + i) + ' - FOH - SWITCH ' + l.name; });
    (p.groups || []).forEach(g => { g.name = 'STAGE LEFT FOH - ' + g.name; });
    await j('PUT', '/api/project', p);
    app.project = await j('GET', '/api/project');
    app.dedupeProjectLayers('letter_fit_names');
    await app.refreshProcessors();
    app.renderLayers();
    window.canvasRenderer.render();
}"""


SHOWS = {
    'binder': (BINDER_SEED_JS, None),
    'fiber': (MANY_JS, 6),
    'header-footer': (HF_SEED_JS, None),
}


@pytest.mark.parametrize('show', list(SHOWS))
def test_nothing_runs_into_the_title_block(page, show):
    pg, errors = page
    seed, arg = SHOWS[show]
    if arg is None:
        pg.evaluate(seed)
    else:
        pg.evaluate(seed, arg)
    pg.wait_for_timeout(800)
    # long names, as a real show has them ("SCREEN G - FOH - SWITCH")
    pg.evaluate(LONG_NAMES_JS)
    pg.wait_for_timeout(400)
    for sheet in ('letter', 'a4', 'tabloid'):
        for tb in (True, False):
            out = pg.evaluate(AUDIT_JS, _opts(sheet, tb))
            assert out['sheets'] > 0, (show, sheet)
            assert out['bad'] == [], (show, sheet, tb, out['bad'][:12])
    assert errors == []

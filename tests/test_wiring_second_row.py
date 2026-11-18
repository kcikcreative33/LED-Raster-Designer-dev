"""A data wiring sheet with more boxes than a side holds at its usual
pitch (app-binder-wiring.js: the tight pitch, and channelPlan).

The owner (2026-11-18), of a 30 x 7 wall on an MX2000 Pro with two
MX_4x10G cards, each on OPT Split with a CVT10 on every OPT - eight boxes,
four over the wall and four under it, three to a row: "there is
overlapping on the wiring diagram page". The fourth box on each side stood
in a second row behind the first, and its runs came straight down through
the front row's boxes, their sockets and their names.

Then (the same day): "the screen graphic is far too small. need to
maximize led screen sizes" - two rows a side left the wall a third of the
width. So a side first closes its pitch (down to TIGHT_PITCH) to hold its
boxes in ONE row, and the wall takes the width; only past that does a
second row stand, and its runs go between the inner row's boxes and along
the channel between the two rows to their sockets.

Two shows, built through the routes, read off the sheet the binder really
draws: Jared's (one MX2000, eight boxes, one row a side) and the same wall
twice as wide on two MX2000s (sixteen boxes, two rows a side).
"""
import json
import os
import sys
import urllib.error
import urllib.request

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

pytest.importorskip("playwright.sync_api", reason="playwright not installed")

ROWS, HALF = 7, 15
TITLE = 'Screen A - Data Wiring'


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


class _Session:
    """The few JSON calls the seed makes, on the standard library (CI
    installs no HTTP client)."""

    def __init__(self, base):
        self.base = base

    def _call(self, method, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status, json.loads(resp.read() or b'null')
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode(errors='replace')

    def get(self, path):
        return self._call('GET', path)

    def post(self, path, body=None):
        return self._call('POST', path, body if body is not None else {})

    def put(self, path, body):
        return self._call('PUT', path, body)

    def delete(self, path):
        return self._call('DELETE', path)


def _ok(res):
    status, body = res
    assert status in (200, 201), (status, str(body)[:400])
    return body


def _seed(base, cols):
    s = _Session(base)
    _ok(s.post('/api/project/new'))
    for layer in _ok(s.get('/api/project'))['layers']:
        _ok(s.delete(f"/api/layer/{layer['id']}"))
    _ok(s.post('/api/layer/add', {
        'name': 'Screen A', 'columns': cols, 'rows': ROWS,
        'cabinet_width': 256, 'cabinet_height': 256}))
    lid = _ok(s.get('/api/project'))['layers'][-1]['id']
    _ok(s.put(f'/api/layer/{lid}', {
        'processorType': 'novastar-coex-1g', 'frameRate': 60, 'bitDepth': 8,
        'flowPattern': 'custom', 'customPortIndex': cols,
        'customPortPaths': {str(c + 1): [{'col': c, 'row': r} for r in range(ROWS)]
                            for c in range(cols)}}))
    cards = []
    box = 0
    for _ in range(cols // (2 * HALF)):
        st = _ok(s.post('/api/processors', {'deviceId': 'novastar-mx2000-pro'}))
        pid = st['processors'][-1]['id']
        _ok(s.put(f'/api/processors/{pid}', {'redundancy': True}))
        for slot in (0, 1):
            st = _ok(s.put(f'/api/processors/{pid}/slots/{slot}',
                           {'deviceId': 'novastar-card-mx-4x10g'}))
            cid = next(p for p in st['processors'] if p['id'] == pid)['slots'][slot]['card']['id']
            _ok(s.put(f'/api/processors/{pid}/cards/{cid}', {'redundancyMode': 'halves'}))
            for _ in range(4):
                _ok(s.post(f'/api/processors/{pid}/cards/{cid}/cvts',
                           {'deviceId': 'novastar-cvt10', 'pair': False,
                            'name': f'CVT {box + 1}'}))
                box += 1
            cards.append(cid)
    screens = [{'layerId': str(lid), 'name': 'Screen A', 'ports': cols}]
    for i in range(cols):
        _ok(s.post('/api/port-assignments/place', {
            'screens': screens, 'layerId': str(lid), 'index': i,
            'cardId': cards[i // HALF], 'port': i % HALF + 1}))


SHEET_JS = """async (title) => {
    const app = window.app;
    app.project = await fetch('/api/project').then(r => r.json());
    app.selectLayer(app.project.layers[0]);
    await app.refreshProcessors();
    await app.refreshPortAssignment();
    app.renderLayers();
    const opts = app.readBinderOptions();
    const plan = app.planBinder(opts);
    const idx = plan.findIndex(p => p.title === title);
    if (idx < 0) return { missing: title, plan: plan.map(p => p.title) };
    const r = app.renderBinderPage(opts, idx);
    return { halves: r.wiring.halves.map(h => ({ side: h.side,
        availW: h.availW, wall: h.map,
        blocks: h.blocks.map(b => ({ title: b.title, x: b.x, y: b.y, w: b.w, h: b.h,
                                     side: b.side, row: b.row,
                                     sockets: b.sockets.map(k => ({ n: k.n, x: k.x, r: k.r })) })),
        runs: h.runs.map(x => ({ device: x.device, socket: x.socket, points: x.points })) })) };
}"""


def _read(pg, base, cols):
    _seed(base, cols)
    out = pg.evaluate(SHEET_JS, TITLE)
    assert 'missing' not in out, out
    halves = [h for h in out['halves'] if h['side'] == 'signal']
    assert len(halves) == 1, out
    return halves[0]


@pytest.fixture(scope="module")
def sheets(e2e_server, pw_browser):
    context = pw_browser.new_context(viewport={'width': 1700, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_first_run_done','1');}catch(e){}")
    pg = context.new_page()
    errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(2000)
    out = {'one': _read(pg, e2e_server, 30), 'two': _read(pg, e2e_server, 60)}
    context.close()
    assert not errors, errors
    return out


def _cuts(a, b, box, pad=0.5):
    """Does the segment a-b (a horizontal or a vertical) pass through the
    inside of `box`?"""
    x0, x1 = sorted((a[0], b[0]))
    y0, y1 = sorted((a[1], b[1]))
    return (x1 > box['x'] + pad and x0 < box['x'] + box['w'] - pad
            and y1 > box['y'] + pad and y0 < box['y'] + box['h'] - pad)


def test_eight_boxes_stand_one_row_a_side_and_the_wall_takes_the_width(sheets):
    sheet = sheets['one']
    blocks = sheet['blocks']
    assert len(blocks) == 8, [b['title'] for b in blocks]
    assert all(b['row'] == 0 for b in blocks), [(b['title'], b['side'], b['row']) for b in blocks]
    assert sum(b['side'] == 'top' for b in blocks) == 4, blocks
    # the wall as wide as the boxes' row: within a few percent of the width
    assert sheet['wall']['w'] >= 0.95 * sheet['availW'], (sheet['wall'], sheet['availW'])
    # the sockets closed in to fit, never past their floor
    rs = {round(k['r'], 3) for b in blocks for k in b['sockets']}
    assert len(rs) == 1, rs


def test_sixteen_boxes_still_take_a_second_row_a_side(sheets):
    blocks = sheets['two']['blocks']
    assert len(blocks) == 16, [b['title'] for b in blocks]
    for side in ('top', 'bottom'):
        assert any(b['side'] == side and b['row'] > 0 for b in blocks), (
            'the case channelPlan is for: a second row on the %s side' % side, blocks)


@pytest.mark.parametrize('which', ['one', 'two'])
def test_no_run_passes_through_a_box(sheets, which):
    sheet = sheets[which]
    blocks = sheet['blocks']
    bad = []
    for r in sheet['runs']:
        pts = r['points']
        for i, (a, b) in enumerate(zip(pts, pts[1:])):
            last = i == len(pts) - 2
            for box in blocks:
                if last and box['title'] == r['device']:
                    continue   # the drop into its own socket
                if _cuts(a, b, box):
                    bad.append((r['device'], r['socket'], box['title'], a, b))
    assert bad == [], bad[:6]


@pytest.mark.parametrize('which', ['one', 'two'])
def test_every_run_still_lands_on_its_socket(sheets, which):
    sheet = sheets[which]
    blocks = {b['title']: b for b in sheet['blocks']}
    for r in sheet['runs']:
        b = blocks[r['device']]
        sk = next(k for k in b['sockets'] if k['n'] == r['socket'])
        assert abs(r['points'][-1][0] - sk['x']) < 0.01, (r, sk)
        pts = r['points']
        for a, c in zip(pts, pts[1:]):
            assert abs(a[0] - c[0]) < 0.01 or abs(a[1] - c[1]) < 0.01, ('no diagonals', r)

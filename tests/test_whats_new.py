"""The "What's New" window: shown once after an update that has something
to say (a new MAJOR.MINOR's highlights, or Advanced Guide steps added by
any release, patches included), with Show me running exactly those steps;
never stacked on the first-run guide; reopenable from Help.

Two halves:

  Static (no browser) - the rot guard and the wiring:
    - VERSION.txt's top version MUST have an entry in whatsnew_content.js.
      This is the test that FAILS when a new MAJOR.MINOR ships without its
      curated highlights.
    - every entry is 4-8 items, plain text, no emoji;
    - index.html loads both scripts and carries ONE Help menu item for What's
      New, and app-menubar.js dispatches it.

  Browser (Playwright, shared e2e server) - the gating matrix and the modal:
    - newSteps() filters the Advanced steps by `since`, in guide order;
    - decide(): a patch with new steps offers them, a patch without is
      silent, skipped versions get every step since, a minor/major change
      shows its entry, first run stamps silently, older versions are quiet;
    - autoRun(): a patch update with steps opens the window with Show me,
      Close stamps and skips, a patch with none is not offered;
    - Show me runs only the new steps, each from its entry snapshot;
    - Help -> What's New reopens it regardless of the stamp.

Run the browser half ALONE (the harness pins one port):
    python -m pytest tests/test_whats_new.py -v --browser chromium
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SRC = os.path.join(ROOT, 'src')

CONTENT_JS = os.path.join(SRC, 'static', 'js', 'whatsnew_content.js')
LOGIC_JS = os.path.join(SRC, 'static', 'js', 'whatsnew.js')
INDEX_HTML = os.path.join(SRC, 'templates', 'index.html')
MENUBAR_JS = os.path.join(SRC, 'static', 'js', 'app-menubar.js')
VERSION_TXT = os.path.join(SRC, 'VERSION.txt')


def _read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def _top_version():
    """First vX.Y[.Z] heading in VERSION.txt - the shipped version."""
    m = re.search(r'^v(\d+)\.(\d+)(?:\.\d+)*\s*-', _read(VERSION_TXT), re.M)
    assert m, 'VERSION.txt has no vX.Y version heading'
    return '%s.%s' % (m.group(1), m.group(2))


def _content_entries():
    """{major.minor: entry-source} parsed from whatsnew_content.js."""
    src = _read(CONTENT_JS)
    keys = [(m.group(1), m.start())
            for m in re.finditer(r"^\s{4}'(\d+\.\d+)':", src, re.M)]
    assert keys, 'whatsnew_content.js defines no version entries'
    entries = {}
    for i, (key, start) in enumerate(keys):
        end = keys[i + 1][1] if i + 1 < len(keys) else len(src)
        entries[key] = src[start:end]
    return entries


# ── the rot guard ────────────────────────────────────────────────────────

def test_top_version_has_a_whatsnew_entry():
    """A new MAJOR.MINOR cannot ship without curated highlights.

    When VERSION.txt's top version moves to a new feature version (0.13,
    1.0, ...) this fails until whatsnew_content.js gets that entry.
    """
    top = _top_version()
    assert top in _content_entries(), (
        "VERSION.txt ships v%s but whatsnew_content.js has no '%s' entry - "
        "write the highlights before releasing a new MAJOR.MINOR." % (top, top))


def test_entries_are_4_to_8_items():
    for key, body in _content_entries().items():
        n = len(re.findall(r'\{\s*h:', body))
        assert 4 <= n <= 8, '%s entry has %d items; the splash wants 4-8' % (key, n)
        assert re.search(r"title:\s*'", body), '%s entry has no title' % key


def test_content_is_plain_text_no_emoji():
    src = _read(CONTENT_JS)
    # No emoji / pictographs anywhere in the file.
    for ch in src:
        assert not (0x1F000 <= ord(ch) <= 0x1FAFF or 0x2600 <= ord(ch) <= 0x27BF), (
            'emoji %r in whatsnew_content.js; the splash is plain text' % ch)
    # No HTML markup inside item strings (textContent rendering, plain voice).
    for key, body in _content_entries().items():
        for m in re.finditer(r"[hd]:\s*'([^']*)'", body):
            assert '<' not in m.group(1), '%s entry contains markup: %r' % (key, m.group(1))


def test_content_never_says_retired_words():
    """The splash is pure display text, so the whole file must stay clean
    of the words the app no longer says: 'tails' (circuits, not tails -
    user ruling, 2026-08-30), 'Signal + Power' (the tick is Wiring; Power
    Wiring and Data Wiring are sheets of their own), 'N-way' (a snake is an
    N channel snake) and 'Halves' (the port shape is OPT Split / Split).
    Same guard as tests/test_tour_anchors.py runs over the tours."""
    from test_tour_anchors import _retired_wording_hits
    hits = _retired_wording_hits(_read(CONTENT_JS))
    assert not hits, 'whatsnew_content.js still says:\n' + '\n'.join(hits)


def test_every_item_is_its_own_subject():
    """One entry per thing that changed for the user, none twice: no two
    items share a heading, and no item is the run-on that grew by
    accretion - each d stays under a short paragraph."""
    for key, body in _content_entries().items():
        heads = re.findall(r"h:\s*'([^']*)'", body)
        assert len(heads) == len(set(heads)), '%s repeats a heading: %r' % (key, heads)
        for m in re.finditer(r"d:\s*'([^']*)'", body):
            d = m.group(1)
            assert len(d) <= 1000, (
                '%s item %r runs to %d characters; split it into entries a '
                'reader can scan' % (key, d[:40], len(d)))


# ── the wiring (new files must not rot) ──────────────────────────────────

def test_index_loads_splash_scripts():
    html = _read(INDEX_HTML)
    assert '/static/js/whatsnew_content.js' in html
    assert '/static/js/whatsnew.js' in html
    # Content loads before the logic that reads it.
    assert html.index('whatsnew_content.js') < html.index('/static/js/whatsnew.js')
    # The splash defers to the tour, so it must load after quickstart.js.
    assert html.index('quickstart.js') < html.index('/static/js/whatsnew.js')


def test_help_menu_has_whats_new():
    html = _read(INDEX_HTML)
    m = re.search(r'data-action="whats-new"[^>]*data-label="([^"]+)"', html)
    assert m, 'Help menu has no whats-new option'
    assert 'New' in m.group(1)


def test_menu_action_dispatches_to_whatsnew():
    src = _read(MENUBAR_JS)
    assert "case 'whats-new':" in src
    assert 'WhatsNew.open()' in src


def test_help_menu_has_one_whats_new_entry():
    """The What's New in 1.0 guide is gone: its menu item and handler with
    it. One entry opens the window; Show me lives inside it."""
    html = _read(INDEX_HTML)
    help_menu = html[html.index('id="menu-help"'):]
    help_menu = help_menu[:help_menu.index('</div>\n\n')] if '</div>\n\n' in help_menu else help_menu
    labels = re.findall(r'data-label="([^"]*New[^"]*)"', help_menu)
    assert labels == ['What’s New…'], labels
    assert 'whats-new-tour' not in html
    assert 'whats-new-tour' not in _read(MENUBAR_JS)


def test_logic_uses_its_own_storage_key():
    src = _read(LOGIC_JS)
    assert "lrd_whatsnew_seen" in src
    # It must not touch the tour's key except to read whether the tour runs.
    assert "localStorage.setItem('lrd_quickstart_disabled'" not in src


# ── browser: gating matrix + modal behavior ──────────────────────────────

pw = pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    """Leave the shared server project the way this module found it."""


@pytest.fixture(scope="module")
def page(e2e_server, pw_browser):
    context = pw_browser.new_context()
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}"
    )
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_timeout(1500)
    yield pg
    context.close()


def _decide(page, current, stamped):
    return page.evaluate(
        "([c, s]) => window.WhatsNew.decide(c, s)", [current, stamped])


def _new_steps(page, after, up_to):
    return page.evaluate(
        "([a, u]) => window.QuickStart.newSteps(a, u)", [after, up_to])


def _since_table(page):
    """[(key, since)] of the Advanced Guide, in guide order."""
    return [tuple(x) for x in page.evaluate("""() => {
        const S = window.QuickStart.steps();
        return window.QuickStart.tours().advanced.map(s =>
            [Object.keys(S).find(k => S[k] === s), s.since || null]);
    }""")]


def _v(s):
    return tuple(int(x) for x in s.split('.'))


def _pad(t):
    return t + (0,) * (4 - len(t))


# ── the steps the walkthrough runs ───────────────────────────────────────

def test_new_steps_filter_by_since(page):
    """newSteps(after, upTo) is every Advanced step whose `since` is newer
    than `after` and not newer than `upTo`, in guide order, checked
    against the step table for several windows, and by name for the 1.5.3
    steps."""
    table = _since_table(page)
    assert any(s for _, s in table), 'no Advanced step carries since'
    for after, up_to in (('1.4.9', '1.5.0'), ('1.5.0', '1.5.2'), ('1.5.2', '1.5.3'),
                         ('1.5', '1.5.3'), ('1.0', '1.5.3'), ('1.5.3', '1.5.3')):
        want = [k for k, s in table if s
                and _pad(_v(after)) < _pad(_v(s)) <= _pad(_v(up_to))]
        assert _new_steps(page, after, up_to) == want, (after, up_to)
    assert _new_steps(page, '1.5.2', '1.5.3') == [
        'cableStock', 'cableStockPieces', 'takeOver', 'customPower', 'customDraw', 'sweepShare',
        'addService', 'serviceDistro']
    # A step is never newer than the running version.
    assert not set(_new_steps(page, '1.5.2', '1.5.2'))
    assert _new_steps(page, 'junk', '1.5.3') == []


# ── decide(): the gating matrix ──────────────────────────────────────────

def test_decide_patch_update_with_new_steps_offers_them(page):
    d = _decide(page, '1.5.3', '1.5.2')
    assert d['show'] is True and d['stamp'] is None, d
    assert d['window'] == {'key': None, 'after': '1.5.2', 'upTo': '1.5.3',
                           'steps': _new_steps(page, '1.5.2', '1.5.3')}, d
    assert d['window']['steps'], d


def test_decide_skipped_versions_get_every_step_since(page):
    """1.5.0 -> 1.5.3: every step added in 1.5.1, 1.5.2 and 1.5.3, in
    guide order. A stamp from before 1.5.3 holds MAJOR.MINOR only ('1.5'),
    which reads as 1.5.0."""
    d = _decide(page, '1.5.3', '1.5.0')
    assert d['show'] and d['window']['steps'] == _new_steps(page, '1.5.0', '1.5.3'), d
    assert 'fileExports' in d['window']['steps'], d
    assert _decide(page, '1.5.3', '1.5')['window']['steps'] == d['window']['steps']


def test_decide_patch_without_new_steps_is_silent(page):
    assert _decide(page, '1.5.4', '1.5.3') == {'show': False, 'stamp': '1.5.4', 'window': None}
    assert _decide(page, '1.0.2', '1.0.1') == {'show': False, 'stamp': '1.0.2', 'window': None}


def test_decide_minor_change_shows_the_entry_and_its_steps(page):
    d = _decide(page, '1.5.0', '1.4.2')
    assert d['show'] and d['window']['key'] == '1.5', d
    assert d['window']['steps'] == _new_steps(page, '1.4.2', '1.5.0'), d
    # A feature version with an entry and no steps still shows (no Show me).
    d = _decide(page, '1.4.0', '1.3.2')
    assert d['show'] and d['window']['key'] == '1.4' and d['window']['steps'] == [], d


def test_decide_major_change_shows(page):
    assert page.evaluate("window.WhatsNew._majorMinor('1.0.3')") == '1.0'
    d = _decide(page, '1.0.1', '0.11.2')
    assert d['show'] and d['window']['key'] == '1.0', d


def test_decide_first_run_stamps_silently(page):
    """No stamp = brand-new install: never show (the guide owns first run)."""
    assert _decide(page, '1.5.3', None) == {'show': False, 'stamp': '1.5.3', 'window': None}


def test_decide_same_or_older_version_is_silent(page):
    assert _decide(page, '1.5.3', '1.5.3') == {'show': False, 'stamp': None, 'window': None}
    assert _decide(page, '1.5.2', '1.5.3') == {'show': False, 'stamp': '1.5.2', 'window': None}


def test_decide_unknown_version_stamps_silently(page):
    """Feature version changed but no curated entry and no steps: quiet."""
    assert _decide(page, '1.99.0', '1.98.0') == {'show': False, 'stamp': '1.99.0', 'window': None}


def test_decide_garbage_version_is_silent(page):
    assert _decide(page, 'not-a-version', '0.11') == {'show': False, 'stamp': None, 'window': None}


# ── autoRun(): what the first launch after an update does ───────────────

def _modal_visible(page):
    return page.evaluate(
        "() => { const m = document.getElementById('whatsnew-modal');"
        " return !!m && m.style.display !== 'none'; }")


def _serve_version(page, version):
    page.unroute('**/api/version')
    page.route('**/api/version', lambda r: r.fulfill(json={'version': version}))


def _wait_modal(page):
    page.wait_for_function(
        "() => { const m = document.getElementById('whatsnew-modal');"
        " return !!m && m.style.display === 'block'; }")


def test_autorun_update_shows_then_stamp_silences(page):
    """Stamp behind the running version -> window; dismiss stamps the
    running version; quiet after."""
    page.unroute('**/api/version')
    page.evaluate("localStorage.setItem(window.WhatsNew.LS_KEY, '0.10')")
    page.evaluate("window.WhatsNew.autoRun(true)")
    _wait_modal(page)
    heading = page.evaluate(
        "document.querySelector('#whatsnew-modal .modal-content').textContent")
    server = page.evaluate("fetch('/api/version').then(r => r.json()).then(d => d.version)")
    server_mm = page.evaluate("(v) => window.WhatsNew._majorMinor(v)", server)
    assert ('v' + server_mm) in heading
    page.click('#whatsnew-close')
    assert not _modal_visible(page)
    assert page.evaluate("localStorage.getItem(window.WhatsNew.LS_KEY)") == server
    page.evaluate("window.WhatsNew.autoRun(true)")
    page.wait_for_timeout(400)
    assert not _modal_visible(page)


def test_autorun_patch_update_with_new_steps_offers_show_me(page):
    """1.5.2 -> 1.5.3: the window opens on a patch release because the
    release added guide steps; with no entry of its own it lists their
    titles, offers Show me, and Close skips them (stamped, quiet after)."""
    _serve_version(page, '1.5.3')
    try:
        page.evaluate("localStorage.setItem(window.WhatsNew.LS_KEY, '1.5.2')")
        page.evaluate("window.WhatsNew.autoRun(true)")
        _wait_modal(page)
        text = page.evaluate("document.querySelector('#whatsnew-modal .modal-content').textContent")
        titles = page.evaluate("""(keys) => keys.map(k => {
            const t = document.createElement('textarea');
            t.innerHTML = window.QuickStart.steps()[k].title; return t.value; })""",
            _new_steps(page, '1.5.2', '1.5.3'))
        assert 'v1.5.3' in text, text
        for t in titles:
            assert t in text, (t, text)
        assert page.evaluate("!!document.getElementById('whatsnew-show-me')")
        page.click('#whatsnew-close')
        assert page.evaluate("localStorage.getItem(window.WhatsNew.LS_KEY)") == '1.5.3'
        assert not page.evaluate("window.QuickStart.state().visible")
        page.evaluate("window.WhatsNew.autoRun(true)")
        page.wait_for_timeout(400)
        assert not _modal_visible(page)
    finally:
        page.unroute('**/api/version')


def test_autorun_patch_update_without_new_steps_is_not_offered(page):
    _serve_version(page, '1.5.4')
    try:
        page.evaluate("localStorage.setItem(window.WhatsNew.LS_KEY, '1.5.3')")
        page.evaluate("window.WhatsNew.autoRun(true)")
        page.wait_for_function(
            "() => localStorage.getItem(window.WhatsNew.LS_KEY) === '1.5.4'")
        assert not _modal_visible(page)
    finally:
        page.unroute('**/api/version')


def test_autorun_first_run_never_stacks_on_tour(page):
    """Fresh install: no window, stamp written silently."""
    page.evaluate("localStorage.removeItem(window.WhatsNew.LS_KEY)")
    page.evaluate("window.WhatsNew.autoRun(true)")
    page.wait_for_function(
        "() => !!localStorage.getItem(window.WhatsNew.LS_KEY)")
    assert not _modal_visible(page)


def test_help_reopens_regardless_of_stamp(page):
    """The stamp silences auto-show only; Help -> What's New always opens."""
    page.evaluate("window.WhatsNew.open()")
    _wait_modal(page)
    assert _modal_visible(page)


def test_modal_fits_theme_and_offers_show_me(page):
    """Open panel sits inside the viewport, opaque, with Show me (the
    running feature version brought guide steps) and Close."""
    box = page.evaluate(
        "() => { const p = document.querySelector('#whatsnew-modal .modal-content');"
        " const r = p.getBoundingClientRect();"
        " const bg = getComputedStyle(p).backgroundColor;"
        " return { top: r.top, left: r.left, right: r.right, bottom: r.bottom,"
        "   vw: window.innerWidth, vh: window.innerHeight, bg }; }")
    assert box['top'] >= 0 and box['left'] >= 0
    assert box['right'] <= box['vw'] and box['bottom'] <= box['vh']
    assert box['bg'] not in ('rgba(0, 0, 0, 0)', 'transparent')
    assert page.evaluate("document.getElementById('whatsnew-show-me').textContent") == 'Show me'
    assert page.evaluate("!!document.getElementById('whatsnew-close')")
    page.click('#whatsnew-close')
    assert not _modal_visible(page)


# ── Show me runs exactly the new steps ───────────────────────────────────

@pytest.fixture
def guide_page(e2e_server, pw_browser):
    """The snapshot builder's viewport, so the steps play on the walls the
    shipped snapshots frame."""
    context = pw_browser.new_context(viewport={'width': 1600, 'height': 950})
    context.add_init_script(
        "try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    pg = context.new_page()
    pg.goto(e2e_server, wait_until='domcontentloaded')
    pg.wait_for_function(
        "() => !!(window.app && window.app.project && window.canvasRenderer"
        " && window.QuickStart && window.WhatsNew)")
    pg.wait_for_timeout(1500)
    yield pg
    pg.evaluate("() => window.QuickStart.end()")
    context.close()


def test_show_me_runs_only_the_new_steps(guide_page):
    """1.5.2 -> 1.5.3, Show me: the walkthrough is exactly the steps added
    in 1.5.3, in guide order, each landing on its own entry snapshot and
    taking; Done puts the person's project back."""
    from test_tour_anchors import _wait_step
    pg = guide_page
    _serve_version(pg, '1.5.3')
    keys = _new_steps(pg, '1.5.2', '1.5.3')
    before = pg.evaluate("() => window.app._canonicalJson(window.app.project)")
    pg.evaluate("localStorage.setItem(window.WhatsNew.LS_KEY, '1.5.2')")
    pg.evaluate("window.WhatsNew.autoRun(true)")
    _wait_modal(pg)
    pg.evaluate("window.QuickStart.setSpeed(3)")
    pg.click('#whatsnew-show-me')
    assert not _modal_visible(pg)
    assert pg.evaluate("localStorage.getItem(window.WhatsNew.LS_KEY)") == '1.5.3'
    titles = pg.evaluate("(keys) => keys.map(k => window.QuickStart.steps()[k].title)", keys)
    for i, key in enumerate(keys):
        if i:
            pg.locator('#qs-next').click()
        st = _wait_step(pg, i)
        qs = pg.evaluate("window.QuickStart.state()")
        assert qs['tour'] == 'whatsNew' and qs['steps'] == keys, qs
        assert st['qs']['index'] == i and st['state'] == 'done' and not st['fail'], (key, st)
        assert qs['jumpedVia'] == 'snapshot', (key, qs)
        assert pg.evaluate("document.querySelector('#qs-callout h3').innerHTML") == titles[i]
    assert pg.evaluate("document.getElementById('qs-next').textContent") == 'Done'
    pg.locator('#qs-next').click()
    pg.wait_for_function("() => !window.QuickStart.state().visible && !window.QuickStart.state().running")
    assert pg.evaluate("() => window.app._canonicalJson(window.app.project)") == before

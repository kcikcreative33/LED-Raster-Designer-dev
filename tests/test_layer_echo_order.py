"""An older copy of a screen never comes back over a newer edit.

The server echoes (layer_updated) and answers each PUT with the screen as
that PUT left it. Two quick edits to one screen on a slow machine let the
first one's echo land after the second edit, and the page showed the older
copy until the next echo: a renamed screen flicked back to its old name,
and the Advanced Guide read a 3fer as unshared (CI, 2026-10-19). Echoes are
held back here so they always land late.
"""
import pytest

pytest.importorskip("playwright.sync_api", reason="playwright not installed")


@pytest.fixture(scope="module", autouse=True)
def _guard(server_project_guard):
    yield


DELAY_LAYER_UPDATED = """(() => {
    let real;
    Object.defineProperty(window, 'io', {
        configurable: true,
        get() { return real; },
        set(v) {
            real = function (...args) {
                const s = v(...args), on = s.on.bind(s);
                s.on = (ev, h) => on(ev, ev === 'layer_updated'
                    ? (...x) => setTimeout(() => h(...x), 400) : h);
                return s;
            };
            Object.assign(real, v);
        },
    });
})();"""


TWO_EDITS_JS = """async () => {
    const app = window.app, l = app.project.layers[0];
    l.name = 'FIRST'; app.updateLayers([l]);
    await new Promise(r => setTimeout(r, 50));
    l.name = 'SECOND'; app.updateLayers([l]);
    const seen = [];
    for (let i = 0; i < 24; i++) {
        await new Promise(r => setTimeout(r, 50));
        seen.push(app.project.layers[0].name);
    }
    await app._layerSavesSettled();
    const server = (await (await fetch('/api/project')).json()).layers[0].name;
    return { seen, server };
}"""


def test_a_late_echo_never_puts_an_older_copy_back(e2e_server, pw_browser):
    ctx = pw_browser.new_context()
    ctx.add_init_script("try{localStorage.setItem('lrd_quickstart_disabled','1');}catch(e){}")
    ctx.add_init_script(DELAY_LAYER_UPDATED)
    pg = ctx.new_page()
    try:
        pg.goto(e2e_server, wait_until='domcontentloaded')
        pg.wait_for_function("() => !!(window.app && window.app._initialLoadComplete)")
        out = pg.evaluate(TWO_EDITS_JS)
        assert 'FIRST' not in out['seen'], out
        assert out['seen'][-1] == 'SECOND' and out['server'] == 'SECOND', out
    finally:
        ctx.close()

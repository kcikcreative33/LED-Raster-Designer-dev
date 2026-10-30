// app-mirror-screens: feature methods for LEDRasterApp, attached to the
// prototype via the carrier class.
//
// ── Mirror a screen (owner, 2026-10-30) ──────────────────────────────────
//
// "You pick the screen to copy; the copy screen's port map follows the first
// automatically and can't be drawn separately. A mismatch in size or panel is
// refused." NovaStar's Copy mode is what feeds it: on an H_4xfiber "OPT 3
// copies the output on OPT 1, while OPT 4 copies the output on OPT 2" (H15
// Video Wall Splicer Specifications V1.15.0 p.36), on the enhanced card OPT
// 5-8 copy OPT 1-4 (p.37), and on an MX40 Pro in 20-port mode OPT 3/4 are
// "the copy channel" of OPT 1/2 (User Manual V1.5.0 p.9), where each box
// there is set Mirror or Backup.
//
// The setting is the layer's `dataMirrorOf` (the screen it copies), set from
// Screen Info's Data Settings and validated by the layer PUT
// (port_assignment.mirror_set_refusal). Two things follow from it here:
//
//   * THE MAP IS THE SOURCE'S. Every field that decides which cabinet rides
//     which port (MIRROR_DATA_FIELDS) is copied from the source onto the
//     mirror at every history snapshot (_syncMirrorScreens, from saveState),
//     so the canvas, the port count and every export read the mirror's own
//     layer and find the source's map on it.
//   * THE MAP IS READ-ONLY on the mirror: its data-map controls are dimmed,
//     and any attempt - a control, a custom run, a fill, a placement in the
//     tray - is refused with an error naming the source (never silent, the
//     locked-screen rule's shape).
//
// Where the mirror's runs land is the server's (port_assignment's mirror
// pass): port N of the source on socket S lands port N of the mirror on the
// copy of S, and the resolution says exactly what is missing where it cannot.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

// The fields that make a screen's data port map, copied from the source onto
// its mirror. The processing settings ride with the walk because they decide
// how many cabinets a port carries.
export const MIRROR_DATA_FIELDS = [
    'flowPattern', 'lastFlowPattern', 'portMappingMode',
    'customPortPaths', 'customPortIndex', 'customPortOverrides',
    'processorType', 'bitDepth', 'frameRate', 'lowLatency',
];

// The Screen Info controls that edit the data port map. On a mirror they
// are dimmed and any attempt on them is refused with the mirror's error.
const MIRROR_LOCKED_CONTROLS = [
    '#processor-type', '#bit-depth', '#frame-rate', '#mapping-organized',
    '#mapping-max-capacity', '#low-latency', '.flow-pattern-btn',
    '#custom-flow-toggle', '#custom-active-port-input', '#custom-prev-port',
    '#custom-next-port', '#custom-clear-port', '#custom-clear-all',
    '#custom-clear-selection',
].join(', ');

class _MirrorScreens {
    // The screen `layer` mirrors, or null: a screen layer of this project
    // other than itself. A stale id (its source deleted) reads as null here
    // and is said in Screen Info from the resolution's issue.
    mirrorSourceOf(layer) {
        if (!layer || layer.dataMirrorOf === undefined
                || layer.dataMirrorOf === null || layer.dataMirrorOf === '') {
            return null;
        }
        const id = String(layer.dataMirrorOf);
        const src = ((this.project && this.project.layers) || [])
            .find(l => String(l.id) === id);
        if (!src || src === layer || (src.type || 'screen') !== 'screen') return null;
        return src;
    }

    // The screens set to mirror `layer`.
    mirrorsOf(layer) {
        if (!layer) return [];
        return ((this.project && this.project.layers) || [])
            .filter(l => l !== layer && l.dataMirrorOf !== undefined
                && l.dataMirrorOf !== null
                && String(l.dataMirrorOf) === String(layer.id));
    }

    // The resolution's word on one mirror - why it is not landing (a
    // resize since it was set, nowhere to plug in) - as message lines.
    _mirrorIssueLines(layer) {
        const issues = (this._assignment && this._assignment.issues) || [];
        return issues
            .filter(i => i && String(i.layerId) === String(layer.id)
                && /^mirror-/.test(i.kind || ''))
            .map(i => i.message);
    }

    // Copy the source's data map onto every mirror (MIRROR_DATA_FIELDS),
    // and PUT the mirrors that changed. Called from saveState, so the
    // snapshot, the save and the canvas all carry the copied map. Returns
    // the mirrors it wrote.
    _syncMirrorScreens() {
        const layers = (this.project && this.project.layers) || [];
        const wrote = [];
        layers.forEach(layer => {
            const src = this.mirrorSourceOf(layer);
            if (!src || src.dataMirrorOf) return;
            const body = {};
            MIRROR_DATA_FIELDS.forEach(k => {
                const want = src[k] === undefined ? undefined
                    : JSON.parse(JSON.stringify(src[k]));
                if (JSON.stringify(layer[k]) === JSON.stringify(want)) return;
                if (want === undefined) delete layer[k];
                else layer[k] = want;
                body[k] = want === undefined ? null : want;
            });
            if (Object.keys(body).length) {
                wrote.push(layer);
                if (typeof this._putLayer === 'function') this._putLayer(layer.id, body);
            }
        });
        if (wrote.length) {
            sendClientLog('mirror_screens_synced',
                          { layerIds: wrote.map(l => l.id) });
        }
        return wrote;
    }

    // The error a change to a mirror's data map says, naming the source.
    _mirrorErrorText(layer) {
        const src = this.mirrorSourceOf(layer);
        const name = layer.name || `Screen ${layer.id}`;
        const from = src ? (src.name || `Screen ${src.id}`) : 'another screen';
        return `${name} mirrors ${from} - its data port map follows ${from}'s `
            + 'and cannot be changed on its own. Change it on '
            + `${from}, or stop mirroring in Screen Info.`;
    }

    // True (and the error said) when any of `layers` mirrors a screen: for
    // a data-map change that must not reach a mirror.
    _mirrorRefused(layers) {
        const list = (Array.isArray(layers) ? layers : [layers]).filter(Boolean);
        const hit = list.find(l => this.mirrorSourceOf(l));
        if (!hit) return false;
        if (typeof this._toast === 'function') {
            this._toast(this._mirrorErrorText(hit), true, 6000);
        }
        sendClientLog('mirror_edit_refused', { layerId: hit.id });
        return true;
    }

    // Screen Info's "Mirror a screen" row, refreshed with the rest of the
    // data settings (updatePortCapacityDisplay): the pick, the note naming
    // the source (or the mirrors of this screen), and the dimmed map
    // controls while the shown screen is a mirror.
    updateMirrorScreenControl() {
        this._wireMirrorScreenControl();
        const row = document.getElementById('mirror-screen-row');
        const select = document.getElementById('mirror-screen');
        const note = document.getElementById('mirror-screen-note');
        if (!row || !select) return;
        const layer = this.currentLayer;
        const isScreen = !!layer && (layer.type || 'screen') === 'screen';
        row.style.display = isScreen ? '' : 'none';
        if (note) note.style.display = 'none';
        const src = isScreen ? this.mirrorSourceOf(layer) : null;
        this._dimMirrorControls(!!src);
        if (!isScreen) return;
        const layers = ((this.project && this.project.layers) || [])
            .filter(l => l !== layer && (l.type || 'screen') === 'screen'
                && !this.mirrorSourceOf(l));
        select.innerHTML = '';
        const none = document.createElement('option');
        none.value = '';
        none.textContent = 'None';
        select.appendChild(none);
        layers.forEach(l => {
            const opt = document.createElement('option');
            opt.value = String(l.id);
            opt.textContent = l.name || `Screen ${l.id}`;
            select.appendChild(opt);
        });
        const stored = layer.dataMirrorOf;
        const value = stored === undefined || stored === null ? '' : String(stored);
        if (value && !layers.some(l => String(l.id) === value)) {
            // a source that is gone (or became a mirror) still shows what
            // is stored, so the note below has something to name
            const gone = document.createElement('option');
            gone.value = value;
            gone.textContent = `Screen ${value} (not in the project)`;
            select.appendChild(gone);
        }
        select.value = value;
        const mirrors = this.mirrorsOf(layer);
        let lines = [];
        let warn = false;
        if (src) {
            const from = src.name || `Screen ${src.id}`;
            lines.push(`Port map follows ${from}. Its runs come off the copy `
                + `outputs of the card feeding ${from}.`);
            const issues = this._mirrorIssueLines(layer);
            if (issues.length) { lines = lines.concat(issues); warn = true; }
        } else if (value) {
            lines.push('The screen this one mirrors is not in the project. '
                + 'Choose the screen to copy again.');
            warn = true;
        } else if (mirrors.length) {
            const names = mirrors.map(m => m.name || `Screen ${m.id}`);
            lines.push(`Mirrored by ${names.join(', ')}.`);
        }
        // Mirroring a screen that is itself a source is not offered: a
        // copy of a copy is refused.
        select.disabled = !!mirrors.length && !value;
        if (note && lines.length) {
            note.textContent = lines.join(' ');
            note.style.color = warn ? '#d05a52' : '#888';
            note.style.display = '';
        }
    }

    _dimMirrorControls(on) {
        document.querySelectorAll(MIRROR_LOCKED_CONTROLS).forEach(el => {
            el.style.opacity = on ? '0.45' : '';
            if (on) el.dataset.mirrorLocked = '1';
            else delete el.dataset.mirrorLocked;
        });
    }

    _wireMirrorScreenControl() {
        if (this._mirrorControlWired) return;
        const select = document.getElementById('mirror-screen');
        if (!select) return;
        this._mirrorControlWired = true;
        select.addEventListener('change', () => {
            const layer = this.currentLayer;
            if (!layer) return;
            this.setLayerMirror(layer, select.value || null);
        });
        // Every attempt on a mirror's data-map controls is refused out
        // loud, before the control's own handler runs.
        const guard = (e) => {
            const el = e.target && e.target.closest
                ? e.target.closest(MIRROR_LOCKED_CONTROLS) : null;
            if (!el || !this.currentLayer
                    || !this.mirrorSourceOf(this.currentLayer)) return;
            if (e.type === 'keydown' && ['Tab', 'Shift', 'Escape']
                .includes(e.key)) return;
            e.preventDefault();
            e.stopImmediatePropagation();
            if (e.type !== 'mousedown') this._mirrorRefused(this.currentLayer);
        };
        ['mousedown', 'click', 'keydown', 'change'].forEach(type =>
            document.addEventListener(type, guard, true));
    }

    // Set (sourceId) or clear (null) the screen `layer` mirrors. The server
    // validates and answers 409 with the reason where it refuses; nothing
    // changes then. On success the mirror lets go of its own pins (the
    // server drops them too), takes the source's map, and one history step
    // records it.
    setLayerMirror(layer, sourceId) {
        if (!layer) return Promise.resolve(false);
        if (this._lockedRefused && this._lockedRefused(layer)) {
            this.updateMirrorScreenControl();
            return Promise.resolve(false);
        }
        const want = sourceId === null || sourceId === undefined || sourceId === ''
            ? null : sourceId;
        const typed = want === null ? null
            : (Number.isFinite(Number(want)) ? Number(want) : want);
        return fetch(`/api/layer/${layer.id}?edited=1`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ dataMirrorOf: typed }),
        })
            .then(r => r.json().then(data => ({ ok: r.ok, data })))
            .then(({ ok, data }) => {
                if (!ok) {
                    if (typeof this._toast === 'function') {
                        this._toast((data && data.error)
                            || 'That screen cannot be mirrored.', true, 6000);
                    }
                    this.updateMirrorScreenControl();
                    return false;
                }
                if (typed === null) delete layer.dataMirrorOf;
                else layer.dataMirrorOf = typed;
                if (typed !== null && this.project && this.project.port_assignments
                        && Array.isArray(this.project.port_assignments.pins)) {
                    this.project.port_assignments.pins = this.project
                        .port_assignments.pins
                        .filter(p => String(p.layerId) !== String(layer.id));
                }
                sendClientLog('mirror_screen_set',
                              { layerId: layer.id, mirrorOf: typed });
                this.saveState(typed === null ? 'Stop Mirroring' : 'Mirror Screen');
                if (typeof this.refreshPortAssignment === 'function') {
                    this.refreshPortAssignment();
                }
                if (typeof this.updatePortCapacityDisplay === 'function') {
                    this.updatePortCapacityDisplay();
                }
                if (window.canvasRenderer) window.canvasRenderer.render();
                return true;
            })
            .catch(err => {
                sendClientLog('mirror_screen_set_failed',
                              { layerId: layer.id, error: String(err) });
                return false;
            });
    }

    // ── a box on a copy OPT: Mirror or Backup ────────────────────────────
    //
    // On a card whose copy OPTs pick per box (the MX40 Pro in 20-port mode -
    // owner, 2026-10-30, "Either, you pick") an add that puts a box on a
    // copy OPT, or brings one there as the default pair, asks which it is
    // (resolve_card's nextBoxOnCopy). Resolves 'mirror', 'backup' or null
    // (cancelled: nothing is added).
    askCopyRole(card) {
        const modal = document.getElementById('copy-role-modal');
        if (!modal) return Promise.resolve('backup');
        if (!this._copyRoleWired) {
            this._copyRoleWired = true;
            const on = (id, result) => {
                const btn = document.getElementById(id);
                if (btn) btn.addEventListener('click', () => this._closeCopyRole(result));
            };
            on('copy-role-cancel', null);
            on('copy-role-backup', 'backup');
            on('copy-role-mirror', 'mirror');
            modal.addEventListener('click', (e) => {
                if (e.target === modal) this._closeCopyRole(null);
            });
            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape' && this._copyRoleResolve) this._closeCopyRole(null);
            });
        }
        const text = document.getElementById('copy-role-text');
        if (text) {
            const pairs = (card && card.copyTrunkList) || [];
            const copies = pairs.map(t => `${t.trunkTitle} copies ${t.copiesTitle}`)
                .join(', ');
            text.textContent = `This box goes on a copy output${copies
                ? ` (${copies})` : ''}. Mirror: it feeds a mirror screen. `
                + 'Backup: it backs up the output it copies.';
        }
        if (this._copyRoleResolve) this._copyRoleResolve(null);
        modal.style.display = 'block';
        return new Promise(resolve => { this._copyRoleResolve = resolve; });
    }

    _closeCopyRole(result) {
        const modal = document.getElementById('copy-role-modal');
        if (modal) modal.style.display = 'none';
        const resolve = this._copyRoleResolve;
        this._copyRoleResolve = null;
        if (resolve) resolve(result);
    }

    // Add one box to `card` through the processor routes, asking Mirror or
    // Backup first where the box lands on a copy OPT of a per-box card.
    addBoxWithRole(proc, card, body, action = 'Add Breakout Box') {
        const url = `/api/processors/${proc.id}/cards/${card.id}/cvts`;
        if (!card.nextBoxOnCopy) {
            return this._processorRequest(url, 'POST', body, action);
        }
        return this.askCopyRole(card).then(role => {
            if (!role) return null;
            return this._processorRequest(url, 'POST',
                Object.assign({}, body, { copyRole: role }), action);
        });
    }

    // The box gear's MIRROR / BACKUP strip, on a box sitting on a copy OPT
    // of a card that picks per box (resolve_card's copyRoleChoice).
    _buildBoxCopyRoleStrip(proc, cvt) {
        const strip = document.createElement('div');
        strip.className = 'hw-pop-red-strip hw-pop-box-copyrole';
        strip.style.marginTop = '6px';
        const cap = document.createElement('span');
        cap.className = 'hw-pop-red-cap';
        cap.textContent = 'COPY';
        cap.title = 'What this box on a copy output carries.';
        strip.appendChild(cap);
        const bar = document.createElement('div');
        bar.className = 'hw-pop-seg';
        bar.setAttribute('role', 'radiogroup');
        bar.setAttribute('aria-label', 'Copy');
        bar.dataset.lrdField = `processor-cvt-copyrole-${cvt.id}`;
        [['mirror', 'Mirror', 'Feeds a mirror screen: set a screen to mirror '
            + 'the one on the output this box copies.'],
         ['backup', 'Backup', 'Backs up the output this box copies.']]
            .forEach(([role, text, tip]) => {
                const lit = (cvt.copyRole || 'backup') === role;
                const seg = document.createElement('button');
                seg.type = 'button';
                seg.className = 'hw-pop-seg-btn' + (lit ? ' hw-pop-seg-on' : '');
                seg.setAttribute('role', 'radio');
                seg.setAttribute('aria-checked', lit ? 'true' : 'false');
                seg.dataset.level = role;
                seg.textContent = text;
                seg.title = tip;
                seg.addEventListener('click', () => {
                    if (lit) return;
                    this._processorRequest(
                        `/api/processors/${proc.id}/cvts/${cvt.id}`, 'PUT',
                        { copyRole: role }, 'Set Box Copy');
                });
                bar.appendChild(seg);
            });
        strip.appendChild(bar);
        return strip;
    }

    // ── per port: the card's own RJ45 or the box ─────────────────────────
    //
    // Where a card's RJ45s are also carried out on its OPTs (plugChoice:
    // the MX40 Pro, the H_16xRJ45+2xfiber), each port plugs in at ONE
    // place (owner, 2026-10-30, "Per port"). The port's chip says where and
    // switches it; the card's gear switches a whole OPT's ports at once.

    _plugCardWord(proc, card) {
        const word = typeof this.unitWordFor === 'function'
            ? this.unitWordFor(proc, card) : 'card';
        return `${word.charAt(0).toUpperCase()}${word.slice(1)} RJ45`;
    }

    _buildPlugSeg(fieldKey, now, cardText, onPick) {
        const strip = document.createElement('div');
        strip.className = 'hw-pop-red-strip hw-pop-port-plug';
        strip.style.margin = '2px 0 4px 0';
        const cap = document.createElement('span');
        cap.className = 'hw-pop-red-cap';
        cap.textContent = 'PLUGS IN AT';
        cap.title = 'One place per port: never the same port both ways.';
        strip.appendChild(cap);
        const bar = document.createElement('div');
        bar.className = 'hw-pop-seg';
        bar.setAttribute('role', 'radiogroup');
        bar.setAttribute('aria-label', 'Plugs in at');
        bar.dataset.lrdField = fieldKey;
        [['card', cardText, `The port plugs in at the ${cardText}.`],
         ['box', 'Breakout box', 'The port plugs in at the breakout box on '
            + 'the OPT that carries it.']]
            .forEach(([plug, text, tip]) => {
                const lit = now === plug;
                const seg = document.createElement('button');
                seg.type = 'button';
                seg.className = 'hw-pop-seg-btn' + (lit ? ' hw-pop-seg-on' : '');
                seg.setAttribute('role', 'radio');
                seg.setAttribute('aria-checked', lit ? 'true' : 'false');
                seg.dataset.level = plug;
                seg.textContent = text;
                seg.title = tip;
                seg.addEventListener('click', () => { if (!lit) onPick(plug); });
                bar.appendChild(seg);
            });
        strip.appendChild(bar);
        return strip;
    }

    // One port's strip, for the chip's editor.
    _buildPortPlugStrip(proc, card, port) {
        if (!port || !port.plug) return null;
        return this._buildPlugSeg(
            `processor-port-plug-${card.id}-${port.number}`, port.plug,
            this._plugCardWord(proc, card),
            (plug) => this._processorRequest(
                `/api/processors/${proc.id}/cards/${card.id}/ports/${port.number}`,
                'PUT', { plug }, 'Set Port Plug'));
    }

    // The card gear's per-OPT shortcut: each primary box whose ports have
    // the choice, all of its ports at once.
    _buildCardPlugRows(proc, card) {
        const limit = card.plugChoicePorts;
        if (!limit) return null;
        const byNumber = new Map((card.ports || []).map(p => [p.number, p]));
        const rows = [];
        (card.cvts || []).forEach(cvt => {
            if (cvt.copyRole || cvt.beyondTrunks || !cvt.portCount) return;
            const numbers = [];
            for (let n = cvt.firstPort; n < cvt.firstPort + cvt.portCount; n++) {
                if (n <= limit && byNumber.has(n) && byNumber.get(n).plug) numbers.push(n);
            }
            if (!numbers.length) return;
            const atCard = numbers.filter(n => byNumber.get(n).plug === 'card');
            const now = atCard.length === numbers.length ? 'card'
                : (atCard.length ? 'mixed' : 'box');
            const wrap = document.createElement('div');
            wrap.style.marginTop = '4px';
            const head = document.createElement('div');
            head.style.fontSize = '11px';
            head.style.color = 'var(--ps-dim, #c0c0c0)';
            head.textContent = `${cvt.trunkTitle || cvt.displayTitle}: ports `
                + `${numbers[0]}-${numbers[numbers.length - 1]}`
                + (now === 'mixed' ? ` (${atCard.length} at the RJ45)` : '');
            wrap.appendChild(head);
            wrap.appendChild(this._buildPlugSeg(
                `processor-card-plug-${card.id}-${cvt.id}`, now,
                this._plugCardWord(proc, card),
                (plug) => {
                    const set = new Set(card.ethernetPorts || []);
                    numbers.forEach(n => (plug === 'card' ? set.add(n) : set.delete(n)));
                    return this._processorRequest(
                        `/api/processors/${proc.id}/cards/${card.id}`, 'PUT',
                        { ethernetPorts: [...set].sort((a, b) => a - b) },
                        'Set Port Plugs');
                }));
            rows.push(wrap);
        });
        if (!rows.length) return null;
        const block = document.createElement('div');
        block.className = 'hw-pop-plug-block';
        block.style.marginTop = '6px';
        rows.forEach(r => block.appendChild(r));
        return block;
    }
}

for (const k of Object.getOwnPropertyNames(_MirrorScreens.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_MirrorScreens.prototype, k));
    }
}

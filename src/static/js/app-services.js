// app-services: the SERVICE - the house power several distros are fed
// from (owner rulings, 2026-10-20: "in situations where I choose 600A
// service and 400A and 200A distros i then need to be able to use both on
// the same 600A"). The model, the checks it carries, and its card in the
// Hardware tray's Power view.
//
// THE RULINGS, in the owner's terms:
//   * A service is a name, an amps-per-leg rating, a system (the same
//     systems a distro offers) and its own "100% rated" switch, like a
//     distro's main. A show has any number of them, or none - and none is
//     exactly the show it always was: no key is written for it.
//   * A distro goes on a service by dragging its header bar onto the
//     Service card, or by picking the service behind its ⚙; it comes off
//     by picking None there, or from the service card's ⚙. Only a distro
//     of the SAME system goes on; anything else is refused, saying why.
//     Every change is one history entry.
//   * The checks, on the card and in the binder: each leg's load (its
//     distros' leg loads summed) against the service under the distro's own
//     continuous rule (80% of the rating on a US system unless the service
//     is 100% rated); the distros' ratings added up against the service;
//     and the imbalance across all its distros together, read the way a
//     distro's is.
//
// THE SHAPE, stored on the project beside the distros and riding the same
// push and the same project-wide history snapshot:
//     project['services'] -> [{id: 's1', name, ratingA, system, voltage,
//                              phase, main100?}]       in tray order
//     distro['serviceId'] -> 's1' | absent
// A service carries its system's voltage and phase the way a distro does,
// so every distro-systems reader (distroMainLimit, distroLegNames,
// distroSupplyText ...) reads a service record unchanged. The server's
// funnel (app.py _normalize_services) keeps the ids unique and clears a
// serviceId that names no service, or one of another system.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';

class _Services {

    // ---- the model -----------------------------------------------------------

    // The project's services, never creating the key: a show with none
    // saves exactly as it always did.
    getServices() {
        const list = this.project && this.project.services;
        return Array.isArray(list) ? list.filter(s => s && typeof s === 'object' && s.id) : [];
    }

    serviceById(id) {
        if (!id) return null;
        return this.getServices().find(s => s.id === id) || null;
    }

    // The service a distro is on, or null - a serviceId naming no service,
    // or one of another system (a file edited by hand), is no service.
    distroService(d) {
        if (!d || !d.serviceId) return null;
        const s = this.serviceById(d.serviceId);
        return s && d.system && s.system === d.system ? s : null;
    }

    // The distros on one service, in tray order.
    serviceDistros(serviceId) {
        const all = typeof this.getDistros === 'function' ? this.getDistros() : [];
        return all.filter(d => {
            const s = this.distroService(d);
            return s && s.id === serviceId;
        });
    }

    // "600 A · 120/208V 3φ" - the service's size and system.
    serviceSizeText(s) {
        if (!s) return '';
        return `${+(Number(s.ratingA) || 0).toFixed(1)} A · ${this.distroSystemName(s)}`;
    }

    // "House 600 A · 120/208V 3φ" - how the card, the gear and the binder
    // name a service.
    serviceLabel(s) {
        if (!s) return '';
        return `${s.name || s.id} ${this.serviceSizeText(s)}`;
    }

    addService(opts = {}) {
        if (!this.project) return null;
        if (!Array.isArray(this.project.services)) this.project.services = [];
        const list = this.project.services;
        const n = list.reduce((m, s) => Math.max(m, Number(String(s && s.id).replace('s', '')) || 0), 0) + 1;
        const prefs = (typeof this.getPreferences === 'function') ? this.getPreferences() : {};
        const sys = this.distroSystemById(opts.system)
            || this.distroSystemById(this.preferenceDistroSystem(prefs))
            || this.distroSystems()[0];
        const s = {
            id: 's' + n,
            name: String(opts.name || '').trim() || `SERVICE ${n}`,
            ratingA: Number(opts.ratingA) > 0 ? Number(opts.ratingA) : 600,
            system: sys.id,
            voltage: sys.voltage,
            phase: sys.phase,
        };
        list.push(s);
        this.saveState('Add Service');
        this._persistDistros();
        return s;
    }

    // One committed field, one entry. Returns the service, or null when
    // nothing changed - refused (said why) or not found.
    updateService(id, patch = {}, action = 'Edit Service') {
        const s = this.serviceById(id);
        if (!s) return null;
        if (patch.system !== undefined && patch.system !== s.system) {
            const sys = this.distroSystemById(patch.system);
            if (!sys) return null;
            // The distros on it are of its system; a service that changed
            // system under them would feed distros it cannot.
            const on = this.serviceDistros(s.id);
            if (on.length) {
                this._sayServiceRefusal(`${s.name || s.id} feeds ${on.map(d => d.name || d.id).join(', ')}. `
                    + 'Take them off before changing its system.');
                return null;
            }
            s.system = sys.id;
            s.voltage = sys.voltage;
            s.phase = sys.phase;
            // "100% rated" is a US main's switch (distroMainLimit).
            if (sys.region !== 'us') delete s.main100;
        }
        if (patch.name !== undefined) s.name = String(patch.name).trim() || s.name;
        if (patch.ratingA !== undefined) s.ratingA = Number(patch.ratingA) > 0 ? Number(patch.ratingA) : s.ratingA;
        if (patch.main100 !== undefined) {
            if (patch.main100) s.main100 = true; else delete s.main100;
        }
        this.saveState(action || 'Edit Service');
        this._persistDistros();
        return s;
    }

    // The service goes, and every distro on it comes off it - ONE entry,
    // so a single undo brings the service back with its distros on it.
    removeService(id) {
        const list = this.project && this.project.services;
        if (!Array.isArray(list)) return false;
        const i = list.findIndex(s => s && s.id === id);
        if (i === -1) return false;
        list.splice(i, 1);
        for (const d of (typeof this.getDistros === 'function' ? this.getDistros() : [])) {
            if (d.serviceId === id) delete d.serviceId;
        }
        this.saveState('Remove Service');
        this._persistDistros();
        return true;
    }

    // Why a distro cannot go on a service, or null when it can: only a
    // distro of the service's own system.
    _serviceRefusal(d, s) {
        const dn = d.name || d.id;
        const sn = s.name || s.id;
        const sys = this.distroSystem(d);
        if (!sys) {
            return `${dn} has no system yet. Pick its system behind its ⚙, then put it on ${sn}.`;
        }
        if (sys.id !== s.system) {
            return `${dn} is ${sys.name} and ${sn} is ${this.distroSystemName(s)}. `
                + 'A distro goes only on a service of the same system.';
        }
        return null;
    }

    _sayServiceRefusal(text) {
        if (typeof this._toast === 'function') this._toast(text, true, 4000);
        if (typeof this._dockSay === 'function') this._dockSay(text);
        sendClientLog('service_refused', { text });
    }

    // Put a distro on a service, or take it off (`serviceId` null). One
    // entry when something changes; a refusal says why and changes
    // nothing. Returns whether the distro moved.
    setDistroService(distroId, serviceId) {
        const d = (typeof this.getDistros === 'function' ? this.getDistros() : [])
            .find(x => x.id === distroId);
        if (!d) return false;
        const want = serviceId || null;
        if (!want) {
            if (!d.serviceId) return false;
            delete d.serviceId;
            this.saveState('Take Distro off Service');
            this._persistDistros();
            return true;
        }
        const s = this.serviceById(want);
        if (!s) return false;
        const cur = this.distroService(d);
        if (cur && cur.id === s.id) return false;
        const why = this._serviceRefusal(d, s);
        if (why) {
            this._sayServiceRefusal(why);
            return false;
        }
        d.serviceId = s.id;
        this.saveState('Put Distro on Service');
        this._persistDistros();
        return true;
    }

    // A distro on a service keeps the service's system (rulings 2): a
    // patch that would move it to another is refused here, saying why.
    // Read by updateDistro before it changes anything. True when refused.
    _serviceRefusesDistroPatch(d, patch) {
        const s = this.distroService(d);
        if (!s) return false;
        let next = null;
        if (patch.system !== undefined) {
            next = patch.system;
        } else if (patch.voltage !== undefined || patch.phase !== undefined) {
            next = this._systemForVoltagePhase(
                patch.voltage !== undefined ? patch.voltage : d.voltage,
                patch.phase !== undefined ? patch.phase : d.phase).id;
        } else {
            return false;
        }
        if (next === s.system) return false;
        this._sayServiceRefusal(`${d.name || d.id} is on ${s.name || s.id} (${this.distroSystemName(s)}). `
            + 'Take it off the service before changing its system.');
        return true;
    }

    // ---- the checks ----------------------------------------------------------

    // One record per service, off the distros' own roll-up (getDistroLoads)
    // - never a second walk of the circuits:
    //   { id, name, label, ratingA, system, limitA, limitPct, main100,
    //     distros: [{ distro, load }], ratingSum, ratingsOver,
    //     watts, amps, legs, worstLeg, imbalancePct, pct, over }
    // A leg's load is its distros' figures for that leg ADDED, the way the
    // owner reads them off the headers (rulings 3a) - on the safe side of
    // the phasor sum where line-to-line and line-to-neutral distros share
    // a service, and the very sum where they do not. `legs` has the shape
    // a distro's has, so the LEGS line and the binder's Load line read a
    // service exactly as they read a distro.
    getServiceLoads() {
        const services = this.getServices();
        if (!services.length) return [];
        const loads = typeof this.getDistroLoads === 'function' ? this.getDistroLoads() : [];
        return services.map(s => this._serviceLoad(s, loads));
    }

    _serviceLoad(s, loads) {
        const names = this.distroLegNames(s);
        const rows = this.serviceDistros(s.id).map(d => ({
            distro: d, load: (loads || []).find(x => x.id === d.id) || null,
        }));
        const rating = Number(s.ratingA) || 0;
        const rule = this.distroMainLimit(s);
        const limit = rating > 0 ? rule.limitA : 0;
        const past = (a) => limit > 0 && a > limit + 1e-9;
        const watts = rows.reduce((t, r) => t + ((r.load && r.load.watts) || 0), 0);
        let amps = rows.reduce((t, r) => t + ((r.load && r.load.amps) || 0), 0);
        let legs = null;
        let imbalancePct = 0;
        if (names.length) {
            const one = (k) => {
                let a = 0;
                let w = 0;
                for (const r of rows) {
                    const L = r.load && r.load.legs && r.load.legs[k];
                    if (L) { a += L.amps || 0; w += L.watts || 0; }
                }
                return { watts: w, amps: a, pct: rating > 0 ? (a / rating) * 100 : 0, over: past(a) };
            };
            legs = { X: one('X'), Y: one('Y'), Z: one('Z') };
            const legAmps = names.map(k => legs[k].amps);
            const avg = legAmps.reduce((t, x) => t + x, 0) / legAmps.length;
            // NEMA-style, as a distro's: max deviation from the average.
            imbalancePct = avg > 0
                ? (Math.max(...legAmps.map(x => Math.abs(x - avg))) / avg) * 100 : 0;
            legs.names = names.slice();
            legs.labels = names.map(k => this.distroLegLabel(s, k));
            legs.avgAmps = avg;
            legs.worstAmps = Math.max(...legAmps);
            legs.worst = names[legAmps.indexOf(legs.worstAmps)];
            legs.over = past(legs.worstAmps);
            amps = legs.worstAmps;
        }
        const ratingSum = rows.reduce((t, r) => t + (Number(r.distro.ratingA) || 0), 0);
        return {
            id: s.id, name: s.name || s.id, label: this.serviceLabel(s),
            ratingA: rating, system: s.system || null,
            limitA: limit, limitPct: rule.pct, main100: !!rule.main100,
            distros: rows, ratingSum,
            ratingsOver: rating > 0 && ratingSum > rating + 1e-9,
            watts, amps, legs, worstLeg: legs ? legs.worst : null, imbalancePct,
            pct: rating > 0 ? (amps / rating) * 100 : 0,
            over: past(amps),
            // a service has no Accept overload: its OVER always reads red
            overloadAccepted: false,
        };
    }

    // ---- the card in the tray ------------------------------------------------

    // The services strip across the top of the Power view's tray, above the
    // distro columns: one card per service. Its warnings join the strip's.
    // Nothing at all for a show with no services.
    _dockRenderServices(host) {
        const services = this.getServices();
        if (!services.length) return;
        const loads = this.getServiceLoads();
        const strip = document.createElement('div');
        // one full-width row of the tray grid (_dockMasonry, style.css)
        strip.className = 'hw-dock-services hw-dock-span-all';
        services.forEach(s => {
            const load = loads.find(x => x.id === s.id);
            strip.appendChild(this._dockBuildService(s, load));
            this._dockServiceWarnings(s, load);
        });
        host.appendChild(strip);
    }

    _dockServiceWarnings(s, load) {
        if (!load || !this._dockPowerWarnings) return;
        const name = s.name || s.id;
        if (load.over) {
            const leg = load.legs && load.worstLeg
                ? ` worst leg ${this.distroLegLabel(s, load.worstLeg)}` : '';
            const note = this.distroMainLimitNote(this.distroMainLimit(s));
            this._dockPowerWarnings.push({
                text: `${name} service:${leg} ${load.amps.toFixed(1)} A / ${+load.limitA.toFixed(1)} A`
                    + (note ? ` (${note}, continuous)` : ` (${Math.round(load.pct)}%)`) + ', OVER',
            });
        }
        if (load.ratingsOver) {
            this._dockPowerWarnings.push({
                mild: true,
                text: `${name} service: its distros are rated ${+load.ratingSum.toFixed(1)} A together `
                    + `(${load.distros.map(r => `${r.distro.name || r.distro.id} ${+(Number(r.distro.ratingA) || 0).toFixed(1)} A`).join(', ')}) `
                    + `on a ${+load.ratingA.toFixed(1)} A service`,
            });
        }
    }

    _dockBuildService(s, load) {
        const card = document.createElement('div');
        card.className = 'hw-dock-service';
        card.dataset.lrdService = s.id;
        card.dataset.hwdock = `service-${s.id}`;
        card.title = `${s.name || s.id}: the house power these distros are fed from. Drag a `
            + 'distro\'s header bar here to put it on this service. The ⚙ sets its rating '
            + 'and system and takes distros off.';
        const head = document.createElement('div');
        head.className = 'hw-dock-svc-head';
        const tag = document.createElement('span');
        tag.className = 'hw-dock-svc-tag';
        tag.textContent = 'SERVICE';
        head.appendChild(tag);
        head.appendChild(this._dockHeadName({
            value: s.name,
            placeholder: 'service',
            key: `service-name-${s.id}`,
            title: 'Name this service - House, Generator A.',
            onCommit: (val) => {
                this.updateService(s.id, { name: val }, 'Rename Service');
                this.renderHardwareDock();
            },
        }));
        const size = document.createElement('span');
        size.className = 'hw-dock-svc-size';
        size.textContent = this.serviceSizeText(s);
        head.appendChild(size);
        if (load) this._dockServiceGlance(head, s, load);
        const gear = document.createElement('button');
        gear.className = 'hw-dock-gear';
        gear.textContent = '⚙';
        gear.title = 'Configure this service - rating, system, 100% rated, the distros on it, remove.';
        gear.dataset.hwpop = `service-${s.id}`;
        gear.dataset.lrdField = `hwgear-service-${s.id}`;
        gear.addEventListener('click', (e) => {
            e.stopPropagation();
            this._hwPopoverToggle(gear, `service-${s.id}`, () => {
                const live = this.serviceById(s.id);
                return live ? this._buildServiceGearContent(live) : null;
            });
        });
        head.appendChild(gear);
        card.appendChild(head);
        const legs = load && load.distros.length ? this._dockDistroLegsLine(load) : null;
        if (legs) {
            legs.title = 'Each leg is its distros\' loads on that leg added together, read against '
                + 'the service. Imbalance is NEMA-style: max deviation from the average, across '
                + 'every distro on the service.';
            card.appendChild(legs);
        }
        card.appendChild(this._dockServiceFeeds(s, load));
        return card;
    }

    // The busiest leg against the service's continuous limit, the way a
    // distro header reads it: "412.0/480 A", "· 80% of 600 A", OVER, and a
    // bar filled against the rating.
    _dockServiceGlance(head, s, load) {
        const rule = this.distroMainLimit(s);
        const limit = load.limitA > 0 ? load.limitA : load.ratingA;
        const note = this.distroMainLimitNote(rule);
        const title = `Busiest leg ${load.amps.toFixed(1)} A of a ${+limit.toFixed(1)} A limit`
            + (note ? ` - ${note}: a show load is continuous. Tick 100% rated behind the ⚙ if `
                + 'the service is.' : (rule.main100 ? ' - the service is 100% rated.' : ' - the rating.'));
        const use = document.createElement('span');
        use.className = 'hw-dock-unit-use' + (load.over ? ' hw-dock-unit-use-over' : '');
        use.textContent = `${load.amps.toFixed(1)}/${+limit.toFixed(1)} A`;
        use.title = title;
        head.appendChild(use);
        if (note) {
            const lim = document.createElement('span');
            lim.className = 'hw-dock-unit-lim';
            lim.textContent = `· ${note}`;
            lim.title = title;
            head.appendChild(lim);
        }
        if (load.over) {
            const flag = document.createElement('span');
            flag.className = 'hw-dock-unit-flag';
            flag.textContent = 'OVER';
            flag.title = 'The busiest leg is past the service\'s limit.';
            head.appendChild(flag);
        }
        const bar = document.createElement('span');
        bar.className = 'hw-dock-headbar';
        const meat = document.createElement('i');
        if (load.over) meat.className = 'hw-dock-bar-over';
        meat.style.width = `${Math.min(Math.max(load.ratingA > 0 ? load.amps / load.ratingA : 0, 0), 1) * 100}%`;
        bar.appendChild(meat);
        head.appendChild(bar);
    }

    // The FEEDS line: one chip per distro on the service with its rating,
    // then the ratings added up against the service - amber past it.
    _dockServiceFeeds(s, load) {
        const row = document.createElement('div');
        row.className = 'hw-dock-svc-feeds';
        const cap = document.createElement('span');
        cap.className = 'hw-dock-legs-cap';
        cap.textContent = 'FEEDS';
        row.appendChild(cap);
        const rows = load ? load.distros : [];
        if (!rows.length) {
            const empty = document.createElement('span');
            empty.className = 'hw-dock-svc-empty';
            empty.textContent = 'Drag a distro\'s header bar here.';
            row.appendChild(empty);
            return row;
        }
        rows.forEach(({ distro: d }) => {
            const chip = document.createElement('span');
            chip.className = 'hw-dock-svc-chip';
            chip.dataset.lrdSvcDistro = d.id;
            chip.textContent = `${d.name || d.id} ${+(Number(d.ratingA) || 0).toFixed(1)} A`;
            row.appendChild(chip);
        });
        const sum = document.createElement('span');
        sum.className = 'hw-dock-svc-sum' + (load.ratingsOver ? ' hw-dock-svc-sum-over' : '');
        sum.textContent = `ratings ${+load.ratingSum.toFixed(1)} A on ${+load.ratingA.toFixed(1)} A`;
        sum.title = load.ratingsOver
            ? 'The distros\' ratings add up past the service. Their load is what is checked '
                + 'against it, leg by leg; this says that, run full, they would be past it.'
            : 'The distros\' ratings added up, within the service.';
        row.appendChild(sum);
        return row;
    }

    // The service card's ⚙: system, rating per leg, 100% rated, the
    // distros on it (each with Take off), and Remove service. Every field
    // one history entry, through updateService.
    _buildServiceGearContent(s) {
        const wrap = document.createElement('div');
        const heading = document.createElement('div');
        heading.className = 'hw-pop-heading';
        heading.textContent = s.name || 'service';
        wrap.appendChild(heading);
        const cap = (t) => this._distroGearCap(t);
        const done = () => this.renderHardwareDock();

        const r1 = this._distroGearRow();
        r1.classList.add('hw-pop-supply');
        r1.appendChild(cap('System'));
        const sel = document.createElement('select');
        sel.className = 'info-select';
        sel.dataset.lrdField = `service-system-${s.id}`;
        sel.title = 'The service\'s system. Only distros of the same system go on it.';
        this.distroSystems().forEach(sys => {
            const opt = document.createElement('option');
            opt.value = sys.id;
            opt.textContent = sys.name;
            if (sys.id === s.system) opt.selected = true;
            sel.appendChild(opt);
        });
        sel.addEventListener('change', () => {
            this.updateService(s.id, { system: sel.value }, 'Set Service System');
            done();
        });
        r1.appendChild(sel);
        wrap.appendChild(r1);

        const r2 = this._distroGearRow();
        r2.classList.add('hw-pop-supply');
        r2.appendChild(cap('Rating'));
        const rate = document.createElement('input');
        rate.type = 'number';
        rate.min = '1';
        rate.value = s.ratingA;
        rate.style.width = '64px';
        rate.dataset.lrdField = `service-rating-${s.id}`;
        rate.title = 'The service\'s rating per leg in amps. Its distros\' leg loads added up '
            + 'are read against it.';
        rate.addEventListener('change', () => {
            this.updateService(s.id, { ratingA: rate.value }, 'Set Service Rating');
            done();
        });
        r2.appendChild(rate);
        const per = document.createElement('small');
        per.textContent = 'A per leg';
        per.style.color = 'var(--ps-faint, #969696)';
        r2.appendChild(per);
        wrap.appendChild(r2);

        if (this.distroMainLimit(s).us) {
            const r3 = this._distroGearRow();
            const lab = document.createElement('label');
            lab.className = 'hw-pop-check';
            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.checked = !!s.main100;
            cb.dataset.lrdField = `service-main100-${s.id}`;
            cb.addEventListener('change', () => {
                this.updateService(s.id, { main100: cb.checked }, 'Set Service 100% Rated');
                done();
            });
            lab.appendChild(cb);
            lab.appendChild(document.createTextNode('100% rated'));
            lab.title = 'Off: the busiest leg is held to 80% of the rating per leg, the way a '
                + 'distro\'s main is (a show load is continuous). On: the service carries its '
                + 'full rating.';
            r3.appendChild(lab);
            wrap.appendChild(r3);
        }

        const list = document.createElement('div');
        list.className = 'hw-pop-svc-list';
        const listCap = this._distroGearRow();
        listCap.appendChild(cap('Distros on it'));
        list.appendChild(listCap);
        const on = this.serviceDistros(s.id);
        if (!on.length) {
            const hint = document.createElement('div');
            hint.className = 'hw-pop-outs-hint';
            hint.textContent = 'None yet. Drag a distro\'s header bar onto the card, or pick '
                + 'this service behind the distro\'s ⚙.';
            list.appendChild(hint);
        }
        on.forEach(d => {
            const r = this._distroGearRow();
            r.classList.add('hw-pop-svc-row');
            const name = document.createElement('span');
            name.className = 'hw-pop-svc-name';
            name.textContent = `${d.name || d.id} · ${+(Number(d.ratingA) || 0).toFixed(1)} A`;
            r.appendChild(name);
            const off = document.createElement('button');
            off.className = 'btn';
            off.textContent = 'Take off';
            off.dataset.lrdField = `service-off-${s.id}-${d.id}`;
            off.title = `Take ${d.name || d.id} off ${s.name || s.id}. Undo puts it back.`;
            off.addEventListener('click', () => {
                this.setDistroService(d.id, null);
                done();
            });
            r.appendChild(off);
            list.appendChild(r);
        });
        wrap.appendChild(list);

        const remove = document.createElement('button');
        remove.className = 'btn hw-pop-remove';
        remove.textContent = 'Remove service';
        remove.title = 'Remove this service. Its distros come off it and stay in the tray; '
            + 'undo puts it back.';
        remove.dataset.lrdField = `service-del-${s.id}`;
        remove.addEventListener('click', () => {
            if (typeof this._hwPopoverClose === 'function') this._hwPopoverClose();
            this.removeService(s.id);
            done();
        });
        wrap.appendChild(remove);
        return wrap;
    }

    // The distro gear's SERVICE row: None, or one of the show's services.
    // Shown once the show has a service (a show with none reads as it
    // always did). A pick of another system is refused, saying why, and
    // the rebuilt popover shows the distro where it still is.
    _buildDistroServiceRow(d, wrap) {
        const services = this.getServices();
        if (!services.length && !d.serviceId) return;
        const r = this._distroGearRow();
        r.classList.add('hw-pop-supply');
        r.appendChild(this._distroGearCap('Service'));
        const sel = document.createElement('select');
        sel.className = 'info-select';
        sel.dataset.lrdField = `distro-service-${d.id}`;
        sel.title = 'The service this distro is fed from. Only a service of the distro\'s own '
            + 'system takes it.';
        const cur = this.distroService(d);
        const none = document.createElement('option');
        none.value = '';
        none.textContent = 'None';
        if (!cur) none.selected = true;
        sel.appendChild(none);
        services.forEach(s => {
            const opt = document.createElement('option');
            opt.value = s.id;
            opt.textContent = this.serviceLabel(s);
            if (cur && cur.id === s.id) opt.selected = true;
            sel.appendChild(opt);
        });
        sel.addEventListener('change', () => {
            this.setDistroService(d.id, sel.value || null);
            this.renderHardwareDock();
        });
        r.appendChild(sel);
        wrap.appendChild(r);
    }

    // The Service card under a point, by its rectangle - a distro dragged
    // over it is the "put it on" gesture (app-dock-drag.js _dockHitTest).
    _dockServiceAt(ev) {
        for (const el of document.querySelectorAll('#hardware-dock-body [data-lrd-service]')) {
            const r = el.getBoundingClientRect();
            if (r.width && ev.clientX >= r.left && ev.clientX <= r.right
                    && ev.clientY >= r.top && ev.clientY <= r.bottom) {
                return el.dataset.lrdService;
            }
        }
        return null;
    }

    // The card a distro drag hovers lights up - accent where the drop
    // takes, red where it would be refused. Null clears every card.
    _dockMarkServiceDrop(target, payload) {
        const want = target && target.kind === 'service' ? target.serviceId : null;
        let refused = false;
        if (want && payload && payload.type === 'distro') {
            const d = (typeof this.getDistros === 'function' ? this.getDistros() : [])
                .find(x => x.id === payload.distroId);
            const s = this.serviceById(want);
            refused = !d || !s || !!this._serviceRefusal(d, s);
        }
        document.querySelectorAll('#hardware-dock-body [data-lrd-service]').forEach(el => {
            const on = el.dataset.lrdService === want;
            el.classList.toggle('hw-dock-svc-drop', on && !refused);
            el.classList.toggle('hw-dock-svc-drop-no', on && refused);
        });
    }
}

for (const k of Object.getOwnPropertyNames(_Services.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_Services.prototype, k));
    }
}

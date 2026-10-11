// Exercise the page's request/render lifecycle without third-party dependencies.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/js/stats.js'), 'utf8');

function page() {
    const elements = new Map();
    function element() {
        const classes = new Set();
        return {
            textContent: '', innerHTML: '', listeners: {}, attributes: {},
            classList: {
                add: value => classes.add(value), remove: value => classes.delete(value),
                contains: value => classes.has(value),
                toggle(value, force = !classes.has(value)) { force ? classes.add(value) : classes.delete(value); },
            },
            addEventListener(name, listener) { this.listeners[name] = listener; },
            setAttribute(name, value) { this.attributes[name] = value; },
            getAttribute(name) { return this.attributes[name]; },
            querySelectorAll() { return []; },
        };
    }
    const requests = [];
    vm.runInNewContext(source, {
        document: {
            getElementById(id) { if (!elements.has(id)) elements.set(id, element()); return elements.get(id); },
            createElement: element, addEventListener() {},
        },
        fetch(url) { return new Promise((resolve, reject) => requests.push({url, resolve, reject})); },
        console: {warn() {}},
    });
    return {
        elements, requests,
        select(year) {
            elements.get('yearDropdownMenu').listeners.click({
                target: {closest: () => ({getAttribute: () => year})},
                preventDefault() {}, stopPropagation() {},
            });
        },
    };
}

function report(year, count = 2) {
    return {
        selected_year: year, current_year: '2026', total_tickets: count, total_cities: count,
        years_current: 1, years_last: 0,
        yearly_counts: [{year: '2026', count: 1}, {year, count}],
        monthly_counts: count ? [{month: '02', count}] : [],
        type_counts: count ? [{type: '车票', count}] : [], top_places: [],
    };
}

async function respond(request, data) {
    request.resolve({ok: true, json: async () => ({success: true, data})});
    await new Promise(resolve => setImmediate(resolve));
}

test('historical selection requests and renders that year, including monthly totals', async () => {
    const ui = page();
    await respond(ui.requests[0], report('2026'));
    ui.select('2024');
    assert.equal(ui.requests[1].url, '/api/stats/yearly?year=2024');
    await respond(ui.requests[1], report('2024', 7));
    assert.equal(ui.elements.get('yearDropdownLabel').textContent, '2024');
    assert.equal(ui.elements.get('currentYearTitle').textContent, '2024');
    assert.equal(ui.elements.get('totalTickets').textContent, 7);
    assert.equal(ui.elements.get('totalCities').textContent, 7);
    assert.match(ui.elements.get('monthGrid').innerHTML, /2月: 7张/);
    assert.equal(ui.elements.get('statsStatus').textContent, '');
});

test('out-of-order responses cannot overwrite the latest selection', async () => {
    const ui = page();
    ui.select('2024');
    ui.select('2025');
    await respond(ui.requests[2], report('2025', 5));
    await respond(ui.requests[1], report('2024', 4));
    await respond(ui.requests[0], report('2026', 6));
    assert.equal(ui.elements.get('yearDropdownLabel').textContent, '2025');
    assert.equal(ui.elements.get('totalTickets').textContent, 5);
});

test('failed year switch retains a consistently labelled report and offers retry', async () => {
    const ui = page();
    await respond(ui.requests[0], report('2026', 6));
    ui.select('2024');
    ui.requests[1].reject(new Error('offline'));
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(ui.elements.get('yearDropdownLabel').textContent, '2026');
    assert.equal(ui.elements.get('totalTickets').textContent, 6);
    assert.match(ui.elements.get('statsStatus').textContent, /加载失败.*2026/);
    ui.select('2024');
    await respond(ui.requests[2], report('2024', 0));
    assert.equal(ui.elements.get('totalTickets').textContent, 0);
    assert.equal(ui.elements.get('typeTotalCount').textContent, '0');
    assert.equal(ui.elements.get('typeDonutSegments').innerHTML, '');
    assert.equal(ui.elements.get('statsStatus').textContent, '所选年份暂无票据');
});

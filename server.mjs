#!/usr/bin/env node
/**
 * Playwright MCP Server — Node.js + Docker
 * Multi-browser pool, session persistence, REST API
 */

import http from 'node:http';
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SESSION_DIR = path.join(__dirname, 'sessions');
fs.mkdirSync(SESSION_DIR, { recursive: true });

// API Key from environment
const p = {}; // placeholder
const API_KEY = (typeof process !== 'undefined' && process.env && process.env.MCP_API_KEY) || '';
const PORT = parseInt(process.env.PORT) || parseInt(process.argv[3]) || 8000;

// Browser Pool

class BrowserPool {
    constructor() {
        this._playwright = null;
        this._instances = new Map();
        this._counter = 0;
    }

    async _ensurePlaywright() {
        if (!this._playwright) {
            this._playwright = await chromium.launch({
                headless: true,
                args: ['--no-sandbox', '--disable-setuid-sandbox'],
            });
            console.log('[Pool] Browser pool started');
        }
    }

    async start(headless = true) {
        await this._ensurePlaywright();
        this._counter++;
        const bid = `browser_${this._counter}`;
        const context = await (await chromium.launch({
            headless,
            args: ['--no-sandbox', '--disable-setuid-sandbox'],
        })).newContext({ viewport: { width: 1280, height: 720 } });
        const page = await context.newPage();
        this._instances.set(bid, { browser: context.browser(), context, page });
        console.log(`[Pool] Started ${bid} (total: ${this._instances.size})`);
        return bid;
    }

    _get(bid) {
        const s = this._instances.get(bid);
        if (!s) throw new Error(`Browser ${bid} not found`);
        return s;
    }

    async navigate(bid, url) {
        const s = this._get(bid);
        await s.page.goto(url, { waitUntil: 'load', timeout: 30000 });
        return { url: s.page.url(), title: await s.page.title() };
    }

    async screenshot(bid) {
        const s = this._get(bid);
        const data = await s.page.screenshot({ type: 'png' });
        return { base64: data.toString('base64'), mimeType: 'image/png' };
    }

    async click(bid, selector) {
        await this._get(bid).page.click(selector);
        return { clicked: selector };
    }

    async type(bid, selector, text) {
        await this._get(bid).page.fill(selector, text);
        return { typed: selector, text };
    }

    async wait(bid, selector, timeout = 5000) {
        if (selector) {
            await this._get(bid).page.waitForSelector(selector, { timeout });
            return { waited: selector };
        }
        await new Promise(r => setTimeout(r, timeout));
        return { waited: `${timeout}ms` };
    }

    async getText(bid, selector) {
        const text = await this._get(bid).page.textContent(selector);
        return { selector, text };
    }

    async getUrl(bid) {
        return { url: this._get(bid).page.url() };
    }

    async scroll(bid, dir = 'down', amount = 500) {
        const y = dir === 'up' ? -amount : amount;
        await this._get(bid).page.evaluate(y => window.scrollBy(0, y), y);
        return { scrolled: `${dir} ${amount}px` };
    }

    async waitForUrl(bid, pattern, timeout = 120000) {
        await this._get(bid).page.waitForURL(pattern, { timeout });
        return { url: this._get(bid).page.url() };
    }

    async evaluate(bid, script) {
        const result = await this._get(bid).page.evaluate(script);
        return { result };
    }

    async sessionSave(bid, sessionId) {
        const s = this._get(bid);
        const state = await s.context.storageState();
        const sid = sessionId || bid;
        fs.writeFileSync(path.join(SESSION_DIR, `${sid}.json`), JSON.stringify(state));
        return { sessionId: sid, saved: true };
    }

    async sessionLoad(bid, sessionId) {
        const p = path.join(SESSION_DIR, `${sessionId}.json`);
        if (!fs.existsSync(p)) return { loaded: false, error: 'Not found' };
        const state = JSON.parse(fs.readFileSync(p, 'utf-8'));
        const s = this._get(bid);
        await s.context.addCookies(state.cookies || []);
        await s.page.reload();
        return { sessionId, loaded: true };
    }

    sessionList() {
        return fs.readdirSync(SESSION_DIR)
            .filter(f => f.endsWith('.json'))
            .map(f => {
                const stat = fs.statSync(path.join(SESSION_DIR, f));
                return { sessionId: f.replace('.json', ''), size: stat.size };
            });
    }

    async closePage(bid) {
        await this._get(bid).page.close();
    }

    async stop(bid) {
        const s = this._instances.get(bid);
        if (s) {
            await s.browser.close();
            this._instances.delete(bid);
            console.log(`[Pool] Stopped ${bid}`);
        }
    }

    status() {
        return {
            activeBrowsers: this._instances.size,
            browserIds: Array.from(this._instances.keys()),
            sessions: this.sessionList().map(s => s.sessionId),
        };
    }
}

const pool = new BrowserPool();

async function handleTool(action, args = {}) {
    try {
        if (action === 'browser_start')
            return { browserId: await pool.start(args.headless !== false), status: 'started' };
        else if (action === 'browser_stop')
            { await pool.stop(args.browserId); return { stopped: args.browserId }; }
        else if (action === 'browser_status')
            return pool.status();

        const bid = args.browserId || '';
        switch (action) {
            case 'navigate': return await pool.navigate(bid, args.url);
            case 'screenshot': return await pool.screenshot(bid);
            case 'click': return await pool.click(bid, args.selector);
            case 'type': return await pool.type(bid, args.selector, args.text);
            case 'wait': return await pool.wait(bid, args.selector, args.timeout);
            case 'get_text': return await pool.getText(bid, args.selector);
            case 'get_url': return await pool.getUrl(bid);
            case 'scroll': return await pool.scroll(bid, args.direction, args.amount);
            case 'wait_for_url': return await pool.waitForUrl(bid, args.pattern, args.timeout);
            case 'evaluate': return await pool.evaluate(bid, args.script);
            case 'close_page': { await pool.closePage(bid); return { closed: bid }; }
            case 'session_save': return await pool.sessionSave(bid, args.sessionId);
            case 'session_load': return await pool.sessionLoad(bid, args.sessionId);
            case 'session_list': return { sessions: pool.sessionList() };
            default: return { error: `Unknown action: ${action}` };
        }
    } catch (e) {
        return { error: e.message };
    }
}

const server = http.createServer(async (req, res) => {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');
    res.setHeader('Content-Type', 'application/json; charset=utf-8');

    if (req.method === 'OPTIONS') return res.writeHead(200).end();

    if (req.method === 'GET') {
        return res.end(JSON.stringify({
            service: 'playwright-mcp',
            version: '2.0.0',
            runtime: 'node.js',
            node: process.version,
            apiKeyRequired: !!API_KEY,
            tools: ['browser_start','navigate','screenshot','click','type','wait','get_text','scroll','session_save','session_load','session_list','browser_status','browser_stop'],
        }));
    }

    try {
        if (API_KEY) {
            const auth = req.headers.authorization || '';
            const key = auth.startsWith('Bearer ') ? auth.slice(7) : '';
            if (key !== API_KEY) return res.writeHead(401).end(JSON.stringify({ error: 'Unauthorized' }));
        }

        const body = await new Promise((resolve) => {
            let data = '';
            req.on('data', c => data += c);
            req.on('end', () => {
                try { resolve(JSON.parse(data)); }
                catch { resolve({}); }
            });
        });

        const { action, arguments: args, args: altArgs } = body;
        const result = await handleTool(action, args || altArgs || {});
        res.end(JSON.stringify(result));
    } catch (e) {
        res.writeHead(500).end(JSON.stringify({ error: e.message }));
    }
});

server.listen(PORT, () => {
    console.log(`[MCP] Playwright MCP Server v2.0.0`);
    console.log(`[MCP] Node.js ${process.version} — http://0.0.0.0:${PORT}`);
    console.log(`[MCP] API Key: ${API_KEY ? 'enabled' : 'DISABLED'}`);
});

process.on('SIGTERM', async () => {
    console.log('[MCP] Shutting down...');
    for (const bid of pool.status().browserIds) {
        await pool.stop(bid).catch(() => {});
    }
    process.exit(0);
});

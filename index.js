#!/usr/bin/env node
// ─── Playwright MCP Server ─────────────────────────────
// MCP Protocol over stdio — Agent kết nối trực tiếp
// Các tool: navigate, screenshot, click, type, wait...
// Chạy: node index.js

import { chromium } from 'playwright';
import { createInterface } from 'readline';

const SERVER_NAME = 'playwright-mcp';
const SERVER_VERSION = '1.0.0';

let browser = null;
let pages = {};  // pageId → Page

// ─── MCP Protocol ───────────────────────────────────

const rl = createInterface({ input: process.stdin });
let pending = '';

rl.on('line', async (line) => {
    try {
        const message = JSON.parse(line);
        if (message.jsonrpc !== '2.0') return;

        if (message.method) {
            const result = await handleRequest(message);
            if (result !== undefined) {
                send({ jsonrpc: '2.0', result, id: message.id });
            }
        }
    } catch (err) {
        send({ jsonrpc: '2.0', error: { code: -32603, message: err.message }, id: null });
    }
});

function send(msg) {
    process.stdout.write(JSON.stringify(msg) + '\n');
}

// ─── Tool Handlers ──────────────────────────────────

const TOOLS = {
    initialize: {
        description: 'Khởi động browser (gọi đầu tiên)',
        inputSchema: {
            type: 'object',
            properties: {
                headless: { type: 'boolean', description: 'Không hiển thị cửa sổ (mặc định: true)' },
            },
        },
    },
    navigate: {
        description: 'Mở URL trong tab mới, trả về pageId',
        inputSchema: {
            type: 'object',
            properties: {
                url: { type: 'string', description: 'URL cần mở' },
            },
            required: ['url'],
        },
    },
    screenshot: {
        description: 'Chụp ảnh màn hình của tab, trả về base64',
        inputSchema: {
            type: 'object',
            properties: {
                pageId: { type: 'string', description: 'ID của tab (từ navigate)' },
                fullPage: { type: 'boolean', description: 'Chụp toàn trang (default: false)' },
            },
            required: ['pageId'],
        },
    },
    click: {
        description: 'Click vào element',
        inputSchema: {
            type: 'object',
            properties: {
                pageId: { type: 'string', description: 'ID của tab' },
                selector: { type: 'string', description: 'CSS selector hoặc text' },
            },
            required: ['pageId', 'selector'],
        },
    },
    type: {
        description: 'Gõ text vào element',
        inputSchema: {
            type: 'object',
            properties: {
                pageId: { type: 'string', description: 'ID của tab' },
                selector: { type: 'string', description: 'CSS selector' },
                text: { type: 'string', description: 'Nội dung cần gõ' },
            },
            required: ['pageId', 'selector', 'text'],
        },
    },
    wait: {
        description: 'Đợi element xuất hiện hoặc đợi N ms',
        inputSchema: {
            type: 'object',
            properties: {
                pageId: { type: 'string', description: 'ID của tab' },
                selector: { type: 'string', description: 'CSS selector cần đợi (optional)' },
                timeout: { type: 'number', description: 'Timeout ms (default: 5000)' },
            },
            required: ['pageId'],
        },
    },
    get_text: {
        description: 'Lấy text từ element',
        inputSchema: {
            type: 'object',
            properties: {
                pageId: { type: 'string', description: 'ID của tab' },
                selector: { type: 'string', description: 'CSS selector' },
            },
            required: ['pageId', 'selector'],
        },
    },
    get_url: {
        description: 'Lấy URL hiện tại của tab',
        inputSchema: {
            type: 'object',
            properties: {
                pageId: { type: 'string', description: 'ID của tab' },
            },
            required: ['pageId'],
        },
    },
    close_page: {
        description: 'Đóng tab',
        inputSchema: {
            type: 'object',
            properties: {
                pageId: { type: 'string', description: 'ID của tab' },
            },
            required: ['pageId'],
        },
    },
    scroll: {
        description: 'Cuộn trang',
        inputSchema: {
            type: 'object',
            properties: {
                pageId: { type: 'string', description: 'ID của tab' },
                direction: { type: 'string', description: 'up hoặc down (default: down)' },
                amount: { type: 'number', description: 'Số pixel cuộn (default: 500)' },
            },
            required: ['pageId'],
        },
    },
    wait_for_url: {
        description: 'Đợi URL thay đổi đến pattern cụ thể (dùng cho login redirect)',
        inputSchema: {
            type: 'object',
            properties: {
                pageId: { type: 'string', description: 'ID của tab' },
                pattern: { type: 'string', description: 'URL pattern cần khớp (glob hoặc regex)' },
                timeout: { type: 'number', description: 'Timeout ms (default: 120000 = 2 phút)' },
            },
            required: ['pageId', 'pattern'],
        },
    },
};

// ─── Request Handler ─────────────────────────────────

async function handleRequest(req) {
    switch (req.method) {
        case 'initialize':
            return handleInitialize(req.params);

        case 'tools/list':
            return {
                tools: Object.entries(TOOLS).map(([name, tool]) => ({
                    name,
                    description: tool.description,
                    inputSchema: tool.inputSchema,
                })),
            };

        case 'tools/call':
            return handleToolCall(req.params.name, req.params.arguments);

        case 'shutdown':
            await cleanup();
            return {};
    }
}

// ─── Tool Implementation ──────────────────────────────

async function handleInitialize(params = {}) {
    await ensureBrowser(params);
    return {
        protocolVersion: '2024-11-05',
        serverInfo: { name: SERVER_NAME, version: SERVER_VERSION },
        capabilities: { tools: {} },
    };
}

async function ensureBrowser(params = {}) {
    if (!browser) {
        browser = await chromium.launch({
            headless: params.headless !== false,
            args: ['--no-sandbox', '--disable-setuid-sandbox'],
        });
        console.error(`[MCP] Browser started (headless: ${params.headless !== false})`);
    }
}

async function handleToolCall(name, args = {}) {
    await ensureBrowser();

    try {
        const result = await executeTool(name, args);
        return {
            content: [{ type: 'text', text: typeof result === 'string' ? result : JSON.stringify(result, null, 2) }],
        };
    } catch (err) {
        return {
            content: [{ type: 'text', text: `Error: ${err.message}` }],
            isError: true,
        };
    }
}

async function executeTool(name, args) {
    switch (name) {
        case 'initialize':
            return 'Browser đã sẵn sàng';

        case 'navigate': {
            const page = await browser.newPage();
            await page.goto(args.url, { waitUntil: 'networkidle', timeout: 30000 });
            const pageId = `page_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
            pages[pageId] = page;
            return { pageId, url: page.url(), title: await page.title() };
        }

        case 'screenshot': {
            const page = pages[args.pageId];
            if (!page) throw new Error(`Page ${args.pageId} not found`);
            const buffer = await page.screenshot({ fullPage: args.fullPage || false, type: 'png' });
            return { pageId: args.pageId, base64: buffer.toString('base64'), mimeType: 'image/png' };
        }

        case 'click': {
            const page = pages[args.pageId];
            if (!page) throw new Error(`Page ${args.pageId} not found`);
            await page.click(args.selector);
            return { clicked: args.selector };
        }

        case 'type': {
            const page = pages[args.pageId];
            if (!page) throw new Error(`Page ${args.pageId} not found`);
            await page.fill(args.selector, args.text);
            return { typed: args.selector, text: args.text };
        }

        case 'wait': {
            const page = pages[args.pageId];
            if (!page) throw new Error(`Page ${args.pageId} not found`);
            if (args.selector) {
                await page.waitForSelector(args.selector, { timeout: args.timeout || 5000 });
                return { waited: `selector '${args.selector}' appeared` };
            }
            await page.waitForTimeout(args.timeout || 1000);
            return { waited: `${args.timeout || 1000}ms` };
        }

        case 'get_text': {
            const page = pages[args.pageId];
            if (!page) throw new Error(`Page ${args.pageId} not found`);
            const text = await page.textContent(args.selector);
            return { selector: args.selector, text };
        }

        case 'get_url': {
            const page = pages[args.pageId];
            if (!page) throw new Error(`Page ${args.pageId} not found`);
            return { pageId: args.pageId, url: page.url() };
        }

        case 'close_page': {
            const page = pages[args.pageId];
            if (!page) throw new Error(`Page ${args.pageId} not found`);
            await page.close();
            delete pages[args.pageId];
            return { closed: args.pageId };
        }

        case 'scroll': {
            const page = pages[args.pageId];
            if (!page) throw new Error(`Page ${args.pageId} not found`);
            const dir = args.direction === 'up' ? -1 : 1;
            await page.evaluate(([dir, amount]) => window.scrollBy(0, dir * amount), [dir, args.amount || 500]);
            return { scrolled: `${args.direction || 'down'} ${args.amount || 500}px` };
        }

        case 'wait_for_url': {
            const page = pages[args.pageId];
            if (!page) throw new Error(`Page ${args.pageId} not found`);
            await page.waitForURL(args.pattern, { timeout: args.timeout || 120000 });
            return { pageId: args.pageId, currentUrl: page.url() };
        }

        default:
            throw new Error(`Unknown tool: ${name}`);
    }
}

// ─── Cleanup ──────────────────────────────────────────

async function cleanup() {
    for (const pageId of Object.keys(pages)) {
        try { await pages[pageId].close(); } catch {}
    }
    pages = {};
    if (browser) {
        try { await browser.close(); } catch {}
        browser = null;
    }
    console.error('[MCP] Browser closed');
    process.exit(0);
}

process.on('SIGINT', cleanup);
process.on('SIGTERM', cleanup);
process.on('exit', cleanup);

// ─── Error handling ──────────────────────────────────

process.on('unhandledRejection', (err) => {
    console.error('[MCP] Unhandled:', err);
});

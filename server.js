'use strict';
/**
 * 아산시 홍보 사업 성과 분석 시스템 - 웹서버 (Node 18+, 외부 의존성 없음)
 *
 * 환경변수
 *   PORT             포트 (Render가 자동 지정, 기본 10000)
 *   PUBLIC_URL       OG 태그에 쓸 공개 주소(선택). 없으면 접속 도메인 사용
 *   ADMIN_ID         관리자 아이디
 *   ADMIN_PASSWORD   관리자 비밀번호
 *   SESSION_SECRET   쿠키 서명 키(선택). 없으면 관리자 정보에서 파생
 *   GITHUB_TOKEN     Actions 실행 권한이 있는 토큰 (fine-grained: Actions Read and write)
 *   GITHUB_REPO      계정명/저장소명
 *   GITHUB_WORKFLOW  워크플로 파일명 (기본 daily.yml)
 */
const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

// 로컬 실행 시 .env 읽기 (Render 에서는 환경변수 사용)
try {
  const envFile = path.join(__dirname, '.env');
  if (fs.existsSync(envFile)) {
    for (const line of fs.readFileSync(envFile, 'utf8').split(/\r?\n/)) {
      const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/);
      if (m && !(m[1] in process.env)) process.env[m[1]] = m[2].replace(/^['"]|['"]$/g, '');
    }
  }
} catch (e) { /* 무시 */ }

const ROOT = path.resolve(__dirname, 'dashboard');
const PORT = Number(process.env.PORT) || 10000;
const ADMIN_ID = process.env.ADMIN_ID || '';
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || '';
const GITHUB_TOKEN = process.env.GITHUB_TOKEN || '';
const GITHUB_REPO = process.env.GITHUB_REPO || '';
const WORKFLOW = process.env.GITHUB_WORKFLOW || 'daily.yml';
const COOKIE = 'asan_admin';
const SESSION_MS = 8 * 60 * 60 * 1000;
const SECRET = process.env.SESSION_SECRET
  ? Buffer.from(process.env.SESSION_SECRET)
  : crypto.createHash('sha256').update('asan-session:' + ADMIN_ID + ':' + ADMIN_PASSWORD).digest();

const MIME = {
  '.html': 'text/html; charset=utf-8', '.js': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon', '.webp': 'image/webp', '.txt': 'text/plain; charset=utf-8',
};

// ── 공통 ─────────────────────────────────────────
function send(res, code, body, headers) {
  const h = Object.assign({
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
    'Referrer-Policy': 'strict-origin-when-cross-origin',
  }, headers || {});
  res.writeHead(code, h);
  res.end(body);
}
function json(res, code, obj, headers) {
  send(res, code, JSON.stringify(obj), Object.assign({ 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' }, headers || {}));
}
function clientIp(req) {
  const cf = req.headers['cf-connecting-ip'];
  if (cf) return String(cf).trim();
  const xff = req.headers['x-forwarded-for'];
  if (xff) {
    const parts = String(xff).split(',').map(s => s.trim()).filter(Boolean);
    if (parts.length) return parts[parts.length - 1]; // 프록시가 붙인 마지막 값(위조 불가)
  }
  return req.socket.remoteAddress || 'unknown';
}
function isHttps(req) {
  return String(req.headers['x-forwarded-proto'] || '').split(',')[0].trim() === 'https' || !!req.socket.encrypted;
}
function origin(req) {
  if (process.env.PUBLIC_URL) return process.env.PUBLIC_URL.replace(/\/+$/, '');
  const host = String(req.headers['x-forwarded-host'] || req.headers.host || 'localhost').split(',')[0].trim();
  if (!/^[A-Za-z0-9.\-:\[\]]+$/.test(host)) return '';
  return (isHttps(req) ? 'https' : 'http') + '://' + host;
}
function parseCookies(req) {
  const out = {};
  String(req.headers.cookie || '').split(';').forEach(p => {
    const i = p.indexOf('=');
    if (i > 0) out[p.slice(0, i).trim()] = p.slice(i + 1).trim();
  });
  return out;
}
function readBody(req, limit) {
  return new Promise((resolve, reject) => {
    let size = 0; const chunks = [];
    req.on('data', c => { size += c.length; if (size > limit) { reject(new Error('too large')); req.destroy(); } else chunks.push(c); });
    req.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
    req.on('error', reject);
  });
}
function safeEqual(a, b) {
  const ha = crypto.createHash('sha256').update(String(a)).digest();
  const hb = crypto.createHash('sha256').update(String(b)).digest();
  return crypto.timingSafeEqual(ha, hb);
}

// ── 세션 쿠키 (HMAC 서명) ─────────────────────────
function sign(payload) {
  const data = Buffer.from(JSON.stringify(payload)).toString('base64url');
  const mac = crypto.createHmac('sha256', SECRET).update(data).digest('base64url');
  return data + '.' + mac;
}
function verify(token) {
  if (!token || token.indexOf('.') < 0) return null;
  const [data, mac] = token.split('.');
  const expect = crypto.createHmac('sha256', SECRET).update(data).digest('base64url');
  const a = Buffer.from(mac || ''), b = Buffer.from(expect);
  if (a.length !== b.length || !crypto.timingSafeEqual(a, b)) return null;
  try {
    const p = JSON.parse(Buffer.from(data, 'base64url').toString('utf8'));
    if (!p.exp || Date.now() > p.exp || p.u !== ADMIN_ID) return null;
    return p;
  } catch (e) { return null; }
}
function isAdmin(req) {
  if (!ADMIN_ID || !ADMIN_PASSWORD) return false;
  return !!verify(parseCookies(req)[COOKIE]);
}
function cookieHeader(req, value, maxAgeSec) {
  return `${COOKIE}=${value}; Path=/; HttpOnly; SameSite=Strict; Max-Age=${maxAgeSec}` + (isHttps(req) ? '; Secure' : '');
}

// ── 무차별 대입 방지 ─────────────────────────────
const fails = new Map(); // ip -> {count, until}
let globalFails = [];    // 실패 시각 목록
let globalUntil = 0;
const IP_MAX = 5, IP_LOCK_MS = 15 * 60 * 1000;
const G_MAX = 20, G_WINDOW_MS = 60 * 60 * 1000, G_LOCK_MS = 60 * 60 * 1000;

function lockStatus(ip) {
  const now = Date.now();
  if (globalUntil > now) return Math.ceil((globalUntil - now) / 60000);
  const f = fails.get(ip);
  if (f && f.until > now) return Math.ceil((f.until - now) / 60000);
  return 0;
}
function recordFail(ip) {
  const now = Date.now();
  const f = fails.get(ip) || { count: 0, until: 0 };
  if (f.until && f.until <= now) { f.count = 0; f.until = 0; }
  f.count += 1;
  if (f.count >= IP_MAX) f.until = now + IP_LOCK_MS;
  fails.set(ip, f);
  globalFails = globalFails.filter(t => now - t < G_WINDOW_MS);
  globalFails.push(now);
  if (globalFails.length >= G_MAX) { globalUntil = now + G_LOCK_MS; globalFails = []; }
}
setInterval(() => { const now = Date.now(); for (const [k, v] of fails) if (v.until < now && v.count < IP_MAX) fails.delete(k); }, 10 * 60 * 1000).unref();

// ── GitHub Actions ───────────────────────────────
let lastDispatch = 0;
const COOLDOWN_MS = 10 * 60 * 1000;

function gh(method, url, body) {
  return fetch('https://api.github.com' + url, {
    method,
    headers: {
      Authorization: 'Bearer ' + GITHUB_TOKEN,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      'User-Agent': 'asan-news-dashboard',
      'Content-Type': 'application/json',
    },
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(15000),
  });
}
const STATUS_KO = { queued: '대기 중', in_progress: '실행 중', waiting: '대기 중', requested: '요청됨', pending: '대기 중', completed: '완료' };
const CONCL_KO = { success: '성공', failure: '실패', cancelled: '취소됨', skipped: '건너뜀', timed_out: '시간 초과' };
async function latestRun() {
  const r = await gh('GET', `/repos/${GITHUB_REPO}/actions/workflows/${WORKFLOW}/runs?per_page=1`);
  if (!r.ok) throw new Error('GitHub ' + r.status);
  const j = await r.json();
  const run = (j.workflow_runs || [])[0];
  if (!run) return null;
  return {
    status: run.status, conclusion: run.conclusion, created_at: run.created_at, event: run.event,
    status_text: (STATUS_KO[run.status] || run.status) + (run.conclusion ? ' · ' + (CONCL_KO[run.conclusion] || run.conclusion) : ''),
  };
}
function deployedGenerated() {
  try {
    const fd = fs.openSync(path.join(ROOT, 'data.js'), 'r');
    const buf = Buffer.alloc(4096); fs.readSync(fd, buf, 0, 4096, 0); fs.closeSync(fd);
    const m = buf.toString('utf8').match(/"generated":"([^"]+)"/);
    return m ? m[1] : null;
  } catch (e) { return null; }
}

// ── API ──────────────────────────────────────────
function sameOrigin(req) {
  const o = req.headers.origin;
  if (!o) return true; // 같은 출처의 일부 요청은 Origin 이 없음 (SameSite=Strict 로 보호)
  try { return new URL(o).host === String(req.headers['x-forwarded-host'] || req.headers.host || '').split(',')[0].trim(); }
  catch (e) { return false; }
}

async function handleApi(req, res, p) {
  if (req.method === 'POST' && !sameOrigin(req)) return json(res, 403, { ok: false, error: '허용되지 않은 요청 출처' });

  if (p === '/api/session' && req.method === 'GET') return json(res, 200, { admin: isAdmin(req), configured: !!(ADMIN_ID && ADMIN_PASSWORD) });

  if (p === '/api/login' && req.method === 'POST') {
    if (!ADMIN_ID || !ADMIN_PASSWORD) return json(res, 503, { ok: false, error: '관리자 계정이 설정되지 않았습니다(ADMIN_ID / ADMIN_PASSWORD 환경변수).' });
    const ip = clientIp(req);
    const lock = lockStatus(ip);
    if (lock) return json(res, 429, { ok: false, error: `로그인 시도가 너무 많습니다. ${lock}분 후 다시 시도하세요.` });
    let body;
    try { body = JSON.parse(await readBody(req, 4096) || '{}'); } catch (e) { return json(res, 400, { ok: false, error: '잘못된 요청' }); }
    const idOk = safeEqual(body.id || '', ADMIN_ID);
    const pwOk = safeEqual(body.password || '', ADMIN_PASSWORD);
    if (!(idOk && pwOk)) {
      recordFail(ip);
      return json(res, 401, { ok: false, error: '아이디 또는 비밀번호가 올바르지 않습니다.' });
    }
    fails.delete(ip);
    const token = sign({ u: ADMIN_ID, exp: Date.now() + SESSION_MS, n: crypto.randomBytes(8).toString('hex') });
    return json(res, 200, { ok: true }, { 'Set-Cookie': cookieHeader(req, token, SESSION_MS / 1000) });
  }

  if (p === '/api/logout' && req.method === 'POST') return json(res, 200, { ok: true }, { 'Set-Cookie': cookieHeader(req, '', 0) });

  if (p === '/api/refresh' || p === '/api/refresh-status') {
    if (!isAdmin(req)) return json(res, 401, { ok: false, error: '관리자 로그인이 필요합니다.' });
    const configured = !!(GITHUB_TOKEN && GITHUB_REPO);

    if (p === '/api/refresh-status' && req.method === 'GET') {
      const out = { configured, generated: deployedGenerated(), running: false, last: null };
      if (configured) {
        try { out.last = await latestRun(); out.running = !!(out.last && out.last.status !== 'completed'); }
        catch (e) { out.error = '실행 상태 조회 실패'; }
      }
      return json(res, 200, out);
    }
    if (p === '/api/refresh' && req.method === 'POST') {
      if (!configured) return json(res, 503, { ok: false, disable: true, error: 'GITHUB_TOKEN / GITHUB_REPO 가 설정되지 않아 갱신할 수 없습니다.' });
      const wait = lastDispatch + COOLDOWN_MS - Date.now();
      if (wait > 0) return json(res, 429, { ok: false, error: `최근에 갱신을 요청했습니다. ${Math.ceil(wait / 60000)}분 후 다시 시도하세요.` });
      try {
        const last = await latestRun();
        if (last && last.status !== 'completed') return json(res, 409, { ok: false, error: '이미 갱신 작업이 실행 중입니다.' });
        const r = await gh('POST', `/repos/${GITHUB_REPO}/actions/workflows/${WORKFLOW}/dispatches`, { ref: 'main' });
        if (r.status !== 204) return json(res, 502, { ok: false, error: 'GitHub 실행 요청 실패(' + r.status + ')' });
        lastDispatch = Date.now();
        return json(res, 200, { ok: true });
      } catch (e) {
        return json(res, 502, { ok: false, error: 'GitHub 연결 실패' });
      }
    }
  }
  return json(res, 404, { ok: false, error: '없는 API' });
}

// ── 정적 파일 ────────────────────────────────────
function serveStatic(req, res, p) {
  if (p === '/admin/') return send(res, 301, '', { Location: '/admin' });
  if (p === '/' || p === '/admin') p = '/index.html';
  if (p.endsWith('/')) p += 'index.html';
  const file = path.resolve(ROOT, '.' + p);
  if (!file.startsWith(ROOT + path.sep)) return send(res, 403, 'Forbidden', { 'Content-Type': 'text/plain; charset=utf-8' });
  if (path.basename(file).startsWith('.') || file.endsWith('.tmp')) return send(res, 404, 'Not Found', { 'Content-Type': 'text/plain; charset=utf-8' });
  fs.stat(file, (err, st) => {
    if (err || !st.isFile()) return send(res, 404, '페이지를 찾을 수 없습니다.', { 'Content-Type': 'text/plain; charset=utf-8' });
    const ext = path.extname(file).toLowerCase();
    const type = MIME[ext] || 'application/octet-stream';
    const noCache = ext === '.html' || ext === '.js';
    const headers = { 'Content-Type': type, 'Cache-Control': noCache ? 'no-cache' : 'public, max-age=86400' };
    if (ext === '.html') {
      fs.readFile(file, 'utf8', (e2, txt) => {
        if (e2) return send(res, 500, '오류', { 'Content-Type': 'text/plain; charset=utf-8' });
        send(res, 200, req.method === 'HEAD' ? '' : txt.split('%%ORIGIN%%').join(origin(req)), headers);
      });
      return;
    }
    headers['Content-Length'] = st.size;
    res.writeHead(200, Object.assign({ 'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY' }, headers));
    if (req.method === 'HEAD') return res.end();
    fs.createReadStream(file).on('error', () => res.destroy()).pipe(res);
  });
}

const server = http.createServer(async (req, res) => {
  try {
    const raw = String(req.url || '/').split('?')[0];
    let p;
    try { p = decodeURIComponent(raw); } catch (e) { return send(res, 400, 'Bad Request', { 'Content-Type': 'text/plain; charset=utf-8' }); }
    if (p.includes('\0')) return send(res, 400, 'Bad Request', { 'Content-Type': 'text/plain; charset=utf-8' });
    if (p.startsWith('/api/')) return await handleApi(req, res, p);
    if (req.method !== 'GET' && req.method !== 'HEAD') return send(res, 405, 'Method Not Allowed', { Allow: 'GET, HEAD' });
    if (p === '/healthz') return send(res, 200, 'ok', { 'Content-Type': 'text/plain' });
    return serveStatic(req, res, p);
  } catch (e) {
    console.error('[요청 오류]', e);
    if (!res.headersSent) send(res, 500, '서버 오류', { 'Content-Type': 'text/plain; charset=utf-8' });
  }
});

process.on('uncaughtException', e => console.error('[uncaughtException]', e));
process.on('unhandledRejection', e => console.error('[unhandledRejection]', e));

server.listen(PORT, () => {
  console.log(`서버 시작: http://localhost:${PORT}  (관리자: /admin)`);
  if (!ADMIN_ID || !ADMIN_PASSWORD) console.log('※ ADMIN_ID / ADMIN_PASSWORD 미설정 - 관리자 로그인 비활성');
  if (!GITHUB_TOKEN || !GITHUB_REPO) console.log('※ GITHUB_TOKEN / GITHUB_REPO 미설정 - 갱신 버튼 비활성');
});

import {bundle} from '@remotion/bundler';
import {openBrowser, renderMedia, renderStill, selectComposition} from '@remotion/renderer';
import {spawnSync} from 'node:child_process';
import crypto from 'node:crypto';
import fsSync from 'node:fs';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

// Usage: render-remotion.mjs <source> <output> <quality> [frames]
//   frames omitted → full video at <output>; "12" → still at <output>; "12,40,88" → stills <output>/frame-000012.png …
const [source, output, quality, frameArg] = process.argv.slice(2);
if (!source || !output) throw new Error('source directory and output required');
const inputProps = JSON.parse(await fs.readFile(path.join(source, 'input.json'), 'utf8'));
const scale = quality === 'preview' ? 640 / Math.max(inputProps.timeline.width, inputProps.timeline.height) : 1;
const engineRoot = path.dirname(fileURLToPath(import.meta.url));
// WebGL backend for headless Chrome. Default "angle" renders on the GPU (Direct3D on Windows): ~2.6x faster 3D than
// Chrome's software default, PSNR 39-55 dB vs it. Failures fall back to "swangle" per chunk (video) or per run (stills).
let chromiumOptions = {gl: process.env.EDITVIDEO_GL || 'angle'};

// Bundle cache: webpack runs once per code version (not per frame), and the public media folder is hardlinked into the
// bundle instead of copied (Remotion copies public/ on Windows). Cache lives per project via EDITVIDEO_BUNDLE_CACHE.
async function codeHash(dir) {
  const h = crypto.createHash('sha256');
  const walk = async (d, rel) => {
    for (const e of (await fs.readdir(d, {withFileTypes: true})).sort((a, b) => a.name.localeCompare(b.name))) {
      const r = rel ? rel + '/' + e.name : e.name;
      // Data files are not code: input.json reaches Remotion as inputProps, input.js only feeds the HyperFrames page.
      if (r === 'public' || r === 'input.json' || r === 'input.js' || r === 'source-meta.json' || r === 'node_modules') continue;
      if (e.isDirectory()) await walk(path.join(d, e.name), r);
      else if (/\.(tsx?|m?js|cjs|json|css)$/.test(e.name)) {h.update(r); h.update(await fs.readFile(path.join(d, e.name)));}
    }
  };
  await walk(dir, '');
  return h.digest('hex').slice(0, 20);
}
async function syncPublic(from, to) {
  if (!fsSync.existsSync(from)) return;
  await fs.mkdir(to, {recursive: true});
  for (const e of await fs.readdir(from, {withFileTypes: true})) {
    const s = path.join(from, e.name), d = path.join(to, e.name);
    if (e.isDirectory()) {await syncPublic(s, d); continue;}
    const ss = await fs.stat(s);
    const ds = await fs.stat(d).catch(() => null);
    if (ds && ds.size === ss.size && ds.ino === ss.ino) continue;
    if (ds) await fs.rm(d, {force: true});
    try {await fs.link(s, d);} catch (err) {if (err.code !== 'EEXIST') await fs.copyFile(s, d);}
  }
}
async function bundled() {
  const cacheRoot = process.env.EDITVIDEO_BUNDLE_CACHE || path.join(os.tmpdir(), 'editvideo-bundles');
  const outDir = path.join(cacheRoot, await codeHash(source));
  if (!fsSync.existsSync(path.join(outDir, 'ready.json'))) {
    const tmp = outDir + '.tmp-' + process.pid;
    const empty = path.join(cacheRoot, 'empty-public');
    await fs.mkdir(empty, {recursive: true});
    // enableCaching:false — the whole bundle is cached here; webpack's own 200+ MB pack per source copy is waste.
    await bundle({entryPoint: path.join(source, 'index.tsx'), publicDir: empty, outDir: tmp, enableCaching: false,
      webpackOverride: (config) => ({...config, resolve: {...config.resolve, modules: [path.join(engineRoot, 'node_modules'), ...(config.resolve?.modules ?? [])]}})});
    await fs.writeFile(path.join(tmp, 'ready.json'), JSON.stringify({source, at: new Date().toISOString()}));
    try {await fs.rename(tmp, outDir);} catch {await fs.rm(tmp, {recursive: true, force: true});} // another process won the race
  }
  await syncPublic(path.join(source, 'public'), path.join(outDir, 'public'));
  return outDir;
}

// Stills: one browser for every frame (launching Chrome per frame dominated snapshot time).
async function stills(serveUrl) {
  const browser = await openBrowser('chrome', {chromiumOptions});
  try {
    const composition = await selectComposition({serveUrl, id: 'AgentVideo', inputProps, puppeteerInstance: browser});
    const frames = String(frameArg).split(',').filter(Boolean).map(Number);
    const many = frames.length > 1 || !output.endsWith('.png');
    if (many) await fs.mkdir(output, {recursive: true});
    for (const frame of frames) {
      const target = many ? path.join(output, `frame-${String(frame).padStart(6, '0')}.png`) : output;
      await renderStill({serveUrl, composition, inputProps, output: target, frame, scale, imageFormat: 'png', puppeteerInstance: browser});
    }
  } finally {await browser.close({silent: true});}
}

// Video: rendered in chunks, each with a fresh browser. A long render that mounts several WebGL scenes with large
// textures in the same tabs can exhaust GPU resources and crash a page; a fresh browser per chunk releases them, and a
// failure re-renders only that chunk (same backend once, then software WebGL) instead of the whole film.
async function video(serveUrl) {
  const composition = await selectComposition({serveUrl, id: 'AgentVideo', inputProps, chromiumOptions});
  // Tabs are bounded by free commit memory, not just CPUs. Measured on the Mars film (RTX 3060, angle, 8K-capped
  // textures): ~3.5 GB fixed (compositor, encoder, GPU process) + ~1.3 GB per tab; Windows counts GPU allocations
  // against commit, so running out crashes Chrome (0xe0000008) rather than swapping. 3 tabs ran 92% as fast as 6.
  const memGb = Number(process.env.EDITVIDEO_MEM_AVAILABLE_MB || 0) / 1024;
  const fitTabs = memGb ? Math.max(1, Math.floor((memGb - 5) / 1.3)) : Infinity;
  const concurrency = Math.max(1, Math.min(Number(process.env.EDITVIDEO_RENDER_CONCURRENCY) || 6, os.cpus().length, fitTabs));
  const half = Math.max(1, Math.floor(concurrency / 2));
  // Optional section render "a-b" (inclusive frames) for previews and benchmarks.
  const range = process.env.EDITVIDEO_FRAME_RANGE ? process.env.EDITVIDEO_FRAME_RANGE.split('-').map(Number) : [0, composition.durationInFrames - 1];
  const size = Math.max(30, Number(process.env.EDITVIDEO_CHUNK_FRAMES) || 300);
  const chunks = [];
  for (let a = range[0]; a <= range[1]; a += size) chunks.push([a, Math.min(range[1], a + size - 1)]);
  const total = range[1] - range[0] + 1;
  // Retry ladder per chunk: same backend with half the tabs (memory), then software WebGL unless the backend is forced.
  const gl0 = chromiumOptions.gl;
  const attempts = [{gl: gl0, tabs: concurrency}, {gl: gl0, tabs: half}, ...(process.env.EDITVIDEO_GL ? [] : [{gl: 'swangle', tabs: half}])];
  const parts = chunks.length > 1 ? output + '.parts' : null;
  if (parts) await fs.mkdir(parts, {recursive: true});
  // Remotion's default video-frame cache is half of free RAM; on a machine with little free commit that starves Chrome.
  const videoCache = process.env.EDITVIDEO_VIDEO_CACHE_MB ? Number(process.env.EDITVIDEO_VIDEO_CACHE_MB) * 2 ** 20 : null;
  const used = [];
  let done = 0, lastPct = -1;
  try {
    for (const [i, [a, b]] of chunks.entries()) {
      const target = parts ? path.join(parts, `part-${String(i).padStart(4, '0')}.ts`) : output;
      for (const [k, {gl, tabs}] of attempts.entries()) {
        try {
          await renderMedia({serveUrl, composition, inputProps, outputLocation: target, frameRange: [a, b],
            codec: parts ? 'h264-ts' : 'h264', muted: true, crf: 18, concurrency: tabs, scale, chromiumOptions: {gl}, colorSpace: 'bt709', overwrite: true,
            offthreadVideoCacheSizeInBytes: videoCache,
            onProgress: ({progress}) => {
              const pct = Math.floor(((done + progress * (b - a + 1)) / total) * 100);
              if (pct !== lastPct && pct % 5 === 0) {lastPct = pct; process.stderr.write(`render ${pct}%\n`);}
            }});
          used.push({frames: `${a}-${b}`, gl, tabs, attempts: k + 1});
          break;
        } catch (err) {
          if (k === attempts.length - 1) throw err;
          const next = attempts[k + 1];
          process.stderr.write(`chunk ${a}-${b} failed with gl=${gl} tabs=${tabs} (${String(err?.message || err).split('\n')[0]}); retrying with gl=${next.gl} tabs=${next.tabs}\n`);
        }
      }
      done += b - a + 1;
    }
    if (parts) {
      const list = path.join(parts, 'list.txt');
      // Each part's length is stated: the concat demuxer otherwise reads it from the TS file and came up a frame short
      // at some joins (round 13: frames 1200, 1800 and 3000 repeated the previous timestamp).
      await fs.writeFile(list, chunks.map(([a, b], i) => `file 'part-${String(i).padStart(4, '0')}.ts'\nduration ${((b - a + 1) / composition.fps).toFixed(6)}`).join('\n'));
      const r = spawnSync(process.env.FFMPEG_BINARY || 'ffmpeg', ['-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', list,
        '-c', 'copy', '-movflags', '+faststart', output], {cwd: parts, encoding: 'utf8'});
      if (r.status !== 0) throw new Error(`chunk concat failed: ${r.stderr || r.error}`);
    }
  } finally {
    if (parts) await fs.rm(parts, {recursive: true, force: true});
  }
  process.stderr.write(`EDITVIDEO_RENDER ${JSON.stringify({chunks: used.length, tabs: concurrency, free_commit_gb: memGb ? +memGb.toFixed(1) : null,
    fallbacks: used.filter((u) => u.attempts > 1)})}\n`);
}

const serveUrl = await bundled();
if (frameArg !== undefined) {
  try {
    await stills(serveUrl);
  } catch (err) {
    if (process.env.EDITVIDEO_GL || chromiumOptions.gl !== 'angle') throw err;
    process.stderr.write(`GPU (angle) stills failed, retrying with software WebGL: ${err?.message || err}\n`);
    chromiumOptions = {gl: 'swangle'};
    await stills(serveUrl);
  }
} else {
  await video(serveUrl);
}

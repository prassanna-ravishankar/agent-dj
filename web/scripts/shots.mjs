/**
 * Capture review screenshots from the production build in demo mode.
 * Writes to web/screenshots/ at stable paths.
 */

import { chromium } from 'playwright'
import { createServer } from 'node:http'
import { readFile, mkdir } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { join, extname, resolve } from 'node:path'

const ROOT = resolve(process.cwd())
const DIST = join(ROOT, 'dist')
const OUT = join(ROOT, 'screenshots')

const TYPES = {
  '.html': 'text/html',
  '.js': 'text/javascript',
  '.css': 'text/css',
  '.map': 'application/json',
  '.svg': 'image/svg+xml',
}

const VIEWPORTS = [
  { name: 'desktop', width: 1600, height: 1000 },
  { name: 'tablet', width: 900, height: 1000 },
  { name: 'mobile', width: 390, height: 844 },
]

const SHOTS = [
  { scenario: 'live-safe', viewports: ['desktop', 'tablet', 'mobile'] },
  { scenario: 'coverage-critical', viewports: ['desktop', 'mobile'] },
  { scenario: 'clock-uncertain', viewports: ['desktop'] },
  { scenario: 'generation-failed', viewports: ['desktop'] },
  { scenario: 'agent-absent', viewports: ['desktop'] },
  { scenario: 'recording', viewports: ['desktop'] },
  { scenario: 'offline', viewports: ['desktop'] },
  { scenario: 'empty', viewports: ['desktop'] },
]

if (!existsSync(DIST)) {
  console.error('dist/ missing — run `npm run build` first.')
  process.exit(1)
}

const server = createServer(async (req, res) => {
  const url = (req.url ?? '/').split('?')[0]
  let path = join(DIST, url === '/' ? 'index.html' : url)
  if (!existsSync(path)) path = join(DIST, 'index.html')
  try {
    const body = await readFile(path)
    res.writeHead(200, { 'content-type': TYPES[extname(path)] ?? 'application/octet-stream' })
    res.end(body)
  } catch {
    res.writeHead(404)
    res.end('not found')
  }
})

await new Promise((r) => server.listen(0, r))
const port = server.address().port
await mkdir(OUT, { recursive: true })

const browser = await chromium.launch()
let count = 0

for (const shot of SHOTS) {
  for (const vpName of shot.viewports) {
    const vp = VIEWPORTS.find((v) => v.name === vpName)
    const context = await browser.newContext({
      viewport: { width: vp.width, height: vp.height },
      deviceScaleFactor: 2,
      colorScheme: 'dark',
    })
    const page = await context.newPage()
    await page.goto(
      `http://127.0.0.1:${port}/?demo=true&scenario=${shot.scenario}`,
      { waitUntil: 'networkidle' },
    )
    await page.waitForTimeout(400)
    const file = join(OUT, `${shot.scenario}-${vpName}.png`)
    await page.screenshot({ path: file, fullPage: vpName !== 'desktop' })
    console.log(`  ${file.replace(ROOT + '/', '')}`)
    count += 1
    await context.close()
  }
}

await browser.close()
server.close()
console.log(`\n${count} screenshots written to web/screenshots/`)

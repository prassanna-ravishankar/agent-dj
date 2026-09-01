/**
 * Token discipline: tokens.css is the ONLY source of colour, type, spacing and motion.
 * A literal colour or duration anywhere else fails the build.
 *
 * Two deliberate exemptions, both documented in the design contract:
 *  - base.css carries the SVG grain data-URI and the focus outline colour token reference.
 *  - rgba() built from the amber/red channel inside tokens.css itself.
 */

import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = fileURLToPath(new URL('..', import.meta.url))
const SRC = join(ROOT, 'src')
const TOKENS = join(SRC, 'styles', 'tokens.css')

const HEX = /#[0-9a-fA-F]{3,8}\b/g
const RGB = /\brgba?\s*\(/g
const HSL = /\bhsla?\s*\(/g
const DURATION = /(?<![\w-])\d+(\.\d+)?m?s(?![\w-])/g

/** Animations and transitions defined in a module may use keyframe percentages, not durations. */
const ALLOWED_FILES = new Set([relative(ROOT, TOKENS)])

function walk(dir) {
  const out = []
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) out.push(...walk(full))
    else if (entry.endsWith('.css')) out.push(full)
  }
  return out
}

const failures = []

for (const file of walk(SRC)) {
  const rel = relative(ROOT, file)
  if (ALLOWED_FILES.has(rel)) continue
  const source = readFileSync(file, 'utf8')

  source.split('\n').forEach((line, index) => {
    // The grain texture is an inline SVG data-URI; it carries no palette decision.
    if (line.includes('data:image/svg+xml')) return
    const trimmed = line.trim()
    if (trimmed.startsWith('/*') || trimmed.startsWith('*')) return

    for (const [pattern, label] of [
      [HEX, 'literal hex colour'],
      [RGB, 'literal rgb()/rgba() colour'],
      [HSL, 'literal hsl()/hsla() colour'],
      [DURATION, 'literal duration'],
    ]) {
      pattern.lastIndex = 0
      const match = pattern.exec(line)
      if (match) {
        failures.push(`${rel}:${index + 1}  ${label}: ${match[0].trim()}`)
      }
    }
  })
}

if (failures.length > 0) {
  console.error('Token discipline violations (tokens.css is the only source of these values):\n')
  for (const failure of failures) console.error(`  ${failure}`)
  console.error(`\n${failures.length} violation(s).`)
  process.exit(1)
}

console.log('token discipline: ok')

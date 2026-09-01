import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import { DESIGN_CONTRACT } from './src/designContract'

/**
 * Emits the design contract as the first child comment of <body>, and stamps the root with
 * data-design-contract. Both are asserted by tests/contract.test.ts.
 */
function designContract(): Plugin {
  return {
    name: 'agent-dj-design-contract',
    transformIndexHtml(html) {
      return html
        .replace('<body>', `<body>\n    <!--${DESIGN_CONTRACT}-->`)
        .replace(
          '<html lang="en">',
          '<html lang="en" data-design-contract="agent-dj/PRODUCT.md#the-horizon" data-contract-seed="6d715286">',
        )
    },
  }
}

export default defineConfig(({ mode }) => ({
  plugins: [react(), designContract()],
  define: { __DEMO_DEFAULT__: JSON.stringify(mode === 'demo') },
  server: {
    port: 5173,
    strictPort: false,
    proxy: { '/api': 'http://127.0.0.1:8765' },
  },
  build: { outDir: 'dist', sourcemap: true },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./tests/setup.ts'],
    include: ['tests/**/*.test.{ts,tsx}'],
  },
}))

import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// While developing, run the Python backend (python webui.py --ui none) and `npm run dev`.
// Set GRAB_DEV_TOKEN for the backend and open http://127.0.0.1:5173/?t=<that token>.
const backend = process.env.GRAB_BACKEND ?? 'http://127.0.0.1:8765'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // The production build is written next to webui.py, which serves it.
  build: {
    outDir: '../webui_dist',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules')) {
            if (id.includes('react/') || id.includes('react-dom/')) {
              return 'vendor-react'
            }
            if (id.includes('lucide-react/')) {
              return 'vendor-icons'
            }
          }
        },
      },
    },
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: { '/api': backend, '/files': backend },
  },
  // Keep DOM-heavy Library tests from competing with too many jsdom workers.
  test: { environment: 'jsdom', setupFiles: ['./src/test/setup.ts'], css: false, maxWorkers: 4 },
})

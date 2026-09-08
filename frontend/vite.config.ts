import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    chunkSizeWarningLimit: 700,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined
          if (id.includes('@tanstack/react-query') || id.includes('@tanstack/react-router')) return 'vendor-tanstack'
          if (id.includes('framer-motion') || id.includes('recharts')) return 'vendor-viz'
          if (id.includes('@ffmpeg/ffmpeg') || id.includes('@ffmpeg/util')) return 'vendor-ffmpeg'
          if (id.includes('react') || id.includes('react-dom')) return 'vendor-react'
          if (id.includes('axios')) return 'vendor-axios'
          if (id.includes('zod')) return 'vendor-zod'
          return undefined
        },
      },
    },
  },
  server: {
    host: true, // Listen on all addresses (0.0.0.0)
    port: 5173,
    watch: {
      usePolling: true, // Needed for Docker on some systems
    },
    // Cross-Origin Isolation: required for SharedArrayBuffer, which FFmpeg.wasm
    // uses internally for worker communication. Without these headers the FFmpeg
    // web worker fails immediately ("message channel closed" console error).
    // credentialless COEP lets the CDN (unpkg.com) resources load without CORP headers.
    headers: {
      'Cross-Origin-Opener-Policy': 'same-origin',
      'Cross-Origin-Embedder-Policy': 'credentialless',
    },
  },
  preview: {
    host: true,
    port: 8080,
    // vite 7 types: string[] | true — use true via cast for strict ts
    allowedHosts: true as unknown as string[],
  },
})

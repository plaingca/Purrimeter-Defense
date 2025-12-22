import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    host: '0.0.0.0',
    // Allow all hosts - needed for accessing via hostname/IP
    allowedHosts: true,
    cors: true,
  },
})


/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Cat defense theme - warm oranges and protective blues
        'purrple': {
          50: '#fef7ee',
          100: '#fdedd3',
          200: '#fad7a5',
          300: '#f6bb6d',
          400: '#f19333',
          500: '#ee7711',
          600: '#df5c09',
          700: '#b9440a',
          800: '#93360f',
          900: '#772f10',
        },
        'catblue': {
          50: '#f0f7ff',
          100: '#e0efff',
          200: '#b9dfff',
          300: '#7cc4ff',
          400: '#36a6ff',
          500: '#0c8ce7',
          600: '#006fc7',
          700: '#0059a1',
          800: '#034b85',
          900: '#08406e',
        },
        'midnight': {
          50: '#f4f6f7',
          100: '#e3e7ea',
          200: '#c9d1d7',
          300: '#a4b1bc',
          400: '#778899',
          500: '#5c6d7e',
          600: '#4f5c6b',
          700: '#444e5a',
          800: '#3c444d',
          900: '#1a1e24',
          950: '#0d1014',
        },
        'alert': {
          red: '#ef4444',
          orange: '#f97316',
          yellow: '#eab308',
          green: '#22c55e',
        },
      },
      fontFamily: {
        'display': ['Fredoka', 'Comic Sans MS', 'cursive'],
        'mono': ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'bounce-subtle': 'bounce-subtle 2s ease-in-out infinite',
        'wiggle': 'wiggle 1s ease-in-out infinite',
        'alert-flash': 'alert-flash 0.5s ease-in-out infinite',
        'cat-walk': 'cat-walk 2s ease-in-out infinite',
      },
      keyframes: {
        'bounce-subtle': {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-5px)' },
        },
        'wiggle': {
          '0%, 100%': { transform: 'rotate(-3deg)' },
          '50%': { transform: 'rotate(3deg)' },
        },
        'alert-flash': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.5' },
        },
        'cat-walk': {
          '0%': { transform: 'translateX(0) scaleX(1)' },
          '25%': { transform: 'translateX(5px) scaleX(1)' },
          '50%': { transform: 'translateX(0) scaleX(1)' },
          '75%': { transform: 'translateX(-5px) scaleX(-1)' },
          '100%': { transform: 'translateX(0) scaleX(1)' },
        },
      },
      boxShadow: {
        'glow': '0 0 20px rgba(241, 147, 51, 0.3)',
        'glow-alert': '0 0 30px rgba(239, 68, 68, 0.5)',
      },
    },
  },
  plugins: [],
}


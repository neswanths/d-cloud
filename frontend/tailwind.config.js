/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        navy: {
          900: '#0a0e1a',
          800: '#0d1325',
          700: '#111827',
          600: '#1a2340',
        },
        cyan: {
          400: '#22d3ee',
          500: '#00d4ff',
          glow: '#00d4ff',
        },
        purple: {
          500: '#8b5cf6',
          600: '#7c3aed',
          700: '#6d28d9',
        },
      },
      backgroundImage: {
        'hero-gradient': 'linear-gradient(135deg, #0a0e1a 0%, #0d1325 40%, #1a1040 100%)',
      },
      backdropBlur: {
        glass: '12px',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'chunk-send': 'chunkSend 0.8s ease-in-out forwards',
        'fade-in': 'fadeIn 0.4s ease-out',
        'slide-up': 'slideUp 0.3s ease-out',
        'glow-pulse': 'glowPulse 2s ease-in-out infinite',
        'spin-slow': 'spin 4s linear infinite',
      },
      keyframes: {
        chunkSend: {
          '0%':   { opacity: '1', transform: 'translateX(0) scale(1)' },
          '80%':  { opacity: '0.8', transform: 'translateX(120px) scale(0.8)' },
          '100%': { opacity: '0', transform: 'translateX(160px) scale(0.6)' },
        },
        fadeIn: {
          '0%':   { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%':   { opacity: '0', transform: 'translateY(12px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        glowPulse: {
          '0%, 100%': { boxShadow: '0 0 8px rgba(0, 212, 255, 0.3)' },
          '50%':      { boxShadow: '0 0 24px rgba(0, 212, 255, 0.7)' },
        },
      },
      boxShadow: {
        glass: '0 8px 32px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255,255,255,0.06)',
        'glass-hover': '0 16px 48px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255,255,255,0.1)',
        'glow-cyan': '0 0 20px rgba(0, 212, 255, 0.4)',
        'glow-red': '0 0 20px rgba(239, 68, 68, 0.4)',
        'glow-green': '0 0 20px rgba(34, 197, 94, 0.4)',
      },
    },
  },
  plugins: [],
}

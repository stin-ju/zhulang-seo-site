/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        night: '#0B1220',
        deep: '#0F1A2E',
        elevated: '#16243D',
        turf: '#10B981',
        'turf-soft': 'rgba(16,185,129,0.15)',
        gold: '#F5C242',
        'gold-soft': 'rgba(245,194,66,0.12)',
        miss: '#3F4A60',
        ink: '#E8EEF7',
        muted: '#94A3B8',
        divider: 'rgba(255,255,255,0.08)',
      },
      fontFamily: {
        sans: ['Inter', 'Noto Sans SC', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Roboto Mono', 'ui-monospace', 'monospace'],
      },
      boxShadow: {
        card: '0 8px 24px rgba(0,0,0,0.35)',
        gold: '0 0 0 1px rgba(245,194,66,0.45), 0 12px 32px rgba(245,194,66,0.18)',
      },
      keyframes: {
        shimmer: {
          '0%': { transform: 'translateX(-120%)' },
          '100%': { transform: 'translateX(220%)' },
        },
        fadeIn: {
          '0%': { opacity: '0', transform: 'translateY(4px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        shimmer: 'shimmer 1.6s ease-out 0.3s 1 forwards',
        'fade-in': 'fadeIn 200ms ease-out both',
      },
      transitionTimingFunction: {
        soft: 'cubic-bezier(0.22, 1, 0.36, 1)',
      },
    },
  },
  plugins: [],
};

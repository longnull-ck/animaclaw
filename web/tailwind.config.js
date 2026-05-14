/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        anima: {
          bg: '#0f1419',
          card: '#1a2332',
          border: '#2a3a4e',
          accent: '#00d4aa',
          accent2: '#7c5cfc',
          warm: '#ff9f43',
          danger: '#ff6b6b',
          text: '#e8edf3',
          muted: '#7a8fa6',
        },
      },
      animation: {
        'pulse-slow': 'pulse 3s ease-in-out infinite',
        'slide-in': 'slideIn 0.3s ease-out',
        'fade-in': 'fadeIn 0.4s ease-out',
        'glow': 'glow 2s ease-in-out infinite alternate',
      },
      keyframes: {
        slideIn: {
          '0%': { transform: 'translateX(20px)', opacity: '0' },
          '100%': { transform: 'translateX(0)', opacity: '1' },
        },
        fadeIn: {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        glow: {
          '0%': { boxShadow: '0 0 5px rgba(0, 212, 170, 0.3)' },
          '100%': { boxShadow: '0 0 20px rgba(0, 212, 170, 0.6)' },
        },
      },
      screens: {
        'xs': '475px',
      },
    },
  },
  plugins: [],
  // 优化：只生成使用到的 class
  future: {
    hoverOnlyWhenSupported: true,
  },
}

/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: { sans: ['-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'Helvetica', 'Arial', 'sans-serif'] },
      fontSize: {
        xs: '12px', sm: '14px', base: '16px',
        lg: '20px', xl: '24px', '2xl': '32px',
      },
      spacing: { '18': '72px' },
      colors: {
        surface: { DEFAULT: '#f5f5f7', 1: '#ffffff', 2: '#f2f2f7' },
        border: '#d2d2d7',
        text: { primary: '#1d1d1f', secondary: '#86868b', muted: '#86868b' },
        accent: { DEFAULT: '#007aff', hover: '#0062cc' },
        status: {
          queued: '#86868b',
          scheduled: '#007aff',
          running: '#34c759',
          completed: '#34c759',
          failed: '#ff3b30',
          dead: '#ff9500',
          claimed: '#ffcc00',
        },
      },
    },
  },
  plugins: [],
}

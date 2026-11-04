/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        brand: { 50: '#effcf9', 100: '#c9f5eb', 400: '#2dd4bf', 500: '#14b8a6', 600: '#0d9488', 700: '#0f766e', 900: '#134e4a' },
        ink: { 900: '#0b1220', 800: '#111a2e', 700: '#1a2540', 600: '#24314f' },
      },
      fontFamily: { sans: ['Inter', 'system-ui', 'Segoe UI', 'sans-serif'] },
    },
  },
  plugins: [],
}

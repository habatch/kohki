import type { Config } from 'tailwindcss';

const config: Config = {
  darkMode: 'class',
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}', './lib/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink:    { 50:'#f4f5f7', 100:'#e5e7eb', 200:'#c8ccd3', 300:'#9ba0ab', 400:'#6b7280', 500:'#4a4f5c', 600:'#363a43', 700:'#262930', 800:'#181a1f', 900:'#0f1014', 950:'#0a0b0f' },
        depth:  { 50:'#eef4fb', 100:'#d5e3f4', 200:'#a5c3e5', 300:'#6f9fd1', 400:'#4280b8', 500:'#26659b', 600:'#1d4f7a', 700:'#173d5d', 800:'#112c44', 900:'#0b1d2e' },
        copper: { 50:'#fbf3ec', 100:'#f2dfcc', 200:'#e3bb96', 300:'#d29661', 400:'#c47936', 500:'#a85f1f', 600:'#854918', 700:'#633711', 800:'#44270c', 900:'#2a1807' },
        success:'#3a8b3a', warn:'#c47936', danger:'#b73a3a',
      },
      fontFamily: {
        sans: ['IBM Plex Sans','ui-sans-serif','system-ui','sans-serif'],
        mono: ['JetBrains Mono','ui-monospace','SFMono-Regular','monospace'],
      },
      borderRadius: { sm:'4px', md:'6px', lg:'8px', xl:'12px' },
    },
  },
  plugins: [],
};
export default config;

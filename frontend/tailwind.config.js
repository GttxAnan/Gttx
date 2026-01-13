/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
            colors: {
                background: '#09090b', // Zinc 950
                surface: '#18181b', // Zinc 900
                'surface-highlight': '#27272a', // Zinc 800
                primary: '#fafafa', // Zinc 50 (White-ish for high contrast accents)
                'primary-foreground': '#09090b',
                secondary: '#27272a', // Zinc 800
                'secondary-foreground': '#fafafa',
                accent: '#2563eb', // A professional blue for active states
                muted: '#71717a', // Zinc 500
                border: '#27272a', // Zinc 800
            },
            fontFamily: {
                sans: ['Inter', 'sans-serif'],
                mono: ['JetBrains Mono', 'monospace'],
            },
            animation: {
                'fade-in': 'fadeIn 0.5s ease-out',
                'slide-up': 'slideUp 0.5s ease-out',
            },
            keyframes: {
                fadeIn: {
                    '0%': { opacity: '0' },
                    '100%': { opacity: '1' },
                },
                slideUp: {
                    '0%': { transform: 'translateY(20px)', opacity: '0' },
                    '100%': { transform: 'translateY(0)', opacity: '1' },
                }
            }
        },
    },
    plugins: [],
}

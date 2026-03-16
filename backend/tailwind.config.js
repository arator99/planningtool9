/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',  // html.dark — één mechanisme overal
  content: [
    './templates/**/*.html',
    './partials/**/*.html',
  ],
  theme: {
    extend: {
      colors: {
        // Primair
        'primair':            'var(--primair)',
        'primair-hover':      'var(--primair-hover)',
        'primair-zacht':      'var(--primair-zacht)',
        // Achtergronden
        'achtergrond':        'var(--achtergrond)',
        'oppervlak':          'var(--achtergrond-widget)',
        'oppervlak-hover':    'var(--hover-bg)',
        // Tekst
        'tekst':              'var(--tekst)',
        'tekst-zacht':        'var(--tekst-secundair)',
        // Randen
        'rand':               'var(--rand)',
        'rand-sterk':         'var(--rand-sterk)',
        // Status
        'succes':             'var(--succes)',
        'succes-zacht':       'var(--msg-succes-bg)',
        'gevaar':             'var(--fout)',
        'gevaar-zacht':       'var(--msg-fout-bg)',
        'waarschuwing':       'var(--waarschuwing)',
        'waarschuwing-zacht': 'var(--msg-waarschuwing-bg)',
        'info':               'var(--info)',
        'info-zacht':         'var(--msg-info-bg)',
      },
    },
  },
  plugins: [],
}

/* Aplicar el tema antes del CSS evita un destello claro al abrir otra página. */
(() => {
    const key = 'sala-de-tareas-theme';
    const systemTheme = window.matchMedia('(prefers-color-scheme: dark)');
    let preference = null;
    try {
        const saved = localStorage.getItem(key);
        if (saved === 'dark' || saved === 'light') preference = saved;
    } catch (_) {
        // La selección sigue funcionando si el navegador bloquea el almacenamiento.
    }

    function applyTheme(theme) {
        document.documentElement.dataset.theme = theme;
        document.documentElement.style.colorScheme = theme;
        document.querySelectorAll('.theme-toggle').forEach(button => {
            const dark = theme === 'dark';
            const label = dark ? 'Activar modo claro' : 'Activar modo oscuro';
            button.setAttribute('aria-pressed', String(dark));
            button.setAttribute('aria-label', label);
            button.title = label;
            button.querySelector('.theme-label').textContent = dark ? 'Modo claro' : 'Modo oscuro';
        });
    }

    applyTheme(preference || (systemTheme.matches ? 'dark' : 'light'));
    document.addEventListener('DOMContentLoaded', () => {
        applyTheme(document.documentElement.dataset.theme);
        document.querySelectorAll('.theme-toggle').forEach(button => {
            button.addEventListener('click', () => {
                preference = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
                try { localStorage.setItem(key, preference); } catch (_) {}
                applyTheme(preference);
            });
        });
    });
    systemTheme.addEventListener('change', event => {
        if (!preference) applyTheme(event.matches ? 'dark' : 'light');
    });
})();

# Referência: snippets do pré-apontamento

Copiados de `spaceon_main.html`, `spaceon.css` e `spaceon_time_entry.js`. Ao reutilizar, **renomeie IDs** e ajuste textos.

## HTML (header + botão + dialog)

```html
<header class="q1-card-header">
    <div class="q1-card-header__title">
        <i class="fas fa-calendar-check" aria-hidden="true"></i>
        <h2>Pré-apontamento</h2>
    </div>
    <button
        type="button"
        class="q1-card-header__info"
        id="q1-pre-entry-info-open"
        aria-haspopup="dialog"
        aria-controls="q1-pre-entry-info-dialog"
        aria-label="Informações sobre o pré-apontamento"
    >
        <i class="fas fa-info-circle" aria-hidden="true"></i>
    </button>
</header>

<dialog id="q1-pre-entry-info-dialog" class="q1-pre-entry-dialog" aria-labelledby="q1-pre-entry-info-title">
    <div class="q1-pre-entry-dialog__panel">
        <div class="q1-pre-entry-dialog__head">
            <h3 id="q1-pre-entry-info-title">Sobre o pré-apontamento</h3>
            <button type="button" class="q1-pre-entry-dialog__close" id="q1-pre-entry-info-close" aria-label="Fechar">
                <i class="fas fa-times" aria-hidden="true"></i>
            </button>
        </div>
        <div class="q1-pre-entry-dialog__body">
            <section class="q1-pre-entry-dialog__section">
                <h4>Título da seção</h4>
                <p>Texto explicativo.</p>
            </section>
        </div>
    </div>
</dialog>
```

## CSS (bloco completo — fonte: `spaceon.css`)

Inclui `.q1-card-header` (gradiente do strip) para contexto do botão.

```css
.q1-card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 10px 16px;
    border-radius: 10px 10px 0 0;
    color: #fff;
    background: linear-gradient(90deg, var(--green-dark), var(--green-light) 55%, var(--green-dark) 100%);
}

.q1-card-header__title {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
}

.q1-card-header h2 {
    font-size: 18px;
    font-weight: 700;
    color: #fff;
    margin: 0;
}

.q1-card-header__info {
    flex-shrink: 0;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 34px;
    height: 34px;
    padding: 0;
    border: 1px solid rgba(255, 255, 255, 0.35);
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.12);
    color: rgba(255, 255, 255, 0.82);
    font-size: 15px;
    cursor: pointer;
    transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
}

.q1-card-header__info:hover {
    background: rgba(255, 255, 255, 0.22);
    color: #fff;
    border-color: rgba(255, 255, 255, 0.55);
}

.q1-card-header__info:focus-visible {
    outline: 2px solid rgba(255, 255, 255, 0.95);
    outline-offset: 2px;
}

.q1-pre-entry-dialog {
    position: fixed;
    inset: 0;
    width: min(520px, calc(100vw - 28px));
    max-width: calc(100vw - 28px);
    max-height: min(85vh, 520px);
    height: fit-content;
    margin: auto;
    padding: 0;
    border: none;
    background: transparent;
    box-sizing: border-box;
}

.q1-pre-entry-dialog::backdrop {
    background: rgba(0, 0, 0, 0.48);
}

.q1-pre-entry-dialog__panel {
    background: var(--color-bg-secondary);
    color: var(--color-text);
    border-radius: 12px;
    border: 1px solid var(--color-border);
    box-shadow: 0 16px 48px rgba(0, 0, 0, 0.22);
    overflow: hidden;
}

.q1-pre-entry-dialog__head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 14px 16px;
    border-bottom: 1px solid var(--color-border);
    background: color-mix(in srgb, var(--color-bg-primary) 65%, var(--color-bg-secondary));
}

.q1-pre-entry-dialog__head h3 {
    margin: 0;
    font-size: 17px;
    font-weight: 700;
    color: var(--color-title);
}

.q1-pre-entry-dialog__close {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    padding: 0;
    border: none;
    border-radius: 8px;
    background: transparent;
    color: var(--color-text-muted);
    font-size: 18px;
    cursor: pointer;
}

.q1-pre-entry-dialog__close:hover {
    background: color-mix(in srgb, var(--color-text) 8%, transparent);
    color: var(--color-text);
}

.q1-pre-entry-dialog__body {
    padding: 14px 18px 18px;
    max-height: min(70vh, 420px);
    overflow-y: auto;
}

.q1-pre-entry-dialog__section {
    margin: 0 0 14px;
}

.q1-pre-entry-dialog__section:last-child {
    margin-bottom: 0;
}

.q1-pre-entry-dialog__section h4 {
    margin: 0 0 6px;
    font-size: 14px;
    font-weight: 700;
    color: var(--green-light);
}

.q1-pre-entry-dialog__section p {
    margin: 0;
    font-size: 14px;
    line-height: 1.5;
    color: var(--color-text);
}
```

## JS (padrão — fonte: `spaceon_time_entry.js`)

```javascript
var infoDialog = document.getElementById("q1-pre-entry-info-dialog");
var infoOpen = document.getElementById("q1-pre-entry-info-open");
var infoClose = document.getElementById("q1-pre-entry-info-close");
if (infoDialog && infoOpen && typeof infoDialog.showModal === "function") {
    infoOpen.addEventListener("click", function () {
        infoDialog.showModal();
    });
    if (infoClose) {
        infoClose.addEventListener("click", function () {
            infoDialog.close();
        });
    }
    infoDialog.addEventListener("click", function (ev) {
        if (ev.target === infoDialog) {
            infoDialog.close();
        }
    });
}
```

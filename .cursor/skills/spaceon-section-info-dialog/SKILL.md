---
name: spaceon-section-info-dialog
description: >-
  Documenta o botão circular de informação (ícone "i") no canto direito do
  header de card SpaceOn e o modal `<dialog>` associado (painel, título,
  fechar, corpo com seções). Usar ao replicar o mesmo padrão em outras
  seções da home SpaceOn (`/user/spaceon/home/`) ou páginas com o mesmo
  design system (tokens `--color-*`, `--green-*`), ou quando o usuário
  pedir "ícone de informação como no pré-apontamento" / modal de ajuda
  contextual no header.
---

# SpaceOn: ícone de informação + modal no header do card

## Quando aplicar

- Header de **card** estilo SpaceOn (`spaceon-card`) com título à esquerda e **botão de ajuda** à direita.
- Conteúdo explicativo em **modal** sem navegar (sem reload): `<dialog>` nativo + `showModal()` / `close()`.
- Manter **tokens CSS** do projeto (`var(--color-*)`, `var(--green-*)`); não inventar paleta nova no modal.

Para HTML/CSS/JS **copiáveis** linha a linha, ver [reference.md](reference.md).

## Referência canônica no repositório

| Peça | Arquivo |
|------|---------|
| HTML (Pré-apontamento) | `app/templates/xperience/partials/user/spaceon/spaceon_main.html` — `header.q1-card-header`, botão `#q1-pre-entry-info-open`, `dialog#q1-pre-entry-info-dialog` |
| CSS (header + botão + modal) | `app/static/xperience/css/spaceon.css` — blocos `.q1-card-header` … `.q1-pre-entry-dialog__section p` |
| JS (abrir/fechar/backdrop) | `app/static/xperience/js/spaceon_time_entry.js` — busca por `q1-pre-entry-info-dialog` / `q1-pre-entry-info-open` / `q1-pre-entry-info-close` |

Font Awesome já usado no projeto: `fa-info-circle` (botão), `fa-times` (fechar).

## Estrutura do header

1. `header` com **flex** horizontal: `justify-content: space-between`, `align-items: center`, `gap`.
2. Bloco do título: `div` com ícone contextual + `h2` (ou `h3` coerente com hierarquia da página).
3. Botão de informação **após** o título no DOM (fica à direita com flex).

## Botão de informação (canto direito)

- `button type="button"` com classe **`q1-card-header__info`** (hoje acoplada ao header verde `.q1-card-header`; ver nota abaixo).
- Ícone: `<i class="fas fa-info-circle" aria-hidden="true"></i>`.
- Acessibilidade: `aria-haspopup="dialog"`, `aria-controls="<id-do-dialog>"`, `aria-label` descritivo (ex.: "Informações sobre o pré-apontamento").
- **IDs únicos** por instância na página: ex. `{prefix}-info-open`, `{prefix}-info-dialog`, `{prefix}-info-close`, `{prefix}-info-title`.

Estilo do botão (referência — copiar de `spaceon.css` se duplicar classes):

- Círculo **34×34px**, `border-radius: 50%`, borda branca semitransparente, fundo branco ~12% opacidade, cor do ícone ~82% branco.
- Hover: fundo e borda um pouco mais fortes, ícone branco sólido.
- `focus-visible`: outline claro (acessível no header em gradiente verde).

## Modal (`<dialog>`)

1. Elemento `dialog` com classe **`q1-pre-entry-dialog`** + `aria-labelledby` no `h3` do cabeçalho interno.
2. **Painel** interno `div.q1-pre-entry-dialog__panel` (fundo e borda usam tokens; o `dialog` em si fica transparente, largura limitada, centralizado com `margin: auto`).
3. **Cabeçalho** `div.q1-pre-entry-dialog__head`: título `h3` + `button.q1-pre-entry-dialog__close` com `fa-times` e `aria-label="Fechar"`.
4. **Corpo** `div.q1-pre-entry-dialog__body`: scroll vertical se necessário (`max-height` + `overflow-y: auto`).
5. Conteúdo em **`section.q1-pre-entry-dialog__section`**: `h4` + `p`; última seção sem margem inferior extra.

Backdrop: `::backdrop` com `rgba(0, 0, 0, 0.48)`.

Títulos das subseções no modal usam **`color: var(--green-light)`** para alinhar à marca SpaceOn (ver `.q1-pre-entry-dialog__section h4`).

## JavaScript mínimo

Após garantir que `dialog` e botões existem:

1. Clique no botão abrir: `if (typeof infoDialog.showModal === "function") infoDialog.showModal();`
2. Clique no fechar: `infoDialog.close();`
3. Clique no **próprio** `dialog` (backdrop implícito do elemento): se `ev.target === infoDialog`, então `infoDialog.close();`

Opcional: listener `cancel` no `dialog` ou tecla Escape já fecha o modal nativamente em muitos navegadores; manter consistência com outros modais do projeto.

## Generalização para novas seções

- **IDs e textos**: trocar prefixo (`q1-pre-entry-*` → ex. `q2-memorized-*`) para evitar colisão.
- **Classes CSS**: hoje os nomes são `q1-*` / `q1-pre-entry-dialog*`. Para uma segunda seção pode-se:
  - **Duplicar** blocos em `spaceon.css` com novo prefixo (mais isolado), ou
  - **Extrair** classes genéricas (ex. `spaceon-card-header__info`, `spaceon-info-dialog`) num refator futuro — só fazer se várias telas forem migradas de uma vez.
- **Header não verde**: o botão `q1-card-header__info` assume fundo **gradiente verde** no header (texto/ícone claros). Se o card tiver header neutro, criar variante de botão (mesmas medidas, cores derivadas de `var(--color-text)` / borda `var(--color-border)`) em vez de reaproveitar o rgba branco literal.

## Checklist rápido

- [ ] Header em flex com título + botão info à direita.
- [ ] `aria-controls` / `aria-labelledby` / `aria-label` coerentes.
- [ ] `dialog` + painel + fechar + corpo com seções; conteúdo em linguagem clara.
- [ ] CSS: largura máxima responsiva, `::backdrop`, painel com `var(--color-bg-secondary)`, borda `var(--color-border)`.
- [ ] JS: `showModal`, fechar, clique fora (target === dialog); feature-detect `showModal`.
- [ ] IDs únicos na página; cache bust `?v=` em CSS/JS se alterar estáticos.

## O que não fazer

- Não trocar o `<dialog>` por div full-screen sem motivo (perde semântica e foco).
- Não remover o painel interno: o `dialog` usa fundo transparente de propósito (só o painel “cartão”).
- Não hardcodar cores de texto de modal fora dos tokens já usados no bloco existente.

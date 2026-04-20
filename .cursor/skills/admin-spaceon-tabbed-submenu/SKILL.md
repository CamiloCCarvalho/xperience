---
name: admin-spaceon-tabbed-submenu
description: >-
  Define o padrão visual e técnico do sub-menu em abas na admin Spaceon: faixa
  verde com links, painéis por hash (#id), cartão único (tabbed shell), e
  data-admin-tt-force-hash para focar a aba certa após POST com erro. Usar ao
  adicionar ou refatorar seções com abas horizontais no estilo Templates /
  Expedientes / Departamentos / Membros, ou quando o usuário pedir o mesmo
  sub-menu por abas na home admin ou páginas equivalentes.
---

# Sub-menu em abas (admin Spaceon)

## Quando aplicar

- Nova **área com várias sub-seções** trocadas por clique, no **mesmo cartão** da home admin (ou página com `.admin-spaceon-home`).
- Replicar o **visual**: faixa superior em gradiente verde, abas que “encaixam” no painel claro abaixo, conteúdo em `article` oculto/mostrado por estado.
- Garantir **URL com hash** (`#admin-tt-...`) para bookmark e para **voltar na aba certa** após validação Django no painel errado.

Para **listas, pills, modais de criar/editar** dentro de cada aba, use em conjunto a skill **[admin-entity-list-modal](../admin-entity-list-modal/SKILL.md)**.

## Referência viva no repositório

| Peça | Arquivo |
|------|---------|
| HTML do bloco | `app/templates/xperience/partials/admin/spaceon/spaceon_home_time_tracking.html` |
| Mesmo padrão na config workspace | `app/templates/xperience/partials/admin/spaceon/spaceon_config/spaceon_config_main.html` + `app/static/xperience/js/admin_config_workspace_tabs.js` — escopo **`.admin-config-ws-main .admin-tt-*`** e CSS em `spaceon_config.css` |
| CSS (abas, painel, cartão) | `app/static/xperience/css/admin_time_tracking_home.css` — seletores `.admin-tt-stack`, `.admin-tt-tabbed-shell`, `.admin-tt-tabs-*`, `.admin-tt-tab`, `.admin-tt-panel`, `.admin-tt-body` |
| Comportamento hash / abas | `app/static/xperience/js/admin_spaceon_home_tabs.js` |
| Base (cache bust) | `base_templates/global/admin/home.html` |

## Estrutura HTML obrigatória

1. **Escopo**: o bloco deve estar dentro de um ancestral com classe **`admin-spaceon-home`** (os estilos são prefixados assim).

2. **Stack** — wrapper único por bloco de abas:
   - `div.admin-tt-stack`
   - Opcional: `data-admin-tt-force-hash="#admin-tt-<painel>"` quando a resposta do servidor deve **abrir uma aba específica** (ex.: erro de formulário numa aba que não é a primeira). O script lê isso no `init` e ajusta `location.hash` antes de sincronizar abas.

3. **Cartão + faixa de abas**:
   - `div.admin-tt-tabbed-shell.spaceon-card` (o `spaceon-card` alinha com o restante da UI Spaceon).
   - `header.admin-tt-tabs-strip` → `nav.admin-tt-tabs` com `role="tablist"` e `aria-label` descritivo.

4. **Cada aba** — link âncora (não `<button>`), para funcionar sem JS degradado e com hash nativo:
   - `a.admin-tt-tab` com `href="#<id-do-painel>"`, `role="tab"`, `id="tab-<id-do-painel>"`, `aria-controls="<id-do-painel>"`, `aria-selected="true|false"`.
   - Aba ativa na carga inicial da primeira seção: `admin-tt-tab--active` + `aria-selected="true"`; demais `aria-selected="false"`.

5. **Cada painel** — `article` (ou elemento com o mesmo papel):
   - `id` estável e único na página (ex.: `admin-tt-templates`).
   - Classes: `admin-tt-panel` + `admin-tt-panel--active` só no painel visível inicialmente.
   - `role="tabpanel"`, `aria-labelledby` apontando para o `id` do `tab-*`, `aria-hidden="true|false"` coerente com ativo.

6. **Conteúdo do painel**: `div.admin-tt-body` envolvendo o conteúdo (títulos auxiliares, listas, botões “Criar”, `<dialog>`, etc.).

### Convenção de IDs

- Prefixo sugerido: **`admin-tt-`** + nome curto em minúsculas (ex.: `admin-tt-relatorios`).
- IDs de aba: `tab-` + mesmo sufixo do painel (`tab-admin-tt-relatorios`).

## JavaScript (`admin_spaceon_home_tabs.js`)

- A lista **`PANEL_IDS`** deve incluir **todos** os `id` dos painéis do bloco, **na ordem das abas**. Sem isso, hash e `activate()` ignoram o painel novo.
- Clique nas abas: `preventDefault` + `location.hash = id` para manter uma única fonte de verdade; `hashchange` chama `sync()` / `activate()`.
- Hash inválido (não está em `PANEL_IDS`): `replaceState` remove o fragmento e cai no primeiro painel da lista.
- **`data-admin-tt-force-hash`**: usar quando flags de contexto indicarem modal/erro numa aba (ex.: `template_create_dialog_open`). Ordem dos `{% elif %}` no template: priorizar a aba “mais específica” ou a que o produto exige (na home atual: Membros → Expedientes → Departamentos → Templates).

Ao adicionar um novo painel: **atualizar `PANEL_IDS`**, o **partial HTML** e o **`data-admin-tt-force-hash`** na view/template.

## CSS

- Manter regras sob **`.admin-spaceon-home .admin-tt-...`** para não vazar para outras páginas.
- Padrões-chave: `admin-tt-tabbed-shell` (borda, raio, sombra), `admin-tt-tabs-strip` (gradiente verde), `admin-tt-tab` / `admin-tt-tab--active` (aba “solta” sobre o painel), `.admin-tt-panel:not(.admin-tt-panel--active) { display: none }`.

## Django + modal na aba

- Flags booleanas no contexto por fluxo (ex.: `*_create_dialog_open`, `*_edit_dialog_open`) alimentam `data-auto-open` nos `<dialog>` e o `data-admin-tt-force-hash` no `.admin-tt-stack`.
- Formulários de **criar** com **prefixo** distinto do **editar** (evita colisão de `name` entre painéis no mesmo POST futuro ou na mesma página).

## Checklist — nova aba no sub-menu

- [ ] Novo `article.admin-tt-panel` com `id` único e ARIA ligado ao `a.admin-tt-tab`.
- [ ] Novo `a.admin-tt-tab` na faixa, `href` coerente com o painel.
- [ ] Inclusão do `id` do painel em **`PANEL_IDS`** em `admin_spaceon_home_tabs.js`.
- [ ] Se houver POST com erro nessa aba: flag no contexto + `data-admin-tt-force-hash` no `elif` correto.
- [ ] Bump de **`?v=`** em `home.html` para o JS (e CSS se novas classes).

## O que não fazer

- Não usar só `display`/`hidden` no servidor sem alinhar `aria-hidden` e `admin-tt-tab--active` na carga inicial (o JS corrige após load, mas o HTML inicial deve ser acessível).
- Não duplicar o mesmo `id` de painel em dois blocos na mesma página.
- Não esquecer de atualizar `PANEL_IDS` — sintoma: clique na aba não muda o painel ou hash “perdido” após reload.

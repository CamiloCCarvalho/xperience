---
name: admin-entity-list-modal
description: >-
  Padroniza listas administrativas estilizadas (linha com metadados, pills,
  botões só ícone para editar/excluir) e modais `<dialog>` centralizados para
  edição ou formulários secundários, com formulários Django prefixados,
  reabertura após erro de validação e hash de aba. Usar ao criar ou refatorar
  telas admin Spaceon/Django com listas + CRUD inline, padrão semelhante a
  templates/expedientes/departamentos/membros na home admin, ou quando o
  usuário pedir o mesmo padrão visual de lista e modal.
---

# Lista admin + modal (padrão Xperience)

## Quando aplicar

- Nova seção na home admin (ou outra página) com **lista de entidades** e ações **editar** / **excluir**.
- Refatorar tabela ou lista antiga (`admin-config-list`, `btn-primary` “Excluir”) para o padrão atual.
- Manter **POST + redirect** no Django; só mudar layout/UX, salvo exceções documentadas (ex.: form inválido sem redirect quando fizer sentido mostrar erros no modal).

## Referência viva no repositório

- **CSS**: `app/static/xperience/css/admin_time_tracking_home.css` — classes `admin-tt-template-list`, `admin-tt-template-row`, `admin-tt-pill`, `admin-tt-icon-btn`, `admin-tt-edit-dialog`, `admin-tt-entity-meta`, `admin-tt-ud-links` (ajustes para membros).
- **HTML**: `app/templates/xperience/partials/admin/spaceon/spaceon_home_time_tracking.html`.
- **JS**: `app/static/xperience/js/admin_template_edit_modal.js`, `app/static/xperience/js/admin_tt_schedule_dept_member_modals.js`.
- **Abas + hash**: `app/static/xperience/js/admin_spaceon_home_tabs.js` (`data-admin-tt-force-hash` no stack). Para o **layout do sub-menu em abas** (faixa verde, painéis, `PANEL_IDS`), ver **[admin-spaceon-tabbed-submenu](../admin-spaceon-tabbed-submenu/SKILL.md)**.
- **Base**: `base_templates/global/admin/home.html` (CSS/JS com `?v=` para cache bust).
- **View**: `app/views/admin.py` — `admin_home`: formulários com prefixo para modal, flags `*_edit_dialog_open`, `*_target_id`.

## Estrutura HTML da lista

1. Container da página já deve incluir `.admin-spaceon-home` (escopo dos estilos).
2. Lista: `ul.admin-tt-template-list` com `role="list"`.
3. Cada item: `li.admin-tt-template-row` com:
   - `div.admin-tt-template-row__main` — título `span.admin-tt-template-row__name`, opcional `p.admin-tt-entity-meta`, opcional `div.admin-tt-template-row__badges` com `span.admin-tt-pill` / `admin-tt-pill--muted`.
   - `div.admin-tt-template-row__actions` — botão editar + form de exclusão.

## Botões de ação

- **Editar**: `button type="button"` com classes `admin-tt-icon-btn admin-tt-icon-btn--edit`, ícone `fa-pen` (ou coerente com o contexto), `title` e `aria-label` **estáticos** (evitar quebra com aspas no nome da entidade).
- **Excluir**: `form.admin-tt-template-del-form` + `button type="submit"` com `admin-tt-icon-btn admin-tt-icon-btn--danger` e `fa-trash-alt`.
- Atributos `data-*` no botão editar para o JS preencher o modal (ex.: `data-template-id`, `data-name`, flags). Valores de texto: usar `|escape` no Django quando forem para atributos HTML.

## Modal (`<dialog>`)

- `dialog.admin-tt-edit-dialog` com `aria-labelledby` apontando para o título.
- Painel interno: `admin-tt-edit-dialog__panel` → `__head` (título `h3` + `button.admin-tt-edit-dialog__close` com `fa-times`) → `__body` → `form.admin-config-form.admin-tt-edit-dialog__form`.
- **Reabrir após erro de validação**: `data-auto-open="1"` no `<dialog>` quando a view setar a flag correspondente; o JS remove o atributo após `showModal()`.
- Fechar: botão fechar + clique no **backdrop** (`ev.target === dialog`).
- Cabeçalho com subtítulo (ex. email do membro): usar `admin-tt-edit-dialog__head--stack` e `p.admin-tt-edit-dialog__subtitle`.

## Django (view + formulários)

1. **Criar** sem prefixo; **editar no modal** com **prefixo único** (ex.: `tpl_edit`, `sch_edit`, `dept_edit`, `ud_assign`) para não colidir com o POST do formulário de criação.
2. No `POST` de update: instanciar `Form(request.POST, prefix="...", instance=obj)`. Se **inválido**: recriar o form de criação vazio (quando aplicável), manter o form de edição com erros, `*_dialog_open = True`, `*_target_id` a partir do POST (id da entidade).
3. Passar no `context` o form de edição, flags de modal e id alvo para o `hidden` do update.
4. Se o modal estiver em **aba** diferente da padrão: no wrapper `.admin-tt-stack`, definir `data-admin-tt-force-hash="#admin-tt-..."` quando houver modal aberto por erro; o `admin_spaceon_home_tabs.js` aplica o hash antes do `sync()`. Na home admin, hashes válidos incluem `#admin-tt-templates`, `#admin-tt-expedientes`, `#admin-tt-departamentos`, `#admin-tt-membros`.

## JavaScript

- Um IIFE por “família” de modais ou arquivo dedicado; checar `dialog.showModal`.
- Delegar ou ligar `click` nos `[data-admin-*-edit]`; usar `openFromButton(this)` para ler `dataset` corretamente.
- Checkboxes/selects: ids gerados pelo Django com prefixo (`id_prefix-field`); confirmar com `python manage.py shell` se necessário.
- **Assign / modal limpo**: ao abrir pelo botão, `form.reset()` só quando fizer sentido; restaurar `hidden` (ex. `user_id`) e rótulo **após** o reset.

## Checklist rápido

- [ ] Lista com `admin-tt-template-list` / `admin-tt-template-row`, não tabela genérica, salvo caso tabular seja requisito explícito.
- [ ] Excluir só ícone; editar só ícone (ou ícone semanticamente claro).
- [ ] Modal com formulário POST, `csrf_token`, `action` + ids ocultos corretos.
- [ ] Form de edição com prefixo e view tratando invalidação + flags.
- [ ] `data-auto-open` + JS para reabrir; `data-admin-tt-force-hash` se houver abas.
- [ ] Incluir JS/CSS na base admin com versão `?v=` quando alterar arquivos estáticos.

## O que não fazer

- Não misturar campos de criar e editar no mesmo prefixo / mesmo `name` sem planejamento.
- Não colocar `aria-label` com nome de entidade sem escapar (preferir label fixo + `title` genérico).
- Não remover o padrão de redirect em fluxos de sucesso sem alinhar com o restante do app.

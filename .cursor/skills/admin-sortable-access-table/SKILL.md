---
name: admin-sortable-access-table
description: >-
  Padroniza lista administrativa em formato tabela responsiva com cabeçalho
  ordenável, paginação client-side e células com tags interativas para vínculo
  rápido via fetch. Usar ao replicar o padrão da aba Membros em
  /user_admin/spaceon/config/ ou quando o usuário pedir tabela com ordenação
  por coluna no estilo SpaceOn admin.
---

# Tabela admin ordenável (padrão Membros/Config)

## Quando aplicar

- Seções administrativas que precisam exibir muitos registros em layout tabular com colunas claras.
- Cenários com ordenação por coluna no front-end (sem reload de página).
- Listas com ações inline por linha (remover, vincular, desvincular) e atualização visual imediata.

## Referência viva no repositório

- **Template**: `app/templates/xperience/partials/admin/spaceon/spaceon_config/spaceon_config_main.html` (painel `#admin-config-ws-membros`).
- **JS**: `app/static/xperience/js/admin_config_members_access.js`.
- **CSS**: `app/static/xperience/css/spaceon_config.css` (bloco `.acf-members*`).

## Estrutura base (HTML)

1. Container raiz com atributos `data-*` para endpoints e estado:
   - `data-acf-members-access`
   - `data-url-link-*`, `data-url-unlink-*`, `data-url-remove-*`
   - `data-page-size`
2. Wrapper com scroll horizontal: `.acf-members__table-scroll`.
3. Tabela com `role="grid"` e semântica completa:
   - `thead` com botões de ordenação (`button[data-sort-key]`) em cada `th`.
   - Ícone padrão de ordenação em `.acf-members__sort-icon`.
   - `tbody` com linhas `.acf-members__row`.
4. Cada `tr` precisa de atributos `data-sort-*` por coluna e `data-original-index` para reset da ordem inicial.
5. Área de paginação separada: `[data-acf-members-pager]`.

## Regra de ordenação

- Ordenação é **triestado** por coluna: `asc -> desc -> reset`.
- `reset` remove chave/direção e restaura `data-original-index`.
- Comparação deve usar `localeCompare(..., { numeric: true, sensitivity: "base" })`.
- Ao alterar dados da linha (ex.: adicionou/removou tag), atualizar imediatamente os `data-sort-*`.
- Estados visuais:
  - padrão: `fa-sort`
  - asc: `fa-sort-up`
  - desc: `fa-sort-down`
  - expor `aria-sort` no botão ativo.

## Regra de paginação

- Paginação client-side após ordenação.
- `pageSize` configurável por `data-page-size`.
- Botões: anterior (`‹`), páginas numeradas, próximo (`›`).
- Ao remover linha, recalcular total e ajustar página atual para o novo intervalo válido.

## Células com vínculos dinâmicos (tags)

- Células de cliente/projeto usam:
  - container de tags (`[data-acf-tags-*]`)
  - `select` inline para adicionar novo vínculo.
- Cada tag tem botão interno de remoção (`.acf-members__tag-x`).
- Fluxo de adição:
  1. `change` no `select`.
  2. `fetch POST` com CSRF.
  3. Em sucesso, inserir tag no DOM.
  4. Ocultar/desabilitar opção já vinculada no `select`.
  5. Recalcular `data-sort-*`.
- Fluxo de remoção:
  1. click no `x`.
  2. `fetch POST` para desvincular.
  3. Remover tag do DOM.
  4. Reexibir opção correspondente no `select`.
  5. Recalcular `data-sort-*`.

## CSS do padrão

- Escopo por página: `.spaceon-config-page .admin-config-ws-main .acf-members...`.
- Responsividade e usabilidade:
  - `overflow-x: auto` no wrapper da tabela.
  - tipografia compacta (`~0.8125rem`) para densidade.
  - linhas com `hover` sutil e contraste consistente.
  - `focus-visible` claro em botões de ordenação/ação.
- Tags:
  - formato pill (`border-radius: 999px`);
  - variantes semânticas (cliente, projeto, departamento);
  - texto truncado com `text-overflow: ellipsis`.
- Paginação com botões pequenos e estado ativo destacado.

## Contrato backend (Django)

- Endpoints POST retornam JSON consistente:
  - sucesso: `{ ok: true, ...ids..., label }`
  - erro: `{ ok: false, error: "mensagem" }`
- Sempre validar permissão de workspace no backend.
- CSRF obrigatório (`X-CSRFToken` + `credentials: "same-origin"`).
- Em caso de falha de rede/validação, front deve informar erro sem quebrar o estado da tabela.

## Checklist de implementação

- [ ] `th` usa `button[data-sort-key]` (não click direto no `th`).
- [ ] Cada `tr` possui `data-original-index` e `data-sort-*`.
- [ ] Ordenação triestado com ícone e `aria-sort`.
- [ ] Paginação recalculada após ordenar/adicionar/remover.
- [ ] Ações de vínculo atualizam DOM e `data-sort-*` no mesmo fluxo.
- [ ] Wrapper com `overflow-x: auto` para mobile.
- [ ] Estilos escopados para não vazar para outras tabelas.

## O que evitar

- Não ordenar baseado apenas no texto renderizado quando já existe `data-sort-*` normalizado.
- Não usar tabela sem wrapper de scroll horizontal em contexto administrativo denso.
- Não acoplar ordenação/paginação no backend para esse padrão (salvo volumes extremos e decisão explícita).

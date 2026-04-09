# Xperience

Sistema online de apontamentos de trabalho e controle financeiro por workspace (empresa).

## Visao geral

O Xperience facilita a rotina de apontamentos diarios de horas (por funcionario e por projeto) e ajuda a gestao a acompanhar:

- horas trabalhadas, faltas e horas extras
- custo total por projeto e por area
- visibilidade financeira vinculada (futuramente) a prazos e budgets

Ele foi pensado para atender empresas pequenas e grandes, inclusive fora da area de TI (ex.: padarias, lojas de roupas), com flexibilidade para adaptar a forma como o trabalho e organizado.

## Problema que resolve

Em muitas empresas, apontamentos e custos ficam espalhados em planilhas, comunicacoes informais ou processos manualmente demorados. Isso cria dificuldades para:

- registrar trabalho de forma consistente ao longo do tempo
- consolidar horas por projeto, funcionario e periodo
- entender custo real (horas x custo) e impactos por area/projeto
- acompanhar indicadores (metricas) e apoiar decisoes

## Solucao (como o produto funciona)

O sistema e organizado por camadas:

1. Multi-tenant por workspace (empresa)
2. Papais e perfis (admin e funcionarios)
3. Estruturas de trabalho (projetos e organizacoes por area, quando aplicavel)
4. Registro de apontamentos diarios
5. Relatorios e metricas
6. Controle financeiro por projeto/area (incluindo custos e agregacoes)

## Conceitos principais

### Workspace (empresa)
Representa uma empresa assinante que utiliza o sistema. No workspace ficam as configuracoes e os dados daquela organizacao (isolamento de dados).

### Assinantes / Administradores do workspace
Usuarios administradores do workspace (quem gerencia a empresa no sistema). Eles criam e organizam:

- workspaces (empresas)
- projetos
- funcionarios (users que fazem os apontamentos)

### Funcionarios
Usuarios do workspace que registram apontamentos de trabalho. Tipicamente:

- apontam horas por dia
- vinculam o tempo a projetos
- visualizam suas informacoes e retornam para a gestao via dashboards/relatorios

### Projetos (e opcionalmente areas)
Estruturas onde o trabalho e registrado. Projetos permitem:

- consolidar horas por periodo
- calcular custo total do projeto
- comparar eficiencia, carga e evolucao

### Apontamentos (horas, faltas e extras)
Registros do trabalho por funcionario e por dia. A partir deles, o sistema calcula:

- horas normais
- faltas (ausencia ou nao apontamento, conforme regra definida)
- horas extras (quando ultrapassarem limites/regra do workspace)

### Relatorios e metricas
Dashboards para gestao com agregacoes por:

- periodo
- funcionario
- projeto
- area (quando aplicavel)

Exemplos de metricas desejadas:

- horas totais
- horas extras por periodo
- faltas por funcionario e por equipe
- custo por projeto e por area
- tendencias e comparativos (ex.: semana vs semana)

### Financeiro (custo por projeto/area)
Modulo responsavel por apoiar a gestao financeira a partir dos apontamentos.

O primeiro foco e viabilizar a base do calculo de custo total por projeto/area.

Posteriormente, o financeiro pode ser vinculado a:

- prazos
- budget (orcamento)
- custos estimados vs reais

## Telas (norte do frontend)

Ja existe um esqueleto de telas (rotas e templates) separado em tres areas:

- Public: paginas de apresentacao do sistema
- User: telas para o funcionario (ex.: workspaces, home, dashboard, configuracao, account)
- Admin: telas para o administrador do workspace (ex.: home, workspaces, dashboard, configuracao, account)

Essas telas funcionam como direcao inicial para integrar o backend depois.

## Estado atual do projeto

Neste momento:

- ha base Django com rotas e renderizacao de templates
- os templates e CSS base estao definidos para o estilo geral
- ainda nao existe modelagem de dados no banco (os `models` ainda nao foram implementados)
- autenticao/autoridades por papais ainda nao foram integradas as views
- apontamentos, projetos e financeiro ainda nao estao persistidos nem calculados

Ou seja: o projeto esta pronto para evoluir da camada de telas para a camada de dados/negocio.

## Requisitos

- Python (versao utilizada: 3.13.x)
- Django 6.x
- Empacotamento e ambiente virtual via `.venv`

## Como rodar localmente

1. Criar o ambiente virtual:
   - `python -m venv .venv`
   - no Windows PowerShell: `.\.venv\Scripts\Activate.ps1`

2. Instalar dependencias:
   - `pip install -r requirements.txt`

3. Rodar o servidor:
   - `python manage.py runserver`

4. (Depois que models estiverem implementados) gerar migracoes:
   - `python manage.py makemigrations`
   - `python manage.py migrate`

## Roadmap (proximos passos)

### Fase 1: Modelagem e base do dominio

- definir models do core:
  - workspace
  - usuario/funcoes (admin x funcionario)
  - projetos
  - apontamentos (horas por dia)
  - configuracoes necessarias do workspace (para regras como limites e calculos)
- criar migrations e administrar dados via Django admin
- garantir isolamento por workspace nas consultas

### Fase 2: Autenticacao e autorizacao por papel

- integrar login/logout
- aplicar permissao por papel:
  - admin gerencia workspace e cadastros
  - funcionario registra apontamentos e acessa apenas o que pertence ao workspace

### Fase 3: Apontamentos e regras (faltas e horas extras)

- criar tela/form para registro diario
- definir regras de faltas e horas extras (configuraveis por workspace)
- validar consistencia (ex.: somas, limites, dias permitidos)

### Fase 4: Relatorios e metricas

- dashboards por periodo/projeto/funcionario
- graficos e indicadores baseados nos apontamentos
- exportacao (opcional) e filtros

### Fase 5: Financeiro e custo total

- calcular custo por projeto/area a partir de parametros do workspace (ex.: custo por hora)
- integrar com visoes de gestao (painel financeiro)
- preparar estrutura para prazos e budget (futuro)

## Objetivo final

Entregar um sistema robusto para:

- facilitar apontamentos online
- transformar registros em informacoes uteis de gestao
- apoiar controle financeiro por projeto/area
- escalar de pequenas operacoes para empresas maiores com flexibilidade de regras

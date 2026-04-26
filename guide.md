# Tips
  - Para limpar o banco local (na raiz do projeto): Remove-Item db.sqlite3
  - Para subir um esquema limpo: .\.venv\Scripts\python.exe manage.py migrate
  - Para executar o projeto: Play (debug last) > Debugger: Django

# Tasks (total = 15)
  - [1] Criar conteudo para tela publica "Plataforma"
  - [2] Criar conteudo para tela publica "Soluções"
  - [3] Criar conteudo para tela publica "Recursos"
  - [4] Criar tela "Esqueceu Login"
  - [5] Criar tela "Planos"
  - [6] Criar tela "Termos de Uso | Politicas e Privacidade"
  - [7] Limpar conteudo da tela user "Dashboard"
  - [8] Limpar conteudo da tela admin "Configurações"
  - [9] Criar tela admin para cadastro de "Clintes" > "Projetos"
  - [10] Criar tela admin para cadastro de "Fornecedores"
  - [11] Ajustar CSS de todos Cabeçalhos (Public, User, Admin)
  - [12] Ajustar CSS de telas public/admin
  - [13] Criar nova tela de cadastro de admin sendo liberada apenas com o Pagamento
  - [14] Controle de sessão e navegação por tipo de usuário (ADMIN)
  - [15] Correção do fluxo de cadastro de administradores

# WIP
  - [12] Ajustar CSS de telas public/admin (Camilo) 2h
  - [13] Criar nova tela de cadastro de admin sendo liberada apenas com o Pagamento - 4h
  -

# Finished (with Hours)
  - [14] Controle de sessão e navegação por tipo de usuário (ADMIN) (Asce) ~1h
    - Logo do header admin (admin_brand.html) passou a apontar para 'admin-workspaces' ao invés de 'public-home'.
      Resultado: clicar na logo dentro da área /user_admin/* mantém o admin no painel dele.
    - View public.home() ganhou guard no início: se request.user é admin autenticado, redireciona para 'admin-workspaces'.
      Defesa em profundidade para acesso direto a "/" via bookmark/link/logo da public_brand.html.
    - Itens já existentes que cobrem a task (não precisaram de mudança):
      * User.PlatformRole.ADMIN em app/models.py
      * _post_login_redirect() em app/views/public.py — já mandava admin para 'admin-workspaces' após login
      * Decorator @platform_admin_required em app/decorators.py — já protegia toda view admin (verifica auth + role + redireciona para LOGIN_URL se anônimo)
    - Módulos alterados:
      * app/templates/xperience/partials/admin/admin_brand.html
      * app/views/public.py (função home)

  - [15] Correção do fluxo de cadastro de administradores (Asce) ~1h
    - View public.register_admin_plan(): removido `if request.user.is_authenticated: return _post_login_redirect(...)`.
      Agora a página de cadastro nunca expulsa um usuário já logado — sempre renderiza o form em branco.
    - View public.register(): mesma remoção. Mantida sem auto-login (continua redirecionando para /login/ após criar conta).
    - Auto-login pós-cadastro em register_admin_plan() agora chama logout(request) + clear_admin_workspace + clear_member_workspace
      antes de fazer login() do novo admin. Isso evita que sessão antiga contamine a nova quando alguém cadastra um segundo admin
      estando já logado como o primeiro.
    - GET de ambas as views já usava `AdminRegisterForm()` sem argumentos — form sempre vem limpo, nunca prefilled da sessão.
    - Templates não precisaram mudar.
    - Módulos alterados:
      * app/views/public.py (funções register e register_admin_plan)

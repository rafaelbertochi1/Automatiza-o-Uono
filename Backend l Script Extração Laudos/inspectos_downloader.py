"""
Robô que baixa em massa os "Laudo Completo" da plataforma Inspectos
(cliente Santander) para um período de datas, salvando os PDFs direto
em data/laudos/ - prontos pro santander_extractor.py processar depois.

COMO USAR:
    1. pip install playwright
    2. playwright install chromium
    3. python inspectos_downloader.py

IMPORTANTE - PRIMEIRA VERSÃO:
Este script foi escrito com base em prints de tela, sem acesso direto
ao site. É bem provável que algum passo precise de ajuste fino (nome
exato de um campo, texto de um botão, etc). Rode com LIMITE_TESTE=3
primeiro, veja até onde ele consegue ir sozinho, e me mande o erro
exato que aparecer no terminal (a última linha, tipo
"playwright._impl._api_types.TimeoutError: ...") que eu ajusto.

SEGURANÇA: o e-mail e a senha são digitados na hora que você roda o
script (nunca ficam salvos no arquivo nem vão pro GitHub).
"""

import os
import re
import getpass
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

LOGIN_URL = "https://inspectos.com/sistema/index.html#/home"
PASTA_SCRIPT = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(PASTA_SCRIPT, "data", "laudos")
# Pasta onde o Chrome guarda a sessão/cookies de login entre uma execução
# e outra. NUNCA suba essa pasta pro GitHub (já está no .gitignore) -
# ela guarda o acesso logado à sua conta da Inspectos.
PERFIL_DIR = os.path.join(PASTA_SCRIPT, "chrome_profile_inspectos")

# Quantos laudos baixar nesta execução. Cada página da lista tem 30
# laudos, então 40 força passar da página 1 pra 2 e testa a paginação.
# Depois que estiver funcionando, aumente para 9999 para pegar tudo do
# período.
LIMITE_TESTE = 40


def extrair_numero_proposta(texto_linha):
    """Tenta achar o N° de Proposta dentro do texto de uma linha da tabela."""
    match = re.search(r'\b(\d{6,10})\b', texto_linha)
    return match.group(1) if match else None


def pedir_dado(pergunta):
    """Pede um dado ao usuário com um aviso visual bem claro."""
    print("\n" + "-" * 60)
    print(">>> PRECISO DE UMA INFORMAÇÃO SUA <<<")
    return input(f"{pergunta}: ").strip()


def pausar_para_usuario(*linhas_instrucao):
    """Pausa o robô e deixa bem claro que é a vez do usuário agir."""
    print("\n" + "#" * 60)
    print("#  A AÇÃO É SUA AGORA - O ROBÔ ESTÁ PAUSADO")
    print("#" * 60)
    for linha in linhas_instrucao:
        print(linha)
    input(">>> Quando terminar, clique aqui no terminal e pressione ENTER... ")
    print("#" * 60 + "\n")


def main():
    print("=" * 60)
    print(" ROBÔ DE DOWNLOAD - INSPECTOS")
    print("=" * 60)
    data_inicio = pedir_dado("Data inicial (dd/mm/aaaa)")
    data_fim = pedir_dado("Data final (dd/mm/aaaa)")
    email = pedir_dado("E-mail Inspectos")
    print("\n" + "-" * 60)
    print(">>> PRECISO DE UMA INFORMAÇÃO SUA <<<")
    senha = getpass.getpass("Senha Inspectos (não aparece na tela, é normal): ")

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    os.makedirs(PERFIL_DIR, exist_ok=True)

    with sync_playwright() as p:
        # headless=False = abre o Chrome de verdade na sua tela, pra
        # você acompanhar o robô clicando sozinho. NÃO mexa na janela
        # enquanto ele estiver rodando.
        # launch_persistent_context guarda a sessão em PERFIL_DIR: depois
        # da primeira vez que você confirmar o código de verificação (MFA)
        # manualmente, as próximas execuções não devem mais pedir isso.
        context = p.chromium.launch_persistent_context(
            PERFIL_DIR, headless=False, slow_mo=300, accept_downloads=True
        )
        page = context.new_page()

        try:
            # ----------------------------------------------------------------
            # 1. LOGIN
            # ----------------------------------------------------------------
            print("\n[1/6] Abrindo página de login...")
            page.goto(LOGIN_URL)
            page.wait_for_selector("input", timeout=15000)
            # O "E-mail"/"Senha" na tela é só texto ao lado do campo, não um
            # <label> ligado a ele - por isso localizamos pelo tipo/posição
            # do campo em vez do texto do rótulo.
            page.locator("input[type='password']").fill(senha)
            page.locator("input:not([type='password']):not([type='checkbox'])").first.fill(email)
            page.get_by_role("button", name=re.compile("entrar|login|acessar", re.IGNORECASE)).click()

            # ----------------------------------------------------------------
            # 2. PASSAR PELA TELA(S) PÓS-LOGIN (escolha de cliente / MFA)
            # ----------------------------------------------------------------
            # Ordem confirmada do site: a escolha do cliente (Santander)
            # sempre vem ANTES da verificação de segurança por e-mail (se
            # ela aparecer). A verificação só costuma pedir na primeira vez
            # com um perfil/sessão novo em PERFIL_DIR.
            print("[2/6] Aguardando tela pós-login...")

            def chegou_no_painel(timeout=8000):
                try:
                    page.wait_for_selector("text=GRID DE INSPEÇÃO", timeout=timeout)
                    return True
                except PlaywrightTimeout:
                    return False

            # Espera curta aqui (2s): na prática a escolha de cliente sempre
            # aparece, então não vale a pena esperar vários segundos por um
            # cenário raro (sessão pular direto pro painel) antes de agir.
            if chegou_no_painel(timeout=2000):
                print("      Já entrou direto no painel do Santander (sessão já confiável).")
            else:
                # Tela "Escolha o cliente desejado": 2 cartões lado a lado
                # (Itaú à esquerda, Santander à direita), com 2 links
                # "SELECIONAR" nessa mesma ordem. Pegamos o segundo.
                print("      Selecionando cliente Santander...")
                page.wait_for_selector("text=SELECIONAR", timeout=40000)
                page.get_by_text("SELECIONAR", exact=True).nth(1).click()

                # Espera a tela pós-login terminar de carregar de vez - pode
                # ser a verificação de segurança (MFA) ou já o painel
                # principal, dependendo da sessão. Esperamos por QUALQUER UM
                # dos dois (o que aparecer primeiro), com um tempo mais
                # generoso (30s) do que uma checagem rápida isolada.
                print("      Aguardando tela pós-login carregar...")
                try:
                    page.locator("text=VERIFICAÇÃO DE SEGURANÇA").or_(
                        page.locator("text=GRID DE INSPEÇÃO")
                    ).first.wait_for(timeout=30000)
                except PlaywrightTimeout:
                    pass  # nenhum dos dois apareceu a tempo - tratado abaixo

                # O robô não tem como ler o código do seu e-mail/SMS, então
                # a verificação de segurança (se apareceu) é manual.
                if page.locator("text=VERIFICAÇÃO DE SEGURANÇA").count() > 0:
                    pausar_para_usuario(
                        "A Inspectos pediu uma verificação de segurança (MFA).",
                        "1. Na janela do Chrome, escolha E-MAIL (ou SMS/App).",
                        "2. Digite o código que você receber e confirme.",
                        "3. Espere até estar de volta dentro do sistema.",
                    )

                if not chegou_no_painel(timeout=15000):
                    pausar_para_usuario(
                        "O robô ainda não conseguiu chegar no painel principal",
                        "(a tela com 'GRID DE INSPEÇÃO').",
                        "Complete manualmente o que estiver faltando na tela até",
                        "chegar lá.",
                    )

            # ----------------------------------------------------------------
            # 3. MENU -> ADMINISTRATIVO -> RELATÓRIOS -> INSPEÇÕES -> ANALÍTICO
            # ----------------------------------------------------------------
            print("[3/6] Navegando até Relatório Analítico...")
            page.wait_for_selector("text=GRID DE INSPEÇÃO", timeout=20000)
            # Botão de hambúrguer real (confirmado via Inspecionar elemento):
            # <button class="hamburger hamburger--collapse" ng-click="exibirMenu()">
            page.locator("button.hamburger").click()
            page.click("text=Administrativo")
            page.click("text=Relatórios")
            page.click("text=Inspeções")
            page.click("text=Analítico")

            # ----------------------------------------------------------------
            # 4. PREENCHER PERÍODO E CLICAR EM EXIBIR
            # ----------------------------------------------------------------
            print("[4/6] Preenchendo período e clicando em Exibir...")
            page.wait_for_selector("text=PERÍODO DE SOLICITAÇÃO DA INSPEÇÃO", timeout=15000)
            # A classe "insp360-filtro-data" NÃO é exclusiva desses 2 campos -
            # o painel FILTROS (recolhido) tem vários outros pares de data
            # (Agendamento, Limite, etc.) com essa mesma classe. Por isso
            # buscamos só os campos que vêm DEPOIS do texto "PERÍODO DE
            # SOLICITAÇÃO DA INSPEÇÃO" no HTML, ignorando o painel FILTROS.
            # Cada um abre um calendário pop-up ao ser clicado/preenchido,
            # por isso fechamos com Escape logo depois de preencher.
            titulo_periodo = page.locator("text=PERÍODO DE SOLICITAÇÃO DA INSPEÇÃO")
            campos_data = titulo_periodo.locator(
                "xpath=following::input[contains(@class,'insp360-filtro-data')]"
            )

            def preencher_data(campo, valor):
                # .fill() não convive bem com a máscara de data desse campo
                # (ui-date-mask) - por isso clicamos, selecionamos tudo que
                # já está escrito e digitamos por cima, tecla por tecla.
                campo.click()
                campo.press("Control+A")
                campo.type(valor, delay=50)
                page.keyboard.press("Escape")
                page.wait_for_timeout(300)

            preencher_data(campos_data.nth(0), data_inicio)
            preencher_data(campos_data.nth(1), data_fim)
            page.get_by_role("button", name="Exibir").click()

            # ----------------------------------------------------------------
            # 5. PERCORRER A LISTA DE LAUDOS (COM PAGINAÇÃO)
            # ----------------------------------------------------------------
            print("[5/6] Processando lista de laudos...")
            # Não é uma <table> HTML de verdade: cada linha de dado é uma
            # <div class="insp360-mouse-link insp360-tabela-relatorio insp360-cor-tabela-rel"
            #      ng-repeat="insp in listaInspecao">
            # (confirmado via Inspecionar elemento). As 3 classes juntas
            # evitam pegar a linha de cabeçalho por engano.
            LINHA_SELECTOR = "div.insp360-mouse-link.insp360-tabela-relatorio.insp360-cor-tabela-rel"
            page.wait_for_selector(LINHA_SELECTOR, timeout=20000)

            total_baixados = 0
            pagina_num = 1

            while total_baixados < LIMITE_TESTE:
                # Lemos o N° de Proposta e ID de TODAS as linhas da página
                # de uma vez, ANTES de abrir qualquer modal. Depois de abrir
                # e fechar um modal, a lista pode reorganizar seus elementos
                # internamente - por isso NÃO usamos mais a posição (1ª, 2ª,
                # 3ª linha...) pra reabrir cada laudo, e sim o N° de Proposta
                # (relocalizamos a linha certa pelo conteúdo, não pela posição).
                linhas = page.locator(LINHA_SELECTOR)
                qtd_linhas = linhas.count()
                print(f"  Página {pagina_num}: {qtd_linhas} laudos encontrados na tela.")

                laudos_da_pagina = []
                for i in range(qtd_linhas):
                    texto_linha = linhas.nth(i).inner_text()
                    numero_proposta = extrair_numero_proposta(texto_linha) or f"linha{i}"
                    laudo_id = texto_linha.split("\n")[0].strip()
                    laudos_da_pagina.append((numero_proposta, laudo_id))

                for numero_proposta, laudo_id in laudos_da_pagina:
                    if total_baixados >= LIMITE_TESTE:
                        break

                    destino = os.path.join(DOWNLOAD_DIR, f"laudo_{numero_proposta}.pdf")

                    # Se esse laudo já foi baixado numa execução anterior
                    # (o arquivo já existe em data/laudos), pula sem nem
                    # abrir a linha - economiza tempo em reprocessamentos.
                    if os.path.exists(destino):
                        print(f"    -> {laudo_id} (proposta {numero_proposta}) já baixado antes, pulando.")
                        continue

                    print(f"    -> Abrindo laudo {laudo_id} (proposta {numero_proposta})...")

                    # Cada laudo é tratado isoladamente: se algo der errado
                    # SÓ nesse item (sem laudo publicado ainda, travamento
                    # pontual, etc.), o robô registra, pula ESSE laudo e
                    # continua pro próximo - nunca para o lote inteiro por
                    # causa de um caso isolado.
                    try:
                        # Relocaliza a linha AGORA, pelo N° de Proposta (não
                        # por posição), pra pegar o estado atual da lista.
                        linha = page.locator(LINHA_SELECTOR, has_text=numero_proposta)
                        if linha.count() == 0:
                            print(f"       [PULADO] Não achei mais a linha de {laudo_id} na tela.")
                            continue
                        linha.first.click()
                        page.wait_for_selector("text=DETALHAR INSPEÇÃO", timeout=15000)
                        page.click("text=Laudos")

                        # Pode não existir nenhum laudo publicado ainda pra
                        # essa inspeção (ex: "Nenhum laudo encontrado até o
                        # momento"). Esperamos por QUALQUER UM dos dois sinais:
                        # um laudo de verdade (ícone de engrenagem) ou o aviso
                        # de que não tem nada.
                        icone_engrenagem = page.locator("i.fa-cog, i.fa-gear, .fa-cog")
                        aviso_sem_laudo = page.locator("text=Nenhum laudo encontrado")
                        icone_engrenagem.or_(aviso_sem_laudo).first.wait_for(timeout=15000)

                        if aviso_sem_laudo.count() > 0:
                            print(f"       [PULADO] Ainda não há laudo publicado para {laudo_id}.")
                        else:
                            icone_engrenagem.first.click()
                            page.click("text=Download")

                            page.wait_for_selector("text=DOWNLOAD DE LAUDO", timeout=15000)
                            page.click("text=Laudo Completo")

                            with page.expect_download(timeout=30000) as download_info:
                                page.get_by_role("button", name="Download").click()
                            download = download_info.value
                            download.save_as(destino)
                            print(f"       salvo em: {destino}")
                            total_baixados += 1

                    except PlaywrightTimeout as e:
                        print(f"       [PULADO - ERRO] Travou nesse laudo específico: {str(e).splitlines()[0]}")
                    except Exception as e:
                        print(f"       [PULADO - ERRO INESPERADO] {str(e)}")
                    finally:
                        # Sempre tenta fechar o modal e voltar pra lista, mesmo
                        # se algo deu errado acima, pra não travar os próximos.
                        try:
                            if page.locator(".modal.in").count() > 0:
                                page.locator("i.insp360-icone-fechar").first.click()
                                page.wait_for_selector(".modal.in", state="hidden", timeout=15000)
                        except Exception:
                            pass
                        page.wait_for_selector(LINHA_SELECTOR, timeout=15000)

                if total_baixados >= LIMITE_TESTE:
                    break

                # A tela tem 5 abas (Crédito PF, PJ, Garantias, Renegociação,
                # Renegociação CI) e CADA uma tem seu próprio botão "próxima"
                # no HTML ao mesmo tempo (só o da aba ativa fica visível) -
                # por isso filtramos só o visível, senão dá erro de "resolveu
                # pra vários elementos".
                botao_proxima = page.locator("a:visible", has_text="próxima")
                if botao_proxima.count() == 0:
                    print("  Não há mais páginas.")
                    break
                # AngularJS (ng-disabled) marca o link como indisponível
                # adicionando o atributo "disabled" quando não há próxima
                # página - ainda não testamos essa parte na última página
                # de verdade, então avise se ela não funcionar como esperado.
                if botao_proxima.get_attribute("disabled") is not None:
                    print("  Não há mais páginas.")
                    break
                botao_proxima.click()
                pagina_num += 1
                page.wait_for_selector(LINHA_SELECTOR, timeout=15000)

            print(f"\n[6/6] Concluído! {total_baixados} laudo(s) baixado(s) em {DOWNLOAD_DIR}")

        except PlaywrightTimeout as e:
            print("\n[ERRO] O robô travou esperando um elemento aparecer na tela.")
            print("Copie a mensagem abaixo e me envie, junto com o que estava")
            print("aparecendo na janela do Chrome nesse momento:")
            print(str(e))
        except Exception as e:
            print("\n[ERRO INESPERADO]")
            print(str(e))
        finally:
            print("\n" + "#" * 60)
            print("#  A AÇÃO É SUA AGORA - O ROBÔ ESTÁ PAUSADO")
            print("#" * 60)
            input(">>> Pressione ENTER aqui para fechar o navegador... ")
            context.close()


if __name__ == "__main__":
    main()

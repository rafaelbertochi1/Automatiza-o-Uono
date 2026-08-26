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

LOGIN: o robô guarda a sessão (cookies) num arquivo próprio depois de um
login bem-sucedido, e recarrega esse arquivo nas próximas execuções - não
pede e-mail/senha. Se a sessão expirar, ele pausa e pede pra você fazer
login manualmente na janela do Chrome, uma vez, e salva de novo.
"""

import os
import re
import sys
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

LOGIN_URL = "https://inspectos.com/sistema/index.html#/home"
PASTA_SCRIPT = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(PASTA_SCRIPT, "data", "laudos")
# Arquivo com os cookies/sessão salvos depois do último login bem-sucedido.
# NUNCA suba esse arquivo pro GitHub (já está no .gitignore) - ele guarda
# o acesso logado à sua conta da Inspectos. Usamos um arquivo próprio (em
# vez de só a pasta de perfil do Chrome) porque o cookie de login da
# Inspectos parece ser um "cookie de sessão", que o navegador descarta de
# propósito ao fechar normalmente - salvando/recarregando manualmente,
# contornamos isso.
SESSION_FILE = os.path.join(PASTA_SCRIPT, "sessao_inspectos.json")
# Cada execução salva um log completo aqui (também nunca vai pro GitHub).
LOG_DIR = os.path.join(PASTA_SCRIPT, "logs")

# Quantos laudos baixar nesta execução. Cada página da lista tem 30
# laudos, então 40 força passar da página 1 pra 2 e testa a paginação.
# Depois que estiver funcionando, aumente para 9999 para pegar tudo do
# período.
LIMITE_TESTE = 40

# True = remove a pausa artificial entre cada clique (bem mais rápido).
# A janela do Chrome continua visível mesmo com True - mantemos assim de
# propósito, porque se a verificação de segurança (MFA) pedir de novo no
# futuro, você precisa conseguir ver e responder na tela. Só considere
# rodar 100% escondido (headless) depois que o robô estiver rodando sem
# nenhum ajuste há um bom tempo.
MODO_RAPIDO = True


class Tee:
    """Escreve simultaneamente no terminal e num arquivo de log."""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, dado):
        for s in self.streams:
            s.write(dado)

    def flush(self):
        for s in self.streams:
            s.flush()


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
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)

    # Tudo que aparece no terminal a partir daqui também é salvo num
    # arquivo de log (um por execução), pra você ter um histórico do que
    # rodou, quando, e o que foi baixado/pulado/deu erro.
    log_path = os.path.join(LOG_DIR, f"execucao_{datetime.now():%Y%m%d_%H%M%S}.txt")
    log_file = open(log_path, "w", encoding="utf-8")
    stdout_original = sys.stdout
    sys.stdout = Tee(stdout_original, log_file)

    print("=" * 60)
    print(" ROBÔ DE DOWNLOAD - INSPECTOS")
    print("=" * 60)
    print(f"Log desta execução: {log_path}")
    data_inicio = pedir_dado("Data inicial (dd/mm/aaaa)")
    data_fim = pedir_dado("Data final (dd/mm/aaaa)")
    # O que você digita no input() não aparece sozinho no arquivo de log
    # (só o teclado ecoando na tela, não passa pelo print) - por isso
    # repetimos aqui, pra o log sempre mostrar qual período foi usado.
    print(f"Período usado: {data_inicio} até {data_fim}")

    with sync_playwright() as p:
        # A janela do Chrome fica sempre visível (headless=False) - de
        # propósito, pra você poder ver e responder se a verificação de
        # segurança (MFA) pedir de novo. MODO_RAPIDO só controla a pausa
        # artificial entre cliques (slow_mo).
        browser = p.chromium.launch(headless=False, slow_mo=0 if MODO_RAPIDO else 300)
        # Se já existe uma sessão salva de uma execução anterior, carrega
        # ela agora (cookies + localStorage), em vez de começar do zero.
        sessao_existente = os.path.exists(SESSION_FILE)
        context = browser.new_context(
            accept_downloads=True,
            storage_state=SESSION_FILE if sessao_existente else None,
        )
        page = context.new_page()

        def salvar_sessao():
            context.storage_state(path=SESSION_FILE)

        try:
            # ----------------------------------------------------------------
            # 1. USAR A SESSÃO JÁ SALVA (sem pedir e-mail/senha)
            # ----------------------------------------------------------------
            # SESSION_FILE guarda os cookies de login, cliente selecionado e
            # verificação de segurança confirmados numa execução anterior.
            # Vamos direto pra URL do painel, sem passar pela tela de login.
            print("\n[1/4] Verificando sessão salva...")

            def chegou_no_painel(timeout=8000):
                try:
                    page.wait_for_selector("text=GRID DE INSPEÇÃO", timeout=timeout)
                    return True
                except PlaywrightTimeout:
                    return False

            page.goto(LOGIN_URL)
            if sessao_existente and chegou_no_painel(timeout=10000):
                print("      Sessão válida, painel carregado direto.")
            else:
                # A sessão salva expirou, foi limpa, nunca existiu, ou pediu
                # verificação de novo. Como o robô não tem como digitar
                # e-mail/senha nem ler um código de segurança, esse trecho é
                # sempre manual.
                pausar_para_usuario(
                    "A sessão salva não está mais válida (ou pediu login/",
                    "verificação de novo).",
                    "1. Faça o login manualmente na janela do Chrome (e-mail e senha).",
                    "2. Selecione o cliente Santander, se for pedido.",
                    "3. Complete a verificação de segurança, se pedir.",
                    "4. Espere até ver a tela com 'GRID DE INSPEÇÃO'.",
                )
                if not chegou_no_painel(timeout=10000):
                    print("\n[ERRO] Ainda não consegui ver o painel principal (GRID DE INSPEÇÃO).")
                    print("Encerrando esta execução.")
                    return
                # Login (re)feito com sucesso - salva a sessão agora pra não
                # precisar repetir esse passo manual da próxima vez.
                salvar_sessao()
                print("      Sessão salva para as próximas execuções.")

            # ----------------------------------------------------------------
            # 2. MENU -> ADMINISTRATIVO -> RELATÓRIOS -> INSPEÇÕES -> ANALÍTICO
            # ----------------------------------------------------------------
            print("[2/4] Navegando até Relatório Analítico...")
            page.wait_for_selector("text=GRID DE INSPEÇÃO", timeout=20000)
            # Botão de hambúrguer real (confirmado via Inspecionar elemento):
            # <button class="hamburger hamburger--collapse" ng-click="exibirMenu()">
            page.locator("button.hamburger").click()
            page.click("text=Administrativo")
            page.click("text=Relatórios")
            page.click("text=Inspeções")
            page.click("text=Analítico")

            # ----------------------------------------------------------------
            # 3. PREENCHER PERÍODO E CLICAR EM EXIBIR
            # ----------------------------------------------------------------
            print("[3/4] Preenchendo período e clicando em Exibir...")
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
            # 4. PERCORRER A LISTA DE LAUDOS (COM PAGINAÇÃO)
            # ----------------------------------------------------------------
            print("[4/4] Processando lista de laudos...")
            # Não é uma <table> HTML de verdade: cada linha de dado é uma
            # <div class="insp360-mouse-link insp360-tabela-relatorio insp360-cor-tabela-rel"
            #      ng-repeat="insp in listaInspecao">
            # (confirmado via Inspecionar elemento). As 3 classes juntas
            # evitam pegar a linha de cabeçalho por engano.
            LINHA_SELECTOR = "div.insp360-mouse-link.insp360-tabela-relatorio.insp360-cor-tabela-rel"
            page.wait_for_selector(LINHA_SELECTOR, timeout=20000)

            total_baixados = 0
            total_pulados_existentes = 0
            total_sem_laudo = 0
            total_erros = 0
            pagina_num = 1

            while total_baixados < LIMITE_TESTE:
                # Lemos o código (ID) de TODAS as linhas da página de uma vez,
                # ANTES de abrir qualquer modal. Depois de abrir e fechar um
                # modal, a lista pode reorganizar seus elementos internamente
                # - por isso NÃO usamos a posição (1ª, 2ª, 3ª linha...) pra
                # reabrir cada laudo, e sim o código do laudo (TAT/TAN/TAP...),
                # que é o único identificador que nunca se repete (N° de
                # Proposta PODE se repetir legitimamente entre laudos
                # diferentes, então não pode ser usado pra identificar a linha
                # nem pra nomear o arquivo).
                linhas = page.locator(LINHA_SELECTOR)
                qtd_linhas = linhas.count()

                # A mesma linha aparece duplicada várias vezes no HTML dessa
                # tela (provavelmente uma versão escondida por responsividade,
                # igual achamos com o botão "próxima"). Por isso removemos
                # duplicatas pelo código do laudo antes de processar, senão o
                # mesmo laudo é reaberto várias vezes à toa na mesma página.
                laudos_da_pagina = []
                codigos_vistos = set()
                for i in range(qtd_linhas):
                    texto_linha = linhas.nth(i).inner_text()
                    laudo_id = texto_linha.split("\n")[0].strip()
                    # As cópias duplicadas dessa linha no HTML vêm com o
                    # código em branco (provavelmente uma variante de layout
                    # responsivo que esconde essa coluna) - sem código de
                    # verdade não dá pra identificar nem reabrir a linha
                    # depois, então só descartamos, sem tratar como erro.
                    if not laudo_id:
                        continue
                    if laudo_id in codigos_vistos:
                        continue
                    codigos_vistos.add(laudo_id)
                    numero_proposta = extrair_numero_proposta(texto_linha) or ""
                    laudos_da_pagina.append((numero_proposta, laudo_id))

                print(f"  Página {pagina_num}: {len(laudos_da_pagina)} laudos únicos encontrados na tela.")

                for numero_proposta, laudo_id in laudos_da_pagina:
                    if total_baixados >= LIMITE_TESTE:
                        break

                    destino = os.path.join(DOWNLOAD_DIR, f"laudo_{laudo_id}.pdf")

                    # Se esse laudo já foi baixado numa execução anterior
                    # (o arquivo já existe em data/laudos), pula sem nem
                    # abrir a linha - economiza tempo em reprocessamentos.
                    if os.path.exists(destino):
                        print(f"    -> {laudo_id} (proposta {numero_proposta}) já baixado antes, pulando.")
                        total_pulados_existentes += 1
                        continue

                    print(f"    -> Abrindo laudo {laudo_id} (proposta {numero_proposta})...")

                    # Cada laudo é tratado isoladamente: se algo der errado
                    # SÓ nesse item (sem laudo publicado ainda, travamento
                    # pontual, etc.), o robô registra, pula ESSE laudo e
                    # continua pro próximo - nunca para o lote inteiro por
                    # causa de um caso isolado.
                    try:
                        # Relocaliza a linha AGORA, pelo código do laudo (não
                        # por posição nem por N° de Proposta, que pode repetir).
                        linha = page.locator(LINHA_SELECTOR, has_text=laudo_id)
                        if linha.count() == 0:
                            print(f"       [PULADO] Não achei mais a linha de {laudo_id} na tela.")
                            total_erros += 1
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
                            total_sem_laudo += 1
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
                        total_erros += 1
                    except Exception as e:
                        print(f"       [PULADO - ERRO INESPERADO] {str(e)}")
                        total_erros += 1
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

            print("\nConcluído!")
            print("-" * 60)
            print(f"  Baixados agora:            {total_baixados}")
            print(f"  Já existiam (pulados):     {total_pulados_existentes}")
            print(f"  Sem laudo publicado ainda: {total_sem_laudo}")
            print(f"  Com erro (pulados):        {total_erros}")
            print(f"  Pasta: {DOWNLOAD_DIR}")
            print("-" * 60)

        except PlaywrightTimeout as e:
            print("\n[ERRO] O robô travou esperando um elemento aparecer na tela.")
            print("Copie a mensagem abaixo e me envie, junto com o que estava")
            print("aparecendo na janela do Chrome nesse momento:")
            print(str(e))
        except Exception as e:
            print("\n[ERRO INESPERADO]")
            print(str(e))
        finally:
            # Salva a sessão de novo antes de fechar (cobre o caso da
            # sessão que já estava valida desde o início) - se o navegador
            # já quebrou por causa de um erro, ignora, não tem sessão pra
            # salvar mesmo.
            try:
                salvar_sessao()
            except Exception:
                pass
            print("\n" + "#" * 60)
            print("#  A AÇÃO É SUA AGORA - O ROBÔ ESTÁ PAUSADO")
            print("#" * 60)
            input(">>> Pressione ENTER aqui para fechar o navegador... ")
            browser.close()
            sys.stdout = stdout_original
            log_file.close()


if __name__ == "__main__":
    main()

import os
import re
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed
import pdfplumber
import psycopg2
from psycopg2.extras import execute_values

# ----------------------------------------------------------------------
# 1. FUNÇÕES AUXILIARES DE TRATAMENTO DE DADOS
# ----------------------------------------------------------------------
def converter_float_seguro(val):
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return round(float(val), 2)

    s_val = str(val).strip()
    if not s_val or s_val.upper() in ['-', '--', '—', 'NONE', 'NULL']:
        return 0.0

    match = re.search(r'[-+]?[\d\.,]+', s_val)
    if not match:
        return 0.0

    num_str = match.group(0)

    if '.' in num_str and ',' in num_str:
        num_str = num_str.replace('.', '').replace(',', '.')
    elif '.' in num_str and ',' not in num_str:
        partes = num_str.split('.')
        if len(partes) == 2 and len(partes[1]) == 3:
            num_str = num_str.replace('.', '')
        elif len(partes) > 2:
            num_str = num_str.replace('.', '')
    elif ',' in num_str:
        num_str = num_str.replace(',', '.')

    try:
        return round(float(num_str), 2)
    except Exception:
        return 0.0

def converter_int_seguro(val):
    try:
        return int(converter_float_seguro(val))
    except Exception:
        return 0

def converter_float_coordenada(val):
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)

    s_val = str(val).strip()
    if not s_val or s_val.upper() in ['-', '--', '—', 'NONE', 'NULL']:
        return None

    s_val = re.sub(r'-\s+', '-', s_val)
    match = re.search(r'[-+]?\d+\.\d+', s_val)
    if not match:
        return None

    try:
        return float(match.group(0))
    except Exception:
        return None

def limpar_txt(val, valor_padrao=""):
    if not val:
        return valor_padrao
    txt = str(val).strip()
    txt = re.sub(r'^(Número|Complemento|Matrícula|Núm|Bairro|Municipio|UF|Endere[çc]o)\s*', '', txt, flags=re.IGNORECASE)
    txt = str(txt).strip()
    return txt if txt and txt.upper() != "NULL" else valor_padrao

# ----------------------------------------------------------------------
# 1.1 EXTRAÇÃO DE COORDENADAS
# ----------------------------------------------------------------------
def extrair_coordenadas_generico(text):
    texto_limpo = re.sub(r'-\s+([\d\.]+)', r'-\1', text)
    match_rotulo = re.search(
        r'(?:Coordenadas|Localização|Geolocalização)[^\n:]*[:\n]?\s*([-\d\.\s,\n]+)',
        texto_limpo,
        re.IGNORECASE
    )
    texto_busca = match_rotulo.group(1) if match_rotulo else texto_limpo
    candidatos = re.findall(r'(-?\d{1,3}\.\d{4,16})', texto_busca)

    if len(candidatos) >= 2:
        lat_raw = converter_float_coordenada(candidatos[0])
        lon_raw = converter_float_coordenada(candidatos[1])
        if lat_raw is not None and lon_raw is not None:
            lat_final = -abs(lat_raw)
            lon_final = -abs(lon_raw)
            return f"{lat_final}, {lon_final}", lat_final, lon_final

    candidatos_full = re.findall(r'(-?\d{1,3}\.\d{4,16})', texto_limpo)
    if len(candidatos_full) >= 2:
        lat_raw = converter_float_coordenada(candidatos_full[0])
        lon_raw = converter_float_coordenada(candidatos_full[1])
        if lat_raw is not None and lon_raw is not None:
            lat_final = -abs(lat_raw)
            lon_final = -abs(lon_raw)
            return f"{lat_final}, {lon_final}", lat_final, lon_final

    return None, None, None

# ----------------------------------------------------------------------
# 1.2 ENDEREÇO E COMPLEMENTO
# ----------------------------------------------------------------------
_TIPOS_LOGRADOURO = (
    r'RUA|AVENIDA|AV\.|AL\.|ALAMEDA|ESTRADA|TRAVESSA|ROD\.|RODOVIA|'
    r'LARGO|PRA[ÇC]A|VIA|QUADRA'
)

def extrair_endereco_numero(text):
    direto = re.search(rf'(?:{_TIPOS_LOGRADOURO})\s+[^\n\r]+', text, re.IGNORECASE)
    if direto:
        trecho = direto.group(0).strip()
        m = re.match(
            rf'^((?:{_TIPOS_LOGRADOURO})\s+[^\d\n]+?)\s+(\d{{1,5}}|S/N)\b',
            trecho, re.IGNORECASE
        )
        if m:
            return m.group(1).strip(), m.group(2)
        return trecho, "S/N"
    return "", "S/N"

def extrair_complemento_generico(text):
    if not text:
        return ""
    
    match_rotulo = re.search(r'Complemento\s*[\n\r:]+\s*([^\n]+)', text, re.IGNORECASE)
    txt_busca = match_rotulo.group(1).strip() if match_rotulo else text

    pat_complemento = (
        r'(?:AP|APTO|APARTAMENTO|FLAT|BL|BL-?\d*|BLOCO|TORRE|CASA|SOBRADO|'
        r'LOTE|QUADRA|UNIDADE|SL|SALA|CONDOM[ÍI]NIO).*$'
    )

    match_compl = re.search(pat_complemento, txt_busca, re.IGNORECASE)
    if match_compl:
        return limpar_txt(match_compl.group(0))

    pat_corte_logradouro = (
        rf'^(?:{_TIPOS_LOGRADOURO})\s+.+?\s+(\d{{1,5}}|S/N)\b\s*[:,-]?\s*'
    )
    txt_sem_logradouro = re.sub(pat_corte_logradouro, '', txt_busca, flags=re.IGNORECASE).strip()

    if txt_sem_logradouro and txt_sem_logradouro != txt_busca:
        return limpar_txt(txt_sem_logradouro)

    return ""

# ----------------------------------------------------------------------
# 2. PARSER MODELO DIGITAL (AVM)
# ----------------------------------------------------------------------
def extrair_modelo_digital(text):
    cod_laudo = re.search(r'#(TA[NOP]\d+|\w+\d+)', text)
    num_prop_match = re.search(r'(?:Proposta|N[º°]?\s*da\s*Proposta)\s*[:\n]?\s*(\d{6,12})', text, re.IGNORECASE) or \
                     re.search(r'\b(\d{7,10})\b', text)
    num_proposta_val = num_prop_match.group(1) if num_prop_match else ""

    data_aval = re.search(r'(\d{2}/\d{2}/\d{4})', text)
    
    endereco_val, num_val_fallback = extrair_endereco_numero(text)
    
    num_busca = re.search(r'N[úu]mero\s*[\n\r]+\s*([0-9a-zA-Z/]+)', text, re.IGNORECASE)
    num_val = num_busca.group(1).strip() if num_busca else num_val_fallback

    compl_val = extrair_complemento_generico(text)

    tipo_imovel = re.search(r'\b(Apartamento\s*Tipo|Apartamento|Casa|Sobrado|Terreno(?:\s*-\s*Lote)?)\b', text, re.IGNORECASE)
    tipo_imovel_val = tipo_imovel.group(1).strip() if tipo_imovel else "Apartamento"

    area_priv_match = re.search(r'(?:[Áá]rea\s+privativa[^\d]*|privativa[^\d]*)(\d{1,5}[,\.]?\d{0,2})', text, re.IGNORECASE)
    area_com_match = re.search(r'(?:[Áá]rea\s+comum[^\d]*|comum[^\d]*)(\d{1,5}[,\.]?\d{0,2})', text, re.IGNORECASE)

    area_priv = converter_float_seguro(area_priv_match.group(1) if area_priv_match else None)
    area_comum = converter_float_seguro(area_com_match.group(1) if area_com_match else None)
    area_total = round(float(area_priv + area_comum), 2) if area_priv > 0 else 0.0

    banheiros = re.search(r'Banheiro\s*Social:\s*(\d+)', text, re.IGNORECASE) or re.search(r'(\d+)\s*(?=banheiro)', text, re.IGNORECASE)
    quartos = re.search(r'Dormitóri[oa]s?:\s*(\d+)', text, re.IGNORECASE) or re.search(r'(\d+)\s*(?=quarto|dormit)', text, re.IGNORECASE)
    suites_match = re.search(r'(?:su[íi]te|semi\s*su[íi]te)[^\d]*(\d+)', text, re.IGNORECASE)
    
    vagas_match = re.search(r'Vagas?:\s*(\d+)', text, re.IGNORECASE) or re.search(r'(\d+)\s*(?=vaga)', text, re.IGNORECASE)
    vagas_val = converter_int_seguro(vagas_match.group(1) if vagas_match else 0)

    idade = re.search(r'(\d+)\s*anos', text, re.IGNORECASE)

    padrao_val = None
    termos_invalidos = ['imóvel', 'imovel', 'condomínio', 'condominio', 'de', 'do', 'da']
    matches_padrao = re.findall(r'Padr[ãa]o\s+(?:de\s+)?Acabamento\s*[\n\r]+\s*([A-Za-zÀ-ÿ\s/]+)', text, re.IGNORECASE)
    for m in matches_padrao:
        candidato = m.strip()
        if candidato.lower() not in termos_invalidos and len(candidato) > 1:
            padrao_val = candidato
            break

    if not padrao_val:
        busca_termo = re.search(r'\b(M[ée]dio|Alto|Baixo|Simples|Normal|Superior|Luxo|Standard)\b', text, re.IGNORECASE)
        if busca_termo:
            padrao_val = busca_termo.group(1).strip()

    estado_val = None
    estado_match = re.search(r'Estado\s+de\s+Conserva[çc][ãa]o[^\n:]*[:\n]?\s*([^\n]+)', text, re.IGNORECASE)
    if estado_match:
        bruto = estado_match.group(1).strip()
        limpo = re.sub(r'\s+\d+(\s+\d+)*$', '', bruto).strip()
        estado_val = limpo if limpo else bruto
    if not estado_val:
        busca_est = re.search(r'\b(Bom|Nova\s*\(até\s*5\s*anos\)|Nova\|Regular|Regular|Ótimo|Ruim)\b', text, re.IGNORECASE)
        if busca_est:
            estado_val = busca_est.group(1).strip()

    val_mercado_val = None
    val_venda_f_val = None
    val_unit_val = None

    val_mercado_match = re.search(r'VALOR\s+DE\s+MERCADO[^\d]*?R\$\s*([\d\.,]+)', text, re.IGNORECASE) or re.search(r'R\$\s*([\d\.,]+)', text)
    if val_mercado_match:
        val_mercado_val = val_mercado_match.group(1)

    val_venda_f_match = re.search(r'VENDA\s+FOR[ÇC]ADA[^\d]*?R\$\s*([\d\.,]+)', text, re.IGNORECASE)
    if val_venda_f_match:
        val_venda_f_val = val_venda_f_match.group(1)

    if "casa" in tipo_imovel_val.lower() or "sobrado" in tipo_imovel_val.lower() or "DETALHAMENTO DOS VALORES" in text:
        match_casa_averbada = re.search(
            r'Área\s+constru[íi]da\s+averbada[^\n]*?\n?[^\n]*?R\$\s*([\d\.,]+)', 
            text, re.IGNORECASE | re.DOTALL
        )
        if match_casa_averbada:
            val_unit_val = match_casa_averbada.group(1)

    if not val_unit_val:
        match_gen = re.search(r'UNIT[ÁA]RIO[^\d\n]*R\$\s*([\d\.,]+)', text, re.IGNORECASE)
        if match_gen:
            val_unit_val = match_gen.group(1)

    coords_str, lat, lon = extrair_coordenadas_generico(text)

    return {
        "numero_proposta": num_proposta_val,
        "codigo_laudo": cod_laudo.group(1) if cod_laudo else None,
        "data_avaliacao": data_aval.group(1) if data_aval else None,
        "endereco": limpar_txt(endereco_val),
        "numero": limpar_txt(num_val, valor_padrao="S/N"),
        "complemento": compl_val,
        "tipo_imovel": tipo_imovel_val,
        "area_privativa_m2": area_priv,
        "area_comum_m2": area_comum,
        "area_total_m2": area_total,
        "quartos": converter_int_seguro(quartos.group(1) if quartos else 0),
        "suites": converter_int_seguro(suites_match.group(1) if suites_match else 0),
        "banheiros": converter_int_seguro(banheiros.group(1) if banheiros else 0),
        "vagas": vagas_val,
        "idade_anos": converter_int_seguro(idade.group(1) if idade else 0),
        "padrao_acabamento": padrao_val or "Normal",
        "estado_conservacao": estado_val or "Bom",
        "valor_mercado": converter_float_seguro(val_mercado_val),
        "valor_venda_forcada": converter_float_seguro(val_venda_f_val),
        "valor_unitario_m2": converter_float_seguro(val_unit_val),
        "coordenadas": coords_str,
        "latitude": lat,
        "longitude": lon
    }

# ----------------------------------------------------------------------
# 3. PARSER MODELO FÍSICO (QUESTIONÁRIO / PRESENCIAL)
# ----------------------------------------------------------------------
def extrair_modelo_fisico(text):
    cod_laudo = re.search(r'#(TAP\d+|\w+\d+)', text)
    num_proposta = re.search(r'(?:Proposta|N[º°]?\s*da\s*Proposta)\s*[:\n]?\s*(\d{6,12})', text, re.IGNORECASE) or \
                   re.search(r'\b(\d{7,10})\b', text)

    num_proposta_val = num_proposta.group(1) if num_proposta else ""
    data_aval = re.search(r'(\d{2}/\d{2}/\d{4})', text)

    endereco_bruto, num_val = extrair_endereco_numero(text)
    compl_val = extrair_complemento_generico(text)

    tipo_imovel = re.search(r'\b(Apartamento|Casa|Sobrado|Terreno(?:\s*-\s*Lote)?)\b', text, re.IGNORECASE)
    tipo_imovel_val = tipo_imovel.group(1) if tipo_imovel else "Apartamento"

    # ------------------------------------------------------------------
    # CAPTURA ISOLADA DE ÁREAS (SEÇÕES 18 E 19)
    # ------------------------------------------------------------------
    area_priv = 0.0
    match_18 = re.search(r'18\s*-\s*[ÁA]rea\s+Privativa[^\n]*\n+([^\n]+)', text, re.IGNORECASE)
    if match_18:
        linha_18 = match_18.group(1).strip()
        # O valor fica no fim da linha (ex.: "Ferro 208,13"), não no início
        val_m = re.search(r'([\d\.,]+)\s*$', linha_18)
        if val_m:
            area_priv = converter_float_seguro(val_m.group(1))

    area_comum = 0.0
    match_19 = re.search(r'19\s*-\s*[ÁA]rea\s+Comum[^\n]*\n+([^\n]+)', text, re.IGNORECASE)
    if match_19:
        linha_19 = match_19.group(1).strip()
        val_m = re.search(r'^\s*([\d\.,]+)', linha_19)
        if val_m and not re.search(r'20\s*-', linha_19):
            area_comum = converter_float_seguro(val_m.group(1))

    # Fallback para Terrenos / Casas se Privativa for 0
    if area_priv == 0.0 and ("casa" in tipo_imovel_val.lower() or "terreno" in tipo_imovel_val.lower()):
        match_terreno = re.search(
            r'(?:[Áá]rea\s+do\s+terreno|[Áá]rea\s+constru[íi]da)[^\d]*([\d\.,]+)', 
            text, re.IGNORECASE
        )
        if match_terreno:
            area_priv = converter_float_seguro(match_terreno.group(1))

    # Área total calculada de forma exata
    area_total = round(float(area_priv + area_comum), 2)

    # Banheiros (seção 11) e Dormitórios (seção 12) ficam lado a lado na mesma
    # linha de valores ("<banheiros> <dormitórios>"), então precisam ser lidos
    # de uma vez só — buscar cada rótulo separadamente faz os dois pegarem o
    # primeiro número da linha (duplicando o valor de banheiros em dormitórios).
    banheiros_val = 0
    quartos = None
    match_11_12 = re.search(
        r'11\s*-\s*N[°º]?\s*de\s*Banheiros[^\n]*\n+(\d+)\s+(\d+)',
        text, re.IGNORECASE
    )
    if match_11_12:
        banheiros_val = converter_int_seguro(match_11_12.group(1))
        quartos = match_11_12.group(2)

    # Mesmo problema em Vagas Cobertas (seção 13) e Vagas Descobertas (seção 14)
    vagas_val = 0
    v13 = 0
    v14 = 0
    m_vagas_13_14 = re.search(
        r'13\s*-\s*N[°º]?\s*de\s*Vagas\s+Cobertas[^\n]*\n+(\d+)\s+(\d+)',
        text, re.IGNORECASE
    )
    if m_vagas_13_14:
        v13 = converter_int_seguro(m_vagas_13_14.group(1))
        v14 = converter_int_seguro(m_vagas_13_14.group(2))

    m_vagas_15 = re.search(r'15\s*-\s*N[°º]?\s*de\s*Vagas\s+Privativas[^\n]*\n+([0-9]+)', text, re.IGNORECASE)
    v15 = converter_int_seguro(m_vagas_15.group(1)) if m_vagas_15 else 0

    if v13 > 0:
        vagas_val = v13
    elif v14 > 0:
        vagas_val = v14
    elif v15 > 0:
        vagas_val = v15

    idade_val = 0
    match_idade = re.search(r'04\s*-\s*Idade\s+Aparente[^\n]*.*?\b([0-9]+)\b', text, re.IGNORECASE | re.DOTALL)
    if match_idade:
        idade_val = converter_int_seguro(match_idade.group(1))

    suite_exata = re.search(r'^\s*suite\s+(\d+)', text, re.IGNORECASE | re.MULTILINE) or re.search(r'\bsuite\b.*?\b(\d+)\b', text, re.IGNORECASE)
    total_suites = converter_int_seguro(suite_exata.group(1) if suite_exata else 0)

    estado_cons = None
    match_est = re.search(r'06\s*-\s*Estado\s+de\s+Conserva[çc][ãa]o[^\n]*\n+([A-Za-zÀ-ÿ\s]+)', text, re.IGNORECASE)
    if match_est:
        val = match_est.group(1).strip()
        if val.lower() not in ['do', 'imóvel', 'imovel', 'de']:
            estado_cons = re.sub(r'\s+\d+(\s+\d+)*$', '', val).strip()

    padrao_acab = None
    match_pad = re.search(r'07\s*-\s*Padr[ãa]o\s+de\s+Acabamento[^\n]*\n+([A-Za-zÀ-ÿ\s/]+)', text, re.IGNORECASE)
    if match_pad:
        val = match_pad.group(1).strip()
        val_limpo = re.sub(r'\b(Residencial|Comercial|Industrial)\b', '', val, flags=re.IGNORECASE).strip()
        palavras = [p for p in val_limpo.split() if p.lower() not in ['do', 'imóvel', 'imovel', 'de']]
        padrao_acab = palavras[0] if palavras else None

    val_mercado_val = None
    val_venda_f_val = None
    val_unit_val = None

    val_mercado_match = re.search(r'VALOR\s+DE\s+MERCADO.*?R\$\s*([\d\.,]+)', text, re.IGNORECASE | re.DOTALL)
    if val_mercado_match:
        val_mercado_val = val_mercado_match.group(1)

    val_venda_f_match = re.search(r'VALOR\s+DE\s+VENDA\s+FOR[ÇC]ADA.*?R\$\s*([\d\.,]+)', text, re.IGNORECASE | re.DOTALL)
    if val_venda_f_match:
        val_venda_f_val = val_venda_f_match.group(1)

    if "casa" in tipo_imovel_val.lower() or "sobrado" in tipo_imovel_val.lower() or "DETALHAMENTO DOS VALORES" in text:
        match_casa_averbada = re.search(
            r'Área\s+constru[íi]da\s+averbada[^\n]*?\n?[^\n]*?R\$\s*([\d\.,]+)', 
            text, re.IGNORECASE | re.DOTALL
        )
        if match_casa_averbada:
            val_unit_val = match_casa_averbada.group(1)

    if not val_unit_val:
        val_unit_match = re.search(r'VALOR\s+UNIT[ÁA]RIO.*?R\$\s*([\d\.,]+)', text, re.IGNORECASE | re.DOTALL)
        if val_unit_match:
            val_unit_val = val_unit_match.group(1)

    coords_str, lat, lon = extrair_coordenadas_generico(text)

    return {
        "numero_proposta": num_proposta_val,
        "codigo_laudo": cod_laudo.group(1) if cod_laudo else None,
        "data_avaliacao": data_aval.group(1) if data_aval else None,
        "endereco": limpar_txt(endereco_bruto),
        "numero": num_val,
        "complemento": compl_val,
        "tipo_imovel": tipo_imovel_val,
        "area_privativa_m2": area_priv,
        "area_comum_m2": area_comum,
        "area_total_m2": area_total,
        "quartos": converter_int_seguro(quartos if quartos else 0),
        "suites": total_suites,
        "banheiros": banheiros_val,
        "vagas": vagas_val,
        "idade_anos": idade_val,
        "padrao_acabamento": padrao_acab or "Normal",
        "estado_conservacao": estado_cons or "Bom",
        "valor_mercado": converter_float_seguro(val_mercado_val),
        "valor_venda_forcada": converter_float_seguro(val_venda_f_val),
        "valor_unitario_m2": converter_float_seguro(val_unit_val),
        "coordenadas": coords_str,
        "latitude": lat,
        "longitude": lon
    }

# ----------------------------------------------------------------------
# 4. WORKER DE EXTRAÇÃO
# ----------------------------------------------------------------------
def extrair_dados_pdf(pdf_path):
    try:
        file_name = os.path.basename(pdf_path)
        with pdfplumber.open(pdf_path) as pdf:
            full_text = ""
            for page in pdf.pages:
                full_text += (page.extract_text() or "") + "\n"

            if not full_text.strip():
                return None

            if "Comparativo direto" in full_text or "QUESTIONARIO" in full_text or "QUESTIONÁRIO" in full_text:
                dados = extrair_modelo_fisico(full_text)
                dados["modelo_usado"] = "fisico"
            else:
                dados = extrair_modelo_digital(full_text)
                dados["modelo_usado"] = "digital"

            dados["path"] = file_name
            return dados
    except Exception as e:
        print(f"[ERRO PARSER] {os.path.basename(pdf_path)}: {str(e)}")
        return None

# ----------------------------------------------------------------------
# 5. ORQUESTRADOR EM LOTE (MULTITHREAD + UPSERT BANCO)
# ----------------------------------------------------------------------
def processar_em_lote():
    folder_path = r"data/laudos"
    if not os.path.exists(folder_path):
        folder_path = "."

    pdf_files = [os.path.join(folder_path, f) for f in os.listdir(folder_path) if f.endswith('.pdf')]
    print(f"Total de PDFs encontrados: {len(pdf_files)}")

    if not pdf_files:
        return

    num_workers = min(multiprocessing.cpu_count(), 8)
    dados_extraidos = []

    print(f"Iniciando extração paralela em {num_workers} workers...")
    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = {executor.submit(extrair_dados_pdf, f): f for f in pdf_files}
        for future in as_completed(futures):
            res_laudo = future.result()
            if res_laudo:
                dados_extraidos.append(res_laudo)

    print(f"Extração concluída. Total laudos: {len(dados_extraidos)}")
    if not dados_extraidos:
        return

    host_pg = os.getenv("PGURL", "127.0.0.1")
    dbname = os.getenv("PGNAME", "testdb")
    user = os.getenv("PGUSR", "postgres")
    password = os.getenv("PGPASS", "postgres")
    port = os.getenv("PGPORT", "5432")

    colunas = list(dados_extraidos[0].keys())
    # "Duplicata" = mesmo N° de Proposta (numero_proposta), não mesmo nome
    # de arquivo. Assim, baixar/reprocessar o mesmo laudo em datas ou
    # arquivos diferentes atualiza a linha existente em vez de criar outra.
    # A condição "WHERE numero_proposta <> ''" evita que dois laudos cujo
    # número não foi identificado (campo vazio) se sobrescrevam por engano.
    query_upsert_laudos = f"""
        INSERT INTO laudos ({', '.join(colunas)})
        VALUES %s
        ON CONFLICT (numero_proposta) WHERE numero_proposta <> '' DO UPDATE SET
            codigo_laudo = EXCLUDED.codigo_laudo,
            data_avaliacao = EXCLUDED.data_avaliacao,
            endereco = EXCLUDED.endereco,
            numero = EXCLUDED.numero,
            complemento = EXCLUDED.complemento,
            tipo_imovel = EXCLUDED.tipo_imovel,
            area_privativa_m2 = EXCLUDED.area_privativa_m2,
            area_comum_m2 = EXCLUDED.area_comum_m2,
            area_total_m2 = EXCLUDED.area_total_m2,
            quartos = EXCLUDED.quartos,
            suites = EXCLUDED.suites,
            banheiros = EXCLUDED.banheiros,
            vagas = EXCLUDED.vagas,
            idade_anos = EXCLUDED.idade_anos,
            padrao_acabamento = EXCLUDED.padrao_acabamento,
            estado_conservacao = EXCLUDED.estado_conservacao,
            valor_mercado = EXCLUDED.valor_mercado,
            valor_venda_forcada = EXCLUDED.valor_venda_forcada,
            valor_unitario_m2 = EXCLUDED.valor_unitario_m2,
            coordenadas = EXCLUDED.coordenadas,
            latitude = EXCLUDED.latitude,
            longitude = EXCLUDED.longitude,
            path = EXCLUDED.path,
            modelo_usado = EXCLUDED.modelo_usado;
    """

    valores_laudos = [[d[col] for col in colunas] for d in dados_extraidos]

    try:
        with psycopg2.connect(host=host_pg, dbname=dbname, user=user, password=password, port=port) as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS laudos (
                        id SERIAL PRIMARY KEY,
                        numero_proposta TEXT,
                        codigo_laudo TEXT,
                        data_avaliacao TEXT,
                        endereco TEXT,
                        numero TEXT,
                        complemento TEXT,
                        tipo_imovel TEXT,
                        area_privativa_m2 NUMERIC,
                        area_comum_m2 NUMERIC,
                        area_total_m2 NUMERIC,
                        quartos INTEGER,
                        suites INTEGER,
                        banheiros INTEGER,
                        vagas INTEGER,
                        idade_anos INTEGER,
                        padrao_acabamento TEXT,
                        estado_conservacao TEXT,
                        valor_mercado NUMERIC,
                        valor_venda_forcada NUMERIC,
                        valor_unitario_m2 NUMERIC,
                        coordenadas TEXT,
                        latitude DOUBLE PRECISION,
                        longitude DOUBLE PRECISION,
                        path TEXT,
                        modelo_usado TEXT
                    );
                """)
                # Se a tabela já existia de uma versão anterior (sem essa
                # coluna), adiciona agora - não afeta quem já está com a
                # tabela em dia.
                cursor.execute("""
                    ALTER TABLE laudos ADD COLUMN IF NOT EXISTS modelo_usado TEXT;
                """)
                # Remove a constraint antiga (baseada em "path") de uma versão
                # anterior deste script, se existir no seu banco.
                cursor.execute("""
                    ALTER TABLE laudos DROP CONSTRAINT IF EXISTS laudos_path_key;
                """)
                # Índice único parcial: garante 1 linha por N° de Proposta,
                # mas ignora laudos com numero_proposta vazio (não identificado)
                # para eles não colidirem uns com os outros.
                cursor.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS laudos_numero_proposta_key
                    ON laudos (numero_proposta) WHERE numero_proposta <> '';
                """)
                execute_values(cursor, query_upsert_laudos, valores_laudos, page_size=100)
                conn.commit()
                print("[SUCESSO TOTAL] Processamento paralelo e carga em lote executados!")
    except Exception as e:
        print(f"[ERRO CARGA BANCO]: {str(e)}")

if __name__ == "__main__":
    processar_em_lote()
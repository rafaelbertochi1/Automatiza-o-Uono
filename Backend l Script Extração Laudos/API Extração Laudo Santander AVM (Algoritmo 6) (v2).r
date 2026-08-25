library(pdftools)
library(stringr)
library(dplyr)
library(DBI)
library(RPostgres)

# ----------------------------------------------------------------------
# 1. FUNÇÕES AUXILIARES SEGURAS
# ----------------------------------------------------------------------
limpar_num <- function(x) {
  if (is.null(x) || is.na(x) || length(x) == 0) return(NA_real_)
  val <- gsub("[^0-9,.]", "", x)
  val <- gsub(",", ".", val)
  if (val == "" || is.na(val)) return(NA_real_)
  as.numeric(val)
}

limpar_txt <- function(x) {
  if (is.null(x) || is.na(x) || length(x) == 0) return(NA_character_)
  txt <- str_trim(x)
  if (txt == "" || txt == "NULL") return(NA_character_)
  txt
}

# Captura segura sem erro de coerção booleana
buscar_padrao_seguro <- function(txt, padroes) {
  for (re in padroes) {
    match <- str_match(txt, re)
    if (!all(is.na(match))) {
      if (ncol(match) >= 2) {
        val <- match[1, 2]
        if (!is.na(val) && nchar(str_trim(val)) > 0) {
          return(str_trim(val))
        }
      }
    }
  }
  return(NA_character_)
}

# ----------------------------------------------------------------------
# 2. PARSER MODELO DIGITAL (METODOLOGIA: AVM)
# ----------------------------------------------------------------------
extrair_modelo_digital <- function(txt) {
  cod_laudo    <- buscar_padrao_seguro(txt, c("(?i)#(TA[NOP]\\d+|\\w+\\d+)", "(?i)LAUDO DE AVALIA[ÇC][ÃA]O\\s*\\|\\s*#(\\w+)"))
  num_proposta <- buscar_padrao_seguro(txt, c("(?i)N[°º]?\\s*da\\s*Proposta[^\n]*\n?\\s*(\\d+)", "(?i)Proposta[^\n]*\n?\\s*(\\d+)"))
  data_aval    <- buscar_padrao_seguro(txt, c("(?i)Data\\s*Solicita[çc][ãa]o[^\n]*\n?\\s*(\\d{2}/\\d{2}/\\d{4})", "(?i)Data[^\n]*(\\d{2}/\\d{2}/\\d{4})"))
  
  endereco   <- buscar_padrao_seguro(txt, c("(?i)Endere[çc]o\\s*\\|?[^\n]*\n?\\s*([^\\|\n\r]+)", "(?i)(ESTRADA[^\n]+|RUA[^\n]+|AVENIDA[^\n]+)"))
  numero_end <- buscar_padrao_seguro(txt, c("(?i)N[úu]mero\\s*\\|?[^\n]*\n?\\s*(?:\\|\\s*)?(\\d+|S/N)"))
  compl_end  <- buscar_padrao_seguro(txt, c("(?i)Complemento\\s*\\|?[^\n]*\n?\\s*(?:\\|\\s*)?([^\\|\n\r]+)"))
  
  tipo_imovel <- buscar_padrao_seguro(txt, c("(?i)Tipo\\s*do\\s*im[óo]vel[^\n]*\n?\\s*([A-Za-zçÇãÃáÁéÉíÍóÓúÚ\\s]+)"))
  
  area_priv   <- buscar_padrao_seguro(txt, c("(?i)[áa]rea\\s+privativa[^\n]*\n?\\s*([\\d\\.,]+)", "(?i)Area\\s+Privativa:\\s*([\\d\\.,]+)"))
  area_comum  <- buscar_padrao_seguro(txt, c("(?i)[ÁA]rea\\s+Comum[^\n]*\n?\\s*([\\d\\.,]+)"))
  
  banheiros <- buscar_padrao_seguro(txt, c("(?i)Quantidade\\s+de\\s+banheiros[^\n]*\n?\\s*(\\d+)", "(?i)Banheiro\\s+Social:\\s*(\\d+)"))
  quartos   <- buscar_padrao_seguro(txt, c("(?i)Quantidade\\s+de\\s+quartos[^\n]*\n?\\s*(\\d+)", "(?i)Dormitóri[oa]:\\s*(\\d+)"))
  vagas     <- buscar_padrao_seguro(txt, c("(?i)Quantidade\\s+de\\s+vagas[^\n]*\n?\\s*(\\d+)", "(?i)Vaga:\\s*(\\d+)"))
  idade     <- buscar_padrao_seguro(txt, c("(?i)Idade\\s+do\\s+im[óo]vel[^\n]*\n?\\s*(\\d+)", "(?i)(\\d+)\\s*anos"))
  
  padrao_acab <- buscar_padrao_seguro(txt, c("(?i)Padr[ãa]o\\s+Acabamento[^\n]*\n?\\s*([A-Za-zçÇãÃáÁéÉíÍóÓúÚ]+)"))
  estado_cons <- buscar_padrao_seguro(txt, c("(?i)Estado\\s+de\\s+Conserva[çc][ãa]o\\s+Im[óo]vel[^\n]*\n?\\s*([A-Za-z|/\\s]+)"))
  
  val_mercado <- buscar_padrao_seguro(txt, c("(?i)VALOR\\s+DE\\s+MERCADO\\s*\n?\\s*R\\$\\s*([\\d\\.,]+)", "(?i)Valor\\s+de\\s+avalia[çc][ãa]o[^\n]*R\\$\\s*([\\d\\.,]+)"))
  val_venda_f <- buscar_padrao_seguro(txt, c("(?i)VALOR\\s+DE\\s+VENDA\\s+FOR[ÇC]ADA\\s*\n?\\s*R\\$\\s*([\\d\\.,]+)"))
  val_unit    <- buscar_padrao_seguro(txt, c("(?i)Valor\\s+unit[áa]rio[^\n]*R\\$\\s*([\\d\\.,]+)"))
  
  coords_str  <- buscar_padrao_seguro(txt, c("(?i)Coordenadas:\\s*([-\\d\\.,]+\\s*,\\s*-[\\d\\.,]+)"))
  lat <- NA_real_; lon <- NA_real_
  if (!is.na(coords_str)) {
    pts <- unlist(str_split(coords_str, ","))
    if (length(pts) == 2) { lat <- as.numeric(str_trim(pts[1])); lon <- as.numeric(str_trim(pts[2])) }
  }

  data.frame(
    numero_proposta     = limpar_txt(num_proposta),
    codigo_laudo        = limpar_txt(cod_laudo),
    data_avaliacao      = limpar_txt(data_aval),
    endereco            = limpar_txt(endereco),
    numero              = limpar_txt(numero_end),
    complemento         = limpar_txt(compl_end),
    tipo_imovel         = limpar_txt(tipo_imovel),
    area_privativa_m2   = limpar_num(area_priv),
    area_comum_m2       = limpar_num(area_comum),
    quartos             = as.integer(quartos),
    banheiros           = as.integer(banheiros),
    vagas               = as.integer(vagas),
    idade_anos          = as.integer(idade),
    padrao_acabamento   = limpar_txt(padrao_acab),
    estado_conservacao  = limpar_txt(estado_cons),
    valor_mercado       = limpar_num(val_mercado),
    valor_venda_forcada = limpar_num(val_venda_f),
    valor_unitario_m2   = limpar_num(val_unit),
    coordenadas         = limpar_txt(coords_str),
    latitude            = lat,
    longitude           = lon,
    stringsAsFactors    = FALSE
  )
}

# ----------------------------------------------------------------------
# 3. PARSER MODELO FÍSICO (METODOLOGIA: COMPARATIVO DIRETO DE MERCADO)
# ----------------------------------------------------------------------
extrair_modelo_fisico <- function(txt) {
  cod_laudo    <- buscar_padrao_seguro(txt, c("(?i)#(TAP\\d+|\\w+\\d+)", "(?i)LAUDO DE AVALIA[ÇC][ÃA]O\\s*\\|\\s*#(\\w+)"))
  num_proposta <- buscar_padrao_seguro(txt, c("(?i)N[°º]?\\s*da\\s*Proposta[^\n]*\n?\\s*(\\d+)", "(?i)Proposta[^\n]*\n?\\s*(\\d+)"))
  data_aval    <- buscar_padrao_seguro(txt, c("(?i)Data\\s*Solicita[çc][ãa]o[^\n]*\n?\\s*(\\d{2}/\\d{2}/\\d{4})", "(?i)Data[^\n]*(\\d{2}/\\d{2}/\\d{4})"))
  
  endereco   <- buscar_padrao_seguro(txt, c("(?i)Endere[çc]o[^\n]*\n?\\s*([^\\n\\r]+)"))
  numero_end <- buscar_padrao_seguro(txt, c("(?i)N[úu]mero[^\n]*\n?\\s*(\\d+|S/N)"))
  compl_end  <- buscar_padrao_seguro(txt, c("(?i)Complemento[^\n]*\n?\\s*([^\\n\\r]+)"))
  
  tipo_imovel <- buscar_padrao_seguro(txt, c("(?i)Tipo\\s*do\\s*im[óo]vel[^\n]*\n?\\s*([A-Za-zçÇãÃáÁéÉíÍóÓúÚ\\s]+)"))
  
  area_priv   <- buscar_padrao_seguro(txt, c("(?i)18-\\s*Ar[eA]a\\s+Privativa[^\n]*\n?\\s*([\\d\\.,]+)", "(?i)[ÁA]REA\\s+PRIVATIVA[^\n]*\n?\\s*\\$?([\\d\\.,]+)"))
  area_comum  <- buscar_padrao_seguro(txt, c("(?i)19-\\s*Ar[eA]a\\s+Comum[^\n]*\n?\\s*([\\d\\.,]+)"))
  quartos     <- buscar_padrao_seguro(txt, c("(?i)12-\\s*N[°º]?\\s*de\\s*Dormit[óo]rios[^\n]*\n?\\s*(\\d+)"))
  banheiros   <- buscar_padrao_seguro(txt, c("(?i)11-\\s*N[°º]?\\s*de\\s*Banheiros[^\n]*\n?\\s*(\\d+)"))
  vagas       <- buscar_padrao_seguro(txt, c("(?i)13-\\s*N[°º]?\\s*de\\s*Vagas[^\n]*\n?\\s*(\\d+)"))
  idade       <- buscar_padrao_seguro(txt, c("(?i)04-\\s*Aparente[^\n]*\n?\\s*(\\d+)"))
  
  padrao_acab <- buscar_padrao_seguro(txt, c("(?i)07-\\s*Padr[ãa]o\\s+de\\s+Acabamento[^\n]*\n?\\s*([A-Za-zçÇãÃáÁéÉíÍóÓúÚ]+)"))
  estado_cons <- buscar_padrao_seguro(txt, c("(?i)05-\\s*Estado\\s+de\\s+Conserva[çc][ãa]o[^\n]*\n?\\s*([A-Za-zçÇãÃáÁéÉíÍóÓúÚ]+)"))
  
  val_mercado <- buscar_padrao_seguro(txt, c("(?i)VALOR\\s+DE\\s+MERCADO\\s*\n?\\s*R\\$\\s*([\\d\\.,]+)"))
  val_venda_f <- buscar_padrao_seguro(txt, c("(?i)VALOR\\s+DE\\s+VENDA\\s+FOR[ÇC]ADA\\s*\n?\\s*R\\$\\s*([\\d\\.,]+)"))
  val_unit    <- buscar_padrao_seguro(txt, c("(?i)VALOR\\s+UNIT[ÁA]RIO[^\n]*R\\$\\s*([\\d\\.,]+)"))
  
  data.frame(
    numero_proposta     = limpar_txt(num_proposta),
    codigo_laudo        = limpar_txt(cod_laudo),
    data_avaliacao      = limpar_txt(data_aval),
    endereco            = limpar_txt(endereco),
    numero              = limpar_txt(numero_end),
    complemento         = limpar_txt(compl_end),
    tipo_imovel         = limpar_txt(tipo_imovel),
    area_privativa_m2   = limpar_num(area_priv),
    area_comum_m2       = limpar_num(area_comum),
    quartos             = as.integer(quartos),
    banheiros           = as.integer(banheiros),
    vagas               = as.integer(vagas),
    idade_anos          = as.integer(idade),
    padrao_acabamento   = limpar_txt(padrao_acab),
    estado_conservacao  = limpar_txt(estado_cons),
    valor_mercado       = limpar_num(val_mercado),
    valor_venda_forcada = limpar_num(val_venda_f),
    valor_unitario_m2   = limpar_num(val_unit),
    stringsAsFactors    = FALSE
  )
}

# ----------------------------------------------------------------------
# 4. ROTEADOR
# ----------------------------------------------------------------------
extrair_dados_santander <- function(pdf_path) {
  texto_paginas <- pdf_text(pdf_path)
  txt <- paste(texto_paginas, collapse = "\n")
  
  if (grepl("Comparativo\\s+direto", txt, ignore.case = TRUE) || grepl("QUESTIONARIO", txt, ignore.case = TRUE)) {
    return(extrair_modelo_fisico(txt))
  } else {
    return(extrair_modelo_digital(txt))
  }
}

# ----------------------------------------------------------------------
# 5. EXECUÇÃO E CARGA NO POSTGRESQL
# ----------------------------------------------------------------------
host_pg <- Sys.getenv("PGURL", "host.docker.internal")

con <- dbConnect(
  RPostgres::Postgres(),
  dbname   = Sys.getenv("PGNAME", "testdb"),
  host     = host_pg,
  port     = as.integer(Sys.getenv("PGPORT", "5432")),
  user     = Sys.getenv("PGUSR", "postgres"),
  password = Sys.getenv("PGPASS", "postgres")
)

colunas_banco <- dbListFields(con, "laudos")
caminho_laudos <- "/workspace/data/laudos"
if (!dir.exists(caminho_laudos)) caminho_laudos <- "/workspace"

arquivos_pdf <- list.files(path = caminho_laudos, pattern = "\\.pdf$", full.names = TRUE)

for (pdf in arquivos_pdf) {
  tryCatch({
    dados <- extrair_dados_santander(pdf)
    dados$path <- basename(pdf)
    dados_filtrados <- dados[, intersect(names(dados), colunas_banco), drop = FALSE]
    
    dbWriteTable(con, "laudos", dados_filtrados, append = TRUE, row.names = FALSE)
    message(paste("[SUCESSO GRAVAÇÃO]:", basename(pdf)))
  }, error = function(e) {
    message(paste("[ERRO GRAVAÇÃO]:", basename(pdf), "-", e$message))
  })
}

dbDisconnect(con)
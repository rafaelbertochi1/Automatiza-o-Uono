# Importando pacotes do R...
 # 'pdftools' fornece funções para trabalhar com arquivos PDF (extrair, renderizar e converter).
 library(pdftools)
 # 'stringr' fornece funções simples e consistentes para manipulação de strings.
 library(stringr)
 # 'dplyr' fornece funções simples e consistentes para manipulação de dados.
 library(dplyr)
 # 'tidyr' fornece funções voltadas para melhor formatação (estrutura e consistência) de dados.
 library(tidyr)
 # 'readr' fornece funções que facilitam a importação de dados retangulares (como aqueles em arquivos CSV e TSV).
 library(readr)
#

# Criando comando para extrair padrões de um vetor de caracteres ou algo que possa ser convertido em um...
  # 'str_match()'é um comando do pacote 'stringr' para extrair componentes de uma string.
  # O comando retorna uma matriz de caracteres.
  extract_regex <- function(text, pattern) { 
                                              str_match(text, pattern)[,2]
                                           }
#

# Criando comando para extração de informações dos laudos Santander...
  extrair_info <- function(pdf_path) {
                                        txt <- pdf_text(pdf_path)

                                        txt_all <- paste(txt, collapse = "\n")

                                        tibble(
                                                path = basename(pdf_path),

                                                data = str_extract(txt_all, "\\d{2}/\\d{2}/\\d{4}"),

                                                endereco = extract_regex(txt[3], "(?i)Endere[cç]o[\\s\\S]{0,50}?\\b([A-Z0-9\\s]+)\\b")|> gsub('No', '', x = _) |> trimws(),
                                                          
                                                numero = extract_regex(txt_all, "Nº\\s*(\\d+)"),

                                                complemento = extract_regex(txt_all, "Complemento:\\s*([A-Z0-9\\s]+)"),

                                                # bairro = extract_regex(txt_all, "Bairro:\\s*([A-Z\\s]+)") |> gsub('UF', '', x = _) |> trimws(),
                                            
                                                # cidade = extract_regex(txt_all, "Cidade|Municipio:\\s*([A-Z\\s]+)") |> trimws(),

                                                # uf = extract_regex(txt_all, "UF:\\s*([A-Z]{2})"),
                                                
                                                tipo_imovel = extract_regex(txt_all, "Tipo do Imóvel:\\s*([A-Za-z]+)"),
                                                
                                                area_privativa_m2 = extract_regex(txt_all, "Área Privativa:\\s*([0-9,]+)") |> parse_number(locale = locale(decimal_mark = ",")),
                                                
                                                area_comum_m2 = extract_regex(txt_all, "Área Comum:\\s*([0-9,]+)") |> parse_number(locale = locale(decimal_mark = ",")),
                                                
                                                area_total_m2 = extract_regex(txt_all, "Área Total:\\s*([0-9,]+)") |> parse_number(locale = locale(decimal_mark = ",")),
                                                
                                                quartos = extract_regex(txt_all, "Dormitório:\\s*(\\d+)") |> as.integer(),
                                                
                                                suites = extract_regex(txt_all, "Dormitório:\\s*\\d+\\s*Suíte:\\s*(\\d+)") |> as.integer(),
                                                
                                                banheiros = extract_regex(txt_all, "Banheiro Social:\\s*(\\d+)") |> as.integer(),
                                                
                                                vagas = extract_regex(txt_all, "Vaga:\\s*(\\d+)") |> as.integer(),
                                                
                                                idade_anos = extract_regex(txt_all, "Idade Aparente:\\s*(\\d+)") |> as.integer(),
                                                
                                                # elevador = extract_regex(txt_all, "Elevador\\s*\\n(Não|Sim)"),
                                                
                                                padrao_acabamento = extract_regex(txt_all, "(?i)Padr[aã]o\\s+de\\s+acabamento[\\s\\S]{0,50}?\\b(Bom|M[eé]dio|Ruim|Regular|Ótimo)\\b"),
                                                
                                                estado_conservacao = extract_regex(txt_all, "(?i)Estado\\s+de\\s+conserva[cç][aã][\\s\\S]{0,50}?\\b(Bom|M[eé]dio|Ruim|Regular|Ótimo)\\b"),
                                                
                                                valor_mercado = extract_regex(txt_all, "Valor de Mercado:\\s*R\\$\\s*([0-9\\.]+,[0-9]{2})") |> parse_number(locale = locale(decimal_mark = ",")),
                                                
                                                valor_venda_forcada = extract_regex(txt_all, "Valor de venda forçada:\\s*R\\$\\s*([0-9\\.]+,[0-9]{2})") |> parse_number(locale = locale(decimal_mark = ",")),
                                                
                                                valor_unitario_m2 = extract_regex(txt_all, "VALOR UNITÁRIO \\(R\\$/m²\\)\\s*R\\$\\s*([0-9\\.]+,[0-9]{2})") |> parse_number(locale = locale(decimal_mark = ",")),
                                                
                                                coordenadas = extract_regex(tolower(txt_all), "coordena[d]?as?(?: do imóvel)?\\s*:?\\s*([-0-9\\.,\\s]+)")
                                                
                                                # coordenadas1 = extract_regex(txt_all, "COORDENADAS:\\s*([-0-9\\.,\\s]+)"),
                                                
                                                # coordenadas2 = extract_regex(tolower(txt_all), "coordenadas do imóvel :\\s*([-0-9\\.,\\s]+)"),

                                                # coordenadas3 = extract_regex(tolower(txt_all), "coordenadas do imóvel:\\s*([-0-9\\.,\\s]+)")
                                              )
                                     }
#

# Criando comando para extração de informações dos amostras dos laudos Santander...
  extract_amostra <- function(pdf_path) {
                                          txt_p4 <- pdf_text(pdf_path)[4]
                                          
                                          blocos <- str_split(txt_p4, "(?=Amostra n\\.\\s*\\d+)", simplify = FALSE)[[1]]

                                          x <- blocos[str_detect(blocos, "Amostra n")]
                                          
                                          tibble(
                                                  path = basename(pdf_path),

                                                  amostra = str_extract(x, "Amostra n\\.\\s*\\d+") |> str_extract("\\d+") |> as.integer(),

                                                  data = str_extract(x, "Data\\s+\\d{2}/\\d{2}/\\d{4}") |> str_extract("\\d{2}/\\d{2}/\\d{4}"),
                                                  
                                                  endereco = str_extract(x, "Edereço:\\s*.*") |> str_remove("Edereço:\\s*"),

                                                  bairro = str_extract(x, "Bairro:\\s*.*?(?=Cidade:)") |> str_remove("Bairro:\\s*") |> str_trim(),

                                                  cidade = str_extract(x, "Cidade:\\s*.*?(?=UF:)") |> str_remove("Cidade:\\s*") |> str_trim(),

                                                  uf = str_extract(x, "UF:\\s*[A-Z]{2}") |> str_extract("[A-Z]{2}"),
                                                  
                                                  tipo = str_extract(x, "Tipo:\\s*.*?(?=Padrão)") |> str_remove("Tipo:\\s*") |> str_trim(),

                                                  padrao = str_extract(x, "Padrão de construção:\\s*[A-Za-zÀ-ÿ]+") |> str_remove(".*:\\s*"),

                                                  conservacao = str_extract(x, "Estado de conservação:\\s*[A-Za-zÀ-ÿ]+") |> str_remove(".*:\\s*"),
                                                  
                                                  area_privativa = str_extract(x, "A\\. privativa/construida \\(m\\):\\s*\\d+") |> str_extract("\\d+") |> as.numeric(),
                                                  
                                                  dormitorios = str_extract(x, "N\\.dormitórios/suites:\\s*\\d+") |> str_extract("\\d+") |> as.integer(),
                                                  
                                                  suites = str_extract(x, "N\\.dormitórios/suites:\\s*\\d+/\\d+") |> str_extract("(?<=/)\\d+") |> as.integer(),
                                                  
                                                  vagas = str_extract(x, "N\\.vagas:\\s*\\d+") |> str_extract("\\d+") |> as.integer(),
                                                  
                                                  idade = str_extract(x, "Idade Aparente\\(anos\\):\\s*\\d+") |> str_extract("\\d+") |> as.integer(),
                                                  
                                                  valor_total = str_extract(x, "Valor total \\(R\\$\\):\\s*[0-9\\.,]+") |> str_remove(".*:\\s*") |> str_replace("\\.", "") |> str_replace(",", ".") |> as.numeric(),

                                                  valor_unitario = str_extract(x, "Valor unitário \\(R\\$/m\\):\\s*[0-9\\.,]+") |> str_remove(".*:\\s*") |> str_replace("\\.", "") |> str_replace(",", ".") |> as.numeric(),

                                                  fonte = str_extract(x, "Fonte:\\s*.*?(?=Tel:)") |> str_remove("Fonte:\\s*") |> str_trim(),
                                                                                                    
                                                  link_anunc = str_extract(x, "https?://[^\\s]+")
                                                )
                                        }
#

# Gerando lista de laudos Santander...
  # O comando 'lapply()' é usado para aplicar uma função a cada elemento de uma lista e retornar os resultados também em forma de lista.
  df <- lapply(
                # Lista ou vetor que será tratado como lista.
                list.files(
                            'data/laudos/',
                            full.names = T
                          ),
                # Comando que será aplicado a cada elemento da lista. 
                function(x) {
                              extrair_info(x)
                            }
              )
#

# Gerando data frame dos laudos Santander a partir da lista de laudos Santander...
  # O comando "do.call()" serve para executar outro comando de forma programática, passando os argumentos como uma lista.
  # O operador |> serve para encadear operações, passando o resultado da expressão à esquerda como primeiro argumento da função à direita.
  # O comando "mutate()" serve para criar, modificar ou remover colunas em um data frame ou tibble.
  df <- do.call(
                  # Comando usado para empilhar objetos por linhas.
                  rbind,
                  # Lista de argumentos que serão passados para o comando anterior.
                  df
               )
               |>
        mutate(
                latitude = lapply(
                                    coordenadas,
                                    function(x) { str_split(x, ',')[[1]][1] }
                                 ) |>
                           unlist() |>
                           str_match('[-+]?\\d+.\\d+') |>
                           as.numeric(),
                longitude = lapply(
                                    coordenadas,
                                    function(x) { str_split(x, ',')[[1]][2] }
                                  ) |>
                            unlist() |>
                            str_match('[-+]?\\d+.\\d+') |>
                            as.numeric(),
                valor_unitario_m2 = round(
                                            valor_mercado / area_privativa_m2,
                                            2
                                         )
              )
#

# Gerando lista de amostras dos laudos Santander...
  df.amostra <- lapply(
                        list.files(
                                    'data/laudos/',
                                    full.names = T
                                  ),
                        function(x) {
                                      extract_amostra(x)
                                    }
                      )
#

# Gerando data frame das amostras dos laudos Santander a partir da lista de amostras dos laudos Santander...
  # O comando "do.call()" serve para executar outro comando de forma programática, passando os argumentos como uma lista.
  df.amostra <- do.call(
                          # Comando usado para empilhar objetos por linhas.
                          rbind,
                          # Lista de argumentos que serão passados para o comando anterior.
                          df.amostra
                       )
#

# Criando comunicação entre este script e o nosso PostgreSQL...
  # O comando 'dbConnect()' gera um objeto de conexão entre este script e o nosso PostgreSQL.
  # O comando 'dbConnect()' retorna esse objeto de conexão.
  conn <- dbConnect(
                      # 'RPostgres' é um pacote de driver do R para conexão com o SGBD PostgreSQL.
                      RPostgres::Postgres(),
                      # 'Sys.getenv()' é um comando que acessa variável(is) de ambiente e retorna seu valor.
                      dbname = Sys.getenv('PGNAME'),
                      host = Sys.getenv('PGURL'),
                      port = Sys.getenv('PGPORT'),
                      user = Sys.getenv('PGUSR'),
                      password = Sys.getenv('PGPASS')
                   )
#

# Adicionando linhas do dataframe 'df' a tabela 'laudos' que está no PostgreSQL...
  # O comando dbWriteTable() é usado para copiar um data frame para uma tabela em um banco de dados.
  # O comando permite também criar uma nova tabela, sobrescrever ou adicionar dados a uma já existente.
  dbWriteTable(
                conn = conn,
                name = DBI::Id(
                                schema = 'public',
                                table = 'laudos'
                              ),
                df,
                append  = T,
                row.names = F
              )
#

# Adicionando linhas do dataframe 'df' na tabela 'laudos_amostras' que está no nosso PostgreSQL...
  dbWriteTable(
                conn = conn,
                name = DBI::Id(
                                schema = 'public',
                                table = 'laudos_amostras'
                              ),
                df.amostra,
                append  = T,
                row.names = F
              )
#

# Interrompendo comunicação entre este script e o PostgreSQL...
  dbDisconnect(
                conn = conn
              )
#
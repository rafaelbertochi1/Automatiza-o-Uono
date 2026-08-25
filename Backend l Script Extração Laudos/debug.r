library(pdftools)

caminho_laudos <- "/workspace/data/laudos"
if (!dir.exists(caminho_laudos)) caminho_laudos <- "/workspace"

arquivos <- list.files(caminho_laudos, pattern = "\\.pdf$", full.names = TRUE)

if (length(arquivos) == 0) {
  cat("Nenhum PDF encontrado em:", caminho_laudos, "\n")
} else {
  # Pega o primeiro PDF para inspeção bruta
  pdf_teste <- arquivos[1]
  cat("=========================================\n")
  cat("LENDO ARQUIVO:", basename(pdf_teste), "\n")
  cat("=========================================\n\n")
  
  paginas <- pdf_text(pdf_teste)
  
  cat("--- PÁGINA 1 (TEXTO CRU EXATO) ---\n")
  cat(paginas[1])
}
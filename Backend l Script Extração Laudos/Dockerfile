FROM rocker/tidyverse:latest

# Instala as dependências do sistema necessárias para o pacote pdftools
RUN apt-get update && apt-get install -y \
    libpoppler-cpp-dev \
    && rm -rf /var/lib/apt/lists/*

# Instala o pacote pdftools no R globalmente na imagem
RUN R -e "install.packages('pdftools', repos='https://cloud.r-project.org/')"
'''Importando bibliotecas do Python...
'psycopg2' é uma biblioteca Python para se conectar ao SGBD PostgreSQL.
'sql' é um módulo da biblioteca 'psycopg2' usado para construir queries estruturadas.
'MuPDF' é uma biblioteca C para renderização e manipulação de documentos.
'PyMuPDF' é um pacote Python que faz o binding da biblioteca MuPDF.
'fitz' é um módulo do pacote 'PyMuPDF' que permite o uso das funcionalidades do 'MuPDF'.'''
import psycopg2
from psycopg2 import sql
import fitz



'''Criando função para extrair texto de PDF...'''
def extract_text_from_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text()
    return text



'''Criando função para inserir dados no PostgreSQL a partir do texto extraído de PDF...'''
def insert_into_postgres(text):
    try:
        '''Criando um objeto de conexão entre este script e o PostgreSQL...'''
        conn = psycopg2.connect(
            dbname="seu_banco",
            user="seu_usuario",
            password="sua_senha",
            host="localhost",
            port="5432"
        )

        '''Criando um objeto de cursor entre este script e o PostgreSQL...
        Objeto de cursor permite executar comandos SQL e navegar pelos resultados.
        Ele funciona como uma "ponte" entre o programa Python e o banco de dados.
        Sem o cursor, você não consegue enviar instruções SQL diretamente pela conexão.'''
        cur = conn.cursor()

        '''Criando tabela se ela não existir...'''
        cur.execute("""CREATE TABLE IF NOT EXISTS pdf_data (
                            id SERIAL PRIMARY KEY,
                            content TEXT
                        )
                    """
        )

        '''Inserindo texto no banco de dados...'''
        cur.execute(
            sql.SQL("INSERT INTO pdf_data (content) VALUES (%s)"),
            [text]
        )

        '''Aplicando definitivamente todas as mudanças feitas na transação atual...'''
        conn.commit()

        print("Dados inseridos com sucesso!")
    
    except Exception as e:
        print("Erro ao inserir no banco:", e)
    
    finally:
        if conn:
            cur.close()
            conn.close()



'''Rodando o script de extração de fato...'''
if __name__ == "__main__":
    pdf_path = "C:\Users\guilherme.mendes\Downloads\Uono Sanchez Engenharia\Projeto l AVM 2.0\Test Environment"
    text = extract_text_from_pdf(pdf_path)
    insert_into_postgres(text)
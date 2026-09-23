import random
import string
from contextlib import closing
from database.connection import get_db_connection

def generate_unique_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

class ConfigRow(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            return None

# Funções auxiliares baseadas nas necessidades do projeto
def get_config():
    with closing(get_db_connection()) as conn:
        row = conn.execute("SELECT * FROM configuracoes WHERE id = 1").fetchone()
        if row:
            return ConfigRow(dict(row))
        return None

def get_proximos_cardapios(data_atual_str):
    with closing(get_db_connection()) as conn:
        return conn.execute("SELECT * FROM cardapios WHERE data >= ? ORDER BY data ASC", (data_atual_str,)).fetchall()

def get_proximo_cardapio(data_atual_str):
    with closing(get_db_connection()) as conn:
        return conn.execute("SELECT * FROM cardapios WHERE data >= ? ORDER BY data ASC LIMIT 1", (data_atual_str,)).fetchone()

def get_cardapio_hoje(data_atual_str):
    with closing(get_db_connection()) as conn:
        return conn.execute("SELECT * FROM cardapios WHERE data = ?", (data_atual_str,)).fetchone()

def get_cardapios_hoje(data_atual_str):
    with closing(get_db_connection()) as conn:
        return conn.execute("SELECT * FROM cardapios WHERE data = ?", (data_atual_str,)).fetchall()

def get_cardapio_by_id(id):
    with closing(get_db_connection()) as conn:
        return conn.execute("SELECT * FROM cardapios WHERE id = ?", (id,)).fetchone()

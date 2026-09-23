import json
from datetime import datetime


def datetimeformat(value, format='%d/%m/%Y'):
    if not value:
        return ''
    try:
        return datetime.strptime(value, '%Y-%m-%d').strftime(format)
    except:
        return value


def format_cpf(value):
    if not value:
        return ''
    # Remove all non-numeric characters
    cpf_digits = ''.join(filter(str.isdigit, str(value)))
    # If it has 11 digits, format it
    if len(cpf_digits) == 11:
        return f"{cpf_digits[:3]}.{cpf_digits[3:6]}.{cpf_digits[6:9]}-{cpf_digits[9:]}"
    # Otherwise, return original
    return value


def fromjson_filter(value):
    if not value:
        return []
    try:
        return json.loads(value)
    except:
        return []


from markupsafe import Markup, escape

def nl2br_filter(value):
    if not value:
        return ''
    return Markup('<br>\n'.join(escape(value).split('\n')))

DIAS_SEMANA = [
    'Segunda-feira',
    'Terça-feira',
    'Quarta-feira',
    'Quinta-feira',
    'Sexta-feira',
    'Sábado',
    'Domingo'
]

def data_com_semana(value):
    if not value:
        return ''
    try:
        if isinstance(value, str):
            clean_val = value.strip()[:10]
            dt = datetime.strptime(clean_val, '%Y-%m-%d')
        elif hasattr(value, 'strftime') and hasattr(value, 'weekday'):
            dt = value
        else:
            return value
        dia_sem = DIAS_SEMANA[dt.weekday()]
        return f"{dt.strftime('%d/%m/%Y')} ({dia_sem})"
    except:
        return value

def register_filters(app):
    app.template_filter('datetimeformat')(datetimeformat)
    app.template_filter('format_date')(datetimeformat)
    app.template_filter('format_cpf')(format_cpf)
    app.template_filter('fromjson')(fromjson_filter)
    app.template_filter('nl2br')(nl2br_filter)
    app.template_filter('data_com_semana')(data_com_semana)

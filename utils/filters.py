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


def register_filters(app):
    app.template_filter('datetimeformat')(datetimeformat)
    app.template_filter('format_cpf')(format_cpf)
    app.template_filter('fromjson')(fromjson_filter)

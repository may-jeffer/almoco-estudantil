# -*- coding: utf-8 -*-
"""
Módulo Base de Conhecimento — Biblioteca digital interna de materiais de treinamento.
"""
import os
import uuid
from datetime import datetime
from flask import render_template, request, redirect, url_for, session, flash, send_file
from database import closing, get_db_connection
from utils.auth import is_logged_in_admin, tem_permissao
from utils.helpers import registrar_auditoria
from . import admin_bp

# Tipos de arquivo permitidos (seguro — sem executáveis, scripts)
TIPOS_PERMITIDOS = {
    '.pdf', '.docx', '.doc', '.xlsx', '.xls', '.pptx', '.ppt',
    '.txt', '.csv', '.zip', '.rar', '.7z', '.png', '.jpg', '.jpeg',
    '.gif', '.mp3', '.odt', '.ods', '.odp'
}

UPLOAD_FOLDER = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'static', 'uploads', 'base_conhecimento'
)

ICONES_CATEGORIA = [
    ('folder', 'Pasta'),
    ('book-open', 'Livro'),
    ('graduation-cap', 'Treinamento'),
    ('file-text', 'Documentos'),
    ('clipboard', 'Normas'),
    ('wrench', 'Manuais'),
    ('users', 'Equipe'),
    ('shield', 'Segurança'),
    ('chart-bar', 'Relatórios')
]


def extensao_permitida(nome):
    return os.path.splitext(nome)[1].lower() in TIPOS_PERMITIDOS


def tipo_arquivo_label(nome):
    ext = os.path.splitext(nome)[1].lower() if nome else ''
    mapa = {
        '.pdf': 'PDF', '.docx': 'Word', '.doc': 'Word',
        '.xlsx': 'Excel', '.xls': 'Excel',
        '.pptx': 'PowerPoint', '.ppt': 'PowerPoint',
        '.txt': 'Texto', '.csv': 'CSV',
        '.zip': 'ZIP', '.rar': 'RAR', '.7z': '7Z',
        '.png': 'PNG', '.jpg': 'JPG', '.jpeg': 'JPG', '.gif': 'GIF',
        '.mp3': 'Áudio MP3',
        '.odt': 'LibreOffice Writer', '.ods': 'LibreOffice Calc', '.odp': 'LibreOffice Impress',
    }
    return mapa.get(ext, ext.upper().lstrip('.'))


def icone_ph(nome):
    ext = os.path.splitext(nome)[1].lower() if nome else ''
    if ext == '.pdf': return 'ph-file-pdf'
    if ext in ('.docx', '.doc', '.odt'): return 'ph-file-doc'
    if ext in ('.xlsx', '.xls', '.ods', '.csv'): return 'ph-file-xls'
    if ext in ('.pptx', '.ppt', '.odp'): return 'ph-presentation-chart'
    if ext in ('.zip', '.rar', '.7z'): return 'ph-file-zip'
    if ext in ('.png', '.jpg', '.jpeg', '.gif'): return 'ph-image'
    if ext == '.mp3': return 'ph-music-note'
    return 'ph-file-text'


def fmt_bytes(b):
    if not b: return '---'
    if b < 1024: return f'{b} B'
    if b < 1024**2: return f'{b/1024:.1f} KB'
    return f'{b/1024**2:.1f} MB'


# ─── Página Principal ──────────────────────────────────────────────────────────

@admin_bp.route('/admin/base-conhecimento')
def admin_base_conhecimento():
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('base_conhecimento'): return redirect(url_for('admin.admin_dashboard'))

    busca = request.args.get('q', '').strip()
    cat_filtro = request.args.get('cat', '').strip()

    with closing(get_db_connection()) as conn:
        categorias = conn.execute(
            'SELECT * FROM bc_categorias ORDER BY ordem ASC, nome ASC'
        ).fetchall()

        q_mat = """
            SELECT m.*, c.nome as cat_nome, c.icone as cat_icone
            FROM bc_materiais m
            JOIN bc_categorias c ON m.categoria_id = c.id
            WHERE 1=1
        """
        params = []
        if busca:
            q_mat += ' AND (m.titulo LIKE ? OR m.descricao LIKE ?)'
            like = f'%{busca}%'
            params.extend([like, like])
        if cat_filtro:
            q_mat += ' AND m.categoria_id = ?'
            params.append(int(cat_filtro))
        q_mat += ' ORDER BY m.data_criacao DESC'
        materiais = conn.execute(q_mat, params).fetchall()

        contagens = {}
        for r in conn.execute(
            'SELECT categoria_id, COUNT(*) as total FROM bc_materiais GROUP BY categoria_id'
        ).fetchall():
            contagens[r['categoria_id']] = r['total']

    return render_template('admin/base_conhecimento.html',
        categorias=categorias, materiais=materiais,
        busca=busca, cat_filtro=cat_filtro,
        contagens=contagens, icones_categoria=ICONES_CATEGORIA,
        icone_ph=icone_ph, fmt_bytes=fmt_bytes)


# ─── CRUD de Categorias ────────────────────────────────────────────────────────

@admin_bp.route('/admin/base-conhecimento/categorias/nova', methods=['POST'])
def admin_bc_nova_categoria():
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('base_conhecimento'): return redirect(url_for('admin.admin_dashboard'))
    nome = request.form.get('nome', '').strip()
    if not nome:
        flash('O nome da categoria é obrigatório.', 'error')
        return redirect(url_for('admin.admin_base_conhecimento'))
    descricao = request.form.get('descricao', '').strip()
    icone = request.form.get('icone', 'folder').strip()
    with closing(get_db_connection()) as conn:
        conn.execute(
            'INSERT INTO bc_categorias (nome,descricao,icone,criado_por,data_criacao) VALUES (?,?,?,?,?)',
            (nome, descricao, icone, session.get('admin_usuario', 'Sistema'), datetime.now().isoformat())
        )
        conn.commit()
    registrar_auditoria('Base Conhecimento', f'Criou categoria: {nome}')
    flash(f'Categoria "{nome}" criada com sucesso.', 'success')
    return redirect(url_for('admin.admin_base_conhecimento'))


@admin_bp.route('/admin/base-conhecimento/categorias/<int:cat_id>/editar', methods=['POST'])
def admin_bc_editar_categoria(cat_id):
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('base_conhecimento'): return redirect(url_for('admin.admin_dashboard'))
    nome = request.form.get('nome', '').strip()
    descricao = request.form.get('descricao', '').strip()
    icone = request.form.get('icone', 'folder').strip()
    with closing(get_db_connection()) as conn:
        conn.execute('UPDATE bc_categorias SET nome=?,descricao=?,icone=? WHERE id=?',
                     (nome, descricao, icone, cat_id))
        conn.commit()
    registrar_auditoria('Base Conhecimento', f'Editou categoria ID {cat_id}')
    flash('Categoria atualizada.', 'success')
    return redirect(url_for('admin.admin_base_conhecimento'))


@admin_bp.route('/admin/base-conhecimento/categorias/<int:cat_id>/excluir', methods=['POST'])
def admin_bc_excluir_categoria(cat_id):
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('base_conhecimento'): return redirect(url_for('admin.admin_dashboard'))
    with closing(get_db_connection()) as conn:
        for m in conn.execute('SELECT caminho_arquivo FROM bc_materiais WHERE categoria_id=?', (cat_id,)).fetchall():
            if m['caminho_arquivo'] and os.path.exists(m['caminho_arquivo']):
                try: os.remove(m['caminho_arquivo'])
                except Exception: pass
        conn.execute('DELETE FROM bc_materiais WHERE categoria_id=?', (cat_id,))
        conn.execute('DELETE FROM bc_categorias WHERE id=?', (cat_id,))
        conn.commit()
    registrar_auditoria('Base Conhecimento', f'Excluiu categoria ID {cat_id} e seus materiais')
    flash('Categoria e materiais excluídos.', 'success')
    return redirect(url_for('admin.admin_base_conhecimento'))


# ─── CRUD de Materiais ─────────────────────────────────────────────────────────

@admin_bp.route('/admin/base-conhecimento/materiais/novo', methods=['POST'])
def admin_bc_novo_material():
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('base_conhecimento'): return redirect(url_for('admin.admin_dashboard'))
    titulo = request.form.get('titulo', '').strip()
    descricao = request.form.get('descricao', '').strip()
    categoria_id = request.form.get('categoria_id', '').strip()
    if not titulo or not categoria_id:
        flash('Título e categoria são obrigatórios.', 'error')
        return redirect(url_for('admin.admin_base_conhecimento'))

    arquivo = request.files.get('arquivo')
    nome_arq = cam_arq = tipo = None
    tamanho = 0
    if arquivo and arquivo.filename:
        if not extensao_permitida(arquivo.filename):
            flash('Tipo de arquivo não permitido.', 'error')
            return redirect(url_for('admin.admin_base_conhecimento'))
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        ext = os.path.splitext(arquivo.filename)[1].lower()
        nome_unico = f'{uuid.uuid4().hex}{ext}'
        cam = os.path.join(UPLOAD_FOLDER, nome_unico)
        arquivo.save(cam)
        nome_arq = arquivo.filename
        cam_arq = cam
        tipo = tipo_arquivo_label(arquivo.filename)
        tamanho = os.path.getsize(cam)

    with closing(get_db_connection()) as conn:
        conn.execute(
            """INSERT INTO bc_materiais
               (categoria_id,titulo,descricao,nome_arquivo,caminho_arquivo,
                tipo_arquivo,tamanho_bytes,criado_por,data_criacao)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (int(categoria_id), titulo, descricao, nome_arq, cam_arq, tipo, tamanho,
             session.get('admin_usuario', 'Sistema'), datetime.now().isoformat())
        )
        conn.commit()
    registrar_auditoria('Base Conhecimento', f'Cadastrou material: {titulo}')
    flash(f'Material "{titulo}" cadastrado com sucesso.', 'success')
    return redirect(url_for('admin.admin_base_conhecimento'))


@admin_bp.route('/admin/base-conhecimento/materiais/<int:mat_id>/editar', methods=['POST'])
def admin_bc_editar_material(mat_id):
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('base_conhecimento'): return redirect(url_for('admin.admin_dashboard'))
    titulo = request.form.get('titulo', '').strip()
    descricao = request.form.get('descricao', '').strip()
    categoria_id = request.form.get('categoria_id', '').strip()
    with closing(get_db_connection()) as conn:
        m = conn.execute('SELECT * FROM bc_materiais WHERE id=?', (mat_id,)).fetchone()
        if not m:
            flash('Material não encontrado.', 'error')
            return redirect(url_for('admin.admin_base_conhecimento'))
        nome_arq, cam_arq, tipo, tamanho = m['nome_arquivo'], m['caminho_arquivo'], m['tipo_arquivo'], m['tamanho_bytes']
        novo = request.files.get('arquivo')
        if novo and novo.filename:
            if not extensao_permitida(novo.filename):
                flash('Tipo de arquivo não permitido.', 'error')
                return redirect(url_for('admin.admin_base_conhecimento'))
            if cam_arq and os.path.exists(cam_arq):
                try: os.remove(cam_arq)
                except Exception: pass
            os.makedirs(UPLOAD_FOLDER, exist_ok=True)
            ext = os.path.splitext(novo.filename)[1].lower()
            cam = os.path.join(UPLOAD_FOLDER, f'{uuid.uuid4().hex}{ext}')
            novo.save(cam)
            nome_arq, cam_arq = novo.filename, cam
            tipo = tipo_arquivo_label(novo.filename)
            tamanho = os.path.getsize(cam)
        conn.execute(
            'UPDATE bc_materiais SET titulo=?,descricao=?,categoria_id=?,nome_arquivo=?,caminho_arquivo=?,tipo_arquivo=?,tamanho_bytes=? WHERE id=?',
            (titulo, descricao, int(categoria_id) if categoria_id else m['categoria_id'],
             nome_arq, cam_arq, tipo, tamanho, mat_id)
        )
        conn.commit()
    registrar_auditoria('Base Conhecimento', f'Editou material ID {mat_id}: {titulo}')
    flash('Material atualizado.', 'success')
    return redirect(url_for('admin.admin_base_conhecimento'))


@admin_bp.route('/admin/base-conhecimento/materiais/<int:mat_id>/excluir', methods=['POST'])
def admin_bc_excluir_material(mat_id):
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('base_conhecimento'): return redirect(url_for('admin.admin_dashboard'))
    with closing(get_db_connection()) as conn:
        m = conn.execute('SELECT * FROM bc_materiais WHERE id=?', (mat_id,)).fetchone()
        if m and m['caminho_arquivo'] and os.path.exists(m['caminho_arquivo']):
            try: os.remove(m['caminho_arquivo'])
            except Exception: pass
        conn.execute('DELETE FROM bc_materiais WHERE id=?', (mat_id,))
        conn.commit()
    registrar_auditoria('Base Conhecimento', f'Excluiu material ID {mat_id}')
    flash('Material excluído.', 'success')
    return redirect(url_for('admin.admin_base_conhecimento'))


@admin_bp.route('/admin/base-conhecimento/materiais/<int:mat_id>/download')
def admin_bc_download(mat_id):
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('base_conhecimento'): return redirect(url_for('admin.admin_dashboard'))
    with closing(get_db_connection()) as conn:
        m = conn.execute('SELECT * FROM bc_materiais WHERE id=?', (mat_id,)).fetchone()
        if not m or not m['caminho_arquivo'] or not os.path.exists(m['caminho_arquivo']):
            flash('Arquivo não encontrado.', 'error')
            return redirect(url_for('admin.admin_base_conhecimento'))
        conn.execute('UPDATE bc_materiais SET total_downloads=total_downloads+1 WHERE id=?', (mat_id,))
        conn.commit()
    registrar_auditoria('Base Conhecimento — Download', f'Baixou: {m["titulo"]}')
    return send_file(m['caminho_arquivo'], as_attachment=True,
                     download_name=m['nome_arquivo'] or f'material_{mat_id}')


@admin_bp.route('/admin/base-conhecimento/materiais/<int:mat_id>/visualizar')
def admin_bc_visualizar(mat_id):
    """Abre o arquivo inline no navegador (ideal para PDFs e imagens)."""
    if not is_logged_in_admin(): return redirect(url_for('admin.admin_login'))
    if not tem_permissao('base_conhecimento'): return redirect(url_for('admin.admin_dashboard'))
    with closing(get_db_connection()) as conn:
        m = conn.execute('SELECT * FROM bc_materiais WHERE id=?', (mat_id,)).fetchone()
        if not m or not m['caminho_arquivo'] or not os.path.exists(m['caminho_arquivo']):
            flash('Arquivo não encontrado.', 'error')
            return redirect(url_for('admin.admin_base_conhecimento'))
    registrar_auditoria('Base Conhecimento — Visualização', f'Visualizou: {m["titulo"]}')
    return send_file(m['caminho_arquivo'], as_attachment=False)

from flask import render_template, redirect, url_for, request, flash
from flask_login import current_user

from app import db
from app.models import Page, log_audit, set_published
from app.locks import acquire_lock, active_locks
from app.pages import save_page
from app.views.admin import admin_bp, admin_required, editor_required


@admin_bp.route('/pages/')
@editor_required
def pages_list():
    pages = Page.query.order_by(Page.sort_title).all()
    locked_pages = active_locks('page')
    return render_template('admin/pages.html', pages=pages, locked_pages=locked_pages)


@admin_bp.route('/pages/new/', methods=['GET', 'POST'])
@editor_required
def new_page():
    if request.method == 'POST':
        return save_page(None)
    return render_template('admin/page_editor.html', page=None)


@admin_bp.route('/pages/<int:page_id>/edit/', methods=['GET', 'POST'])
@editor_required
def edit_page(page_id):
    page = db.get_or_404(Page, page_id)
    if request.method == 'POST':
        return save_page(page)
    blocker = acquire_lock('page', page_id)
    if blocker:
        flash(f'"{page.title}" is currently being edited by {blocker}.', 'warning')
        return redirect(url_for('admin.pages_list'))
    return render_template('admin/page_editor.html', page=page, lock_type='page', lock_id=page_id)


@admin_bp.route('/pages/<int:page_id>/delete/', methods=['POST'])
@admin_required
def delete_page(page_id):
    page = db.get_or_404(Page, page_id)
    page_title = page.title
    db.session.delete(page)
    db.session.commit()
    log_audit('page_deleted', detail=page_title, user_id=current_user.id)
    flash('Page deleted.', 'success')
    return redirect(url_for('admin.pages_list'))


@admin_bp.route('/pages/<int:page_id>/publish/', methods=['POST'])
@editor_required
def publish_page(page_id):
    page = db.get_or_404(Page, page_id)
    set_published(page, page.is_draft)  # toggle: publish if currently draft
    db.session.commit()
    status = 'unpublished' if page.is_draft else 'published'
    flash(f'"{page.title}" {status}.', 'success')
    return redirect(url_for('admin.edit_page', page_id=page.id))

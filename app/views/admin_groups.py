import re
from functools import wraps

from flask import render_template, redirect, url_for, request, flash, abort
from flask_login import login_required, current_user

from app import db
from app.models import (Group, GroupJoinRequest, User, SiteSettings,
                        groups_feature_enabled, make_slug, log_audit, utcnow)
from app.views.admin import admin_bp

_HEX_RE = re.compile(r'^#[0-9a-fA-F]{6}$')
_DEFAULT_COLOR = '#6b7785'


def _valid_color(raw):
    """Return a safe hex color for the badge, falling back to the default so a
    crafted value can never break out of the inline style attribute."""
    raw = (raw or '').strip()
    return raw if _HEX_RE.match(raw) else _DEFAULT_COLOR


def groups_admin_required(f):
    """Admin-only, and 404 when the groups feature is off — mirrors how the
    users area 404s/redirects when multi-user is disabled, so a disabled feature
    exposes no routes."""
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        if not groups_feature_enabled(SiteSettings.get()):
            abort(404)
        return f(*args, **kwargs)
    return decorated


@admin_bp.route('/groups/', methods=['GET', 'POST'])
@groups_admin_required
def groups():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('Group name is required.', 'error')
            return redirect(url_for('admin.groups'))
        slug = make_slug(name)
        if not slug:
            flash('That group name cannot be used.', 'error')
            return redirect(url_for('admin.groups'))
        if Group.query.filter((Group.name == name) | (Group.slug == slug)).first():
            flash('A group with this name already exists.', 'error')
            return redirect(url_for('admin.groups'))
        group = Group(name=name, slug=slug,
                      description=request.form.get('description', '').strip(),
                      color=_valid_color(request.form.get('color')))
        db.session.add(group)
        db.session.commit()
        log_audit('group_created', detail=name, user_id=current_user.id)
        flash(f'Group "{name}" created.', 'success')
        return redirect(url_for('admin.group_detail', group_id=group.id))

    all_groups = Group.query.order_by(Group.name).all()
    pending = (GroupJoinRequest.query
               .filter_by(status='pending')
               .order_by(GroupJoinRequest.created_at.asc())
               .all())
    all_access_users = User.query.filter_by(all_groups=True).order_by(User.display_name).all()
    grant_candidates = (User.query
                        .filter(User.all_groups == False)  # noqa: E712
                        .order_by(User.display_name).all())
    return render_template('admin/groups.html', groups=all_groups, pending=pending,
                           all_access_users=all_access_users, grant_candidates=grant_candidates)


@admin_bp.route('/groups/<int:group_id>/', methods=['GET'])
@groups_admin_required
def group_detail(group_id):
    group = db.get_or_404(Group, group_id)
    member_ids = {u.id for u in group.members}
    candidates = (User.query
                  .filter(User.all_groups == False)  # noqa: E712
                  .order_by(User.display_name).all())
    candidates = [u for u in candidates if u.id not in member_ids]
    return render_template('admin/group_detail.html', group=group, candidates=candidates)


@admin_bp.route('/groups/<int:group_id>/edit/', methods=['POST'])
@groups_admin_required
def group_edit(group_id):
    group = db.get_or_404(Group, group_id)
    name = request.form.get('name', '').strip()
    if not name:
        flash('Group name is required.', 'error')
        return redirect(url_for('admin.group_detail', group_id=group.id))
    slug = make_slug(name)
    clash = Group.query.filter(((Group.name == name) | (Group.slug == slug)),
                               Group.id != group.id).first()
    if clash:
        flash('A group with this name already exists.', 'error')
        return redirect(url_for('admin.group_detail', group_id=group.id))
    group.name = name
    group.slug = slug
    group.description = request.form.get('description', '').strip()
    group.color = _valid_color(request.form.get('color'))
    db.session.commit()
    log_audit('group_edited', detail=name, user_id=current_user.id)
    flash('Group updated.', 'success')
    return redirect(url_for('admin.group_detail', group_id=group.id))


@admin_bp.route('/groups/<int:group_id>/delete/', methods=['POST'])
@groups_admin_required
def group_delete(group_id):
    group = db.get_or_404(Group, group_id)
    name = group.name
    # Deleting the group drops its entry/member/join-request associations; any
    # entries restricted only to this group become public again.
    GroupJoinRequest.query.filter_by(group_id=group.id).delete()
    db.session.delete(group)
    db.session.commit()
    log_audit('group_deleted', detail=name, user_id=current_user.id)
    flash(f'Group "{name}" deleted.', 'success')
    return redirect(url_for('admin.groups'))


@admin_bp.route('/groups/<int:group_id>/members/add/', methods=['POST'])
@groups_admin_required
def group_add_member(group_id):
    group = db.get_or_404(Group, group_id)
    user = db.session.get(User, request.form.get('user_id', type=int))
    if not user:
        flash('User not found.', 'error')
    elif user in group.members:
        flash(f'{user.display_name} is already a member.', 'info')
    else:
        group.members.append(user)
        _resolve_open_request(user.id, group.id, 'approved')
        db.session.commit()
        log_audit('group_member_added', detail=f'{user.display_name} → {group.name}',
                  user_id=current_user.id)
        flash(f'{user.display_name} added to {group.name}.', 'success')
    return redirect(url_for('admin.group_detail', group_id=group.id))


@admin_bp.route('/groups/<int:group_id>/members/<int:user_id>/remove/', methods=['POST'])
@groups_admin_required
def group_remove_member(group_id, user_id):
    group = db.get_or_404(Group, group_id)
    user = db.session.get(User, user_id)
    if user and user in group.members:
        group.members.remove(user)
        db.session.commit()
        log_audit('group_member_removed', detail=f'{user.display_name} ✕ {group.name}',
                  user_id=current_user.id)
        flash(f'{user.display_name} removed from {group.name}.', 'success')
    return redirect(url_for('admin.group_detail', group_id=group.id))


@admin_bp.route('/groups/all-access/', methods=['POST'])
@groups_admin_required
def group_toggle_all_access():
    user = db.session.get(User, request.form.get('user_id', type=int))
    if not user:
        flash('User not found.', 'error')
        return redirect(url_for('admin.groups'))
    user.all_groups = 'all_groups' in request.form
    db.session.commit()
    state = 'granted' if user.all_groups else 'revoked'
    log_audit('group_all_access_' + state, detail=user.display_name, user_id=current_user.id)
    flash(f'All-groups access {state} for {user.display_name}.', 'success')
    return redirect(url_for('admin.groups'))


@admin_bp.route('/groups/requests/<int:req_id>/<action>/', methods=['POST'])
@groups_admin_required
def group_request_decide(req_id, action):
    if action not in ('approve', 'deny'):
        abort(404)
    req = db.get_or_404(GroupJoinRequest, req_id)
    if req.status != 'pending':
        flash('That request has already been handled.', 'info')
        return redirect(url_for('admin.groups'))
    req.status = 'approved' if action == 'approve' else 'denied'
    req.decided_by = current_user.id
    req.decided_at = utcnow()
    if action == 'approve' and req.user and req.group and req.user not in req.group.members:
        req.group.members.append(req.user)
    db.session.commit()
    who = req.user.display_name if req.user else 'user'
    grp = req.group.name if req.group else 'group'
    log_audit(f'group_request_{req.status}', detail=f'{who} → {grp}', user_id=current_user.id)
    flash(f'Request {req.status}.', 'success')
    return redirect(url_for('admin.groups'))


def _resolve_open_request(user_id, group_id, status):
    """Mark any pending join request for this (user, group) as resolved when the
    admin acts on membership directly, so it drops out of the pending queue."""
    open_req = GroupJoinRequest.query.filter_by(
        user_id=user_id, group_id=group_id, status='pending').first()
    if open_req:
        open_req.status = status
        open_req.decided_by = current_user.id
        open_req.decided_at = utcnow()

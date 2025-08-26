from flask import render_template, request, jsonify, flash, redirect, url_for, g
from . import projects_bp
from database.db import execute_query
from utils.decorators import login_required, permission_required
from datetime import datetime

@projects_bp.route('/')
@login_required
@permission_required('projects', 'read')
def index():
    """Liste des projets"""
    projects = execute_query("""
        SELECT p.*, e.name as client_name,
               u.first_name || ' ' || u.last_name as manager_name,
               COUNT(pt.id) as task_count,
               COUNT(pt.id) FILTER (WHERE pt.status = 'completed') as completed_tasks
        FROM projects p
        LEFT JOIN entities e ON p.client_id = e.id
        LEFT JOIN users u ON p.project_manager_id = u.id
        LEFT JOIN project_tasks pt ON p.id = pt.project_id
        GROUP BY p.id, e.name, u.first_name, u.last_name
        ORDER BY p.created_at DESC
    """, fetch_all=True)
    
    return render_template('projects/index.html', projects=projects)

@projects_bp.route('/<int:project_id>')
@login_required
@permission_required('projects', 'read')
def detail(project_id):
    """Détail d'un projet"""
    project = execute_query("""
        SELECT p.*, e.name as client_name,
               u.first_name || ' ' || u.last_name as manager_name
        FROM projects p
        LEFT JOIN entities e ON p.client_id = e.id
        LEFT JOIN users u ON p.project_manager_id = u.id
        WHERE p.id = %s
    """, (project_id,), fetch_one=True)
    
    if not project:
        flash('Projet introuvable', 'danger')
        return redirect(url_for('projects.index'))
    
    # Tâches du projet
    tasks = execute_query("""
        SELECT pt.*, s.name as site_name,
               u.first_name || ' ' || u.last_name as assigned_to_name
        FROM project_tasks pt
        LEFT JOIN sites s ON pt.site_id = s.id
        LEFT JOIN users u ON pt.assigned_to = u.id
        WHERE pt.project_id = %s
        ORDER BY pt.priority DESC, pt.start_date
    """, (project_id,), fetch_all=True)
    
    return render_template('projects/detail.html',
                         project=project,
                         tasks=tasks)

@projects_bp.route('/create')
@login_required
@permission_required('projects', 'create')
def create():
    return "Page de création de projet"
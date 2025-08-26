from flask import render_template, request, jsonify, flash, redirect, url_for, session, g
from . import admin_bp
from database.db import execute_query
from utils.decorators import login_required, admin_required
from blueprints.auth.utils import hash_password
from datetime import datetime, timedelta
import json
from utils.decorators import login_required, admin_required, permission_required

@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    """Dashboard administrateur"""
    stats = {}
    
    try:
        # Statistiques globales
        stats['users_count'] = execute_query(
            "SELECT COUNT(*) as count FROM users", 
            fetch_one=True
        )['count']
        
        stats['prospects_count'] = execute_query(
            "SELECT COUNT(*) as count FROM prospects", 
            fetch_one=True
        )['count']
        
        stats['campaigns_count'] = execute_query(
            "SELECT COUNT(*) as count FROM campaigns WHERE status = 'active'", 
            fetch_one=True
        )['count']
        
        stats['sites_count'] = execute_query(
            "SELECT COUNT(*) as count FROM sites WHERE is_active = TRUE", 
            fetch_one=True
        )['count']
        
        # Revenus du mois
        revenue_result = execute_query("""
            SELECT COALESCE(SUM(total_amount), 0) as total
            FROM invoices
            WHERE status = 'paid'
            AND DATE_TRUNC('month', created_at) = DATE_TRUNC('month', CURRENT_DATE)
        """, fetch_one=True)
        stats['monthly_revenue'] = revenue_result['total']
        
        # Données récentes
        recent_prospects = execute_query("""
            SELECT p.*, u.first_name || ' ' || u.last_name as assigned_to_name
            FROM prospects p
            LEFT JOIN users u ON p.assigned_to = u.id
            ORDER BY p.created_at DESC
            LIMIT 5
        """, fetch_all=True)
        
        recent_campaigns = execute_query("""
            SELECT c.*, e.name as client_name
            FROM campaigns c
            LEFT JOIN entities e ON c.client_id = e.id
            ORDER BY c.created_at DESC
            LIMIT 5
        """, fetch_all=True)
        
        # Graphiques et données
        prospects_data = execute_query("""
            SELECT DATE(created_at) as date, COUNT(*) as count
            FROM prospects
            WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
            GROUP BY DATE(created_at)
            ORDER BY date
        """, fetch_all=True)
        
        campaigns_by_status = execute_query("""
            SELECT status, COUNT(*) as count
            FROM campaigns
            GROUP BY status
        """, fetch_all=True)

        # Dans admin/routes.py, dashboard()
        activity_logins = execute_query("""
            SELECT username, login_time
            FROM user_logins
            ORDER BY login_time DESC
            LIMIT 30
        """, fetch_all=True) or []  # Si la requête renvoie None, on met une liste vide

        
        # Préparer les labels et datasets pour les graphiques
        activity_labels = [p['assigned_to_name'] for p in recent_prospects]
        activity_data = [1] * len(activity_labels)  # exemple de données fictives
        prospects_chart_labels = [str(p['date']) for p in prospects_data]
        prospects_chart_values = [p['count'] for p in prospects_data]
        campaigns_status_labels = [c['status'] for c in campaigns_by_status]
        campaigns_status_values = [c['count'] for c in campaigns_by_status]

    except Exception as e:
        print(f"Erreur dashboard: {e}")
        stats = {
            'users_count': 0,
            'prospects_count': 0,
            'campaigns_count': 0,
            'sites_count': 0,
            'monthly_revenue': 0
        }
        recent_prospects = []
        recent_campaigns = []
        prospects_chart_labels = []
        prospects_chart_values = []
        campaigns_status_labels = []
        campaigns_status_values = []
        activity_labels = []
        activity_data = []
        activity_logins = activity_logins or []
    
    activity_actions = []

    return render_template('admin/dashboard.html',
                            stats=stats,
                            recent_prospects=recent_prospects,
                            recent_campaigns=recent_campaigns,
                            prospects_chart_labels=prospects_chart_labels,
                            prospects_chart_values=prospects_chart_values,
                            campaigns_status_labels=campaigns_status_labels,
                            campaigns_status_values=campaigns_status_values,
                            activity_labels=activity_labels,
                            activity_data=activity_data,
                            activity_logins=activity_logins,
                            activity_actions=activity_actions)

@admin_bp.route('/users')
@login_required
@admin_required
def users():
    """Gestion des utilisateurs"""
    users_list = execute_query("""
        SELECT u.*, r.name as role_name, e.name as entity_name
        FROM users u
        LEFT JOIN roles r ON u.role_id = r.id
        LEFT JOIN entities e ON u.entity_id = e.id
        ORDER BY u.created_at DESC
    """, fetch_all=True)
    
    roles = execute_query("SELECT * FROM roles ORDER BY name", fetch_all=True)
    entities = execute_query("SELECT * FROM entities ORDER BY name", fetch_all=True)
    
    return render_template('admin/users.html', 
                         users=users_list, 
                         roles=roles,
                         entities=entities)

@admin_bp.route('/users/create', methods=['POST'])
@login_required
@admin_required
def create_user():
    """Créer un nouvel utilisateur"""
    data = request.get_json()
    
    try:
        # Vérifier si l'email existe déjà
        existing = execute_query(
            "SELECT id FROM users WHERE email = %s",
            (data['email'],),
            fetch_one=True
        )
        
        if existing:
            return jsonify({'error': 'Cet email existe déjà'}), 400
        
        # Créer l'utilisateur
        user_id = execute_query("""
            INSERT INTO users (email, password_hash, first_name, last_name, 
                             phone, role_id, entity_id, must_change_password)
            VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE)
            RETURNING id
        """, (
            data['email'],
            hash_password(data.get('password', 'TempPass123!')),
            data.get('first_name'),
            data.get('last_name'),
            data.get('phone'),
            data.get('role_id'),
            data.get('entity_id')
        ), fetch_one=True, commit=True)
        
        # Log d'audit
        execute_query("""
            INSERT INTO audit_logs (user_id, action, resource_type, resource_id)
            VALUES (%s, 'create_user', 'user', %s)
        """, (session['user_id'], user_id['id']), commit=True)
        
        return jsonify({'success': True, 'message': 'Utilisateur créé avec succès'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/users/<int:user_id>/update', methods=['POST'])
@login_required
@admin_required
def update_user(user_id):
    """Mettre à jour un utilisateur"""
    data = request.get_json()
    
    try:
        execute_query("""
            UPDATE users SET
                first_name = %s,
                last_name = %s,
                phone = %s,
                role_id = %s,
                entity_id = %s,
                is_active = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (
            data.get('first_name'),
            data.get('last_name'),
            data.get('phone'),
            data.get('role_id'),
            data.get('entity_id'),
            data.get('is_active', True),
            user_id
        ), commit=True)
        
        return jsonify({'success': True, 'message': 'Utilisateur mis à jour'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@admin_bp.route('/users/<int:user_id>')
@login_required
@admin_required
def get_user(user_id):
    """Récupérer un utilisateur spécifique"""
    try:
        user = execute_query("""
            SELECT u.*, r.name as role_name, e.name as entity_name
            FROM users u
            LEFT JOIN roles r ON u.role_id = r.id
            LEFT JOIN entities e ON u.entity_id = e.id
            WHERE u.id = %s
        """, (user_id,), fetch_one=True)
        
        if not user:
            return jsonify({'error': 'Utilisateur non trouvé'}), 404
        
        return jsonify(user)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/users/<int:user_id>/reset-password', methods=['POST'])
@login_required
@admin_required
def reset_user_password(user_id):
    """Réinitialiser le mot de passe d'un utilisateur"""
    try:
        # Générer un mot de passe temporaire
        temp_password = 'TempPass123!'
        
        execute_query("""
            UPDATE users SET
                password_hash = %s,
                must_change_password = TRUE,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (
            hash_password(temp_password),
            user_id
        ), commit=True)
        
        return jsonify({'success': True, 'message': 'Mot de passe réinitialisé'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/users/<int:user_id>/toggle-status', methods=['POST'])
@login_required
@admin_required
def toggle_user_status(user_id):
    """Activer/désactiver un utilisateur"""
    data = request.get_json()
    
    try:
        # Empêcher de se désactiver soi-même
        if user_id == session['user_id']:
            return jsonify({'error': 'Vous ne pouvez pas modifier votre propre statut'}), 400
        
        execute_query("""
            UPDATE users SET
                is_active = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (
            data.get('is_active', False),
            user_id
        ), commit=True)
        
        return jsonify({'success': True, 'message': 'Statut utilisateur mis à jour'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/roles')
@login_required
@admin_required
def roles():
    """Gestion des rôles"""
    roles_list = execute_query("""
        SELECT r.*, COUNT(u.id) as user_count
        FROM roles r
        LEFT JOIN users u ON r.id = u.role_id
        GROUP BY r.id
        ORDER BY r.name
    """, fetch_all=True)
    
    # Décoder permissions JSON côté backend
    for role in roles_list:
        try:
            role['permissions'] = json.loads(role['permissions']) if role['permissions'] else {}
        except Exception:
            role['permissions'] = {}
    
    return render_template('admin/roles.html', roles=roles_list)

@admin_bp.route('/roles/<int:role_id>')
@login_required
@admin_required
def get_role(role_id):
    """Récupérer un rôle spécifique"""
    try:
        role = execute_query("""
            SELECT r.*, COUNT(u.id) as user_count
            FROM roles r
            LEFT JOIN users u ON r.id = u.role_id
            WHERE r.id = %s
            GROUP BY r.id
        """, (role_id,), fetch_one=True)
        
        if not role:
            return jsonify({'error': 'Rôle non trouvé'}), 404
        
        # Décoder les permissions JSON
        try:
            role['permissions'] = json.loads(role['permissions']) if role['permissions'] else {}
        except Exception:
            role['permissions'] = {}
        
        return jsonify(role)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/roles/create', methods=['POST'])
@login_required
@admin_required
def create_role():
    """Créer un nouveau rôle"""
    data = request.get_json()
    
    try:
        # Vérifier si le nom existe déjà
        existing = execute_query(
            "SELECT id FROM roles WHERE name = %s",
            (data['name'],),
            fetch_one=True
        )
        
        if existing:
            return jsonify({'error': 'Ce nom de rôle existe déjà'}), 400
        
        role_id = execute_query("""
            INSERT INTO roles (name, description, permissions)
            VALUES (%s, %s, %s)
            RETURNING id
        """, (
            data['name'],
            data.get('description', ''),
            json.dumps(data.get('permissions', {}))
        ), fetch_one=True, commit=True)
        
        return jsonify({'success': True, 'message': 'Rôle créé avec succès', 'id': role_id['id']})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/roles/<int:role_id>/update', methods=['PUT'])
@login_required
@admin_required
def update_role(role_id):
    """Mettre à jour un rôle"""
    data = request.get_json()
    
    try:
        # Vérifier si le nom existe déjà pour un autre rôle
        existing = execute_query(
            "SELECT id FROM roles WHERE name = %s AND id != %s",
            (data['name'], role_id),
            fetch_one=True
        )
        
        if existing:
            return jsonify({'error': 'Ce nom de rôle existe déjà'}), 400
        
        execute_query("""
            UPDATE roles SET
                name = %s,
                description = %s,
                permissions = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (
            data['name'],
            data.get('description', ''),
            json.dumps(data.get('permissions', {})),
            role_id
        ), commit=True)
        
        return jsonify({'success': True, 'message': 'Rôle mis à jour avec succès'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/roles/<int:role_id>/delete', methods=['DELETE'])
@login_required
@admin_required
def delete_role(role_id):
    """Supprimer un rôle"""
    try:
        # Vérifier si le rôle est utilisé par des utilisateurs
        user_count = execute_query(
            "SELECT COUNT(*) as count FROM users WHERE role_id = %s",
            (role_id,),
            fetch_one=True
        )['count']
        
        if user_count > 0:
            return jsonify({'error': 'Ce rôle est utilisé par des utilisateurs et ne peut pas être supprimé'}), 400
        
        execute_query(
            "DELETE FROM roles WHERE id = %s",
            (role_id,),
            commit=True
        )
        
        return jsonify({'success': True, 'message': 'Rôle supprimé avec succès'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@admin_bp.route('/entities')
@login_required
@admin_required
def entities():
    """Gestion des entités"""
    entities_list = execute_query("SELECT * FROM entities ORDER BY name", fetch_all=True)
    return render_template('admin/entities.html', entities=entities_list)


@admin_bp.route('/audit-logs')
@login_required
@admin_required
def audit_logs():
    """Afficher les logs d’audit"""
    logs = execute_query("SELECT * FROM audit_logs ORDER BY created_at DESC", fetch_all=True)
    return render_template('admin/audit_logs.html', logs=logs)


@admin_bp.route('/settings')
@login_required
@admin_required
def settings():
    """Paramètres système"""
    settings_list = execute_query(
        "SELECT * FROM system_settings ORDER BY key",
        fetch_all=True
    )
    
    return render_template('admin/settings.html', settings=settings_list)

@admin_bp.route('/settings/update', methods=['POST'])
@login_required
@admin_required
def update_settings():
    """Mettre à jour les paramètres"""
    data = request.get_json()
    
    try:
        for key, value in data.items():
            execute_query("""
                INSERT INTO system_settings (key, value, updated_by)
                VALUES (%s, %s, %s)
                ON CONFLICT (key) DO UPDATE
                SET value = %s, updated_by = %s, updated_at = CURRENT_TIMESTAMP
            """, (
                key,
                json.dumps(value),
                session['user_id'],
                json.dumps(value),
                session['user_id']
            ), commit=True)
        
        return jsonify({'success': True, 'message': 'Paramètres mis à jour'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
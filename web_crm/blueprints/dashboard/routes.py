from flask import render_template, session, g
from utils.decorators import login_required
from database.db import execute_query
from datetime import datetime, timedelta
import json
from . import main_bp


@main_bp.route('/')
@login_required
def dashboard():
    """Tableau de bord utilisateur"""
    user_id = session['user_id']
    
    stats = {}
    recent_prospects = []
    recent_campaigns = []
    notifications = []
    revenue_chart_data = None
    conversion_chart_data = None
    
    try:
        # Statistiques basées sur les permissions
        if has_permission('prospects', 'read'):
            stats['prospects_count'] = execute_query(
                "SELECT COUNT(*) as count FROM prospects WHERE assigned_to = %s",
                (user_id,), fetch_one=True
            )['count']
            
            stats['new_prospects_today'] = execute_query(
                "SELECT COUNT(*) as count FROM prospects WHERE assigned_to = %s AND DATE(created_at) = CURRENT_DATE",
                (user_id,), fetch_one=True
            )['count']
            
            # Prospects récents
            recent_prospects = execute_query("""
                SELECT p.*, 
                       CASE 
                           WHEN p.status = 'new' THEN 'secondary'
                           WHEN p.status = 'contacted' THEN 'info'
                           WHEN p.status = 'qualified' THEN 'success'
                           WHEN p.status = 'converted' THEN 'primary'
                           ELSE 'warning'
                       END as status_color
                FROM prospects p
                WHERE p.assigned_to = %s
                ORDER BY p.created_at DESC
                LIMIT 5
            """, (user_id,), fetch_all=True)
        
        if has_permission('campaigns', 'read'):
            stats['campaigns_count'] = execute_query(
                "SELECT COUNT(*) as count FROM campaigns WHERE created_by = %s",
                (user_id,), fetch_one=True
            )['count']
            
            stats['active_campaigns'] = execute_query(
                "SELECT COUNT(*) as count FROM campaigns WHERE created_by = %s AND status = 'active'",
                (user_id,), fetch_one=True
            )['count']
            
            # Campagnes récentes
            recent_campaigns = execute_query("""
                SELECT c.*, e.name as client_name,
                       CASE 
                           WHEN c.status = 'planned' THEN 'secondary'
                           WHEN c.status = 'active' THEN 'success'
                           WHEN c.status = 'paused' THEN 'warning'
                           WHEN c.status = 'completed' THEN 'primary'
                           ELSE 'info'
                       END as status_color
                FROM campaigns c
                LEFT JOIN entities e ON c.client_id = e.id
                WHERE c.created_by = %s
                ORDER BY c.created_at DESC
                LIMIT 5
            """, (user_id,), fetch_all=True)
        
        if has_permission('finance', 'read'):
            # Revenus mensuels
            revenue_data = execute_query("""
                SELECT DATE_TRUNC('month', created_at) as month,
                       SUM(total_amount) as revenue
                FROM invoices
                WHERE status = 'paid'
                GROUP BY DATE_TRUNC('month', created_at)
                ORDER BY month DESC
                LIMIT 6
            """, fetch_all=True)
            
            stats['monthly_revenue'] = execute_query("""
                SELECT COALESCE(SUM(total_amount), 0) as revenue
                FROM invoices
                WHERE status = 'paid' AND DATE_TRUNC('month', created_at) = DATE_TRUNC('month', CURRENT_DATE)
            """, fetch_one=True)['revenue']
            
            # Calculer la croissance des revenus
            if len(revenue_data) >= 2:
                current_month = revenue_data[0]['revenue'] or 0
                previous_month = revenue_data[1]['revenue'] or 0
                
                if previous_month > 0:
                    stats['revenue_growth'] = ((current_month - previous_month) / previous_month) * 100
                else:
                    stats['revenue_growth'] = 0
            else:
                stats['revenue_growth'] = 0
            
            # Données pour le graphique de revenus
            if revenue_data:
                revenue_chart_data = {
                    'labels': [r['month'].strftime('%b %Y') for r in reversed(revenue_data)],
                    'datasets': [{
                        'label': 'Revenus',
                        'data': [r['revenue'] for r in reversed(revenue_data)],
                        'backgroundColor': '#0F7BFF',
                        'borderColor': '#0F7BFF',
                        'borderWidth': 1
                    }]
                }
        
        if has_permission('projects', 'read'):
            # Utiliser project_manager_id au lieu de assigned_to
            stats['projects_count'] = execute_query(
                "SELECT COUNT(*) as count FROM projects WHERE project_manager_id = %s",
                (user_id,), fetch_one=True
            )['count']
            
            stats['ongoing_projects'] = execute_query(
                "SELECT COUNT(*) as count FROM projects WHERE project_manager_id = %s AND status = 'in_progress'",
                (user_id,), fetch_one=True
            )['count']
        
        # Notifications
        notifications = execute_query("""
            SELECT n.*, 
                   CASE 
                       WHEN n.type = 'info' THEN 'info-circle'
                       WHEN n.type = 'warning' THEN 'exclamation-triangle'
                       WHEN n.type = 'success' THEN 'check-circle'
                       ELSE 'bell'
                   END as icon,
                   NOW() - n.created_at as time_ago
            FROM notifications n
            WHERE n.user_id = %s AND n.is_read = FALSE
            ORDER BY n.created_at DESC
            LIMIT 5
        """, (user_id,), fetch_all=True)
        
    except Exception as e:
        print(f"Erreur dashboard: {e}")
        # Valeurs par défaut en cas d'erreur
        stats = {
            'prospects_count': 0,
            'new_prospects_today': 0,
            'campaigns_count': 0,
            'active_campaigns': 0,
            'monthly_revenue': 0,
            'revenue_growth': 0,
            'projects_count': 0,
            'ongoing_projects': 0
        }
    
    return render_template('dashboard/index.html',
                         stats=stats,
                         recent_prospects=recent_prospects,
                         recent_campaigns=recent_campaigns,
                         notifications=notifications,
                         revenue_chart_data=revenue_chart_data,
                         conversion_chart_data=conversion_chart_data)

def has_permission(module, action):
    """Vérifie si l'utilisateur a une permission spécifique"""
    if not hasattr(g, "permissions"):
        return False
    
    perms = g.permissions
    
    # Cas spécial : super_admin avec {"all": true}
    if perms.get("all") is True:
        return True
    
    return module in perms and action in perms[module]


def get_user_permissions(user_id):
    """Récupère les permissions d'un utilisateur connecté"""
    row = execute_query("""
        SELECT r.permissions
        FROM users u
        JOIN roles r ON u.role_id = r.id
        WHERE u.id = %s
    """, (user_id,), fetch_one=True)
    
    if row and row["permissions"]:
        try:
            return json.loads(row["permissions"])
        except Exception:
            return {}
    return {}
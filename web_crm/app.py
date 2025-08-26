import json
from flask import Flask, render_template, session, g, redirect, url_for
from flask_cors import CORS
from werkzeug.exceptions import HTTPException
import logging
from datetime import datetime
import os

# Import des blueprints
from blueprints.auth import auth_bp
from blueprints.admin import admin_bp
from blueprints.prospects import prospects_bp
from blueprints.campaigns import campaigns_bp
from blueprints.sites import sites_bp
from blueprints.stock import stock_bp
from blueprints.purchases import purchases_bp
from blueprints.projects import projects_bp
from blueprints.hr import hr_bp
from blueprints.finance import finance_bp
from blueprints.dashboard import main_bp
from blueprints.location import location_bp

# Import de la configuration et de la base de données
from config import Config
from database.db import init_db, execute_query
from utils.decorators import login_required, admin_required, permission_required

# Création de l'application Flask
app = Flask(__name__)
app.config.from_object(Config)

# Configuration CORS
CORS(app)

# Configuration des logs
logging.basicConfig(
    filename=Config.LOG_FILE,
    level=Config.LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Initialisation de la base de données
init_db()

# Enregistrement des blueprints
app.register_blueprint(auth_bp, url_prefix='/auth')
app.register_blueprint(admin_bp, url_prefix='/admin')
app.register_blueprint(prospects_bp, url_prefix='/prospects')
app.register_blueprint(campaigns_bp, url_prefix='/campaigns')
app.register_blueprint(sites_bp, url_prefix='/sites')
app.register_blueprint(stock_bp, url_prefix='/stock')
app.register_blueprint(purchases_bp, url_prefix='/purchases')
app.register_blueprint(projects_bp, url_prefix='/projects')
app.register_blueprint(hr_bp, url_prefix='/hr')
app.register_blueprint(finance_bp, url_prefix='/finance')
app.register_blueprint(main_bp, url_prefix='/dashboard')
app.register_blueprint(location_bp, url_prefix='/location')

@app.before_request
def before_request():
    """Avant chaque requête"""
    g.user = None
    g.permissions = {}

    # Vérifier si l'utilisateur est dans la session
    if 'user' in session or 'user_id' in session:
        # Priorité à user_id si présent
        user_id = session.get('user_id')
        if not user_id and 'user' in session:
            user_data = session.get('user', {})
            user_id = user_data.get('id')
        
        if user_id:
            # Charger l'utilisateur depuis la base avec toutes les informations
            user = execute_query("""
                SELECT u.*, r.name as role_name, r.permissions, e.name as entity_name
                FROM users u
                LEFT JOIN roles r ON u.role_id = r.id
                LEFT JOIN entities e ON u.entity_id = e.id
                WHERE u.id = %s AND u.is_active = TRUE""",
                (user_id,),
                fetch_one=True
            )
            
            if user:
                # Convertir en dictionnaire si nécessaire
                user_dict = dict(user) if hasattr(user, 'items') else user
                g.user = user_dict
                
                # DEBUG: Afficher la structure de l'utilisateur
                print(f"DEBUG - User loaded: {user_dict}")
                print(f"DEBUG - User role: {user_dict.get('role_name')}")
                
                # Charger les permissions
                try:
                    perms = user_dict.get('permissions', {})
                    if isinstance(perms, dict):
                        g.permissions = perms
                        print(f"Permissions already dict for user {user_id}: {perms}")
                    elif isinstance(perms, str):
                        g.permissions = json.loads(perms)
                        print(f"Parsed JSON permissions for user {user_id}: {g.permissions}")
                    else:
                        g.permissions = {}
                        print(f"Unknown permissions format for user {user_id}: {type(perms)}")
                    
                    print(f"DEBUG - Final permissions: {g.permissions}")
                    
                except Exception as e:
                    g.permissions = {}
                    print(f"Erreur lors du chargement des permissions: {e}")
            else:
                # Utilisateur non trouvé, nettoyer la session
                session.clear()

@app.route('/')
def index():
    """Page d'accueil"""
    if hasattr(g, 'user') and g.user:
        print(f"User in index: {g.user}")
        print(f"User role_name: {g.user.get('role_name')}")
        
        # Charger les permissions si elles ne sont pas déjà chargées
        if not hasattr(g, "permissions") or not g.permissions:
            from utils.decorators import get_user_permissions
            g.permissions = get_user_permissions(g.user['id'])
        
        perms = g.permissions
        user_role = g.user.get("role_name")
        
        # Vérifier si l'utilisateur est admin ou super_admin
        is_admin = (
            user_role == "super_admin" or 
            perms.get("all") is True or
            ('admin' in perms and any(action in perms['admin'] for action in ['read', 'write', 'manage']))
        )
        
        print(f"User {g.user['email']} role: {user_role}, is admin: {is_admin}")
        
        if is_admin:
            return redirect(url_for('admin.dashboard')) 
        else:
            return redirect(url_for('main.dashboard'))

    # Pour les visiteurs non connectés
    stats = {
        "prospects": 10,
        "clients": 5,
        "ventes": 3,
        "chiffre": 12000
    }
    return render_template('home.html', stats=stats)

@app.context_processor
def utility_processor():
    def has_permission(module, action):
        """Vérifie si l'utilisateur a une permission spécifique"""
        if not hasattr(g, "user") or not g.user:
            return False
        
        # Récupérer les permissions depuis l'utilisateur dans g
        if hasattr(g, "permissions"):
            perms = g.permissions
        else:
            # Charger les permissions si elles ne sont pas déjà dans g
            perms = get_user_permissions(g.user['id'])
            g.permissions = perms
        
        # Cas spécial : super_admin avec {"all": true}
        if perms.get("all") is True:
            return True
        
        # Vérifier aussi par le nom du rôle
        if g.user.get('role_name') == 'super_admin':
            return True
        
        return module in perms and action in perms[module]
    
    return dict(has_permission=has_permission)

def get_user_permissions(user_id):
    """Récupère les permissions d'un utilisateur"""
    row = execute_query("""
        SELECT r.permissions, r.name as role_name
        FROM users u
        JOIN roles r ON u.role_id = r.id
        WHERE u.id = %s
    """, (user_id,), fetch_one=True)
    
    if row and row["permissions"]:
        try:
            perms = row["permissions"]
            if isinstance(perms, dict):
                return perms
            elif isinstance(perms, str):
                return json.loads(perms)
        except Exception as e:
            print(f"Error parsing permissions: {e}")
            return {}
    return {}

@app.template_filter('datetime')
def format_datetime(value, format='%d/%m/%Y %H:%M'):
    """
    Filtre Jinja2 pour formater les dates.
    Accepte datetime ou chaîne ISO 8601.
    """
    if not value:
        return ""
    
    # Si c'est une chaîne, tenter de parser en datetime
    if isinstance(value, str):
        try:
            # Exemple : '2025-08-22T19:30:00'
            value = datetime.fromisoformat(value)
        except ValueError:
            # Retourne la chaîne brute si échec
            return value
    
    # Si ce n'est pas un datetime maintenant, retourner la valeur telle quelle
    if not isinstance(value, datetime):
        return str(value)
    
    return value.strftime(format)

@app.errorhandler(404)
def not_found(error):
    """Gestion des erreurs 404"""
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    """Gestion des erreurs 500"""
    logging.error(f"Erreur 500: {error}")
    return render_template('errors/500.html'), 500

@app.context_processor
def inject_user():
    """Injecte l'utilisateur dans tous les templates"""
    return dict(current_user=g.user)

if __name__ == '__main__':
    # Création des dossiers nécessaires
    os.makedirs('logs', exist_ok=True)
    os.makedirs('static/uploads', exist_ok=True)
    
    # Lancement de l'application
    app.run(debug=True, port=5000)
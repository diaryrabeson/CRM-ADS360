from functools import wraps
from flask import session, redirect, url_for, g, flash
from database.db import execute_query
import json

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Vérifier user_id OU user dans la session
        user_id = session.get('user_id')
        if not user_id and 'user' in session:
            user_id = session.get('user', {}).get('id')
        
        if not user_id:
            return redirect(url_for('auth.login'))
        
        # Charger l'utilisateur dans g avec toutes les informations nécessaires
        user = execute_query("""
            SELECT u.*, r.name as role_name, r.permissions, e.name as entity_name
            FROM users u
            LEFT JOIN roles r ON u.role_id = r.id
            LEFT JOIN entities e ON u.entity_id = e.id
            WHERE u.id = %s AND u.is_active = TRUE
        """, (user_id,), fetch_one=True)
        
        if not user:
            session.clear()
            return redirect(url_for('auth.login'))
        
        # Convertir en dictionnaire si nécessaire
        user_dict = dict(user) if hasattr(user, 'items') else user
        g.user = user_dict
        
        # Charger les permissions de l'utilisateur
        permissions = get_user_permissions(user_id)
        g.permissions = permissions
        
        # Stocker user_id dans la session pour cohérence
        session['user_id'] = user_id
        
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Décorateur pour restreindre l'accès aux administrateurs"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        print(f"=== ADMIN REQUIRED CHECK ===")
        
        # Obtenir user_id de la session (compatible avec les deux formats)
        user_id = session.get('user_id')
        if not user_id and 'user' in session:
            user_id = session.get('user', {}).get('id')
        
        if not user_id:
            print("Redirecting to login - no user_id in session")
            return redirect(url_for('auth.login'))
        
        # Utiliser les informations déjà dans g si disponibles
        if hasattr(g, "user") and g.user:
            user_dict = g.user
            user_role = user_dict.get("role_name")
            print(f"Using g.user - Role: {user_role}")
        else:
            # Charger l'utilisateur depuis la base de données
            user = execute_query("""
                SELECT u.*, r.name as role_name, r.permissions
                FROM users u 
                LEFT JOIN roles r ON u.role_id = r.id 
                WHERE u.id = %s AND u.is_active = TRUE
            """, (user_id,), fetch_one=True)
            
            if user:
                user_dict = dict(user) if hasattr(user, 'items') else user
                user_role = user_dict.get("role_name")
                g.user = user_dict
                print(f"Loaded from DB - Role: {user_role}")
            else:
                print("User not found")
                session.clear()
                return redirect(url_for('auth.login'))
        
        # Utiliser les permissions déjà dans g si disponibles
        if hasattr(g, "permissions") and g.permissions:
            perms = g.permissions
            print(f"Using g.permissions: {perms}")
        else:
            # Charger les permissions depuis la base de données
            perms = get_user_permissions(user_id)
            g.permissions = perms
            print(f"Loaded from DB - Permissions: {perms}")
        
        # Vérifier si c'est un super_admin (par rôle OU par permissions)
        is_super_admin = (
            user_role == "super_admin" or 
            (perms and perms.get("all") is True)
        )
        
        print(f"Is super admin: {is_super_admin}")
        
        # Vérifier les permissions d'administration
        is_admin = (
            is_super_admin or 
            (perms and 'admin' in perms and any(action in perms['admin'] for action in ['read', 'write', 'manage']))
        )
        
        print(f"Is admin: {is_admin}")
        
        if not is_admin:
            print("Access denied - redirecting to main dashboard")
            flash('Accès réservé aux administrateurs', 'danger')
            return redirect(url_for('main.dashboard'))
        
        print("Access granted to admin")
        return f(*args, **kwargs)
    return decorated_function

def permission_required(module, action):
    """Décorateur pour vérifier les permissions spécifiques"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Obtenir user_id de la session
            user_id = session.get('user_id')
            if not user_id and 'user' in session:
                user_id = session.get('user', {}).get('id')
            
            if not user_id:
                return redirect(url_for('auth.login'))
            
            # Charger les informations si elles ne sont pas dans g
            if not hasattr(g, "user") or not g.user:
                user = execute_query("""
                    SELECT u.*, r.name as role_name, r.permissions
                    FROM users u
                    LEFT JOIN roles r ON u.role_id = r.id
                    WHERE u.id = %s AND u.is_active = TRUE
                """, (user_id,), fetch_one=True)
                
                if user:
                    user_dict = dict(user) if hasattr(user, 'items') else user
                    g.user = user_dict
            
            if not hasattr(g, "permissions") or not g.permissions:
                g.permissions = get_user_permissions(user_id)
            
            perms = g.permissions or {}
            user_role = g.user.get("role_name") if hasattr(g, "user") and g.user else None

            # ✅ Super admin bypass (role + perms all)
            if user_role == "super_admin" or perms.get("all") is True:
                return f(*args, **kwargs)
            
            if module in perms and action in perms[module]:
                return f(*args, **kwargs)
            
            flash('Permission insuffisante', 'danger')
            return redirect(url_for('main.dashboard'))
        return decorated_function
    return decorator

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
            # Vérifier si les permissions sont déjà un dictionnaire
            if isinstance(row["permissions"], dict):
                print(f"Permissions already dict for user {user_id}: {row['permissions']}")
                return row["permissions"]
            # Sinon, essayer de parser comme JSON
            elif isinstance(row["permissions"], str):
                permissions = json.loads(row["permissions"])
                print(f"Parsed JSON permissions for user {user_id}: {permissions}")
                return permissions
            else:
                print(f"Unknown permissions format for user {user_id}: {type(row['permissions'])}")
                return {}
        except Exception as e:
            print(f"Error loading permissions for user {user_id}: {e}")
            return {}
    return {}
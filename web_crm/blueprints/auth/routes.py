from flask import render_template, request, redirect, url_for, session, flash
from . import auth_bp
from database.db import execute_query
from .utils import hash_password, verify_password
from datetime import datetime
import json

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Page de connexion"""
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = execute_query(
            "SELECT * FROM users WHERE email = %s AND is_active = TRUE",
            (email,),
            fetch_one=True
        )
        
        if user and verify_password(password, user['password_hash']):
            session['user_id'] = user['id']
            session.permanent = True
            
            # Mettre à jour last_login
            execute_query(
                "UPDATE users SET last_login = %s WHERE id = %s",
                (datetime.now(), user['id']),
                commit=True
            )
            
            # Log de connexion
            execute_query(
                "INSERT INTO audit_logs (user_id, action, resource_type) VALUES (%s, %s, %s)",
                (user['id'], 'login', 'authentication'),
                commit=True
            )
            
            # Redirection selon le rôle
            if user['must_change_password']:
                return redirect(url_for('auth.change_password'))
            
            flash('Connexion réussie!', 'success')
            return redirect(url_for('index'))
        
        flash('Email ou mot de passe incorrect', 'danger')
    
    return render_template('auth/login.html')

@auth_bp.route('/logout')
def logout():
    """Déconnexion"""
    if 'user_id' in session:
        execute_query(
            "INSERT INTO audit_logs (user_id, action, resource_type) VALUES (%s, %s, %s)",
            (session['user_id'], 'logout', 'authentication'),
            commit=True
        )
        session.clear()
    flash('Vous avez été déconnecté', 'info')
    return redirect(url_for('auth.login'))

@auth_bp.route('/change-password', methods=['GET', 'POST'])
def change_password():
    """Changement de mot de passe"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        old_password = request.form.get('old_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if new_password != confirm_password:
            flash('Les mots de passe ne correspondent pas', 'danger')
            return render_template('auth/change_password.html')
        
        user = execute_query(
            "SELECT * FROM users WHERE id = %s",
            (session['user_id'],),
            fetch_one=True
        )
        
        if not verify_password(old_password, user['password_hash']):
            flash('Ancien mot de passe incorrect', 'danger')
            return render_template('auth/change_password.html')
        
        # Mettre à jour le mot de passe
        execute_query(
            "UPDATE users SET password_hash = %s, must_change_password = FALSE WHERE id = %s",
            (hash_password(new_password), session['user_id']),
            commit=True
        )
        
        flash('Mot de passe modifié avec succès', 'success')
        return redirect(url_for('index'))
    
    return render_template('auth/change_password.html')

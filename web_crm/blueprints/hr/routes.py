from flask import render_template, request, jsonify, flash, redirect, url_for, g
from . import hr_bp
from database.db import execute_query
from utils.decorators import login_required, permission_required
from datetime import datetime, date, timedelta
import json

@hr_bp.route('/')
@login_required
@permission_required('hr', 'read')
def index():
    """Tableau de bord RH"""
    # Liste des employés
    employees = execute_query("""
        SELECT e.*, u.email, u.first_name, u.last_name,
               u.first_name || ' ' || u.last_name as full_name
        FROM employees e
        JOIN users u ON e.user_id = u.id
        ORDER BY u.last_name, u.first_name
    """, fetch_all=True)
    
    # Statistiques
    stats = {
        'total_employees': len(employees),
        'active_contracts': execute_query("""
            SELECT COUNT(*) as count FROM employees 
            WHERE contract_end_date IS NULL OR contract_end_date > CURRENT_DATE
        """, fetch_one=True)['count'],
        'pending_leaves': execute_query("""
            SELECT COUNT(*) as count FROM leaves 
            WHERE status = 'pending'
        """, fetch_one=True)['count'],
        'trainings_month': execute_query("""
            SELECT COUNT(*) as count FROM employee_trainings 
            WHERE scheduled_date >= DATE_TRUNC('month', CURRENT_DATE)
            AND scheduled_date < DATE_TRUNC('month', CURRENT_DATE) + INTERVAL '1 month'
        """, fetch_one=True)['count']
    }
    
    # Congés en attente
    pending_leaves = execute_query("""
        SELECT l.*, e.employee_code,
               u.first_name || ' ' || u.last_name as employee_name
        FROM leaves l
        JOIN employees e ON l.employee_id = e.id
        JOIN users u ON e.user_id = u.id
        WHERE l.status = 'pending'
        ORDER BY l.created_at DESC
        LIMIT 5
    """, fetch_all=True)
    
    # Anniversaires du mois
    birthdays = execute_query("""
        SELECT u.first_name || ' ' || u.last_name as name,
               e.hire_date
        FROM employees e
        JOIN users u ON e.user_id = u.id
        WHERE EXTRACT(MONTH FROM e.hire_date) = EXTRACT(MONTH FROM CURRENT_DATE)
        ORDER BY EXTRACT(DAY FROM e.hire_date)
    """, fetch_all=True)
    
    return render_template('hr/index.html',
                         employees=employees,
                         stats=stats,
                         pending_leaves=pending_leaves,
                         birthdays=birthdays)

@hr_bp.route('/employees/<int:employee_id>')
@login_required
@permission_required('hr', 'read')
def employee_detail(employee_id):
    """Détail d'un employé"""
    employee = execute_query("""
        SELECT e.*, u.email, u.first_name, u.last_name, u.phone,
               r.name as role_name
        FROM employees e
        JOIN users u ON e.user_id = u.id
        LEFT JOIN roles r ON u.role_id = r.id
        WHERE e.id = %s
    """, (employee_id,), fetch_one=True)
    
    if not employee:
        flash('Employé introuvable', 'danger')
        return redirect(url_for('hr.index'))
    
    # Historique des congés
    leaves = execute_query("""
        SELECT * FROM leaves 
        WHERE employee_id = %s 
        ORDER BY start_date DESC
    """, (employee_id,), fetch_all=True)
    
    # Formations
    trainings = execute_query("""
        SELECT et.*, t.name, t.description, t.duration_hours
        FROM employee_trainings et
        JOIN trainings t ON et.training_id = t.id
        WHERE et.employee_id = %s
        ORDER BY et.scheduled_date DESC
    """, (employee_id,), fetch_all=True)
    
    # Évaluations
    reviews = execute_query("""
        SELECT pr.*, u.first_name || ' ' || u.last_name as reviewer_name
        FROM performance_reviews pr
        LEFT JOIN users u ON pr.reviewer_id = u.id
        WHERE pr.employee_id = %s
        ORDER BY pr.created_at DESC
    """, (employee_id,), fetch_all=True)
    
    return render_template('hr/employee_detail.html',
                         employee=employee,
                         leaves=leaves,
                         trainings=trainings,
                         reviews=reviews)

@hr_bp.route('/leaves')
@login_required
@permission_required('hr', 'read')
def leaves():
    """Gestion des congés"""
    all_leaves = execute_query("""
        SELECT l.*, e.employee_code,
               u.first_name || ' ' || u.last_name as employee_name,
               au.first_name || ' ' || au.last_name as approved_by_name
        FROM leaves l
        JOIN employees e ON l.employee_id = e.id
        JOIN users u ON e.user_id = u.id
        LEFT JOIN users au ON l.approved_by = au.id
        ORDER BY l.created_at DESC
    """, fetch_all=True)
    
    return render_template('hr/leaves.html', leaves=all_leaves)

@hr_bp.route('/leaves/<int:leave_id>/approve', methods=['POST'])
@login_required
@permission_required('hr', 'write')
def approve_leave(leave_id):
    """Approuver un congé"""
    try:
        execute_query("""
            UPDATE leaves 
            SET status = 'approved', 
                approved_by = %s,
                approved_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (g.user['id'], leave_id), commit=True)
        
        return jsonify({'success': True, 'message': 'Congé approuvé'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@hr_bp.route('/attendance')
@login_required
@permission_required('hr', 'read')
def attendance():
    """Gestion des présences"""
    today = date.today()
    
    # Présences du jour
    today_attendance = execute_query("""
        SELECT a.*, e.employee_code,
               u.first_name || ' ' || u.last_name as employee_name
        FROM attendance a
        JOIN employees e ON a.employee_id = e.id
        JOIN users u ON e.user_id = u.id
        WHERE a.date = %s
        ORDER BY u.last_name, u.first_name
    """, (today,), fetch_all=True)
    
    # Employés sans pointage aujourd'hui
    missing_attendance = execute_query("""
        SELECT e.*, u.first_name || ' ' || u.last_name as full_name
        FROM employees e
        JOIN users u ON e.user_id = u.id
        WHERE e.id NOT IN (
            SELECT employee_id FROM attendance WHERE date = %s
        )
        AND (e.contract_end_date IS NULL OR e.contract_end_date > %s)
        ORDER BY u.last_name, u.first_name
    """, (today, today), fetch_all=True)
    
    return render_template('hr/attendance.html',
                         today_attendance=today_attendance,
                         missing_attendance=missing_attendance,
                         today=today)
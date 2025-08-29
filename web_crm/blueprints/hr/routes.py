from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, g
from . import hr_bp
from database.db import execute_query
from utils.decorators import login_required, permission_required
from datetime import datetime, date, timedelta
from flask import jsonify
import json
import uuid
from flask import current_app
import os
import uuid 
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash    


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
            WHERE  hire_date IS NOT NULL
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
        SELECT l.*, e.matricule,
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


# Liste des départements
@hr_bp.route('/departments/list')
@login_required
@permission_required('hr', 'read')
def list_departments():
    """Récupérer la liste des départements"""
    departments = execute_query("""
        SELECT id, name, created_at, updated_at
        FROM departments
        ORDER BY name
    """, fetch_all=True)

    # Convertir les dates en string ISO pour le JS
    for dept in departments:
        dept['created_at'] = dept['created_at'].isoformat() if dept['created_at'] else None
        dept['updated_at'] = dept['updated_at'].isoformat() if dept['updated_at'] else None

    return jsonify({'departments': departments})



@hr_bp.route('/departments/create', methods=['POST'])
@login_required
@permission_required('hr', 'create')
def create_department():
    """Créer un nouveau département"""
    name = request.form.get('name', '').strip()
    
    if not name:
        return jsonify({'success': False, 'message': 'Le nom du département est requis.'})
    
    try:
        execute_query(
            "INSERT INTO departments (name) VALUES (%s)",
            (name,),
            commit=True
        )
        return jsonify({'success': True})
    except Exception as e:
        print(e)
        return jsonify({'success': False, 'message': 'Erreur lors de la création du département.'})


    # Récupérer l'id du département ajouté
    new_department = execute_query("""
        SELECT id, name, created_at, updated_at
        FROM departments
        WHERE id = (SELECT MAX(id) FROM departments)
    """, fetch_one=True)

    return jsonify({'success': True, 'department': new_department})

# Récupérer un département
@hr_bp.route('/departments/<int:id>', methods=['GET'])
@login_required
@permission_required('hr', 'read')
def get_department(id):
    department = execute_query("""
        SELECT id, name, created_at, updated_at
        FROM departments
        WHERE id = %s
    """, (id,), fetch_one=True)

    if not department:
        return jsonify({'success': False, 'message': 'Département introuvable'}), 404

    return jsonify({'success': True, 'department': department})

# Mettre à jour un département
@hr_bp.route('/departments/update/<int:id>', methods=['POST'])
@login_required
@permission_required('hr', 'update')
def update_department(id):
    """Modifier un département existant"""
    name = request.form.get('name', '').strip()
    
    if not name:
        return jsonify({'success': False, 'message': 'Le nom du département est requis.'})
    
    try:
        execute_query(
            "UPDATE departments SET name = %s, updated_at = NOW() WHERE id = %s",
            (name, id),
            commit=True
        )
        return jsonify({'success': True})
    except Exception as e:
        print(e)
        return jsonify({'success': False, 'message': 'Erreur lors de la mise à jour du département.'})


# Supprimer un département
@hr_bp.route('/departments/delete/<int:id>', methods=['DELETE'])
@login_required
@permission_required('hr', 'delete')
def delete_department(id):
    """Supprimer un département"""
    try:
        execute_query(
            "DELETE FROM departments WHERE id = %s",
            (id,),
            commit=True
        )
        return jsonify({'success': True})
    except Exception as e:
        print(e)
        return jsonify({'success': False, 'message': 'Erreur lors de la suppression du département.'})


# ===============================
# Routes pour la table positions
# ===============================

# Liste des postes
@hr_bp.route('/positions/list')
@login_required
@permission_required('hr', 'read')
def list_positions():
    """Récupérer la liste des postes"""
    positions = execute_query("""
        SELECT id, name, created_at, updated_at
        FROM positions
        ORDER BY name
    """, fetch_all=True)

    # Convertir les dates en string ISO pour le JS
    for pos in positions:
        pos['created_at'] = pos['created_at'].isoformat() if pos['created_at'] else None
        pos['updated_at'] = pos['updated_at'].isoformat() if pos['updated_at'] else None

    return jsonify({'positions': positions})


# Créer un poste
@hr_bp.route('/positions/create', methods=['POST'])
@login_required
@permission_required('hr', 'create')
def create_position():
    """Créer un nouveau poste"""
    name = request.form.get('name', '').strip()
    
    if not name:
        return jsonify({'success': False, 'message': 'Le nom du poste est requis.'})
    
    try:
        execute_query(
            "INSERT INTO positions (name) VALUES (%s)",
            (name,),
            commit=True
        )
        # Récupérer le poste ajouté
        new_position = execute_query("""
            SELECT id, name, created_at, updated_at
            FROM positions
            WHERE id = (SELECT MAX(id) FROM positions)
        """, fetch_one=True)

        return jsonify({'success': True, 'position': new_position})
    except Exception as e:
        print(e)
        return jsonify({'success': False, 'message': 'Erreur lors de la création du poste.'})


# Récupérer un poste
@hr_bp.route('/positions/<int:id>', methods=['GET'])
@login_required
@permission_required('hr', 'read')
def get_position(id):
    position = execute_query("""
        SELECT id, name, created_at, updated_at
        FROM positions
        WHERE id = %s
    """, (id,), fetch_one=True)

    if not position:
        return jsonify({'success': False, 'message': 'Poste introuvable'}), 404

    return jsonify({'success': True, 'position': position})


# Mettre à jour un poste
@hr_bp.route('/positions/update/<int:id>', methods=['POST'])
@login_required
@permission_required('hr', 'update')
def update_position(id):
    """Modifier un poste existant"""
    name = request.form.get('name', '').strip()
    
    if not name:
        return jsonify({'success': False, 'message': 'Le nom du poste est requis.'})
    
    try:
        execute_query(
            "UPDATE positions SET name = %s, updated_at = NOW() WHERE id = %s",
            (name, id),
            commit=True
        )
        return jsonify({'success': True})
    except Exception as e:
        print(e)
        return jsonify({'success': False, 'message': 'Erreur lors de la mise à jour du poste.'})


# Supprimer un poste
@hr_bp.route('/positions/delete/<int:id>', methods=['DELETE'])
@login_required
@permission_required('hr', 'delete')
def delete_position(id):
    """Supprimer un poste"""
    try:
        execute_query(
            "DELETE FROM positions WHERE id = %s",
            (id,),
            commit=True
        )
        return jsonify({'success': True})
    except Exception as e:
        print(e)
        return jsonify({'success': False, 'message': 'Erreur lors de la suppression du poste.'})





@hr_bp.route('/employees/create', methods=['POST'])
@login_required
@permission_required('hr', 'create')
def create_employee():
    """Créer un nouvel employé avec plusieurs photos"""
    try:
        # 1) Données formulaire
        matricule = request.form.get('matricule', '').strip()
        firstname = request.form.get('firstname', '').strip()
        lastname = request.form.get('lastname', '').strip()
        email = request.form.get('email', '').strip()
        national_id = request.form.get('national_id', '').strip()
        contact = request.form.get('contact', '').strip()
        birth_date = request.form.get('birth_date') or None
        address = request.form.get('address') or None
        hire_date = request.form.get('hire_date') or None
        leave_balance = request.form.get('leave_balance', 0)
        department_id = request.form.get('department_id') or None
        position_id = request.form.get('position_id') or None
        salary = request.form.get('salary') or 0
        create_user_account = request.form.get('create_user_account')  # "on" si coché, sinon None

        # 2) Validation basique
        if not (matricule and firstname and lastname and email and national_id):
            return jsonify({'success': False, 'message': 'Veuillez remplir tous les champs obligatoires.'}), 400

        # 3) Insérer l’employé (SANS photo_id)
        emp = execute_query("""
            INSERT INTO employees (
                matricule, firstname, lastname, email, address, contact,
                national_id, birth_date, hire_date, leave_balance, created_at, updated_at
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, NOW(), NOW())
            RETURNING id
        """, (
            matricule, firstname, lastname, email, address, contact,
            national_id, birth_date, hire_date, leave_balance
        ), fetch_one=True, commit=True)

        # 3a) Récupérer l'id
        employee_id = emp['id'] if isinstance(emp, dict) else emp[0]

        # 3b) Insérer dans informations
        execute_query("""
            INSERT INTO informations (
                department_id, position_id, employee_id, salary, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, NOW(), NOW())
        """, (department_id, position_id, employee_id, salary), commit=True)

        # 4) Traiter les photos multiples
        photos = request.files.getlist('photos')
        if photos:
            upload_dir = current_app.config.get('UPLOAD_FOLDER')
            if not upload_dir:
                return jsonify({'success': False, 'message': "UPLOAD_FOLDER n'est pas configuré."}), 500
            os.makedirs(upload_dir, exist_ok=True)

            for file in photos:
                if not file or file.filename == '':
                    continue
                original = secure_filename(file.filename)
                unique_name = f"{uuid.uuid4().hex}_{original}"
                filepath = os.path.join(upload_dir, unique_name)
                file.save(filepath)
                execute_query("INSERT INTO photos (employee_id, file_path) VALUES (%s, %s)",
                              (employee_id, unique_name), commit=True)

        # 5) Optionnel: créer un compte utilisateur
        if create_user_account:
            hashed_password = generate_password_hash(national_id)
            execute_query("""
                INSERT INTO users (username, email, password, role)
                VALUES (%s, %s, %s, %s)
            """, (email, email, hashed_password, 'employee'), commit=True)

        return jsonify({'success': True, 'message': 'Employé ajouté avec succès.'}), 201

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@hr_bp.route('/employees/list')
@login_required
@permission_required('hr', 'read')
def list_employees():
    """Récupérer la liste des employés"""
    employees = execute_query("""
        SELECT
            id,
            firstname,
            lastname,
            matricule,
            CONCAT(firstname, ' ', lastname) AS full_name,
            hire_date,
            leave_balance
        FROM employees
        ORDER BY lastname, firstname
    """, fetch_all=True)

    # Convertir les dates en string ISO pour le JS
    for emp in employees:
        emp['hire_date'] = emp['hire_date'].isoformat() if emp['hire_date'] else None

    return jsonify({'employees': employees})

@hr_bp.route('/employees/<int:employee_id>', methods=['GET'])
@login_required
def get_employee(employee_id):
    try:
        # Récupérer l'employé
        employee = execute_query("""
            SELECT e.id, e.matricule, e.lastname, e.firstname, e.email,
                   e.address, e.contact, e.national_id, e.birth_date, e.hire_date,
                   e.leave_balance, e.user_id,
                   i.department_id, i.position_id, i.salary
            FROM employees e
            LEFT JOIN informations i ON e.id = i.employee_id
            WHERE e.id = %s
        """, (employee_id,), fetch_one=True)

        if not employee:
            return jsonify({"error": "Employé introuvable"}), 404

        # Récupérer les photos liées
        photos = execute_query("""
            SELECT id, file_path, is_main
            FROM photos
            WHERE employee_id = %s
        """, (employee_id,), fetch_all=True)

        return jsonify({
            "employee": employee,
            "photos": photos
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500









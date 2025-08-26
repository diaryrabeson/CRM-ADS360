from flask import render_template, request, jsonify, flash, redirect, url_for, g
from . import prospects_bp
from database.db import execute_query
from utils.decorators import login_required, permission_required
from datetime import datetime, timedelta
import json

@prospects_bp.route('/')
@login_required
@permission_required('prospects', 'read')
def index():
    """Liste des prospects, clients et partenaires"""
    # Récupérer les filtres pour les prospects
    status = request.args.get('status', '')
    category = request.args.get('category', '')
    assigned_to = request.args.get('assigned_to', '')
    
    # Construire la requête pour les prospects
    query = """
        SELECT p.*, 
               u.first_name || ' ' || u.last_name as assigned_to_name,
               e.name as converted_entity_name
        FROM prospects p
        LEFT JOIN users u ON p.assigned_to = u.id
        LEFT JOIN entities e ON p.converted_entity_id = e.id
        WHERE 1=1
    """
    params = []
    
    if status:
        query += " AND p.status = %s"
        params.append(status)
    
    if category:
        query += " AND p.category = %s"
        params.append(category)
    
    if assigned_to:
        query += " AND p.assigned_to = %s"
        params.append(assigned_to)
    
    query += " ORDER BY p.created_at DESC"
    
    prospects = execute_query(query, params if params else None, fetch_all=True)
    
    # Récupérer les clients (prospects convertis en clients)
    clients_query = """
        SELECT p.*, 
               u.first_name || ' ' || u.last_name as assigned_to_name,
               e.name as converted_entity_name,
               e.created_at as converted_at
        FROM prospects p
        LEFT JOIN users u ON p.assigned_to = u.id
        LEFT JOIN entities e ON p.converted_entity_id = e.id
        WHERE p.status = 'Gagné' AND p.converted_to = 'client'
        ORDER BY p.converted_at DESC
    """
    clients = execute_query(clients_query, fetch_all=True)
    
    # Récupérer les partenaires (prospects convertis en partenaires)
    partners_query = """
        SELECT p.*, 
               u.first_name || ' ' || u.last_name as assigned_to_name,
               e.name as converted_entity_name,
               e.created_at as converted_at
        FROM prospects p
        LEFT JOIN users u ON p.assigned_to = u.id
        LEFT JOIN entities e ON p.converted_entity_id = e.id
        WHERE p.status = 'Gagné' AND p.converted_to = 'partner'
        ORDER BY p.converted_at DESC
    """
    partners = execute_query(partners_query, fetch_all=True)
    
    # Récupérer les commerciaux pour le filtre
    commercials = execute_query("""
        SELECT u.id, u.first_name || ' ' || u.last_name as name
        FROM users u
        JOIN roles r ON u.role_id = r.id
        WHERE r.name IN ('commercial_manager', 'super_admin', 'admin_entity')
        AND u.is_active = TRUE
        ORDER BY name
    """, fetch_all=True)
    
    # Statistiques
    stats = {
        'total': execute_query("SELECT COUNT(*) as count FROM prospects", fetch_one=True)['count'],
        'new': execute_query("SELECT COUNT(*) as count FROM prospects WHERE status = 'Nouveau'", fetch_one=True)['count'],
        'in_progress': execute_query("SELECT COUNT(*) as count FROM prospects WHERE status IN ('Contacté', 'En négociation')", fetch_one=True)['count'],
        'won': execute_query("SELECT COUNT(*) as count FROM prospects WHERE status = 'Gagné'", fetch_one=True)['count']
    }
    
    return render_template('prospects/index.html',
                         prospects=prospects,
                         clients=clients,
                         partners=partners,
                         commercials=commercials,
                         stats=stats,
                         filters={'status': status, 'category': category, 'assigned_to': assigned_to})

@prospects_bp.route('/create', methods=['GET', 'POST'])
@login_required
@permission_required('prospects', 'write')
def create():
    """Créer un nouveau prospect"""
    if request.method == 'POST':
        data = request.form if request.form else request.get_json()
        
        try:
            prospect_id = execute_query("""
                INSERT INTO prospects (
                    company_name, category, country, status, contact_name, contact_email,
                    contact_phone, sector, company_size, source, assigned_to,
                    notes
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                data.get('company_name'),
                data.get('category'),
                data.get('country'),
                data.get('status', 'Nouveau'),
                data.get('contact_name'),
                data.get('contact_email'),
                data.get('contact_phone'),
                data.get('sector'),
                data.get('company_size'),
                data.get('source'),
                data.get('assigned_to') or g.user['id'],
                data.get('notes')
            ), fetch_one=True, commit=True)
            
            # Première relance automatique
            execute_query("""
                INSERT INTO prospect_followups (prospect_id, scheduled_date, type, status)
                VALUES (%s, %s, 'phone', 'pending')
            """, (
                prospect_id['id'],
                datetime.now() + timedelta(days=3)
            ), commit=True)
            
            # Log d'audit
            execute_query("""
                INSERT INTO audit_logs (user_id, action, resource_type, resource_id)
                VALUES (%s, 'create_prospect', 'prospect', %s)
            """, (g.user['id'], prospect_id['id']), commit=True)
            
            flash('Prospect créé avec succès', 'success')
            
            if request.is_json:
                return jsonify({'success': True, 'id': prospect_id['id']})
            return redirect(url_for('prospects.index'))
            
        except Exception as e:
            if request.is_json:
                return jsonify({'error': str(e)}), 500
            flash(f'Erreur: {str(e)}', 'danger')
            return redirect(url_for('prospects.create'))
    
    # GET - Afficher le formulaire
    commercials = execute_query("""
        SELECT u.id, u.first_name || ' ' || u.last_name as name
        FROM users u
        JOIN roles r ON u.role_id = r.id
        WHERE r.name IN ('commercial_manager', 'super_admin')
        ORDER BY name
    """, fetch_all=True)
    
    return render_template('prospects/create.html', commercials=commercials)

@prospects_bp.route('/<int:prospect_id>')
@login_required
@permission_required('prospects', 'read')
def detail(prospect_id):
    """Détail d'un prospect (pour modal)"""
    try:
        # Récupérer le prospect
        prospect = execute_query("""
            SELECT p.*, 
                   u.first_name || ' ' || u.last_name as assigned_to_name,
                   e.name as converted_entity_name
            FROM prospects p
            LEFT JOIN users u ON p.assigned_to = u.id
            LEFT JOIN entities e ON p.converted_entity_id = e.id
            WHERE p.id = %s
        """, (prospect_id,), fetch_one=True)

        if not prospect:
            return jsonify({'error': 'Prospect introuvable'}), 404

        # Historique des interactions
        followups = execute_query("""
            SELECT f.*, u.first_name || ' ' || u.last_name as performed_by_name
            FROM prospect_followups f
            LEFT JOIN users u ON f.performed_by = u.id
            WHERE f.prospect_id = %s
            ORDER BY f.scheduled_date DESC
        """, (prospect_id,), fetch_all=True)

        return jsonify({
            'success': True,
            'prospect': prospect,
            'followups': followups
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@prospects_bp.route('/<int:prospect_id>/edit', methods=['GET', 'POST'])
@login_required
@permission_required('prospects', 'write')
def edit(prospect_id):
    """Modifier un prospect existant via modal (JSON)"""
    try:
        prospect = execute_query("SELECT * FROM prospects WHERE id = %s", (prospect_id,), fetch_one=True)
        if not prospect:
            return jsonify({'error': 'Prospect introuvable'}), 404

        if request.method == 'POST':
            data = request.get_json()
            execute_query("""
                UPDATE prospects SET
                    company_name=%s, category=%s, status=%s, contact_name=%s,
                    contact_email=%s, contact_phone=%s, sector=%s,
                    company_size=%s, source=%s, assigned_to=%s, notes=%s
                WHERE id=%s
            """, (
                data.get('company_name'),
                data.get('category'),
                data.get('status'),
                data.get('contact_name'),
                data.get('contact_email'),
                data.get('contact_phone'),
                data.get('sector'),
                data.get('company_size'),
                data.get('source'),
                data.get('assigned_to') or g.user['id'],
                data.get('notes'),
                prospect_id
            ), commit=True)
            return jsonify({'success': True})

        # GET - retourner les données du prospect pour remplir le modal
        commercials = execute_query("""
            SELECT u.id, u.first_name || ' ' || u.last_name as name
            FROM users u
            JOIN roles r ON u.role_id = r.id
            WHERE r.name IN ('commercial_manager', 'super_admin')
            ORDER BY name
        """, fetch_all=True)

        return jsonify({
            'success': True,
            'prospect': prospect,
            'commercials': commercials
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@prospects_bp.route('/<int:prospect_id>/convert', methods=['POST'])
@login_required
@permission_required('prospects', 'write')
def convert(prospect_id):
    """Convertir un prospect en client ou partenaire"""
    data = request.get_json()
    conversion_type = data.get('type')  # 'client' ou 'partner'
    
    if conversion_type not in ['client', 'partner']:
        return jsonify({'error': 'Type de conversion invalide'}), 400
    
    try:
        # Récupérer le prospect
        prospect = execute_query(
            "SELECT * FROM prospects WHERE id = %s",
            (prospect_id,),
            fetch_one=True
        )
        if not prospect:
            return jsonify({'error': 'Prospect introuvable'}), 404

        # Préparer les données supplémentaires
        additional_data = {}
        if conversion_type == 'partner':
            additional_data = {
                'partnership_type': data.get('partnership_type', 'Commercial'),
                'start_date': data.get('start_date', datetime.now().isoformat())
            }

        # Créer l'entité
        entity_id = execute_query("""
            INSERT INTO entities (name, type, address, email, phone, additional_data)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            prospect['company_name'],
            conversion_type,
            prospect['country'],
            prospect['contact_email'],
            prospect['contact_phone'],
            json.dumps(additional_data) if additional_data else '{}'
        ), fetch_one=True, commit=True)['id']

        # Créer l'utilisateur
        from blueprints.auth.utils import hash_password
        temp_password = 'TempPass123!'
        contact_name = prospect.get('contact_name') or ''
        first_name = contact_name.split()[0] if contact_name else ''
        last_name = ' '.join(contact_name.split()[1:]) if contact_name else ''

        # Vérifier le rôle
        role_name = conversion_type
        role = execute_query("SELECT id FROM roles WHERE name = %s", (role_name,), fetch_one=True)
        if not role:
            return jsonify({'error': f"Role '{role_name}' non trouvé"}), 500

        user_id = execute_query("""
            INSERT INTO users (
                email, password_hash, first_name, last_name, phone,
                role_id, entity_id, must_change_password
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE)
            RETURNING id
        """, (
            prospect['contact_email'],
            hash_password(temp_password),
            first_name,
            last_name,
            prospect['contact_phone'],
            role['id'],
            entity_id
        ), fetch_one=True, commit=True)['id']

        # Mettre à jour le prospect
        execute_query("""
            UPDATE prospects 
            SET status = 'Gagné', 
                converted_at = CURRENT_TIMESTAMP,
                converted_to = %s,
                converted_entity_id = %s
            WHERE id = %s
        """, (conversion_type, entity_id, prospect_id), commit=True)

        # Log d'audit
        execute_query("""
            INSERT INTO audit_logs (user_id, action, resource_type, resource_id, new_values)
            VALUES (%s, 'convert_prospect', 'prospect', %s, %s)
        """, (
            g.user['id'],
            prospect_id,
            json.dumps({'type': conversion_type, 'entity_id': entity_id, 'user_id': user_id})
        ), commit=True)

        # TODO: Envoyer un email avec les identifiants

        return jsonify({
            'success': True,
            'message': f'Prospect converti en {conversion_type} avec succès',
            'entity_id': entity_id,
            'user_id': user_id
        })

    except Exception as e:
        import traceback
        print(traceback.format_exc())  # affichage console pour debugging
        return jsonify({'error': str(e)}), 500


@prospects_bp.route('/<int:prospect_id>/followup', methods=['POST'])
@login_required
@permission_required('prospects', 'write')
def add_followup(prospect_id):
    """Ajouter une relance"""
    data = request.get_json()
    
    try:
        followup_id = execute_query("""
            INSERT INTO prospect_followups (
                prospect_id, scheduled_date, type, notes, performed_by
            ) VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, (
            prospect_id,
            data.get('scheduled_date'),
            data.get('type', 'phone'),
            data.get('notes'),
            g.user['id']
        ), fetch_one=True, commit=True)
        
        return jsonify({'success': True, 'id': followup_id['id']})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Nouvelle route pour créer directement un client
@prospects_bp.route('/create-client', methods=['POST'])
@login_required
@permission_required('prospects', 'write')
def create_client():
    """Créer directement un client (sans passer par un prospect)"""
    data = request.get_json()
    
    try:
        # Créer l'entité client
        entity_id = execute_query("""
            INSERT INTO entities (name, type, email, phone, address)
            VALUES (%s, 'client', %s, %s, %s)
            RETURNING id
        """, (
            data.get('company_name'),
            data.get('contact_email'),
            data.get('contact_phone'),
            data.get('address')
        ), fetch_one=True, commit=True)['id']
        
        # Créer l'utilisateur
        from blueprints.auth.utils import hash_password
        temp_password = 'TempPass123!'
        
        user_id = execute_query("""
            INSERT INTO users (
                email, password_hash, first_name, last_name, phone,
                role_id, entity_id, must_change_password
            )
            VALUES (%s, %s, %s, %s, %s, 
                   (SELECT id FROM roles WHERE name = 'client'), %s, TRUE)
            RETURNING id
        """, (
            data.get('contact_email'),
            hash_password(temp_password),
            data.get('contact_name').split()[0] if data.get('contact_name') else '',
            ' '.join(data.get('contact_name').split()[1:]) if data.get('contact_name') else '',
            data.get('contact_phone'),
            entity_id
        ), fetch_one=True, commit=True)['id']
        
        # TODO: Envoyer un email avec les identifiants
        
        return jsonify({
            'success': True,
            'message': 'Client créé avec succès',
            'entity_id': entity_id,
            'user_id': user_id
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@prospects_bp.route('/create-partner', methods=['POST'])
@login_required
@permission_required('prospects', 'write')
def create_partner():
    """Créer directement un partenaire (insertion dans prospects avec status Gagné + création entité + utilisateur)"""
    data = request.get_json()

    try:
        # 1. Insérer le prospect (status forcé à Gagné)
        prospect = execute_query("""
            INSERT INTO prospects (
                company_name, status, contact_name, contact_email,
                contact_phone, source, assigned_to, notes
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            data.get('company_name'),
            'Gagné',   # status forcé
            data.get('contact_name'),
            data.get('contact_email'),
            data.get('contact_phone'),
            data.get('source'),
            data.get('assigned_to') or g.user['id'],
            data.get('notes')
        ), fetch_one=True, commit=True)

        prospect_id = prospect['id']

        # 2. Log d’audit (après insertion prospect)
        execute_query("""
            INSERT INTO audit_logs (user_id, action, resource_type, resource_id)
            VALUES (%s, 'create_prospect', 'prospect', %s)
        """, (g.user['id'], prospect_id), commit=True)

        # 3. Insérer dans entities
        additional_data = {
            'partnership_type': data.get('partnership_type', 'Commercial'),
            'start_date': data.get('start_date', datetime.now().isoformat())
        }

        entity = execute_query("""
            INSERT INTO entities (name, type, email, phone, address, additional_data)
            VALUES (%s, 'partner', %s, %s, %s, %s)
            RETURNING id
        """, (
            data.get('company_name'),
            data.get('contact_email'),
            data.get('contact_phone'),
            data.get('country'),
            json.dumps(additional_data)
        ), fetch_one=True, commit=True)

        entity_id = entity['id']

        # 4. Créer l’utilisateur associé
        from blueprints.auth.utils import hash_password
        temp_password = 'TempPass123!'

        user = execute_query("""
            INSERT INTO users (
                email, password_hash, first_name, last_name, phone,
                role_id, entity_id, must_change_password
            )
            VALUES (%s, %s, %s, %s, %s, 
                   (SELECT id FROM roles WHERE name = 'partner'), %s, TRUE)
            RETURNING id
        """, (
            data.get('contact_email'),
            hash_password(temp_password),
            data.get('contact_name').split()[0] if data.get('contact_name') else '',
            ' '.join(data.get('contact_name').split()[1:]) if data.get('contact_name') else '',
            data.get('contact_phone'),
            entity_id
        ), fetch_one=True, commit=True)

        user_id = user['id']

        # ✅ Réponse finale
        return jsonify({
            'success': True,
            'message': 'Partenaire créé avec succès',
            'prospect_id': prospect_id,
            'entity_id': entity_id,
            'user_id': user_id
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

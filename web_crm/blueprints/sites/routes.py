from flask import render_template, request, jsonify, flash, redirect, url_for, g
from . import sites_bp
from database.db import execute_query
from utils.decorators import login_required, permission_required
import json

@sites_bp.route('/')
@login_required
@permission_required('sites', 'read')
def index(): 
    """Liste des sites"""
    role = g.user.get('role_name') if isinstance(g.user, dict) else None
    # Filtrer selon le rôle
    if role == 'partner':
        sites = execute_query("""
            SELECT s.*, c.name as city_name, co.name as country_name,
                   COUNT(se.id) as equipment_count
            FROM sites s
            LEFT JOIN cities c ON s.city_id = c.geonameid
            LEFT JOIN countries co ON c.country_code = co.iso2
            LEFT JOIN site_equipment se ON s.id = se.site_id AND se.status = 'active'
            WHERE s.entity_id = %s
            GROUP BY s.id, c.name, co.name
            ORDER BY co.name, c.name, s.name
        """, (g.user['entity_id'],), fetch_all=True)
    else:
        sites = execute_query("""
            SELECT s.*, c.name as city_name, co.name as country_name,
                   e.name as entity_name,
                   COUNT(se.id) as equipment_count
            FROM sites s
            LEFT JOIN cities c ON s.city_id = c.geonameid
            LEFT JOIN countries co ON c.country_code = co.iso2
            LEFT JOIN entities e ON s.entity_id = e.id
            LEFT JOIN site_equipment se ON s.id = se.site_id AND se.status = 'active'
            GROUP BY s.id, c.name, co.name, e.name
            ORDER BY co.name, c.name, s.name
        """, fetch_all=True)

        if role not in ['partner', 'client']:
            entities = execute_query("""
                SELECT id, name, address FROM entities 
                WHERE type = 'partner' 
                ORDER BY name
            """, fetch_all=True)
        else:
            entities = []

    
    stats = {
        'total_sites': len(sites),
        'active_sites': sum(1 for s in sites if s.get('is_active')),
        'equipped_sites': sum(1 for s in sites if s.get('equipment_count', 0) > 0),
        'partner_sites': sum(1 for s in sites if s.get('entity_id'))
    }
    print(g.user)

    return render_template('sites/index.html', sites=sites, stats=stats, partners=entities, role=role)

    
@sites_bp.route('/create', methods=['POST'])
@login_required
@permission_required('sites', 'write')
def create():
    """Créer un nouveau site via modal (JSON seulement)"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Données JSON manquantes'}), 400
            
        print("DEBUG - Données reçues:", data)
        
        try:
            # Déterminer l'entity_id - le champ 'partner' contient l'ID de l'entité
            entity_id = data.get('partner')
            if not entity_id:
                return jsonify({'success': False, 'error': "Veuillez sélectionner un partenaire"}), 400

            # Validation des champs obligatoires - utiliser 'city' au lieu de 'city_id'
            required_fields = ['name', 'type', 'city', 'address_line']
            for field in required_fields:
                if not data.get(field):
                    return jsonify({'success': False, 'error': f"Le champ {field} est obligatoire"}), 400

            # Préparer les données pour l'insertion
            site_data = {
                'name': data.get('name'),
                'type': data.get('type'),
                'entity_id': entity_id,
                'city_id': data.get('city'),  # Utiliser 'city' comme 'city_id'
                'address': data.get('address_line'),
                'latitude': data.get('latitude') or None,
                'longitude': data.get('longitude') or None,
                'opening_hours': data.get('opening_hours', {}),
                'capacity': data.get('capacity') or None,
                'is_active': data.get('is_active', True)
            }

            # Insertion dans la base de données
            site_id = execute_query("""
                INSERT INTO sites (
                    name, type, entity_id, city_id, address,
                    latitude, longitude, opening_hours, capacity, is_active
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                site_data['name'],
                site_data['type'],
                site_data['entity_id'],
                site_data['city_id'],
                site_data['address'],
                site_data['latitude'],
                site_data['longitude'],
                json.dumps(site_data['opening_hours']),
                site_data['capacity'],
                site_data['is_active']
            ), fetch_one=True, commit=True)['id']

            # Log d'audit
            execute_query("""
                INSERT INTO audit_logs (user_id, action, resource_type, resource_id)
                VALUES (%s, 'create_site', 'site', %s)
            """, (g.user['id'], site_id), commit=True)

            # Réponse JSON pour le modal
            return jsonify({
                'success': True, 
                'id': site_id, 
                'message': 'Site créé avec succès',
                'redirect': url_for('sites.index')
            })
            
        except Exception as e:
            error_msg = f"Erreur lors de la création: {str(e)}"
            print(f"ERROR: {error_msg}")
            return jsonify({'success': False, 'error': error_msg}), 500
                
    except Exception as e:
        error_msg = f"Erreur inattendue: {str(e)}"
        print(f"CRITICAL ERROR: {error_msg}")
        return jsonify({'success': False, 'error': error_msg}), 500

@sites_bp.route('/<int:site_id>')
@login_required
@permission_required('sites', 'read')
def detail(site_id):
    """Détail d'un site pour modal (JSON)"""
    site = execute_query("""
        SELECT s.*, c.name as city_name, co.name as country_name,
               e.name as entity_name
        FROM sites s
        LEFT JOIN cities c ON s.city_id = c.geonameid
        LEFT JOIN countries co ON c.country_code = co.iso2
        LEFT JOIN entities e ON s.entity_id = e.id
        WHERE s.id = %s
    """, (site_id,), fetch_one=True)

    if not site:
        return jsonify({'error': 'Site introuvable'}), 404

    # Équipements installés
    equipment = execute_query("""
        SELECT se.*, e.name, e.type, e.serial_number,
               u.first_name || ' ' || u.last_name as installed_by_name
        FROM site_equipment se
        JOIN equipment e ON se.equipment_id = e.id
        LEFT JOIN users u ON se.installed_by = u.id
        WHERE se.site_id = %s AND se.status = 'active'
        ORDER BY se.installation_date DESC
    """, (site_id,), fetch_all=True)

    site['equipment'] = equipment
    return jsonify(site)



@sites_bp.route('/partners')
@login_required
@permission_required('sites', 'read')
def get_partners():
    """Récupérer la liste des partenaires avec leurs données de localisation"""
    partners = execute_query("""
        SELECT id, name, address, additional_data
        FROM entities
        WHERE type = 'partner'
        ORDER BY name
    """, fetch_all=True)

    # Ajouter le code pays si nécessaire
    for partner in partners:
        if partner.get('additional_data'):
            additional = json.loads(partner['additional_data'])
            partner['country_code'] = additional.get('country_code', '')
            
    return jsonify(partners)

@sites_bp.route('/api/equipment/available')
@login_required
@permission_required('sites', 'read')
def available_equipment():
    """Récupérer les équipements disponibles avec quantités"""
    equipment = execute_query("""
        SELECT 
            e.id,
            e.name,
            e.type,
            e.serial_number,
            e.model,
            e.manufacturer,
            e.status,
            COALESCE(SUM(s.quantity), 0) as available_quantity
        FROM equipment e
        LEFT JOIN stock s ON e.id = s.equipment_id AND s.warehouse_id IS NOT NULL
        WHERE e.status = 'available'
        GROUP BY e.id, e.name, e.type, e.serial_number, e.model, e.manufacturer, e.status
        HAVING COALESCE(SUM(s.quantity), 0) > 0
        ORDER BY e.name
    """, fetch_all=True)
    
    return jsonify(equipment)

@sites_bp.route('/api/equipment/<int:equipment_id>/available-quantity')
@login_required
@permission_required('sites', 'read')
def equipment_available_quantity(equipment_id):
    """Récupérer la quantité disponible pour un équipement spécifique"""
    result = execute_query("""
        SELECT COALESCE(SUM(quantity), 0) as available_quantity
        FROM stock 
        WHERE equipment_id = %s AND warehouse_id IS NOT NULL
    """, (equipment_id,), fetch_one=True)
    
    return jsonify({'available_quantity': result['available_quantity']})

@sites_bp.route('/<int:site_id>/equipment')
@login_required
@permission_required('sites', 'read')
def site_equipment(site_id):
    """Récupérer les équipements d'un site avec quantités"""
    equipment = execute_query("""
        SELECT se.*, e.name, e.type, e.serial_number, e.model,
               u.first_name || ' ' || u.last_name as installed_by_name,
               se.quantity as current_quantity  -- Simplified without removed_quantity
        FROM site_equipment se
        JOIN equipment e ON se.equipment_id = e.id
        LEFT JOIN users u ON se.installed_by = u.id
        WHERE se.site_id = %s AND se.status = 'active'
        ORDER BY se.installation_date DESC
    """, (site_id,), fetch_all=True)
    
    return jsonify({'equipment': equipment})

@sites_bp.route('/equipment/install', methods=['POST'])
@login_required
@permission_required('sites', 'write')
def install_equipment():
    """Installer des équipements sur un site avec quantité"""
    data = request.get_json()
    
    try:
        quantity = int(data.get('quantity', 1))
        if quantity <= 0:
            return jsonify({'success': False, 'error': 'Quantité invalide'}), 400
        
        # Vérifier le stock disponible
        available_stock = execute_query("""
            SELECT COALESCE(SUM(quantity), 0) as available
            FROM stock 
            WHERE equipment_id = %s AND warehouse_id IS NOT NULL
        """, (data['equipment_id'],), fetch_one=True)['available']
        
        if available_stock < quantity:
            return jsonify({
                'success': False, 
                'error': f'Stock insuffisant. Disponible: {available_stock}, Demandé: {quantity}'
            }), 400
        
        # Vérifier si une installation existe déjà pour cet équipement sur ce site
        existing_installation = execute_query("""
            SELECT id FROM site_equipment 
            WHERE site_id = %s AND equipment_id = %s AND status = 'active'
        """, (data['site_id'], data['equipment_id']), fetch_one=True)
        
        if existing_installation:
            # Mettre à jour la quantité existante
            execute_query("""
                UPDATE site_equipment 
                SET quantity = quantity + %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (quantity, existing_installation['id']), commit=True)
            installation_id = existing_installation['id']
        else:
            # Créer une nouvelle installation
            installation_id = execute_query("""
                INSERT INTO site_equipment (
                    site_id, equipment_id, installation_date, 
                    installed_by, notes, status, quantity
                ) VALUES (%s, %s, %s, %s, %s, 'active', %s)
                RETURNING id
            """, (
                data['site_id'],
                data['equipment_id'],
                data.get('installation_date'),
                g.user['id'],
                data.get('notes', ''),
                quantity
            ), fetch_one=True, commit=True)['id']
        
        # Réduire le stock disponible
        # On retire d'abord des entrepôts qui ont cet équipement
        # Réduire le stock disponible dans les entrepôts
        warehouses_with_stock = execute_query("""
            SELECT id, warehouse_id, quantity
            FROM stock 
            WHERE equipment_id = %s AND warehouse_id IS NOT NULL
            AND quantity > 0
            ORDER BY quantity DESC
        """, (data['equipment_id'],), fetch_all=True)

        remaining_quantity = quantity
        for warehouse_stock in warehouses_with_stock:
            if remaining_quantity <= 0:
                break
                
            quantity_to_take = min(remaining_quantity, warehouse_stock['quantity'])
            
            # Diminuer directement la quantité dans le stock
            execute_query("""
                UPDATE stock 
                SET quantity = quantity - %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (quantity_to_take, warehouse_stock['id']), commit=True)
            
            # Créer un mouvement de stock pour tracer l'opération
            execute_query("""
                INSERT INTO stock_movements (
                    equipment_id, from_type, from_id, to_type, to_id,
                    quantity, reason, performed_by
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                data['equipment_id'],
                'warehouse',
                warehouse_stock['warehouse_id'],
                'site',
                data['site_id'],
                quantity_to_take,
                'Installation sur site',
                g.user['id']
            ), commit=True)
            
            remaining_quantity -= quantity_to_take
        
        # Log d'audit
        execute_query("""
            INSERT INTO audit_logs (user_id, action, resource_type, resource_id, new_values)
            VALUES (%s, 'install_equipment', 'equipment', %s, %s)
        """, (
            g.user['id'],
            data['equipment_id'],
            json.dumps({
                'site_id': data['site_id'], 
                'installation_date': data.get('installation_date'),
                'quantity': quantity
            })
        ), commit=True)
        
        return jsonify({'success': True, 'installation_id': installation_id})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@sites_bp.route('/equipment/<int:installation_id>/remove', methods=['POST'])
@login_required
@permission_required('sites', 'write')
def remove_equipment(installation_id):
    """Retirer des équipements d'un site avec quantité"""
    data = request.get_json()
    
    try:
        quantity_to_remove = int(data.get('quantity', 1))
        if quantity_to_remove <= 0:
            return jsonify({'success': False, 'error': 'Quantité invalide'}), 400
        
        # Récupérer les infos de l'installation
        installation = execute_query("""
            SELECT * FROM site_equipment WHERE id = %s
        """, (installation_id,), fetch_one=True)
        
        if not installation:
            return jsonify({'success': False, 'error': 'Installation non trouvée'}), 404
        
        current_quantity = installation['quantity'] - (installation['removed_quantity'] or 0)
        if quantity_to_remove > current_quantity:
            return jsonify({
                'success': False, 
                'error': f'Quantité trop élevée. Installé: {current_quantity}, Demandé: {quantity_to_remove}'
            }), 400
        
        # Mettre à jour la quantité retirée
        execute_query("""
            UPDATE site_equipment 
            SET removed_quantity = COALESCE(removed_quantity, 0) + %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (quantity_to_remove, installation_id), commit=True)
        
        # Si toute la quantité est retirée, marquer comme complètement retiré
        if (installation['quantity'] - (installation['removed_quantity'] or 0) - quantity_to_remove) <= 0:
            execute_query("""
                UPDATE site_equipment 
                SET status = 'removed', removed_date = CURRENT_DATE, removed_by = %s
                WHERE id = %s
            """, (g.user['id'], installation_id), commit=True)
        
        # Remettre le stock dans l'entrepôt principal ou un entrepôt par défaut
        # Remettre le stock dans l'entrepôt principal
        main_warehouse = execute_query("""
            SELECT id FROM warehouses ORDER BY id LIMIT 1
        """, fetch_one=True)

        if main_warehouse:
            # Vérifier si le stock existe déjà pour cet équipement dans l'entrepôt
            existing_stock = execute_query("""
                SELECT id FROM stock 
                WHERE equipment_id = %s AND warehouse_id = %s
            """, (installation['equipment_id'], main_warehouse['id']), fetch_one=True)
            
            if existing_stock:
                # Augmenter la quantité existante
                execute_query("""
                    UPDATE stock 
                    SET quantity = quantity + %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (quantity_to_remove, existing_stock['id']), commit=True)
            else:
                # Créer un nouveau stock
                execute_query("""
                    INSERT INTO stock (equipment_id, warehouse_id, quantity, min_quantity)
                    VALUES (%s, %s, %s, 0)
                """, (installation['equipment_id'], main_warehouse['id'], quantity_to_remove), commit=True)
            
            # Créer un mouvement de stock pour tracer l'opération
            execute_query("""
                INSERT INTO stock_movements (
                    equipment_id, from_type, from_id, to_type, to_id,
                    quantity, reason, performed_by
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                installation['equipment_id'],
                'site',
                installation['site_id'],
                'warehouse',
                main_warehouse['id'],
                quantity_to_remove,
                'Retour en stock depuis site',
                g.user['id']
            ), commit=True)
        
        # Log d'audit
        execute_query("""
            INSERT INTO audit_logs (user_id, action, resource_type, resource_id)
            VALUES (%s, 'remove_equipment', 'equipment', %s)
        """, (g.user['id'], installation['equipment_id']), commit=True)
        
        return jsonify({'success': True, 'remaining_quantity': current_quantity - quantity_to_remove})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
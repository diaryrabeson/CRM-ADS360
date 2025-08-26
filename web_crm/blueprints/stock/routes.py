from flask import render_template, request, jsonify, flash, redirect, url_for, g
from . import stock_bp
from database.db import execute_query
from utils.decorators import login_required, permission_required
from datetime import date, datetime

@stock_bp.route('/')
@login_required
@permission_required('stock', 'read')
def index():
    """Vue d'ensemble du stock"""
    # Inventaire par entrepôt
    warehouses = execute_query("""
        SELECT w.*, u.first_name || ' ' || u.last_name as manager_name,
               COUNT(DISTINCT s.equipment_id) as equipment_types,
               SUM(s.quantity) as total_quantity
        FROM warehouses w
        LEFT JOIN users u ON w.manager_id = u.id
        LEFT JOIN stock s ON w.id = s.warehouse_id
        GROUP BY w.id, u.first_name, u.last_name
        ORDER BY w.name
    """, fetch_all=True)
    
    # Équipements en stock
    equipment_stock = execute_query("""
        SELECT e.*, 
               SUM(s.quantity) as total_stock,
               COUNT(DISTINCT s.warehouse_id) as warehouse_count
        FROM equipment e
        LEFT JOIN stock s ON e.id = s.equipment_id
        WHERE e.status IN ('available', 'installed')
        GROUP BY e.id
        ORDER BY e.name
    """, fetch_all=True)
    
    # Alertes de stock minimum
    low_stock_alerts = execute_query("""
        SELECT e.name as equipment_name, w.name as warehouse_name,
               s.quantity, s.min_quantity
        FROM stock s
        JOIN equipment e ON s.equipment_id = e.id
        JOIN warehouses w ON s.warehouse_id = w.id
        WHERE s.quantity <= s.min_quantity
        ORDER BY (s.quantity::float / NULLIF(s.min_quantity, 0))
    """, fetch_all=True)
    
    # Statistiques
    stats = {
        'total_equipment': execute_query("SELECT COUNT(*) as count FROM equipment", fetch_one=True)['count'],
        'total_warehouses': len(warehouses),
        'low_stock_items': len(low_stock_alerts),
        'recent_movements': execute_query(
            "SELECT COUNT(*) as count FROM stock_movements WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'",
            fetch_one=True
        )['count']
    }
    
    return render_template('stock/index.html',
                         warehouses=warehouses,
                         equipment_stock=equipment_stock,
                         low_stock_alerts=low_stock_alerts,
                         stats=stats)

@stock_bp.route('/api/sites')
@login_required
def get_sites():
    equipment_id = request.args.get('equipment_id')
    if equipment_id:
        # Corriger c.id en c.geonameid
        sites = execute_query("""
            SELECT s.*, c.name as city_name
            FROM sites s
            LEFT JOIN cities c ON s.city_id = c.geonameid
            LEFT JOIN warehouses w ON s.warehouse_id = w.id
            LEFT JOIN stock st ON w.id = st.warehouse_id
            WHERE st.equipment_id = %s AND st.quantity > 0
        """, (equipment_id,), fetch_all=True)
    else:
        sites = execute_query("""
            SELECT s.*, c.name as city_name
            FROM sites s
            LEFT JOIN cities c ON s.city_id = c.geonameid
            WHERE s.is_active = TRUE
        """, fetch_all=True)
    
    return jsonify(sites)

@stock_bp.route('/api/warehouses')
@login_required
def get_warehouses():
    """Récupérer tous les entrepôts ou filtrer par équipement"""
    equipment_id = request.args.get('equipment_id')
    filter_type = request.args.get('filter_type', 'all')
    
    if equipment_id and filter_type == 'with_stock':
        # Récupérer seulement les entrepôts qui ont cet équipement en stock
        warehouses = execute_query("""
            SELECT w.*, u.first_name || ' ' || u.last_name as manager_name, s.quantity
            FROM warehouses w
            LEFT JOIN users u ON w.manager_id = u.id
            JOIN stock s ON w.id = s.warehouse_id
            WHERE s.equipment_id = %s AND s.quantity > 0
            ORDER BY w.name
        """, (equipment_id,), fetch_all=True)
    else:
        # Récupérer tous les entrepôts
        warehouses = execute_query("""
            SELECT w.*, u.first_name || ' ' || u.last_name as manager_name
            FROM warehouses w
            LEFT JOIN users u ON w.manager_id = u.id
            ORDER BY w.name
        """, fetch_all=True)
    
    return jsonify(warehouses)

@stock_bp.route('/api/sites/installed-equipment')
@login_required
def get_sites_with_equipment():
    """Récupérer les sites qui ont des équipements installés"""
    equipment_id = request.args.get('equipment_id')
    
    if equipment_id:
        sites = execute_query("""
            SELECT s.*, c.name as city_name, e.name as entity_name
            FROM sites s
            LEFT JOIN cities c ON s.city_id = c.geonameid
            LEFT JOIN entities e ON s.entity_id = e.id
            JOIN site_equipment se ON s.id = se.site_id
            WHERE se.equipment_id = %s AND se.status = 'active'
            ORDER BY s.name
        """, (equipment_id,), fetch_all=True)
    else:
        sites = execute_query("""
            SELECT DISTINCT s.*, c.name as city_name, e.name as entity_name
            FROM sites s
            LEFT JOIN cities c ON s.city_id = c.geonameid
            LEFT JOIN entities e ON s.entity_id = e.id
            JOIN site_equipment se ON s.id = se.site_id
            WHERE se.status = 'active' AND s.is_active = TRUE
            ORDER BY s.name
        """, fetch_all=True)
    
    return jsonify(sites)

@stock_bp.route('/api/warehouse/<int:warehouse_id>/sites')
@login_required
def get_warehouse_sites(warehouse_id):
    """Récupérer les sites desservis par un entrepôt"""
    sites = execute_query("""
        SELECT s.*, c.name as city_name, e.name as entity_name
        FROM sites s
        LEFT JOIN cities c ON s.city_id = c.geonameid
        LEFT JOIN entities e ON s.entity_id = e.id
        WHERE s.warehouse_id = %s AND s.is_active = TRUE
        ORDER BY s.name
    """, (warehouse_id,), fetch_all=True)
    
    return jsonify(sites)

@stock_bp.route('/warehouses/create', methods=['POST'])
@login_required
@permission_required('stock', 'write')
def create_warehouse():
    data = request.get_json()
    
    # Gérer le manager_id optionnel
    manager_id = data.get('manager_id')
    if manager_id == '':
        manager_id = None
    
    try:
        warehouse_id = execute_query("""
            INSERT INTO warehouses (name, location, manager_id)
            VALUES (%s, %s, %s)
            RETURNING id
        """, (data['name'], data['location'], manager_id), fetch_one=True, commit=True)['id']
        
        return jsonify({'success': True, 'warehouse_id': warehouse_id})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@stock_bp.route('/warehouses/<int:warehouse_id>/assign-manager', methods=['POST'])
@login_required
@permission_required('stock', 'write')
def assign_warehouse_manager(warehouse_id):
    data = request.get_json()
    manager_id = data.get('manager_id')
    
    if manager_id == '':
        manager_id = None
    
    execute_query("""
        UPDATE warehouses 
        SET manager_id = %s, updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
    """, (manager_id, warehouse_id), commit=True)
    
    return jsonify({'success': True})

@stock_bp.route('/api/equipment/<int:equipment_id>/warehouses')
@login_required
def get_equipment_warehouses(equipment_id):
    """Trouver les entrepôts qui ont cet équipement en stock"""
    warehouses = execute_query("""
        SELECT w.*, s.quantity
        FROM warehouses w
        JOIN stock s ON w.id = s.warehouse_id
        WHERE s.equipment_id = %s AND s.quantity > 0
        ORDER BY s.quantity DESC
    """, (equipment_id,), fetch_all=True)
    
    return jsonify(warehouses)

@stock_bp.route('/movements')
@login_required
@permission_required('stock', 'read')
def movements():
    """Historique des mouvements de stock"""
    movements = execute_query("""
        SELECT sm.*, e.name as equipment_name,
               u.first_name || ' ' || u.last_name as performed_by_name,
               CASE 
                   WHEN sm.from_type = 'warehouse' THEN wf.name
                   WHEN sm.from_type = 'site' THEN sf.name
               END as from_location,
               CASE 
                   WHEN sm.to_type = 'warehouse' THEN wt.name
                   WHEN sm.to_type = 'site' THEN st.name
               END as to_location
        FROM stock_movements sm
        JOIN equipment e ON sm.equipment_id = e.id
        LEFT JOIN users u ON sm.performed_by = u.id
        LEFT JOIN warehouses wf ON sm.from_type = 'warehouse' AND sm.from_id = wf.id
        LEFT JOIN sites sf ON sm.from_type = 'site' AND sm.from_id = sf.id
        LEFT JOIN warehouses wt ON sm.to_type = 'warehouse' AND sm.to_id = wt.id
        LEFT JOIN sites st ON sm.to_type = 'site' AND sm.to_id = st.id
        ORDER BY sm.created_at DESC
        LIMIT 100
    """, fetch_all=True)
    
    return render_template('stock/movements.html', movements=movements)

@stock_bp.route('/transfer', methods=['GET', 'POST'])
@login_required
@permission_required('stock', 'write')
def transfer():
    """Effectuer un transfert de stock"""
    if request.method == 'POST':
        data = request.get_json()
        
        try:
            # CORRECTION: Convertir explicitement les types
            equipment_id = int(data['equipment_id'])
            from_id = int(data['from_id'])
            to_id = int(data['to_id'])
            quantity = int(data['quantity'])  # Conversion importante ici
            
            # Vérifier la disponibilité du stock
            if data['from_type'] == 'warehouse':
                current_stock = execute_query("""
                    SELECT quantity FROM stock 
                    WHERE equipment_id = %s AND warehouse_id = %s
                """, (equipment_id, from_id), fetch_one=True)
                
                # CORRECTION: Maintenant on compare int avec int
                if not current_stock or current_stock['quantity'] < quantity:
                    return jsonify({'error': 'Stock insuffisant'}), 400
            
            # Enregistrer le mouvement
            movement_id = execute_query("""
                INSERT INTO stock_movements (
                    equipment_id, from_type, from_id, to_type, to_id,
                    quantity, reason, performed_by
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                equipment_id,
                data['from_type'],
                from_id,
                data['to_type'],
                to_id,
                quantity,
                data.get('reason', 'Transfert'),
                g.user['id']
            ), fetch_one=True, commit=True)['id']
            
            # Mettre à jour les stocks
            if data['from_type'] == 'warehouse':
                execute_query("""
                    UPDATE stock 
                    SET quantity = quantity - %s, updated_at = CURRENT_TIMESTAMP
                    WHERE equipment_id = %s AND warehouse_id = %s
                """, (quantity, equipment_id, from_id), commit=True)
            
            if data['to_type'] == 'warehouse':
                # Vérifier si l'enregistrement existe
                existing = execute_query("""
                    SELECT id FROM stock 
                    WHERE equipment_id = %s AND warehouse_id = %s
                """, (equipment_id, to_id), fetch_one=True)
                
                if existing:
                    execute_query("""
                        UPDATE stock 
                        SET quantity = quantity + %s, updated_at = CURRENT_TIMESTAMP
                        WHERE equipment_id = %s AND warehouse_id = %s
                    """, (quantity, equipment_id, to_id), commit=True)
                else:
                    execute_query("""
                        INSERT INTO stock (equipment_id, warehouse_id, quantity)
                        VALUES (%s, %s, %s)
                    """, (equipment_id, to_id, quantity), commit=True)
            
            elif data['to_type'] == 'site':
                # Créer l'installation sur le site
                execute_query("""
                    INSERT INTO site_equipment (
                        site_id, equipment_id, installation_date, installed_by, status
                    ) VALUES (%s, %s, CURRENT_DATE, %s, 'active')
                """, (to_id, equipment_id, g.user['id']), commit=True)
            
            return jsonify({'success': True, 'movement_id': movement_id})
            
        except ValueError as ve:
            return jsonify({'error': f'Données invalides: {str(ve)}'}), 400
        except Exception as e:
            return jsonify({'error': f'Erreur serveur: {str(e)}'}), 500
    
    # GET - Formulaire de transfert
    equipment = execute_query("SELECT * FROM equipment WHERE status = 'available' ORDER BY name", fetch_all=True)
    warehouses = execute_query("SELECT * FROM warehouses ORDER BY name", fetch_all=True)
    sites = execute_query("""
        SELECT s.*, c.name as city_name, e.name as entity_name
        FROM sites s
        LEFT JOIN cities c ON s.city_id = c.geonameid
        LEFT JOIN entities e ON s.entity_id = e.id
        WHERE s.is_active = TRUE
        ORDER BY e.name, c.name, s.name
    """, fetch_all=True)
    return render_template('stock/transfer.html',
                         equipment=equipment,
                         warehouses=warehouses,
                         sites=sites)


@stock_bp.route('/orders/create')
@login_required
@permission_required('stock', 'create')
def create_order():
    return "Page de création de commande"


@stock_bp.route('/api/sites/unassigned')
@login_required
def get_unassigned_sites():
    """Récupérer les sites sans entrepôt assigné"""
    sites = execute_query("""
        SELECT s.*, c.name as city_name, e.name as entity_name
        FROM sites s
        LEFT JOIN cities c ON s.city_id = c.geonameid
        LEFT JOIN entities e ON s.entity_id = e.id
        WHERE s.warehouse_id IS NULL AND s.is_active = TRUE
        ORDER BY s.name
    """, fetch_all=True)
    
    return jsonify(sites)


@stock_bp.route('/api/sites/assign-warehouse', methods=['POST'])
@login_required
@permission_required('stock', 'write')
def assign_site_warehouse():
    """Assigner un entrepôt à des sites"""
    data = request.get_json()
    
    try:
        site_ids = data['site_ids']
        warehouse_id = data['warehouse_id']
        
        # Mettre à jour les sites
        execute_query(
            "UPDATE sites SET warehouse_id = %s, updated_at = CURRENT_TIMESTAMP WHERE id = ANY(%s)",
            (warehouse_id, site_ids),
            commit=True
        )
        
        return jsonify({'success': True, 'message': f'{len(site_ids)} site(s) mis à jour'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@stock_bp.route('/api/equipment/<int:equipment_id>/stock')
@login_required
def get_equipment_stock(equipment_id):
    """Récupérer le stock disponible pour un équipement"""
    stock = execute_query("""
        SELECT SUM(quantity) as available
        FROM stock 
        WHERE equipment_id = %s
    """, (equipment_id,), fetch_one=True)
    
    return jsonify({'available': stock['available'] or 0})

@stock_bp.route('/equipment/create', methods=['POST'])
@login_required
@permission_required('stock', 'write')
def create_equipment():
    try:
        data = request.get_json()
        print("Données reçues:", data)  # Debug
        
        # Validation des champs obligatoires
        if not data.get('name') or not data.get('type') or not data.get('serial_number'):
            return jsonify({'error': 'Nom, type et numéro de série sont obligatoires'}), 400
        
        # Gérer les dates vides
        purchase_date = data.get('purchase_date')
        if purchase_date == '':
            purchase_date = None
        
        # Gérer les prix vides
        purchase_price = data.get('purchase_price')
        if purchase_price == '':
            purchase_price = None
        elif purchase_price:
            purchase_price = float(purchase_price)
        
        # Gérer les quantités
        initial_quantity = int(data.get('initial_quantity', 1))
        min_quantity = int(data.get('min_quantity', 1))
        
        # Gérer le champ JSON specifications
        specifications = data.get('specifications')
        if specifications == '':
            # Pour un champ JSON vide, utiliser un objet JSON vide
            specifications = '{}'
        elif specifications:
            # Si des spécifications sont fournies, les convertir en JSON
            try:
                # Vérifier si c'est déjà du JSON valide
                import json
                json.loads(specifications)
            except json.JSONDecodeError:
                # Si ce n'est pas du JSON, le convertir en objet JSON
                specifications = json.dumps({'notes': specifications})
        
        # Créer l'équipement
        equipment_id = execute_query("""
            INSERT INTO equipment (
                name, type, serial_number, model, manufacturer,
                purchase_date, purchase_price, specifications, status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'available')
            RETURNING id
        """, (
            data['name'],
            data['type'],
            data['serial_number'],
            data.get('model'),
            data.get('manufacturer'),
            purchase_date,
            purchase_price,
            specifications  # Utiliser la variable corrigée
        ), fetch_one=True, commit=True)['id']
        
        # Ajouter au stock si un entrepôt est spécifié
        warehouse_id = data.get('warehouse_id')
        if warehouse_id and warehouse_id != '' and initial_quantity > 0:
            execute_query("""
                INSERT INTO stock (equipment_id, warehouse_id, quantity, min_quantity)
                VALUES (%s, %s, %s, %s)
            """, (
                equipment_id,
                warehouse_id,
                initial_quantity,
                min_quantity
            ), commit=True)
        
        return jsonify({'success': True, 'equipment_id': equipment_id})
        
    except Exception as e:
        print("Erreur complète:", str(e))  # Debug
        return jsonify({'error': f'Erreur serveur: {str(e)}'}), 500
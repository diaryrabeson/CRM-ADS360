from flask import render_template, request, jsonify, flash, redirect, url_for, g
from . import purchases_bp
from database.db import execute_query
from utils.decorators import login_required, permission_required
from datetime import datetime
import json

@purchases_bp.route('/')
@login_required
@permission_required('purchases', 'read')
def index():
    """Liste des commandes et fournisseurs"""
    orders = execute_query("""
        SELECT po.*, s.name as supplier_name,
               u.first_name || ' ' || u.last_name as created_by_name
        FROM purchase_orders po
        JOIN suppliers s ON po.supplier_id = s.id
        LEFT JOIN users u ON po.created_by = u.id
        ORDER BY po.created_at DESC
    """, fetch_all=True)
    
    # Récupérer les fournisseurs avec statistiques pour la liste
    suppliers_stats = execute_query("""
        SELECT s.*, COUNT(po.id) as order_count,
               COALESCE(SUM(po.total_amount), 0) as total_purchases
        FROM suppliers s
        LEFT JOIN purchase_orders po ON s.id = po.supplier_id
        GROUP BY s.id, s.name, s.contact_name, s.email, s.phone, 
                 s.address, s.tax_id, s.payment_terms, s.created_at, s.updated_at
        ORDER BY s.name
    """, fetch_all=True)
    
    # Récupérer les fournisseurs pour le formulaire (liste simple)
    suppliers = execute_query("SELECT * FROM suppliers ORDER BY name", fetch_all=True)
    
    # Récupérer les entrepôts pour le formulaire
    warehouses = execute_query("SELECT * FROM warehouses ORDER BY name", fetch_all=True)
    
    return render_template('purchases/index.html', 
                         orders=orders,
                         suppliers=suppliers_stats,  # Pour la liste avec stats
                         suppliers_form=suppliers,   # Pour les formulaires
                         warehouses=warehouses,
                         today=datetime.now().strftime('%Y-%m-%d'))

@purchases_bp.route('/suppliers')
@login_required
@permission_required('purchases', 'read')
def suppliers():
    """Liste des fournisseurs"""
    suppliers_list = execute_query("""
        SELECT s.*, COUNT(po.id) as order_count,
               COALESCE(SUM(po.total_amount), 0) as total_purchases
        FROM suppliers s
        LEFT JOIN purchase_orders po ON s.id = po.supplier_id
        GROUP BY s.id
        ORDER BY s.name
    """, fetch_all=True)
    
    return render_template('purchases/suppliers.html', suppliers=suppliers_list)

@purchases_bp.route('/suppliers/create', methods=['POST'])
@login_required
@permission_required('purchases', 'write')
def create_supplier():
    """Créer un nouveau fournisseur"""
    data = request.get_json()
    
    try:
        supplier_id = execute_query("""
            INSERT INTO suppliers (
                name, contact_name, email, phone, address, 
                tax_id, payment_terms
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            data['name'],
            data.get('contact_name'),
            data.get('email'),
            data.get('phone'),
            data.get('address'),
            data.get('tax_id'),
            data.get('payment_terms')
        ), fetch_one=True, commit=True)['id']
        
        return jsonify({'success': True, 'supplier_id': supplier_id})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@purchases_bp.route('/create', methods=['POST'])
@login_required
@permission_required('purchases', 'write')
def create_purchase_order():
    """Créer un bon de commande"""
    data = request.get_json()
    
    try:
        # Générer un numéro de commande
        po_number = f"PO-{datetime.now().strftime('%Y%m%d')}-{execute_query('SELECT COUNT(*) FROM purchase_orders', fetch_one=True)['count'] + 1:04d}"
        
        # Calculer le total
        total_amount = sum(line['quantity'] * line['unit_price'] for line in data['lines'])
        
        # Créer la commande
        order_id = execute_query("""
            INSERT INTO purchase_orders (
                po_number, supplier_id, order_date, expected_delivery, 
                total_amount, notes, created_by, status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'draft')
            RETURNING id
        """, (
            po_number,
            data['supplier_id'],
            data['order_date'],
            data.get('expected_delivery'),
            total_amount,
            data.get('notes'),
            g.user['id']
        ), fetch_one=True, commit=True)['id']
        
        # Ajouter les lignes de commande
        for line in data['lines']:
            execute_query("""
                INSERT INTO purchase_order_lines (
                    purchase_order_id, equipment_name, quantity, 
                    unit_price, total_price, warehouse_id
                ) VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                order_id,
                line['equipment_name'],
                line['quantity'],
                line['unit_price'],
                line['quantity'] * line['unit_price'],
                line.get('warehouse_id')
            ), commit=True)
        
        return jsonify({'success': True, 'order_id': order_id, 'po_number': po_number})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@purchases_bp.route('/suppliers/<int:supplier_id>')
@login_required
def get_supplier(supplier_id):
    """Récupérer les infos d'un fournisseur"""
    supplier = execute_query("""
        SELECT * FROM suppliers WHERE id = %s
    """, (supplier_id,), fetch_one=True)
    
    return jsonify(supplier)

# SUPPRIMEZ ou MODIFIEZ ces routes qui utilisent des templates séparés :

@purchases_bp.route('/api/order/<int:order_id>')
@login_required
@permission_required('purchases', 'read')
def api_view_order(order_id):
    """API pour récupérer les détails d'une commande (pour modal)"""
    order = execute_query("""
        SELECT po.*, s.name as supplier_name, s.contact_name, s.email as supplier_email,
               s.phone as supplier_phone, s.address as supplier_address,
               u.first_name || ' ' || u.last_name as created_by_name
        FROM purchase_orders po
        JOIN suppliers s ON po.supplier_id = s.id
        LEFT JOIN users u ON po.created_by = u.id
        WHERE po.id = %s
    """, (order_id,), fetch_one=True)
    
    if not order:
        return jsonify({'error': 'Commande non trouvée'}), 404
    
    # Récupérer les lignes de commande
    lines = execute_query("""
        SELECT pol.*, w.name as warehouse_name
        FROM purchase_order_lines pol
        LEFT JOIN warehouses w ON pol.warehouse_id = w.id
        WHERE pol.purchase_order_id = %s
        ORDER BY pol.id
    """, (order_id,), fetch_all=True)
    
    return jsonify({
        'success': True,
        'order': order,
        'lines': lines
    })

@purchases_bp.route('/<int:order_id>/receive', methods=['POST'])
@login_required
@permission_required('purchases', 'write')
def receive_order(order_id):
    """Marquer une commande comme reçue"""
    try:
        # Marquer la commande comme reçue
        execute_query("""
            UPDATE purchase_orders 
            SET status = 'received', updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (order_id,), commit=True)
        
        # Optionnel: Ajouter les produits au stock
        lines = execute_query("""
            SELECT pol.* 
            FROM purchase_order_lines pol
            WHERE pol.purchase_order_id = %s
        """, (order_id,), fetch_all=True)
        
        for line in lines:
            if line['warehouse_id']:
                # Vérifier si l'équipement existe déjà
                equipment = execute_query("""
                    SELECT id FROM equipment 
                    WHERE name = %s AND serial_number IS NULL
                """, (line['equipment_name'],), fetch_one=True)
                
                if equipment:
                    # Mettre à jour le stock existant
                    execute_query("""
                        UPDATE stock 
                        SET quantity = quantity + %s, updated_at = CURRENT_TIMESTAMP
                        WHERE equipment_id = %s AND warehouse_id = %s
                    """, (line['quantity'], equipment['id'], line['warehouse_id']), commit=True)
                else:
                    # Créer un nouvel équipement
                    equipment_id = execute_query("""
                        INSERT INTO equipment (name, status)
                        VALUES (%s, 'available')
                        RETURNING id
                    """, (line['equipment_name'],), fetch_one=True, commit=True)['id']
                    
                    # Ajouter au stock
                    execute_query("""
                        INSERT INTO stock (equipment_id, warehouse_id, quantity)
                        VALUES (%s, %s, %s)
                    """, (equipment_id, line['warehouse_id'], line['quantity']), commit=True)
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@purchases_bp.route('/api/order/<int:order_id>/print')
@login_required
@permission_required('purchases', 'read')
def api_print_order(order_id):
    """API pour les données d'impression"""
    order = execute_query("""
        SELECT po.*, s.name as supplier_name, s.contact_name, s.email as supplier_email,
               s.phone as supplier_phone, s.address as supplier_address, s.tax_id,
               u.first_name || ' ' || u.last_name as created_by_name
        FROM purchase_orders po
        JOIN suppliers s ON po.supplier_id = s.id
        LEFT JOIN users u ON po.created_by = u.id
        WHERE po.id = %s
    """, (order_id,), fetch_one=True)
    
    if not order:
        return jsonify({'error': 'Commande non trouvée'}), 404
    
    # Récupérer les lignes de commande
    lines = execute_query("""
        SELECT pol.*, w.name as warehouse_name
        FROM purchase_order_lines pol
        LEFT JOIN warehouses w ON pol.warehouse_id = w.id
        WHERE pol.purchase_order_id = %s
        ORDER BY pol.id
    """, (order_id,), fetch_all=True)
    
    return jsonify({
        'success': True,
        'order': order,
        'lines': lines
    })

@purchases_bp.route('/api/suppliers')
@login_required
def api_suppliers():
    """API pour récupérer tous les fournisseurs"""
    suppliers = execute_query("SELECT id, name FROM suppliers ORDER BY name", fetch_all=True)
    return jsonify(suppliers)

@purchases_bp.route('/<int:order_id>/update-status', methods=['POST'])
@login_required
@permission_required('purchases', 'write')
def update_order_status(order_id):
    """Mettre à jour le statut d'une commande"""
    data = request.get_json()
    new_status = data.get('status')
    
    # Liste des statuts valides
    valid_statuses = ['draft', 'sent', 'received', 'cancelled']
    
    if new_status not in valid_statuses:
        return jsonify({'error': 'Statut invalide'}), 400
    
    try:
        # Vérifier si la commande existe
        order = execute_query("SELECT * FROM purchase_orders WHERE id = %s", (order_id,), fetch_one=True)
        if not order:
            return jsonify({'error': 'Commande non trouvée'}), 404
        
        # Mettre à jour le statut
        execute_query("""
            UPDATE purchase_orders 
            SET status = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (new_status, order_id), commit=True)
        
        # Si la commande est marquée comme reçue, ajouter au stock
        if new_status == 'received':
            lines = execute_query("""
                SELECT pol.* 
                FROM purchase_order_lines pol
                WHERE pol.purchase_order_id = %s
            """, (order_id,), fetch_all=True)
            
            for line in lines:
                if line['warehouse_id']:
                    # Vérifier si l'équipement existe déjà
                    equipment = execute_query("""
                        SELECT id FROM equipment 
                        WHERE name = %s AND serial_number IS NULL
                    """, (line['equipment_name'],), fetch_one=True)
                    
                    if equipment:
                        # Mettre à jour le stock existant
                        execute_query("""
                            UPDATE stock 
                            SET quantity = quantity + %s, updated_at = CURRENT_TIMESTAMP
                            WHERE equipment_id = %s AND warehouse_id = %s
                        """, (line['quantity'], equipment['id'], line['warehouse_id']), commit=True)
                    else:
                        # Créer un nouvel équipement
                        equipment_id = execute_query("""
                            INSERT INTO equipment (name, status)
                            VALUES (%s, 'available')
                            RETURNING id
                        """, (line['equipment_name'],), fetch_one=True, commit=True)['id']
                        
                        # Ajouter au stock
                        execute_query("""
                            INSERT INTO stock (equipment_id, warehouse_id, quantity)
                            VALUES (%s, %s, %s)
                        """, (equipment_id, line['warehouse_id'], line['quantity']), commit=True)
        
        return jsonify({'success': True, 'new_status': new_status})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@purchases_bp.route('/suppliers/<int:supplier_id>/update', methods=['PUT'])
@login_required
@permission_required('purchases', 'write')
def update_supplier(supplier_id):
    """Mettre à jour un fournisseur"""
    data = request.get_json()
    
    try:
        # Vérifier si le fournisseur existe
        existing = execute_query("SELECT id FROM suppliers WHERE id = %s", (supplier_id,), fetch_one=True)
        if not existing:
            return jsonify({'error': 'Fournisseur non trouvé'}), 404
        
        # Mettre à jour le fournisseur
        execute_query("""
            UPDATE suppliers SET
                name = %s, contact_name = %s, email = %s, phone = %s, 
                address = %s, tax_id = %s, payment_terms = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (
            data['name'],
            data.get('contact_name'),
            data.get('email'),
            data.get('phone'),
            data.get('address'),
            data.get('tax_id'),
            data.get('payment_terms'),
            supplier_id
        ), commit=True)
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@purchases_bp.route('/suppliers/<int:supplier_id>/delete', methods=['DELETE'])
@login_required
@permission_required('purchases', 'write')
def delete_supplier(supplier_id):
    """Supprimer un fournisseur"""
    try:
        # Vérifier s'il y a des commandes liées à ce fournisseur
        orders_count = execute_query("""
            SELECT COUNT(*) as count FROM purchase_orders WHERE supplier_id = %s
        """, (supplier_id,), fetch_one=True)['count']
        
        if orders_count > 0:
            return jsonify({'error': 'Impossible de supprimer ce fournisseur car il a des commandes associées'}), 400
        
        # Supprimer le fournisseur
        execute_query("DELETE FROM suppliers WHERE id = %s", (supplier_id,), commit=True)
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
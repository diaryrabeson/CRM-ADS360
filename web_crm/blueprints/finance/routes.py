from flask import render_template, request, jsonify, flash, redirect, url_for, g
from . import finance_bp
from database.db import execute_query
from utils.decorators import login_required, permission_required
from datetime import datetime, date, timedelta
import json

@finance_bp.route('/')
@login_required
@permission_required('finance', 'read')
def index():
    """Tableau de bord financier"""
    # Récupérer les clients pour les modals
    clients = execute_query("SELECT id, name FROM entities WHERE type = 'client' ORDER BY name", fetch_all=True)
    
    # Récupérer les factures impayées pour le modal de paiement
    unpaid_invoices = execute_query("""
        SELECT i.id, i.invoice_number, e.name as client_name, 
               (i.total_amount - i.paid_amount) as balance
        FROM invoices i
        JOIN entities e ON i.client_id = e.id
        WHERE i.status != 'paid' AND (i.total_amount - i.paid_amount) > 0
        ORDER BY i.due_date
    """, fetch_all=True)
    
    # Récupérer la liste des devis pour l'onglet devis
    quotes_list = execute_query("""
        SELECT q.*, e.name as client_name
        FROM quotes q
        JOIN entities e ON q.client_id = e.id
        ORDER BY q.created_at DESC
        LIMIT 20
    """, fetch_all=True)
    
    # Statistiques générales
    stats = {
        'revenue_month': execute_query("""
            SELECT COALESCE(SUM(total_amount), 0) as total
            FROM invoices 
            WHERE status = 'paid'
            AND DATE_TRUNC('month', created_at) = DATE_TRUNC('month', CURRENT_DATE)
        """, fetch_one=True)['total'] or 0,
        
        'pending_invoices': execute_query("""
            SELECT COALESCE(SUM(total_amount - paid_amount), 0) as total
            FROM invoices 
            WHERE status IN ('sent', 'overdue')
        """, fetch_one=True)['total'] or 0,
        
        'quotes_pending': execute_query("""
            SELECT COUNT(*) as count
            FROM quotes 
            WHERE status = 'sent'
            AND validity_date >= CURRENT_DATE
        """, fetch_one=True)['count'] or 0,
        
        'overdue_invoices': execute_query("""
            SELECT COUNT(*) as count
            FROM invoices 
            WHERE status = 'sent'
            AND due_date < CURRENT_DATE
        """, fetch_one=True)['count'] or 0
    }
    
    # Factures récentes
    recent_invoices = execute_query("""
        SELECT i.*, e.name as client_name,
               (i.total_amount - i.paid_amount) as balance
        FROM invoices i
        JOIN entities e ON i.client_id = e.id
        ORDER BY i.created_at DESC
        LIMIT 10
    """, fetch_all=True)
    
    today = date.today().isoformat()
    
    return render_template('finance/index.html',
                         stats=stats,
                         recent_invoices=recent_invoices,
                         quotes_list=quotes_list,
                         clients=clients,
                         unpaid_invoices=unpaid_invoices,
                         today=today)

@finance_bp.route('/invoices/create', methods=['POST'])
@login_required
@permission_required('finance', 'create')
def create_invoice():
    """Créer une nouvelle facture"""
    try:
        data = request.get_json()
        
        # Générer le numéro de facture
        current_month = datetime.now().strftime('%Y%m')
        invoice_count = execute_query(
            "SELECT COUNT(*) + 1 as num FROM invoices WHERE invoice_number LIKE %s",
            (f"FACT-{current_month}-%",), fetch_one=True
        )['num']
        invoice_number = f"FACT-{current_month}-{invoice_count:04d}"
        
        # Calculer les totaux
        items = data.get('items', [])
        subtotal = sum(float(item.get('quantity', 0)) * float(item.get('unit_price', 0)) for item in items)
        tax_rate = float(data.get('tax_rate', 20))
        tax_amount = subtotal * (tax_rate / 100)
        total_amount = subtotal + tax_amount
        
        invoice_id = execute_query("""
            INSERT INTO invoices (
                invoice_number, client_id, invoice_date, due_date,
                total_amount, tax_amount, paid_amount, status, items,
                payment_terms, created_by
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            invoice_number,
            data['client_id'],
            data['invoice_date'],
            data['due_date'],
            total_amount,
            tax_amount,
            0.0,
            'draft',
            json.dumps(items),
            data.get('payment_terms', 'Paiement à 30 jours'),
            g.user['id']
        ), fetch_one=True, commit=True)['id']
        
        return jsonify({
            'success': True, 
            'id': invoice_id, 
            'invoice_number': invoice_number,
            'message': 'Facture créée avec succès'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@finance_bp.route('/quotes/create', methods=['POST'])
@login_required
@permission_required('finance', 'create')
def create_quote():
    """Créer un devis"""
    try:
        data = request.get_json()
        
        # Générer le numéro de devis
        current_month = datetime.now().strftime('%Y%m')
        quote_count = execute_query(
            "SELECT COUNT(*) + 1 as num FROM quotes WHERE quote_number LIKE %s",
            (f"DEVIS-{current_month}-%",), fetch_one=True
        )['num']
        quote_number = f"DEVIS-{current_month}-{quote_count:04d}"
        
        # Calculer les totaux
        items = data.get('items', [])
        subtotal = sum(float(item.get('quantity', 0)) * float(item.get('unit_price', 0)) for item in items)
        tax_rate = float(data.get('tax_rate', 20))
        tax_amount = subtotal * (tax_rate / 100)
        total_amount = subtotal + tax_amount
        
        quote_id = execute_query("""
            INSERT INTO quotes (
                quote_number, client_id, amount, validity_date,
                status, items, terms, created_by
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            quote_number,
            data['client_id'],
            total_amount,
            data['validity_date'],
            'draft',
            json.dumps(items),
            data.get('terms', ''),
            g.user['id']
        ), fetch_one=True, commit=True)['id']
        
        return jsonify({
            'success': True, 
            'id': quote_id, 
            'quote_number': quote_number,
            'message': 'Devis créé avec succès'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@finance_bp.route('/payments/record', methods=['POST'])
@login_required
@permission_required('finance', 'write')
def record_payment():
    """Enregistrer un paiement"""
    try:
        data = request.get_json()
        
        # Enregistrer le paiement
        payment_id = execute_query("""
            INSERT INTO payments (
                invoice_id, amount, payment_date, payment_method,
                reference, notes, recorded_by
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            data['invoice_id'],
            data['amount'],
            data['payment_date'],
            data['payment_method'],
            data.get('reference', ''),
            data.get('notes', ''),
            g.user['id']
        ), fetch_one=True, commit=True)['id']
        
        # Mettre à jour le montant payé de la facture
        invoice = execute_query("""
            UPDATE invoices 
            SET paid_amount = paid_amount + %s,
                status = CASE 
                    WHEN paid_amount + %s >= total_amount THEN 'paid'
                    WHEN paid_amount + %s > 0 THEN 'partially_paid'
                    ELSE status
                END
            WHERE id = %s
            RETURNING status, total_amount, paid_amount
        """, (data['amount'], data['amount'], data['amount'], data['invoice_id']), 
            fetch_one=True, commit=True)
        
        return jsonify({
            'success': True,
            'payment_id': payment_id,
            'invoice_status': invoice['status'],
            'message': 'Paiement enregistré avec succès'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@finance_bp.route('/invoices/<int:invoice_id>/send', methods=['POST'])
@login_required
@permission_required('finance', 'write')
def send_invoice(invoice_id):
    """Envoyer une facture par email"""
    try:
        data = request.get_json()
        
        # Mettre à jour le statut de la facture
        execute_query("""
            UPDATE invoices 
            SET status = 'sent', 
                sent_date = CURRENT_DATE
            WHERE id = %s
        """, (invoice_id,), commit=True)
        
        # Ici vous ajouteriez la logique d'envoi d'email
        # (utilisation de Flask-Mail, SendGrid, etc.)
        
        return jsonify({
            'success': True,
            'message': 'Facture envoyée avec succès'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@finance_bp.route('/quotes/<int:quote_id>/send', methods=['POST'])
@login_required
@permission_required('finance', 'write')
def send_quote(quote_id):
    """Envoyer un devis par email"""
    try:
        data = request.get_json()
        
        # Récupérer les informations du client si l'ID est fourni
        client_info = {}
        recipient_email = data.get('recipient_email')
        
        if data.get('recipient_id'):
            client = execute_query("""
                SELECT name, email, phone FROM entities WHERE id = %s
            """, (data['recipient_id'],), fetch_one=True)
            if client:
                client_info = client
                # Utiliser l'email du client si aucun email n'est fourni
                if not recipient_email and client.get('email'):
                    recipient_email = client['email']
        
        if not recipient_email:
            return jsonify({'success': False, 'error': 'Adresse email du destinataire requise'}), 400
        
        # Mettre à jour le statut du devis avec la colonne sent_to
        execute_query("""
            UPDATE quotes 
            SET status = 'sent', 
                sent_date = CURRENT_DATE,
                sent_to = %s
            WHERE id = %s
        """, (recipient_email, quote_id), commit=True)
        
        # Logique d'envoi d'email
        print(f"Envoi du devis {quote_id} à {recipient_email}")
        print(f"Sujet: {data.get('subject')}")
        print(f"Message: {data.get('message')}")
        print(f"Info client: {client_info}")
        
        return jsonify({
            'success': True,
            'message': 'Devis envoyé avec succès'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    

@finance_bp.route('/quotes/<int:quote_id>/convert', methods=['POST'])
@login_required
@permission_required('finance', 'create')
def convert_quote(quote_id):
    """Convertir un devis en facture"""
    try:
        from decimal import Decimal
        import json
        
        data = request.get_json()
        
        # Récupérer les données du devis
        quote = execute_query("""
            SELECT * FROM quotes WHERE id = %s
        """, (quote_id,), fetch_one=True)
        
        if not quote:
            return jsonify({'success': False, 'error': 'Devis introuvable'}), 404
        
        # Générer le numéro de facture
        current_month = datetime.now().strftime('%Y%m')
        invoice_count = execute_query(
            "SELECT COUNT(*) + 1 as num FROM invoices WHERE invoice_number LIKE %s",
            (f"FACT-{current_month}-%",), fetch_one=True
        )['num']
        invoice_number = f"FACT-{current_month}-{invoice_count:04d}"
        
        # Convertir le montant en Decimal si nécessaire
        amount = quote['amount']
        if not isinstance(amount, Decimal):
            amount = Decimal(str(amount))
        
        # Calculer le montant HT et la TVA (TVA à 20%)
        # Utiliser Decimal pour tous les calculs
        tax_rate = Decimal('1.2')  # 1 + 20% de TVA
        subtotal = amount / tax_rate  # Montant HT
        tax_amount = amount - subtotal  # Montant de la TVA
        
        # Créer la facture
        invoice_id = execute_query("""
            INSERT INTO invoices (
                invoice_number, client_id, quote_id, 
                amount, tax_amount, total_amount,
                invoice_date, due_date,
                paid_amount, status, items,
                payment_terms, created_by
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            invoice_number,
            quote['client_id'],
            quote_id,
            float(subtotal),  # Convertir en float pour l'insertion
            float(tax_amount),
            float(amount),
            data.get('invoice_date', datetime.now().date()),
            data.get('due_date'),
            0.0,
            'draft',
            quote['items'] if isinstance(quote['items'], str) else json.dumps(quote['items']),
            data.get('payment_terms', 'Paiement à 30 jours'),
            g.user['id']
        ), fetch_one=True, commit=True)['id']
        
        # Mettre à jour le statut du devis
        execute_query("""
            UPDATE quotes SET status = 'accepted' WHERE id = %s
        """, (quote_id,), commit=True)
        
        return jsonify({
            'success': True,
            'invoice_id': invoice_id,
            'invoice_number': invoice_number,
            'message': 'Devis converti en facture avec succès'
        })
        
    except Exception as e:
        import traceback
        print(f"Erreur lors de la conversion: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': str(e)}), 500

@finance_bp.route('/invoices/<int:invoice_id>/delete', methods=['DELETE'])
@login_required
@permission_required('finance', 'delete')
def delete_invoice(invoice_id):
    """Supprimer une facture"""
    try:
        # Vérifier s'il y a des paiements associés
        payments = execute_query("""
            SELECT COUNT(*) as count FROM payments WHERE invoice_id = %s
        """, (invoice_id,), fetch_one=True)
        
        if payments['count'] > 0:
            return jsonify({
                'success': False, 
                'error': 'Impossible de supprimer une facture avec des paiements'
            }), 400
        
        execute_query("DELETE FROM invoices WHERE id = %s", (invoice_id,), commit=True)
        
        return jsonify({
            'success': True,
            'message': 'Facture supprimée avec succès'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@finance_bp.route('/quotes/<int:quote_id>/delete', methods=['DELETE'])
@login_required
@permission_required('finance', 'delete')
def delete_quote(quote_id):
    """Supprimer un devis"""
    try:
        # Vérifier si le devis a été converti en facture
        invoice = execute_query("""
            SELECT COUNT(*) as count FROM invoices WHERE quote_id = %s
        """, (quote_id,), fetch_one=True)
        
        if invoice['count'] > 0:
            return jsonify({
                'success': False, 
                'error': 'Impossible de supprimer un devis converti en facture'
            }), 400
        
        execute_query("DELETE FROM quotes WHERE id = %s", (quote_id,), commit=True)
        
        return jsonify({
            'success': True,
            'message': 'Devis supprimé avec succès'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    

@finance_bp.route('/invoices/<int:invoice_id>')
@login_required
@permission_required('finance', 'read')
def invoice_detail(invoice_id):
    """Détail d'une facture"""
    invoice = execute_query("""
        SELECT i.*, e.name as client_name, e.address as client_address,
               e.email as client_email, e.phone as client_phone,
               q.quote_number
        FROM invoices i
        JOIN entities e ON i.client_id = e.id
        LEFT JOIN quotes q ON i.quote_id = q.id
        WHERE i.id = %s
    """, (invoice_id,), fetch_one=True)
    
    if not invoice:
        flash('Facture introuvable', 'danger')
        return redirect(url_for('finance.index'))
    
    # Historique des paiements
    payments = execute_query("""
        SELECT p.*, u.first_name || ' ' || u.last_name as recorded_by_name
        FROM payments p
        LEFT JOIN users u ON p.recorded_by = u.id
        WHERE p.invoice_id = %s
        ORDER BY p.payment_date DESC
    """, (invoice_id,), fetch_all=True)
    
    return render_template('finance/invoice_detail.html',
                         invoice=invoice,
                         payments=payments)

@finance_bp.route('/quotes/<int:quote_id>')
@login_required
@permission_required('finance', 'read')
def quote_detail(quote_id):
    """Détail d'un devis"""
    quote = execute_query("""
        SELECT q.*, e.name as client_name, e.address as client_address,
               e.email as client_email, e.phone as client_phone,
               u.first_name || ' ' || u.last_name as created_by_name
        FROM quotes q
        JOIN entities e ON q.client_id = e.id
        LEFT JOIN users u ON q.created_by = u.id
        WHERE q.id = %s
    """, (quote_id,), fetch_one=True)
    
    if not quote:
        flash('Devis introuvable', 'danger')
        return redirect(url_for('finance.index'))
    
    return render_template('finance/quote_detail.html', quote=quote)

@finance_bp.route('/invoices/<int:invoice_id>/print')
@login_required
@permission_required('finance', 'read')
def print_invoice(invoice_id):
    """Imprimer une facture"""
    invoice = execute_query("""
        SELECT i.*, e.name as client_name, e.address as client_address,
               e.email as client_email, e.phone as client_phone,
               q.quote_number
        FROM invoices i
        JOIN entities e ON i.client_id = e.id
        LEFT JOIN quotes q ON i.quote_id = q.id
        WHERE i.id = %s
    """, (invoice_id,), fetch_one=True)
    
    if not invoice:
        flash('Facture introuvable', 'danger')
        return redirect(url_for('finance.index'))
    
    return render_template('finance/print_invoice.html', invoice=invoice)

@finance_bp.route('/clients/emails')
@login_required
@permission_required('finance', 'read')
def get_clients_emails():
    """Récupérer les emails des clients"""
    clients = execute_query("""
        SELECT id, name, email, phone 
        FROM entities 
        WHERE type = 'client' AND email IS NOT NULL
        ORDER BY name
    """, fetch_all=True)
    
    return jsonify(clients)



@finance_bp.route('/payments/list')
@login_required
@permission_required('finance', 'read')
def list_payments():
    """Liste des paiements avec détails"""
    try:
        payments = execute_query("""
            SELECT 
                p.*,
                i.invoice_number,
                e.name as client_name,
                u.first_name || ' ' || u.last_name as recorded_by_name
            FROM payments p
            JOIN invoices i ON p.invoice_id = i.id
            JOIN entities e ON i.client_id = e.id
            LEFT JOIN users u ON p.recorded_by = u.id
            ORDER BY p.payment_date DESC
            LIMIT 100
        """, fetch_all=True)
        
        # Convertir les dates en format JSON serializable
        for payment in payments:
            payment['payment_date'] = payment['payment_date'].isoformat() if payment['payment_date'] else None
            payment['created_at'] = payment['created_at'].isoformat() if payment['created_at'] else None
        
        return jsonify(payments)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@finance_bp.route('/payments/monthly-stats')
@login_required
@permission_required('finance', 'read')
def monthly_payment_stats():
    """Statistiques mensuelles des paiements"""
    try:
        stats = execute_query("""
            SELECT 
                DATE_TRUNC('month', payment_date) as month,
                SUM(amount) as total,
                COUNT(*) as count
            FROM payments
            WHERE payment_date >= CURRENT_DATE - INTERVAL '12 months'
            GROUP BY DATE_TRUNC('month', payment_date)
            ORDER BY month
        """, fetch_all=True)
        
        # Formatter les données pour Chart.js
        labels = []
        data = []
        for stat in stats:
            labels.append(stat['month'].strftime('%B %Y'))
            data.append(float(stat['total']))
        
        return jsonify({
            'labels': labels,
            'data': data
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@finance_bp.route('/reports/monthly/<int:year>/<int:month>')
@login_required
@permission_required('finance', 'read')
def monthly_report(year, month):
    """Générer un rapport mensuel"""
    try:
        # Statistiques du mois
        stats = {
            'invoices_created': execute_query("""
                SELECT COUNT(*) as count, SUM(total_amount) as total
                FROM invoices
                WHERE EXTRACT(YEAR FROM created_at) = %s
                AND EXTRACT(MONTH FROM created_at) = %s
            """, (year, month), fetch_one=True),
            
            'payments_received': execute_query("""
                SELECT COUNT(*) as count, SUM(amount) as total
                FROM payments
                WHERE EXTRACT(YEAR FROM payment_date) = %s
                AND EXTRACT(MONTH FROM payment_date) = %s
            """, (year, month), fetch_one=True),
            
            'quotes_created': execute_query("""
                SELECT COUNT(*) as count, SUM(amount) as total
                FROM quotes
                WHERE EXTRACT(YEAR FROM created_at) = %s
                AND EXTRACT(MONTH FROM created_at) = %s
            """, (year, month), fetch_one=True),
            
            'top_clients': execute_query("""
                SELECT e.name, COUNT(i.id) as invoice_count, SUM(i.total_amount) as total
                FROM invoices i
                JOIN entities e ON i.client_id = e.id
                WHERE EXTRACT(YEAR FROM i.created_at) = %s
                AND EXTRACT(MONTH FROM i.created_at) = %s
                GROUP BY e.name
                ORDER BY total DESC
                LIMIT 5
            """, (year, month), fetch_all=True)
        }
        
        return jsonify({
            'success': True,
            'year': year,
            'month': month,
            'stats': stats
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@finance_bp.route('/reports/quarterly/<int:year>/<int:quarter>')
@login_required
@permission_required('finance', 'read')
def quarterly_report(year, quarter):
    """Générer un rapport trimestriel"""
    try:
        start_month = (quarter - 1) * 3 + 1
        end_month = quarter * 3
        
        stats = {
            'revenue': execute_query("""
                SELECT SUM(total_amount) as total
                FROM invoices
                WHERE EXTRACT(YEAR FROM created_at) = %s
                AND EXTRACT(MONTH FROM created_at) BETWEEN %s AND %s
                AND status = 'paid'
            """, (year, start_month, end_month), fetch_one=True)['total'] or 0,
            
            'payments': execute_query("""
                SELECT SUM(amount) as total
                FROM payments
                WHERE EXTRACT(YEAR FROM payment_date) = %s
                AND EXTRACT(MONTH FROM payment_date) BETWEEN %s AND %s
            """, (year, start_month, end_month), fetch_one=True)['total'] or 0,
            
            'monthly_breakdown': execute_query("""
                SELECT 
                    EXTRACT(MONTH FROM created_at) as month,
                    COUNT(*) as invoice_count,
                    SUM(total_amount) as total
                FROM invoices
                WHERE EXTRACT(YEAR FROM created_at) = %s
                AND EXTRACT(MONTH FROM created_at) BETWEEN %s AND %s
                GROUP BY EXTRACT(MONTH FROM created_at)
                ORDER BY month
            """, (year, start_month, end_month), fetch_all=True)
        }
        
        return jsonify({
            'success': True,
            'year': year,
            'quarter': quarter,
            'stats': stats
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@finance_bp.route('/reports/annual/<int:year>')
@login_required
@permission_required('finance', 'read')
def annual_report(year):
    """Générer un bilan annuel"""
    try:
        stats = {
            'total_revenue': execute_query("""
                SELECT SUM(total_amount) as total
                FROM invoices
                WHERE EXTRACT(YEAR FROM created_at) = %s
                AND status = 'paid'
            """, (year,), fetch_one=True)['total'] or 0,
            
            'total_payments': execute_query("""
                SELECT SUM(amount) as total
                FROM payments
                WHERE EXTRACT(YEAR FROM payment_date) = %s
            """, (year,), fetch_one=True)['total'] or 0,
            
            'pending_amount': execute_query("""
                SELECT SUM(total_amount - paid_amount) as total
                FROM invoices
                WHERE EXTRACT(YEAR FROM created_at) = %s
                AND status != 'paid'
            """, (year,), fetch_one=True)['total'] or 0,
            
            'monthly_revenue': execute_query("""
                SELECT 
                    EXTRACT(MONTH FROM created_at) as month,
                    SUM(total_amount) as total
                FROM invoices
                WHERE EXTRACT(YEAR FROM created_at) = %s
                GROUP BY EXTRACT(MONTH FROM created_at)
                ORDER BY month
            """, (year,), fetch_all=True),
            
            'payment_methods': execute_query("""
                SELECT 
                    payment_method,
                    COUNT(*) as count,
                    SUM(amount) as total
                FROM payments
                WHERE EXTRACT(YEAR FROM payment_date) = %s
                GROUP BY payment_method
                ORDER BY total DESC
            """, (year,), fetch_all=True)
        }
        
        return jsonify({
            'success': True,
            'year': year,
            'stats': stats
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@finance_bp.route('/export/accounting', methods=['POST'])
@login_required
@permission_required('finance', 'read')
def export_accounting():
    """Export comptable en CSV"""
    try:
        import csv
        from io import StringIO
        from flask import Response
        
        data = request.get_json()
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        
        # Récupérer les données
        invoices = execute_query("""
            SELECT 
                i.invoice_number,
                i.invoice_date,
                e.name as client,
                i.amount as ht,
                i.tax_amount as tva,
                i.total_amount as ttc,
                i.paid_amount,
                i.status
            FROM invoices i
            JOIN entities e ON i.client_id = e.id
            WHERE i.invoice_date BETWEEN %s AND %s
            ORDER BY i.invoice_date
        """, (start_date, end_date), fetch_all=True)
        
        # Créer le CSV
        output = StringIO()
        writer = csv.DictWriter(output, fieldnames=[
            'invoice_number', 'invoice_date', 'client', 
            'ht', 'tva', 'ttc', 'paid_amount', 'status'
        ])
        writer.writeheader()
        writer.writerows(invoices)
        
        # Retourner le fichier CSV
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={"Content-Disposition": f"attachment;filename=export_comptable_{start_date}_{end_date}.csv"}
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500
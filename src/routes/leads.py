from flask import Blueprint, request, jsonify
from datetime import datetime
from src.models.lead import Lead, Conversation, FollowUp, db
from src.services.pipedrive_service import get_pipedrive_service
from sqlalchemy import desc, func

leads_bp = Blueprint('leads', __name__)

@leads_bp.route('/leads', methods=['GET'])
def get_leads():
    """Lista todos os leads com filtros opcionais"""
    try:
        # Parâmetros de filtro
        status = request.args.get('status')
        category = request.args.get('category')
        source = request.args.get('source')
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        
        # Query base
        query = Lead.query
        
        # Aplicar filtros
        if status:
            query = query.filter(Lead.status == status)
        if category:
            query = query.filter(Lead.category == category)
        if source:
            query = query.filter(Lead.source == source)
        
        # Ordenação por última interação
        query = query.order_by(desc(Lead.last_interaction))
        
        # Paginação
        leads = query.paginate(
            page=page, 
            per_page=per_page, 
            error_out=False
        )
        
        return jsonify({
            'success': True,
            'data': [lead.to_dict() for lead in leads.items],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': leads.total,
                'pages': leads.pages
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@leads_bp.route('/leads', methods=['POST'])
def create_lead():
    """Cria um novo lead"""
    try:
        data = request.get_json()
        
        # Validação básica
        if not data.get('name'):
            return jsonify({
                'success': False,
                'error': 'Nome é obrigatório'
            }), 400
        
        # Verificar se já existe lead com mesmo email ou telefone
        existing_lead = None
        if data.get('email'):
            existing_lead = Lead.query.filter_by(email=data['email']).first()
        elif data.get('phone'):
            existing_lead = Lead.query.filter_by(phone=data['phone']).first()
        
        if existing_lead:
            return jsonify({
                'success': False,
                'error': 'Lead já existe com este email ou telefone',
                'existing_lead_id': existing_lead.id
            }), 409
        
        # Criar novo lead
        lead = Lead(
            name=data['name'],
            email=data.get('email'),
            phone=data.get('phone'),
            company=data.get('company'),
            location=data.get('location'),
            category=data.get('category'),
            source=data.get('source', 'manual'),
            qualification_score=data.get('qualification_score', 0.0)
        )
        
        db.session.add(lead)
        db.session.commit()
        
        # Sincronizar com Pipedrive se configurado
        pipedrive_service = get_pipedrive_service()
        if pipedrive_service:
            sync_result = pipedrive_service.sync_lead_to_pipedrive(lead)
            if not sync_result['success']:
                # Log do erro, mas não falha a criação do lead
                print(f"Erro ao sincronizar com Pipedrive: {sync_result['error']}")
        
        return jsonify({
            'success': True,
            'data': lead.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@leads_bp.route('/leads/<int:lead_id>', methods=['GET'])
def get_lead(lead_id):
    """Busca um lead específico"""
    try:
        lead = Lead.query.get_or_404(lead_id)
        
        # Incluir conversas recentes
        recent_conversations = Conversation.query.filter_by(lead_id=lead_id)\
            .order_by(desc(Conversation.created_at))\
            .limit(10).all()
        
        lead_data = lead.to_dict()
        lead_data['recent_conversations'] = [conv.to_dict() for conv in recent_conversations]
        
        return jsonify({
            'success': True,
            'data': lead_data
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@leads_bp.route('/leads/<int:lead_id>', methods=['PUT'])
def update_lead(lead_id):
    """Atualiza um lead"""
    try:
        lead = Lead.query.get_or_404(lead_id)
        data = request.get_json()
        
        # Atualizar campos permitidos
        updatable_fields = [
            'name', 'email', 'phone', 'company', 'location', 
            'status', 'category', 'qualification_score'
        ]
        
        for field in updatable_fields:
            if field in data:
                setattr(lead, field, data[field])
        
        lead.updated_at = datetime.utcnow()
        db.session.commit()
        
        # Sincronizar com Pipedrive se configurado
        pipedrive_service = get_pipedrive_service()
        if pipedrive_service:
            sync_result = pipedrive_service.sync_lead_to_pipedrive(lead)
            if not sync_result['success']:
                print(f"Erro ao sincronizar com Pipedrive: {sync_result['error']}")
        
        return jsonify({
            'success': True,
            'data': lead.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@leads_bp.route('/leads/<int:lead_id>/conversations', methods=['POST'])
def add_conversation(lead_id):
    """Adiciona uma nova conversa para um lead"""
    try:
        lead = Lead.query.get_or_404(lead_id)
        data = request.get_json()
        
        # Validação básica
        required_fields = ['channel', 'direction', 'message_content']
        for field in required_fields:
            if not data.get(field):
                return jsonify({
                    'success': False,
                    'error': f'Campo {field} é obrigatório'
                }), 400
        
        # Criar nova conversa
        conversation = Conversation(
            lead_id=lead_id,
            channel=data['channel'],
            direction=data['direction'],
            message_content=data['message_content'],
            intent=data.get('intent'),
            entities=data.get('entities'),
            sentiment=data.get('sentiment'),
            confidence=data.get('confidence')
        )
        
        db.session.add(conversation)
        
        # Atualizar dados de interação do lead
        lead.update_interaction()
        
        # Atualizar sentimento médio se fornecido
        if data.get('sentiment') is not None:
            avg_sentiment = db.session.query(func.avg(Conversation.sentiment))\
                .filter_by(lead_id=lead_id)\
                .filter(Conversation.sentiment.isnot(None))\
                .scalar()
            if avg_sentiment:
                lead.sentiment_score = float(avg_sentiment)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': conversation.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@leads_bp.route('/leads/<int:lead_id>/conversations', methods=['GET'])
def get_conversations(lead_id):
    """Lista conversas de um lead"""
    try:
        Lead.query.get_or_404(lead_id)  # Verificar se lead existe
        
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 50))
        
        conversations = Conversation.query.filter_by(lead_id=lead_id)\
            .order_by(desc(Conversation.created_at))\
            .paginate(page=page, per_page=per_page, error_out=False)
        
        return jsonify({
            'success': True,
            'data': [conv.to_dict() for conv in conversations.items],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': conversations.total,
                'pages': conversations.pages
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@leads_bp.route('/leads/<int:lead_id>/followups', methods=['POST'])
def schedule_followup(lead_id):
    """Agenda um follow-up para um lead"""
    try:
        lead = Lead.query.get_or_404(lead_id)
        data = request.get_json()
        
        # Validação básica
        required_fields = ['scheduled_at', 'message_template', 'channel']
        for field in required_fields:
            if not data.get(field):
                return jsonify({
                    'success': False,
                    'error': f'Campo {field} é obrigatório'
                }), 400
        
        # Converter data
        try:
            scheduled_at = datetime.fromisoformat(data['scheduled_at'].replace('Z', '+00:00'))
        except ValueError:
            return jsonify({
                'success': False,
                'error': 'Formato de data inválido. Use ISO 8601'
            }), 400
        
        # Criar follow-up
        followup = FollowUp(
            lead_id=lead_id,
            scheduled_at=scheduled_at,
            message_template=data['message_template'],
            channel=data['channel']
        )
        
        db.session.add(followup)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': followup.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@leads_bp.route('/leads/stats', methods=['GET'])
def get_lead_stats():
    """Retorna estatísticas dos leads"""
    try:
        # Contadores por status
        status_counts = db.session.query(
            Lead.status, 
            func.count(Lead.id)
        ).group_by(Lead.status).all()
        
        # Contadores por fonte
        source_counts = db.session.query(
            Lead.source, 
            func.count(Lead.id)
        ).group_by(Lead.source).all()
        
        # Contadores por categoria
        category_counts = db.session.query(
            Lead.category, 
            func.count(Lead.id)
        ).group_by(Lead.category).all()
        
        # Leads criados hoje
        today = datetime.utcnow().date()
        leads_today = Lead.query.filter(
            func.date(Lead.created_at) == today
        ).count()
        
        # Score médio de qualificação
        avg_qualification = db.session.query(
            func.avg(Lead.qualification_score)
        ).scalar() or 0
        
        return jsonify({
            'success': True,
            'data': {
                'total_leads': Lead.query.count(),
                'leads_today': leads_today,
                'avg_qualification_score': round(float(avg_qualification), 2),
                'by_status': dict(status_counts),
                'by_source': dict(source_counts),
                'by_category': dict(category_counts)
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@leads_bp.route('/leads/<int:lead_id>/sync-pipedrive', methods=['POST'])
def sync_lead_pipedrive(lead_id):
    """Sincroniza um lead específico com o Pipedrive"""
    try:
        lead = Lead.query.get_or_404(lead_id)
        
        pipedrive_service = get_pipedrive_service()
        if not pipedrive_service:
            return jsonify({
                'success': False,
                'error': 'Integração com Pipedrive não configurada'
            }), 400
        
        result = pipedrive_service.sync_lead_to_pipedrive(lead)
        
        if result['success']:
            return jsonify({
                'success': True,
                'message': 'Lead sincronizado com sucesso',
                'pipedrive_id': result['pipedrive_id']
            })
        else:
            return jsonify({
                'success': False,
                'error': result['error']
            }), 500
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


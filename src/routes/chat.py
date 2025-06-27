from flask import Blueprint, request, jsonify
from datetime import datetime
from src.models.lead import Lead, Conversation, db
from src.services.nlp_service import nlp_service
from src.services.pipedrive_service import get_pipedrive_service
from sqlalchemy import desc

chat_bp = Blueprint('chat', __name__)

@chat_bp.route('/chat/process', methods=['POST'])
def process_message():
    """Processa uma mensagem recebida e gera resposta automatizada"""
    try:
        data = request.get_json()
        
        # Validação básica
        required_fields = ['message', 'channel']
        for field in required_fields:
            if not data.get(field):
                return jsonify({
                    'success': False,
                    'error': f'Campo {field} é obrigatório'
                }), 400
        
        message = data['message']
        channel = data['channel']
        lead_id = data.get('lead_id')
        sender_info = data.get('sender_info', {})
        
        # Buscar ou criar lead
        lead = None
        if lead_id:
            lead = Lead.query.get(lead_id)
        elif sender_info.get('phone') or sender_info.get('email'):
            # Tentar encontrar lead existente
            if sender_info.get('email'):
                lead = Lead.query.filter_by(email=sender_info['email']).first()
            elif sender_info.get('phone'):
                lead = Lead.query.filter_by(phone=sender_info['phone']).first()
        
        # Criar novo lead se não encontrado
        if not lead and sender_info:
            lead = Lead(
                name=sender_info.get('name', 'Lead Anônimo'),
                email=sender_info.get('email'),
                phone=sender_info.get('phone'),
                source=channel,
                status='new'
            )
            db.session.add(lead)
            db.session.flush()  # Para obter o ID
        
        # Analisar mensagem com PLN
        analysis = nlp_service.analyze_message(message)
        
        # Buscar histórico de conversas recentes
        conversation_history = []
        if lead:
            recent_conversations = Conversation.query.filter_by(lead_id=lead.id)\
                .order_by(desc(Conversation.created_at))\
                .limit(10).all()
            conversation_history = [conv.to_dict() for conv in recent_conversations]
        
        # Verificar se deve escalar
        escalation = nlp_service.should_escalate(
            analysis['intent'],
            analysis['sentiment'],
            analysis['confidence'],
            conversation_history
        )
        
        # Gerar resposta
        response_text = nlp_service.generate_response(
            analysis['intent'],
            analysis['entities'],
            analysis['sentiment'],
            lead.name if lead else None,
            {'history': conversation_history}
        )
        
        # Registrar conversa de entrada
        if lead:
            incoming_conversation = Conversation(
                lead_id=lead.id,
                channel=channel,
                direction='inbound',
                message_content=message,
                intent=analysis['intent'],
                entities=analysis['entities'],
                sentiment=analysis['sentiment']['polarity'],
                confidence=analysis['confidence'],
                is_escalated=escalation['should_escalate'],
                escalation_reason=', '.join(escalation['reasons']) if escalation['reasons'] else None
            )
            db.session.add(incoming_conversation)
            
            # Atualizar dados do lead
            lead.update_interaction()
            if analysis['sentiment']['polarity'] is not None:
                # Atualizar sentimento médio
                from sqlalchemy import func
                avg_sentiment = db.session.query(func.avg(Conversation.sentiment))\
                    .filter_by(lead_id=lead.id)\
                    .filter(Conversation.sentiment.isnot(None))\
                    .scalar()
                if avg_sentiment:
                    lead.sentiment_score = float(avg_sentiment)
        
        # Registrar resposta automática se não escalonada
        response_conversation = None
        if not escalation['should_escalate'] and lead:
            response_conversation = Conversation(
                lead_id=lead.id,
                channel=channel,
                direction='outbound',
                message_content=response_text,
                intent='response',
                confidence=analysis['confidence']
            )
            db.session.add(response_conversation)
        
        # Sincronizar com CRM se necessário
        crm_sync_result = None
        if lead and (not lead.pipedrive_id or analysis['intent'] in ['product_inquiry', 'demo_request']):
            pipedrive_service = get_pipedrive_service()
            if pipedrive_service:
                crm_sync_result = pipedrive_service.sync_lead_to_pipedrive(lead)
        
        db.session.commit()
        
        result = {
            'success': True,
            'analysis': analysis,
            'response': response_text,
            'escalation': escalation,
            'lead_id': lead.id if lead else None,
            'conversation_id': response_conversation.id if response_conversation else None
        }
        
        if crm_sync_result:
            result['crm_sync'] = crm_sync_result
        
        return jsonify(result)
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@chat_bp.route('/chat/analyze', methods=['POST'])
def analyze_message():
    """Analisa uma mensagem sem gerar resposta (apenas análise)"""
    try:
        data = request.get_json()
        
        if not data.get('message'):
            return jsonify({
                'success': False,
                'error': 'Campo message é obrigatório'
            }), 400
        
        analysis = nlp_service.analyze_message(data['message'])
        
        return jsonify({
            'success': True,
            'analysis': analysis
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@chat_bp.route('/chat/generate-response', methods=['POST'])
def generate_response():
    """Gera uma resposta baseada em parâmetros específicos"""
    try:
        data = request.get_json()
        
        required_fields = ['intent']
        for field in required_fields:
            if not data.get(field):
                return jsonify({
                    'success': False,
                    'error': f'Campo {field} é obrigatório'
                }), 400
        
        response = nlp_service.generate_response(
            data['intent'],
            data.get('entities', {}),
            data.get('sentiment', {'label': 'neutral', 'polarity': 0}),
            data.get('lead_name'),
            data.get('context', {})
        )
        
        return jsonify({
            'success': True,
            'response': response
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@chat_bp.route('/chat/escalate', methods=['POST'])
def escalate_conversation():
    """Escalona uma conversa para atendimento humano"""
    try:
        data = request.get_json()
        
        conversation_id = data.get('conversation_id')
        lead_id = data.get('lead_id')
        reason = data.get('reason', 'Solicitação manual')
        human_agent_id = data.get('human_agent_id')
        
        if not conversation_id and not lead_id:
            return jsonify({
                'success': False,
                'error': 'conversation_id ou lead_id é obrigatório'
            }), 400
        
        # Buscar conversa ou última conversa do lead
        conversation = None
        if conversation_id:
            conversation = Conversation.query.get(conversation_id)
        elif lead_id:
            conversation = Conversation.query.filter_by(lead_id=lead_id)\
                .order_by(desc(Conversation.created_at))\
                .first()
        
        if not conversation:
            return jsonify({
                'success': False,
                'error': 'Conversa não encontrada'
            }), 404
        
        # Marcar como escalonada
        conversation.is_escalated = True
        conversation.escalation_reason = reason
        conversation.human_agent_id = human_agent_id
        
        # Buscar lead
        lead = Lead.query.get(conversation.lead_id)
        if lead:
            lead.status = 'escalated'
            lead.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        # Aqui você pode adicionar lógica para notificar a equipe humana
        # Por exemplo, enviar para Slack, sistema de tickets, etc.
        
        return jsonify({
            'success': True,
            'message': 'Conversa escalonada com sucesso',
            'conversation_id': conversation.id,
            'lead_id': conversation.lead_id
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@chat_bp.route('/chat/context/<int:lead_id>', methods=['GET'])
def get_conversation_context(lead_id):
    """Busca o contexto completo de conversas de um lead"""
    try:
        lead = Lead.query.get_or_404(lead_id)
        
        # Buscar todas as conversas do lead
        conversations = Conversation.query.filter_by(lead_id=lead_id)\
            .order_by(Conversation.created_at)\
            .all()
        
        # Analisar padrões de comportamento
        total_conversations = len(conversations)
        inbound_count = len([c for c in conversations if c.direction == 'inbound'])
        outbound_count = len([c for c in conversations if c.direction == 'outbound'])
        escalated_count = len([c for c in conversations if c.is_escalated])
        
        # Intenções mais comuns
        intents = [c.intent for c in conversations if c.intent]
        intent_counts = {}
        for intent in intents:
            intent_counts[intent] = intent_counts.get(intent, 0) + 1
        
        # Sentimento médio
        sentiments = [c.sentiment for c in conversations if c.sentiment is not None]
        avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0
        
        context = {
            'lead': lead.to_dict(),
            'conversations': [conv.to_dict() for conv in conversations],
            'stats': {
                'total_conversations': total_conversations,
                'inbound_count': inbound_count,
                'outbound_count': outbound_count,
                'escalated_count': escalated_count,
                'avg_sentiment': round(avg_sentiment, 2),
                'intent_distribution': intent_counts
            }
        }
        
        return jsonify({
            'success': True,
            'context': context
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@chat_bp.route('/chat/intents', methods=['GET'])
def get_available_intents():
    """Retorna as intenções disponíveis no sistema"""
    try:
        intents = list(nlp_service.intent_patterns.keys())
        
        return jsonify({
            'success': True,
            'intents': intents,
            'descriptions': {
                'greeting': 'Saudações e cumprimentos',
                'product_inquiry': 'Perguntas sobre produtos ou serviços',
                'demo_request': 'Solicitações de demonstração',
                'pricing_inquiry': 'Perguntas sobre preços',
                'support_request': 'Pedidos de ajuda ou suporte',
                'complaint': 'Reclamações ou insatisfações',
                'compliment': 'Elogios ou feedback positivo',
                'goodbye': 'Despedidas',
                'contact_info': 'Solicitações de informações de contato',
                'availability': 'Perguntas sobre disponibilidade',
                'general': 'Mensagens gerais sem intenção específica'
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


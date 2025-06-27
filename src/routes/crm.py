from flask import Blueprint, request, jsonify
from datetime import datetime
from src.models.config import CRMIntegration, db
from src.services.pipedrive_service import PipedriveService
import hashlib
import hmac

crm_bp = Blueprint('crm', __name__)

@crm_bp.route('/crm/integrations', methods=['GET'])
def get_integrations():
    """Lista todas as integrações de CRM"""
    try:
        integrations = CRMIntegration.query.all()
        return jsonify({
            'success': True,
            'data': [integration.to_dict() for integration in integrations]
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@crm_bp.route('/crm/integrations', methods=['POST'])
def create_integration():
    """Cria uma nova integração de CRM"""
    try:
        data = request.get_json()
        
        # Validação básica
        required_fields = ['name', 'api_url']
        for field in required_fields:
            if not data.get(field):
                return jsonify({
                    'success': False,
                    'error': f'Campo {field} é obrigatório'
                }), 400
        
        # Verificar se já existe integração com o mesmo nome
        existing = CRMIntegration.query.filter_by(name=data['name']).first()
        if existing:
            return jsonify({
                'success': False,
                'error': 'Já existe uma integração com este nome'
            }), 409
        
        # Criar nova integração
        integration = CRMIntegration(
            name=data['name'],
            api_url=data['api_url'],
            api_key=data.get('api_key'),
            api_token=data.get('api_token'),
            webhook_url=data.get('webhook_url'),
            webhook_secret=data.get('webhook_secret'),
            is_active=data.get('is_active', True)
        )
        
        db.session.add(integration)
        db.session.commit()
        
        # Testar conexão se for Pipedrive
        if data['name'].lower() == 'pipedrive' and data.get('api_token'):
            test_result = test_pipedrive_connection(data['api_token'], data['api_url'])
            if test_result['success']:
                integration.sync_status = 'success'
                integration.last_sync = datetime.utcnow()
            else:
                integration.sync_status = 'error'
                integration.error_message = test_result['error']
            
            db.session.commit()
        
        return jsonify({
            'success': True,
            'data': integration.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@crm_bp.route('/crm/integrations/<int:integration_id>', methods=['PUT'])
def update_integration(integration_id):
    """Atualiza uma integração de CRM"""
    try:
        integration = CRMIntegration.query.get_or_404(integration_id)
        data = request.get_json()
        
        # Atualizar campos permitidos
        updatable_fields = [
            'api_url', 'api_key', 'api_token', 'webhook_url', 
            'webhook_secret', 'is_active'
        ]
        
        for field in updatable_fields:
            if field in data:
                setattr(integration, field, data[field])
        
        integration.updated_at = datetime.utcnow()
        
        # Testar conexão se for Pipedrive e token foi atualizado
        if (integration.name.lower() == 'pipedrive' and 
            'api_token' in data and data['api_token']):
            test_result = test_pipedrive_connection(data['api_token'], integration.api_url)
            if test_result['success']:
                integration.sync_status = 'success'
                integration.last_sync = datetime.utcnow()
                integration.error_message = None
            else:
                integration.sync_status = 'error'
                integration.error_message = test_result['error']
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': integration.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@crm_bp.route('/crm/integrations/<int:integration_id>/test', methods=['POST'])
def test_integration(integration_id):
    """Testa uma integração de CRM"""
    try:
        integration = CRMIntegration.query.get_or_404(integration_id)
        
        if integration.name.lower() == 'pipedrive':
            if not integration.api_token:
                return jsonify({
                    'success': False,
                    'error': 'Token da API não configurado'
                }), 400
            
            result = test_pipedrive_connection(integration.api_token, integration.api_url)
            
            # Atualizar status da integração
            if result['success']:
                integration.sync_status = 'success'
                integration.last_sync = datetime.utcnow()
                integration.error_message = None
            else:
                integration.sync_status = 'error'
                integration.error_message = result['error']
            
            db.session.commit()
            
            return jsonify(result)
        else:
            return jsonify({
                'success': False,
                'error': 'Tipo de CRM não suportado para teste'
            }), 400
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@crm_bp.route('/crm/webhooks/pipedrive', methods=['POST'])
def pipedrive_webhook():
    """Endpoint para receber webhooks do Pipedrive"""
    try:
        # Verificar se existe integração ativa do Pipedrive
        integration = CRMIntegration.query.filter_by(
            name='pipedrive', 
            is_active=True
        ).first()
        
        if not integration:
            return jsonify({
                'success': False,
                'error': 'Integração Pipedrive não encontrada ou inativa'
            }), 404
        
        # Verificar assinatura do webhook se configurada
        if integration.webhook_secret:
            signature = request.headers.get('X-Pipedrive-Signature')
            if not verify_pipedrive_signature(
                request.data, 
                signature, 
                integration.webhook_secret
            ):
                return jsonify({
                    'success': False,
                    'error': 'Assinatura do webhook inválida'
                }), 401
        
        # Processar dados do webhook
        webhook_data = request.get_json()
        
        if not webhook_data:
            return jsonify({
                'success': False,
                'error': 'Dados do webhook inválidos'
            }), 400
        
        # Processar evento baseado no tipo
        event_type = webhook_data.get('event')
        object_type = webhook_data.get('object')
        
        if object_type == 'person':
            result = process_person_webhook(webhook_data)
        elif object_type == 'deal':
            result = process_deal_webhook(webhook_data)
        elif object_type == 'activity':
            result = process_activity_webhook(webhook_data)
        else:
            # Evento não tratado, mas retorna sucesso
            result = {'success': True, 'message': f'Evento {event_type} para {object_type} recebido'}
        
        # Atualizar última sincronização
        integration.last_sync = datetime.utcnow()
        if result['success']:
            integration.sync_status = 'success'
            integration.error_message = None
        else:
            integration.sync_status = 'error'
            integration.error_message = result.get('error', 'Erro desconhecido')
        
        db.session.commit()
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

def test_pipedrive_connection(api_token: str, api_url: str) -> dict:
    """Testa a conexão com a API do Pipedrive"""
    try:
        service = PipedriveService(api_token, api_url)
        
        # Tentar buscar pipelines como teste
        pipelines = service.get_pipelines()
        
        return {
            'success': True,
            'message': 'Conexão com Pipedrive estabelecida com sucesso',
            'pipelines_count': len(pipelines)
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': f'Erro ao conectar com Pipedrive: {str(e)}'
        }

def verify_pipedrive_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verifica a assinatura do webhook do Pipedrive"""
    if not signature or not secret:
        return False
    
    try:
        expected_signature = hmac.new(
            secret.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(signature, expected_signature)
    except Exception:
        return False

def process_person_webhook(webhook_data: dict) -> dict:
    """Processa webhook de pessoa do Pipedrive"""
    try:
        from src.services.pipedrive_service import get_pipedrive_service
        
        event = webhook_data.get('event')
        person_data = webhook_data.get('current', {})
        person_id = person_data.get('id')
        
        if not person_id:
            return {'success': False, 'error': 'ID da pessoa não encontrado'}
        
        pipedrive_service = get_pipedrive_service()
        if not pipedrive_service:
            return {'success': False, 'error': 'Serviço Pipedrive não configurado'}
        
        if event in ['added', 'updated']:
            # Sincronizar pessoa do Pipedrive para o sistema local
            result = pipedrive_service.sync_from_pipedrive(person_id)
            return result
        elif event == 'deleted':
            # Marcar lead como inativo ou deletar
            from src.models.lead import Lead
            lead = Lead.query.filter_by(pipedrive_id=person_id).first()
            if lead:
                lead.status = 'deleted'
                db.session.commit()
            return {'success': True, 'message': 'Lead marcado como deletado'}
        
        return {'success': True, 'message': f'Evento {event} processado'}
        
    except Exception as e:
        return {'success': False, 'error': str(e)}

def process_deal_webhook(webhook_data: dict) -> dict:
    """Processa webhook de negócio do Pipedrive"""
    try:
        event = webhook_data.get('event')
        deal_data = webhook_data.get('current', {})
        person_id = deal_data.get('person_id')
        
        if person_id:
            # Atualizar status do lead baseado no estágio do negócio
            from src.models.lead import Lead
            lead = Lead.query.filter_by(pipedrive_id=person_id).first()
            
            if lead:
                stage_id = deal_data.get('stage_id')
                status = deal_data.get('status')
                
                # Mapear status do negócio para status do lead
                if status == 'won':
                    lead.status = 'converted'
                elif status == 'lost':
                    lead.status = 'lost'
                elif status == 'open':
                    lead.status = 'qualified'
                
                lead.updated_at = datetime.utcnow()
                db.session.commit()
        
        return {'success': True, 'message': f'Evento de negócio {event} processado'}
        
    except Exception as e:
        return {'success': False, 'error': str(e)}

def process_activity_webhook(webhook_data: dict) -> dict:
    """Processa webhook de atividade do Pipedrive"""
    try:
        event = webhook_data.get('event')
        activity_data = webhook_data.get('current', {})
        person_id = activity_data.get('person_id')
        
        if person_id and event == 'added':
            # Registrar atividade como conversa
            from src.models.lead import Lead, Conversation
            lead = Lead.query.filter_by(pipedrive_id=person_id).first()
            
            if lead:
                conversation = Conversation(
                    lead_id=lead.id,
                    channel='pipedrive',
                    direction='outbound',
                    message_content=f"Atividade: {activity_data.get('subject', 'Sem título')}",
                    intent='activity'
                )
                
                db.session.add(conversation)
                lead.update_interaction()
                db.session.commit()
        
        return {'success': True, 'message': f'Evento de atividade {event} processado'}
        
    except Exception as e:
        return {'success': False, 'error': str(e)}


from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
from src.models.lead import Lead, FollowUp, db
from src.services.followup_scheduler import followup_scheduler, FollowUpType, Priority
from src.services.channel_adapters import channel_manager
from sqlalchemy import and_, or_

automation_bp = Blueprint('automation', __name__)

@automation_bp.route('/automation/followups/schedule', methods=['POST'])
def schedule_followup():
    """Agenda um follow-up inteligente"""
    try:
        data = request.get_json()
        
        # Validação básica
        required_fields = ['lead_id', 'followup_type']
        for field in required_fields:
            if not data.get(field):
                return jsonify({
                    'success': False,
                    'error': f'Campo {field} é obrigatório'
                }), 400
        
        lead_id = data['lead_id']
        followup_type_str = data['followup_type']
        
        # Validar tipo de follow-up
        try:
            followup_type = FollowUpType(followup_type_str)
        except ValueError:
            return jsonify({
                'success': False,
                'error': f'Tipo de follow-up inválido: {followup_type_str}',
                'valid_types': [t.value for t in FollowUpType]
            }), 400
        
        # Validar prioridade se fornecida
        priority = None
        if data.get('priority'):
            try:
                priority = Priority[data['priority'].upper()]
            except KeyError:
                return jsonify({
                    'success': False,
                    'error': f'Prioridade inválida: {data["priority"]}',
                    'valid_priorities': [p.name for p in Priority]
                }), 400
        
        # Agendar follow-up
        result = followup_scheduler.schedule_intelligent_followup(
            lead_id=lead_id,
            followup_type=followup_type,
            custom_message=data.get('custom_message'),
            priority=priority
        )
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@automation_bp.route('/automation/followups/pending', methods=['GET'])
def get_pending_followups():
    """Lista follow-ups pendentes"""
    try:
        limit = int(request.args.get('limit', 50))
        
        pending_followups = followup_scheduler.get_pending_followups(limit)
        
        return jsonify({
            'success': True,
            'data': pending_followups,
            'count': len(pending_followups)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@automation_bp.route('/automation/followups/<int:followup_id>/execute', methods=['POST'])
def execute_followup(followup_id):
    """Executa um follow-up específico"""
    try:
        result = followup_scheduler.execute_followup(followup_id)
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@automation_bp.route('/automation/followups/bulk-execute', methods=['POST'])
def bulk_execute_followups():
    """Executa múltiplos follow-ups em lote"""
    try:
        data = request.get_json()
        followup_ids = data.get('followup_ids', [])
        
        if not followup_ids:
            return jsonify({
                'success': False,
                'error': 'Lista de followup_ids é obrigatória'
            }), 400
        
        results = []
        success_count = 0
        error_count = 0
        
        for followup_id in followup_ids:
            result = followup_scheduler.execute_followup(followup_id)
            results.append({
                'followup_id': followup_id,
                'result': result
            })
            
            if result['success']:
                success_count += 1
            else:
                error_count += 1
        
        return jsonify({
            'success': True,
            'summary': {
                'total': len(followup_ids),
                'success': success_count,
                'errors': error_count
            },
            'results': results
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@automation_bp.route('/automation/channels/capabilities', methods=['GET'])
def get_channel_capabilities():
    """Retorna capacidades de todos os canais"""
    try:
        channels = channel_manager.get_supported_channels()
        capabilities = {}
        
        for channel in channels:
            capabilities[channel] = channel_manager.get_channel_capabilities(channel)
        
        return jsonify({
            'success': True,
            'channels': capabilities
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@automation_bp.route('/automation/channels/<channel>/format', methods=['POST'])
def format_message_for_channel(channel):
    """Formata uma mensagem para um canal específico"""
    try:
        data = request.get_json()
        
        if not data.get('message'):
            return jsonify({
                'success': False,
                'error': 'Campo message é obrigatório'
            }), 400
        
        # Validar canal
        if channel not in channel_manager.get_supported_channels():
            return jsonify({
                'success': False,
                'error': f'Canal não suportado: {channel}',
                'supported_channels': channel_manager.get_supported_channels()
            }), 400
        
        # Formatar mensagem
        formatted = channel_manager.format_message(
            channel=channel,
            message=data['message'],
            lead_data=data.get('lead_data'),
            context=data.get('context')
        )
        
        # Validar mensagem formatada
        validation = channel_manager.validate_message(channel, data['message'])
        
        return jsonify({
            'success': True,
            'formatted_message': formatted,
            'validation': validation
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@automation_bp.route('/automation/channels/<channel>/parse', methods=['POST'])
def parse_message_from_channel(channel):
    """Processa uma mensagem recebida de um canal específico"""
    try:
        data = request.get_json()
        
        if not data.get('raw_message'):
            return jsonify({
                'success': False,
                'error': 'Campo raw_message é obrigatório'
            }), 400
        
        # Validar canal
        if channel not in channel_manager.get_supported_channels():
            return jsonify({
                'success': False,
                'error': f'Canal não suportado: {channel}',
                'supported_channels': channel_manager.get_supported_channels()
            }), 400
        
        # Processar mensagem
        parsed = channel_manager.parse_message(
            channel=channel,
            raw_message=data['raw_message']
        )
        
        return jsonify({
            'success': True,
            'parsed_message': parsed
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@automation_bp.route('/automation/workflows/create', methods=['POST'])
def create_workflow():
    """Cria um fluxo de automação personalizado"""
    try:
        data = request.get_json()
        
        required_fields = ['name', 'trigger_conditions', 'actions']
        for field in required_fields:
            if not data.get(field):
                return jsonify({
                    'success': False,
                    'error': f'Campo {field} é obrigatório'
                }), 400
        
        # Aqui você implementaria a lógica de criação de workflow
        # Por enquanto, retornamos um exemplo
        workflow = {
            'id': 'workflow_' + str(datetime.utcnow().timestamp()),
            'name': data['name'],
            'trigger_conditions': data['trigger_conditions'],
            'actions': data['actions'],
            'is_active': data.get('is_active', True),
            'created_at': datetime.utcnow().isoformat()
        }
        
        return jsonify({
            'success': True,
            'workflow': workflow,
            'message': 'Workflow criado com sucesso'
        }), 201
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@automation_bp.route('/automation/smart-scheduling/analyze', methods=['POST'])
def analyze_optimal_timing():
    """Analisa o melhor horário para contatar um lead"""
    try:
        data = request.get_json()
        
        if not data.get('lead_id'):
            return jsonify({
                'success': False,
                'error': 'Campo lead_id é obrigatório'
            }), 400
        
        lead = Lead.query.get(data['lead_id'])
        if not lead:
            return jsonify({
                'success': False,
                'error': 'Lead não encontrado'
            }), 404
        
        # Analisar padrões de resposta
        response_patterns = followup_scheduler._analyze_lead_response_patterns(lead)
        segment_patterns = followup_scheduler._analyze_segment_patterns(lead)
        
        # Calcular horário ideal para diferentes tipos
        optimal_times = {}
        for followup_type in FollowUpType:
            optimal_time = followup_scheduler._calculate_optimal_time(lead, followup_type)
            optimal_times[followup_type.value] = optimal_time.isoformat()
        
        # Calcular prioridade atual
        priority = followup_scheduler._calculate_priority(lead, FollowUpType.NURTURING)
        
        return jsonify({
            'success': True,
            'analysis': {
                'lead_patterns': response_patterns,
                'segment_patterns': segment_patterns,
                'optimal_times': optimal_times,
                'current_priority': priority.name,
                'recommended_channel': followup_scheduler._determine_ideal_channel(lead)
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@automation_bp.route('/automation/followups/types', methods=['GET'])
def get_followup_types():
    """Retorna tipos de follow-up disponíveis"""
    try:
        types = []
        for followup_type in FollowUpType:
            types.append({
                'value': followup_type.value,
                'name': followup_type.name,
                'description': get_followup_type_description(followup_type)
            })
        
        return jsonify({
            'success': True,
            'followup_types': types
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@automation_bp.route('/automation/stats', methods=['GET'])
def get_automation_stats():
    """Retorna estatísticas de automação"""
    try:
        # Estatísticas de follow-ups
        total_scheduled = FollowUp.query.filter_by(status='scheduled').count()
        total_sent = FollowUp.query.filter_by(status='sent').count()
        total_failed = FollowUp.query.filter_by(status='failed').count()
        
        # Follow-ups por canal
        from sqlalchemy import func
        by_channel = db.session.query(
            FollowUp.channel,
            func.count(FollowUp.id).label('count')
        ).group_by(FollowUp.channel).all()
        
        # Follow-ups por status
        by_status = db.session.query(
            FollowUp.status,
            func.count(FollowUp.id).label('count')
        ).group_by(FollowUp.status).all()
        
        # Follow-ups agendados para hoje
        today = datetime.utcnow().date()
        today_scheduled = FollowUp.query.filter(
            and_(
                FollowUp.status == 'scheduled',
                func.date(FollowUp.scheduled_at) == today
            )
        ).count()
        
        return jsonify({
            'success': True,
            'stats': {
                'total_scheduled': total_scheduled,
                'total_sent': total_sent,
                'total_failed': total_failed,
                'today_scheduled': today_scheduled,
                'by_channel': dict(by_channel),
                'by_status': dict(by_status)
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

def get_followup_type_description(followup_type: FollowUpType) -> str:
    """Retorna descrição do tipo de follow-up"""
    descriptions = {
        FollowUpType.WELCOME: "Mensagem de boas-vindas para novos leads",
        FollowUpType.NURTURING: "Nutrição de leads com conteúdo relevante",
        FollowUpType.QUALIFICATION: "Qualificação e coleta de informações",
        FollowUpType.PROPOSAL: "Apresentação de proposta comercial",
        FollowUpType.CLOSING: "Fechamento de negócio",
        FollowUpType.REACTIVATION: "Reativação de leads inativos",
        FollowUpType.FEEDBACK: "Coleta de feedback e satisfação"
    }
    return descriptions.get(followup_type, "Tipo de follow-up personalizado")


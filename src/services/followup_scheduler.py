from datetime import datetime, timedelta, time
from typing import Dict, List, Optional, Tuple
import json
from dataclasses import dataclass
from enum import Enum
from src.models.lead import Lead, Conversation, FollowUp, db
from src.models.config import Analytics
from sqlalchemy import func, and_, or_

class FollowUpType(Enum):
    WELCOME = "welcome"
    NURTURING = "nurturing"
    QUALIFICATION = "qualification"
    PROPOSAL = "proposal"
    CLOSING = "closing"
    REACTIVATION = "reactivation"
    FEEDBACK = "feedback"

class Priority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    URGENT = 4

@dataclass
class OptimalTime:
    hour: int
    minute: int
    day_of_week: Optional[int] = None  # 0=Monday, 6=Sunday
    confidence: float = 0.0

class FollowUpScheduler:
    """Sistema inteligente de agendamento de follow-ups"""
    
    def __init__(self):
        # Horários padrão por tipo de lead
        self.default_business_hours = {
            'start': time(9, 0),  # 9:00
            'end': time(18, 0),   # 18:00
            'lunch_start': time(12, 0),  # 12:00
            'lunch_end': time(14, 0)     # 14:00
        }
        
        # Intervalos padrão entre follow-ups por tipo
        self.default_intervals = {
            FollowUpType.WELCOME: timedelta(hours=2),
            FollowUpType.NURTURING: timedelta(days=3),
            FollowUpType.QUALIFICATION: timedelta(days=1),
            FollowUpType.PROPOSAL: timedelta(days=2),
            FollowUpType.CLOSING: timedelta(hours=24),
            FollowUpType.REACTIVATION: timedelta(days=7),
            FollowUpType.FEEDBACK: timedelta(days=1)
        }
        
        # Pesos para cálculo de prioridade
        self.priority_weights = {
            'qualification_score': 0.3,
            'engagement_level': 0.25,
            'time_since_last_interaction': 0.2,
            'intent_urgency': 0.15,
            'lead_source_quality': 0.1
        }
    
    def schedule_intelligent_followup(self, lead_id: int, followup_type: FollowUpType, 
                                    custom_message: str = None, priority: Priority = None) -> Dict:
        """Agenda um follow-up inteligente baseado em dados históricos"""
        
        try:
            lead = Lead.query.get(lead_id)
            if not lead:
                return {'success': False, 'error': 'Lead não encontrado'}
            
            # Calcular horário ideal
            optimal_time = self._calculate_optimal_time(lead, followup_type)
            
            # Calcular prioridade se não fornecida
            if priority is None:
                priority = self._calculate_priority(lead, followup_type)
            
            # Gerar mensagem se não fornecida
            if custom_message is None:
                custom_message = self._generate_followup_message(lead, followup_type)
            
            # Determinar canal ideal
            ideal_channel = self._determine_ideal_channel(lead)
            
            # Criar follow-up
            followup = FollowUp(
                lead_id=lead_id,
                scheduled_at=optimal_time,
                message_template=custom_message,
                channel=ideal_channel,
                status='scheduled'
            )
            
            db.session.add(followup)
            db.session.commit()
            
            # Registrar analytics
            self._record_followup_analytics(lead, followup_type, priority, optimal_time)
            
            return {
                'success': True,
                'followup_id': followup.id,
                'scheduled_at': optimal_time.isoformat(),
                'channel': ideal_channel,
                'priority': priority.name,
                'message': custom_message
            }
            
        except Exception as e:
            db.session.rollback()
            return {'success': False, 'error': str(e)}
    
    def _calculate_optimal_time(self, lead: Lead, followup_type: FollowUpType) -> datetime:
        """Calcula o horário ideal para o follow-up baseado em dados históricos"""
        
        # Buscar padrões de resposta do lead
        response_patterns = self._analyze_lead_response_patterns(lead)
        
        # Buscar padrões gerais por segmento
        segment_patterns = self._analyze_segment_patterns(lead)
        
        # Calcular horário base
        base_time = datetime.utcnow() + self.default_intervals[followup_type]
        
        # Ajustar baseado nos padrões
        optimal_hour = self._get_optimal_hour(response_patterns, segment_patterns)
        optimal_day = self._get_optimal_day(response_patterns, segment_patterns, followup_type)
        
        # Construir datetime ideal
        optimal_time = base_time.replace(
            hour=optimal_hour.hour,
            minute=optimal_hour.minute,
            second=0,
            microsecond=0
        )
        
        # Ajustar dia da semana se necessário
        if optimal_day is not None:
            days_ahead = optimal_day - optimal_time.weekday()
            if days_ahead <= 0:  # Se o dia já passou esta semana
                days_ahead += 7
            optimal_time += timedelta(days=days_ahead)
        
        # Garantir que está em horário comercial
        optimal_time = self._adjust_to_business_hours(optimal_time)
        
        return optimal_time
    
    def _analyze_lead_response_patterns(self, lead: Lead) -> Dict:
        """Analisa padrões de resposta específicos do lead"""
        
        conversations = Conversation.query.filter_by(lead_id=lead.id)\
            .filter_by(direction='inbound')\
            .order_by(Conversation.created_at)\
            .all()
        
        if not conversations:
            return {}
        
        # Analisar horários de resposta
        response_hours = []
        response_days = []
        
        for conv in conversations:
            response_hours.append(conv.created_at.hour)
            response_days.append(conv.created_at.weekday())
        
        # Calcular estatísticas
        patterns = {
            'preferred_hours': self._get_most_common(response_hours),
            'preferred_days': self._get_most_common(response_days),
            'avg_response_time': self._calculate_avg_response_time(conversations),
            'total_interactions': len(conversations)
        }
        
        return patterns
    
    def _analyze_segment_patterns(self, lead: Lead) -> Dict:
        """Analisa padrões do segmento do lead"""
        
        # Buscar leads similares (mesma categoria, fonte, localização)
        similar_leads = Lead.query.filter(
            and_(
                Lead.id != lead.id,
                or_(
                    Lead.category == lead.category,
                    Lead.source == lead.source,
                    Lead.location == lead.location
                )
            )
        ).limit(100).all()
        
        if not similar_leads:
            return {}
        
        # Analisar conversas dos leads similares
        similar_conversations = Conversation.query.filter(
            and_(
                Conversation.lead_id.in_([l.id for l in similar_leads]),
                Conversation.direction == 'inbound'
            )
        ).all()
        
        if not similar_conversations:
            return {}
        
        # Calcular padrões do segmento
        segment_hours = [conv.created_at.hour for conv in similar_conversations]
        segment_days = [conv.created_at.weekday() for conv in similar_conversations]
        
        return {
            'preferred_hours': self._get_most_common(segment_hours),
            'preferred_days': self._get_most_common(segment_days),
            'sample_size': len(similar_conversations)
        }
    
    def _get_optimal_hour(self, lead_patterns: Dict, segment_patterns: Dict) -> time:
        """Determina a hora ideal baseada nos padrões"""
        
        # Priorizar padrões do lead se tiver dados suficientes
        if lead_patterns.get('total_interactions', 0) >= 3:
            preferred_hours = lead_patterns.get('preferred_hours', [])
            if preferred_hours:
                optimal_hour = preferred_hours[0]  # Hora mais comum
                return time(optimal_hour, 0)
        
        # Usar padrões do segmento
        if segment_patterns.get('sample_size', 0) >= 10:
            preferred_hours = segment_patterns.get('preferred_hours', [])
            if preferred_hours:
                optimal_hour = preferred_hours[0]
                return time(optimal_hour, 0)
        
        # Usar horário padrão (meio da manhã)
        return time(10, 30)
    
    def _get_optimal_day(self, lead_patterns: Dict, segment_patterns: Dict, 
                        followup_type: FollowUpType) -> Optional[int]:
        """Determina o dia ideal da semana"""
        
        # Para follow-ups urgentes, não esperar dia específico
        if followup_type in [FollowUpType.WELCOME, FollowUpType.CLOSING]:
            return None
        
        # Usar padrões do lead
        if lead_patterns.get('total_interactions', 0) >= 3:
            preferred_days = lead_patterns.get('preferred_days', [])
            if preferred_days:
                return preferred_days[0]
        
        # Usar padrões do segmento
        if segment_patterns.get('sample_size', 0) >= 10:
            preferred_days = segment_patterns.get('preferred_days', [])
            if preferred_days:
                return preferred_days[0]
        
        # Padrão: terça a quinta (melhores dias para vendas)
        return 1  # Terça-feira
    
    def _adjust_to_business_hours(self, dt: datetime) -> datetime:
        """Ajusta horário para horário comercial"""
        
        # Se for fim de semana, mover para segunda
        if dt.weekday() >= 5:  # Sábado ou domingo
            days_to_monday = 7 - dt.weekday()
            dt = dt + timedelta(days=days_to_monday)
        
        # Ajustar hora se necessário
        current_time = dt.time()
        
        if current_time < self.default_business_hours['start']:
            dt = dt.replace(
                hour=self.default_business_hours['start'].hour,
                minute=self.default_business_hours['start'].minute
            )
        elif current_time > self.default_business_hours['end']:
            # Mover para próximo dia útil
            dt = dt + timedelta(days=1)
            dt = dt.replace(
                hour=self.default_business_hours['start'].hour,
                minute=self.default_business_hours['start'].minute
            )
            # Verificar se não caiu em fim de semana
            if dt.weekday() >= 5:
                days_to_monday = 7 - dt.weekday()
                dt = dt + timedelta(days=days_to_monday)
        elif (self.default_business_hours['lunch_start'] <= current_time <= 
              self.default_business_hours['lunch_end']):
            # Mover para depois do almoço
            dt = dt.replace(
                hour=self.default_business_hours['lunch_end'].hour,
                minute=self.default_business_hours['lunch_end'].minute
            )
        
        return dt
    
    def _calculate_priority(self, lead: Lead, followup_type: FollowUpType) -> Priority:
        """Calcula a prioridade do follow-up"""
        
        score = 0.0
        
        # Score de qualificação
        score += (lead.qualification_score / 10.0) * self.priority_weights['qualification_score']
        
        # Nível de engajamento
        engagement = self._calculate_engagement_level(lead)
        score += engagement * self.priority_weights['engagement_level']
        
        # Tempo desde última interação
        time_factor = self._calculate_time_urgency(lead)
        score += time_factor * self.priority_weights['time_since_last_interaction']
        
        # Urgência da intenção
        intent_urgency = self._calculate_intent_urgency(lead)
        score += intent_urgency * self.priority_weights['intent_urgency']
        
        # Qualidade da fonte
        source_quality = self._get_source_quality_score(lead.source)
        score += source_quality * self.priority_weights['lead_source_quality']
        
        # Converter score para prioridade
        if score >= 0.8:
            return Priority.URGENT
        elif score >= 0.6:
            return Priority.HIGH
        elif score >= 0.4:
            return Priority.MEDIUM
        else:
            return Priority.LOW
    
    def _calculate_engagement_level(self, lead: Lead) -> float:
        """Calcula nível de engajamento do lead"""
        
        if lead.interaction_count == 0:
            return 0.0
        
        # Normalizar baseado em interações e sentimento
        interaction_score = min(lead.interaction_count / 10.0, 1.0)
        sentiment_score = (lead.sentiment_score + 1) / 2  # Normalizar de -1,1 para 0,1
        
        return (interaction_score + sentiment_score) / 2
    
    def _calculate_time_urgency(self, lead: Lead) -> float:
        """Calcula urgência baseada no tempo desde última interação"""
        
        if not lead.last_interaction:
            return 1.0  # Máxima urgência se nunca interagiu
        
        hours_since = (datetime.utcnow() - lead.last_interaction).total_seconds() / 3600
        
        # Urgência aumenta com o tempo, mas satura em 72h
        urgency = min(hours_since / 72.0, 1.0)
        
        return urgency
    
    def _calculate_intent_urgency(self, lead: Lead) -> float:
        """Calcula urgência baseada na última intenção detectada"""
        
        last_conversation = Conversation.query.filter_by(lead_id=lead.id)\
            .order_by(Conversation.created_at.desc())\
            .first()
        
        if not last_conversation or not last_conversation.intent:
            return 0.5  # Neutro
        
        # Mapeamento de intenções para urgência
        intent_urgency_map = {
            'demo_request': 0.9,
            'pricing_inquiry': 0.8,
            'product_inquiry': 0.7,
            'complaint': 0.9,
            'support_request': 0.6,
            'greeting': 0.3,
            'goodbye': 0.1,
            'general': 0.4
        }
        
        return intent_urgency_map.get(last_conversation.intent, 0.5)
    
    def _get_source_quality_score(self, source: str) -> float:
        """Retorna score de qualidade da fonte"""
        
        source_scores = {
            'referral': 0.9,
            'website': 0.8,
            'linkedin': 0.7,
            'whatsapp': 0.6,
            'facebook': 0.5,
            'instagram': 0.5,
            'cold_call': 0.3,
            'email_campaign': 0.4,
            'unknown': 0.2
        }
        
        return source_scores.get(source, 0.5)
    
    def _generate_followup_message(self, lead: Lead, followup_type: FollowUpType) -> str:
        """Gera mensagem personalizada para o follow-up"""
        
        templates = {
            FollowUpType.WELCOME: [
                f"Olá {lead.name}! Obrigado pelo seu interesse. Como posso ajudá-lo a encontrar a melhor solução?",
                f"Oi {lead.name}! Que bom ter você conosco. Tem alguma dúvida que posso esclarecer?",
                f"Bem-vindo {lead.name}! Estou aqui para ajudar com qualquer informação que precisar."
            ],
            FollowUpType.NURTURING: [
                f"Oi {lead.name}! Como você está? Gostaria de compartilhar algumas novidades que podem interessar você.",
                f"Olá {lead.name}! Espero que esteja bem. Tem algum projeto em mente que posso ajudar?",
                f"Oi {lead.name}! Pensei em você e trouxe algumas informações que podem ser úteis."
            ],
            FollowUpType.QUALIFICATION: [
                f"Olá {lead.name}! Para preparar a melhor proposta, pode me contar um pouco mais sobre suas necessidades?",
                f"Oi {lead.name}! Gostaria de entender melhor seu projeto para oferecer a solução ideal.",
                f"Olá {lead.name}! Que tal conversarmos sobre seus objetivos para eu ajudar da melhor forma?"
            ],
            FollowUpType.PROPOSAL: [
                f"Oi {lead.name}! Preparei uma proposta personalizada para você. Quando podemos conversar?",
                f"Olá {lead.name}! Tenho uma proposta interessante baseada no que conversamos. Posso apresentar?",
                f"Oi {lead.name}! Finalizei sua proposta. Que tal agendarmos uma conversa?"
            ],
            FollowUpType.CLOSING: [
                f"Olá {lead.name}! Como ficou sua decisão sobre nossa proposta? Posso esclarecer alguma dúvida?",
                f"Oi {lead.name}! Gostaria de saber se precisa de mais alguma informação para decidir.",
                f"Olá {lead.name}! Estou aqui para ajudar com qualquer questão sobre nossa proposta."
            ],
            FollowUpType.REACTIVATION: [
                f"Oi {lead.name}! Faz um tempo que não conversamos. Como você está? Posso ajudar em algo?",
                f"Olá {lead.name}! Que saudade! Como andam seus projetos? Tem algo que posso apoiar?",
                f"Oi {lead.name}! Pensei em você. Como posso ajudar hoje?"
            ],
            FollowUpType.FEEDBACK: [
                f"Olá {lead.name}! Como foi sua experiência conosco? Seu feedback é muito importante!",
                f"Oi {lead.name}! Gostaria de saber sua opinião sobre nosso atendimento. Como foi para você?",
                f"Olá {lead.name}! Pode compartilhar sua experiência? Queremos sempre melhorar!"
            ]
        }
        
        # Selecionar template aleatório (pode ser melhorado com ML)
        import random
        return random.choice(templates[followup_type])
    
    def _determine_ideal_channel(self, lead: Lead) -> str:
        """Determina o canal ideal baseado no histórico"""
        
        # Analisar canais mais responsivos
        channel_stats = db.session.query(
            Conversation.channel,
            func.count(Conversation.id).label('count'),
            func.avg(Conversation.sentiment).label('avg_sentiment')
        ).filter_by(lead_id=lead.id, direction='inbound')\
         .group_by(Conversation.channel)\
         .order_by(func.count(Conversation.id).desc())\
         .all()
        
        if channel_stats:
            # Retornar canal com mais interações positivas
            best_channel = channel_stats[0].channel
            return best_channel
        
        # Usar fonte original como fallback
        return lead.source or 'whatsapp'
    
    def _get_most_common(self, items: List) -> List:
        """Retorna itens mais comuns em ordem decrescente"""
        if not items:
            return []
        
        from collections import Counter
        counter = Counter(items)
        return [item for item, count in counter.most_common()]
    
    def _calculate_avg_response_time(self, conversations: List[Conversation]) -> Optional[float]:
        """Calcula tempo médio de resposta em horas"""
        if len(conversations) < 2:
            return None
        
        response_times = []
        for i in range(1, len(conversations)):
            time_diff = conversations[i].created_at - conversations[i-1].created_at
            response_times.append(time_diff.total_seconds() / 3600)  # Em horas
        
        return sum(response_times) / len(response_times) if response_times else None
    
    def _record_followup_analytics(self, lead: Lead, followup_type: FollowUpType, 
                                 priority: Priority, scheduled_time: datetime):
        """Registra analytics do follow-up agendado"""
        
        analytics_data = [
            Analytics(
                metric_name='followup_scheduled',
                metric_value=1,
                metric_type='counter',
                channel=lead.source,
                lead_category=lead.category,
                extra_data={
                    'followup_type': followup_type.value,
                    'priority': priority.name,
                    'lead_qualification_score': lead.qualification_score,
                    'scheduled_hour': scheduled_time.hour,
                    'scheduled_day_of_week': scheduled_time.weekday()
                }
            )
        ]
        
        db.session.add_all(analytics_data)
    
    def get_pending_followups(self, limit: int = 50) -> List[Dict]:
        """Retorna follow-ups pendentes ordenados por prioridade e horário"""
        
        now = datetime.utcnow()
        
        pending_followups = FollowUp.query.filter(
            and_(
                FollowUp.status == 'scheduled',
                FollowUp.scheduled_at <= now
            )
        ).order_by(FollowUp.scheduled_at).limit(limit).all()
        
        result = []
        for followup in pending_followups:
            lead = Lead.query.get(followup.lead_id)
            result.append({
                'followup_id': followup.id,
                'lead': lead.to_dict() if lead else None,
                'scheduled_at': followup.scheduled_at.isoformat(),
                'message': followup.message_template,
                'channel': followup.channel,
                'overdue_minutes': (now - followup.scheduled_at).total_seconds() / 60
            })
        
        return result
    
    def execute_followup(self, followup_id: int) -> Dict:
        """Executa um follow-up agendado"""
        
        try:
            followup = FollowUp.query.get(followup_id)
            if not followup:
                return {'success': False, 'error': 'Follow-up não encontrado'}
            
            if followup.status != 'scheduled':
                return {'success': False, 'error': 'Follow-up já foi executado'}
            
            # Aqui você integraria com o sistema de envio real
            # Por enquanto, apenas marcar como enviado
            followup.status = 'sent'
            followup.sent_at = datetime.utcnow()
            
            # Registrar como conversa
            lead = Lead.query.get(followup.lead_id)
            if lead:
                conversation = Conversation(
                    lead_id=lead.id,
                    channel=followup.channel,
                    direction='outbound',
                    message_content=followup.message_template,
                    intent='followup'
                )
                db.session.add(conversation)
                lead.update_interaction()
            
            db.session.commit()
            
            return {
                'success': True,
                'message': 'Follow-up executado com sucesso',
                'sent_at': followup.sent_at.isoformat()
            }
            
        except Exception as e:
            db.session.rollback()
            return {'success': False, 'error': str(e)}


# Instância global do scheduler
followup_scheduler = FollowUpScheduler()


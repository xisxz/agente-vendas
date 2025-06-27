from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum
import json
from dataclasses import dataclass, asdict
from src.models.lead import Lead, Conversation
from src.models.config import SystemConfig

class NotificationType(Enum):
    ESCALATION = "escalation"
    HIGH_PRIORITY_LEAD = "high_priority_lead"
    URGENT_FOLLOWUP = "urgent_followup"
    COMPLAINT = "complaint"
    HOT_LEAD = "hot_lead"
    SYSTEM_ALERT = "system_alert"
    PERFORMANCE_ALERT = "performance_alert"

class NotificationChannel(Enum):
    EMAIL = "email"
    SLACK = "slack"
    WEBHOOK = "webhook"
    SMS = "sms"
    DASHBOARD = "dashboard"

@dataclass
class Notification:
    id: str
    type: NotificationType
    title: str
    message: str
    priority: str  # low, medium, high, urgent
    lead_id: Optional[int] = None
    conversation_id: Optional[int] = None
    metadata: Optional[Dict] = None
    created_at: Optional[datetime] = None
    channels: Optional[List[NotificationChannel]] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.channels is None:
            self.channels = [NotificationChannel.DASHBOARD]
        if self.metadata is None:
            self.metadata = {}

class NotificationService:
    """Serviço de notificações em tempo real para equipe humana"""
    
    def __init__(self):
        self.notification_queue = []
        self.notification_history = []
        self.max_history_size = 1000
        
        # Configurações de notificação por tipo
        self.notification_configs = {
            NotificationType.ESCALATION: {
                'default_channels': [NotificationChannel.SLACK, NotificationChannel.EMAIL],
                'default_priority': 'high',
                'auto_assign': True
            },
            NotificationType.HIGH_PRIORITY_LEAD: {
                'default_channels': [NotificationChannel.SLACK, NotificationChannel.DASHBOARD],
                'default_priority': 'high',
                'auto_assign': True
            },
            NotificationType.URGENT_FOLLOWUP: {
                'default_channels': [NotificationChannel.DASHBOARD, NotificationChannel.EMAIL],
                'default_priority': 'medium',
                'auto_assign': False
            },
            NotificationType.COMPLAINT: {
                'default_channels': [NotificationChannel.SLACK, NotificationChannel.EMAIL, NotificationChannel.SMS],
                'default_priority': 'urgent',
                'auto_assign': True
            },
            NotificationType.HOT_LEAD: {
                'default_channels': [NotificationChannel.SLACK, NotificationChannel.DASHBOARD],
                'default_priority': 'high',
                'auto_assign': True
            },
            NotificationType.SYSTEM_ALERT: {
                'default_channels': [NotificationChannel.EMAIL, NotificationChannel.WEBHOOK],
                'default_priority': 'medium',
                'auto_assign': False
            },
            NotificationType.PERFORMANCE_ALERT: {
                'default_channels': [NotificationChannel.EMAIL, NotificationChannel.DASHBOARD],
                'default_priority': 'low',
                'auto_assign': False
            }
        }
    
    def create_escalation_notification(self, lead: Lead, conversation: Conversation, 
                                     escalation_reason: str, priority: str = 'high') -> Notification:
        """Cria notificação de escalonamento"""
        
        notification = Notification(
            id=f"escalation_{conversation.id}_{datetime.utcnow().timestamp()}",
            type=NotificationType.ESCALATION,
            title=f"🚨 Escalonamento: {lead.name}",
            message=f"Conversa escalonada para atendimento humano.\n"
                   f"Lead: {lead.name} ({lead.email or lead.phone})\n"
                   f"Motivo: {escalation_reason}\n"
                   f"Canal: {conversation.channel}\n"
                   f"Última mensagem: {conversation.message_content[:100]}...",
            priority=priority,
            lead_id=lead.id,
            conversation_id=conversation.id,
            metadata={
                'escalation_reason': escalation_reason,
                'lead_qualification_score': lead.qualification_score,
                'lead_sentiment': lead.sentiment_score,
                'conversation_channel': conversation.channel,
                'conversation_intent': conversation.intent
            },
            channels=self.notification_configs[NotificationType.ESCALATION]['default_channels']
        )
        
        return self._queue_notification(notification)
    
    def create_high_priority_lead_notification(self, lead: Lead, reason: str) -> Notification:
        """Cria notificação para lead de alta prioridade"""
        
        notification = Notification(
            id=f"high_priority_{lead.id}_{datetime.utcnow().timestamp()}",
            type=NotificationType.HIGH_PRIORITY_LEAD,
            title=f"⭐ Lead Alta Prioridade: {lead.name}",
            message=f"Novo lead de alta prioridade identificado.\n"
                   f"Lead: {lead.name} ({lead.email or lead.phone})\n"
                   f"Score: {lead.qualification_score}/10\n"
                   f"Fonte: {lead.source}\n"
                   f"Motivo: {reason}",
            priority='high',
            lead_id=lead.id,
            metadata={
                'qualification_score': lead.qualification_score,
                'lead_source': lead.source,
                'lead_category': lead.category,
                'priority_reason': reason
            },
            channels=self.notification_configs[NotificationType.HIGH_PRIORITY_LEAD]['default_channels']
        )
        
        return self._queue_notification(notification)
    
    def create_complaint_notification(self, lead: Lead, conversation: Conversation, 
                                    sentiment_score: float) -> Notification:
        """Cria notificação para reclamação"""
        
        urgency = "URGENTE" if sentiment_score < -0.7 else "ALTA"
        
        notification = Notification(
            id=f"complaint_{conversation.id}_{datetime.utcnow().timestamp()}",
            type=NotificationType.COMPLAINT,
            title=f"😡 Reclamação {urgency}: {lead.name}",
            message=f"Reclamação detectada com sentimento muito negativo.\n"
                   f"Lead: {lead.name} ({lead.email or lead.phone})\n"
                   f"Sentimento: {sentiment_score:.2f}\n"
                   f"Canal: {conversation.channel}\n"
                   f"Mensagem: {conversation.message_content}",
            priority='urgent' if sentiment_score < -0.7 else 'high',
            lead_id=lead.id,
            conversation_id=conversation.id,
            metadata={
                'sentiment_score': sentiment_score,
                'conversation_channel': conversation.channel,
                'complaint_severity': 'severe' if sentiment_score < -0.7 else 'moderate'
            },
            channels=self.notification_configs[NotificationType.COMPLAINT]['default_channels']
        )
        
        return self._queue_notification(notification)
    
    def create_hot_lead_notification(self, lead: Lead, trigger_event: str) -> Notification:
        """Cria notificação para lead quente"""
        
        notification = Notification(
            id=f"hot_lead_{lead.id}_{datetime.utcnow().timestamp()}",
            type=NotificationType.HOT_LEAD,
            title=f"🔥 Lead Quente: {lead.name}",
            message=f"Lead demonstrou alto interesse!\n"
                   f"Lead: {lead.name} ({lead.email or lead.phone})\n"
                   f"Evento: {trigger_event}\n"
                   f"Score: {lead.qualification_score}/10\n"
                   f"Interações: {lead.interaction_count}",
            priority='high',
            lead_id=lead.id,
            metadata={
                'trigger_event': trigger_event,
                'qualification_score': lead.qualification_score,
                'interaction_count': lead.interaction_count,
                'lead_source': lead.source
            },
            channels=self.notification_configs[NotificationType.HOT_LEAD]['default_channels']
        )
        
        return self._queue_notification(notification)
    
    def create_urgent_followup_notification(self, lead: Lead, followup_type: str, 
                                          overdue_hours: float) -> Notification:
        """Cria notificação para follow-up urgente"""
        
        notification = Notification(
            id=f"urgent_followup_{lead.id}_{datetime.utcnow().timestamp()}",
            type=NotificationType.URGENT_FOLLOWUP,
            title=f"⏰ Follow-up Urgente: {lead.name}",
            message=f"Follow-up em atraso requer atenção.\n"
                   f"Lead: {lead.name} ({lead.email or lead.phone})\n"
                   f"Tipo: {followup_type}\n"
                   f"Atraso: {overdue_hours:.1f} horas\n"
                   f"Última interação: {lead.last_interaction.strftime('%d/%m/%Y %H:%M') if lead.last_interaction else 'Nunca'}",
            priority='medium' if overdue_hours < 24 else 'high',
            lead_id=lead.id,
            metadata={
                'followup_type': followup_type,
                'overdue_hours': overdue_hours,
                'last_interaction': lead.last_interaction.isoformat() if lead.last_interaction else None
            },
            channels=self.notification_configs[NotificationType.URGENT_FOLLOWUP]['default_channels']
        )
        
        return self._queue_notification(notification)
    
    def create_system_alert(self, alert_type: str, message: str, severity: str = 'medium') -> Notification:
        """Cria alerta do sistema"""
        
        notification = Notification(
            id=f"system_alert_{alert_type}_{datetime.utcnow().timestamp()}",
            type=NotificationType.SYSTEM_ALERT,
            title=f"🔧 Alerta do Sistema: {alert_type}",
            message=message,
            priority=severity,
            metadata={
                'alert_type': alert_type,
                'system_component': 'sales_agent'
            },
            channels=self.notification_configs[NotificationType.SYSTEM_ALERT]['default_channels']
        )
        
        return self._queue_notification(notification)
    
    def create_performance_alert(self, metric_name: str, current_value: float, 
                               threshold: float, trend: str) -> Notification:
        """Cria alerta de performance"""
        
        notification = Notification(
            id=f"performance_alert_{metric_name}_{datetime.utcnow().timestamp()}",
            type=NotificationType.PERFORMANCE_ALERT,
            title=f"📊 Alerta de Performance: {metric_name}",
            message=f"Métrica de performance requer atenção.\n"
                   f"Métrica: {metric_name}\n"
                   f"Valor atual: {current_value}\n"
                   f"Limite: {threshold}\n"
                   f"Tendência: {trend}",
            priority='low' if abs(current_value - threshold) < threshold * 0.1 else 'medium',
            metadata={
                'metric_name': metric_name,
                'current_value': current_value,
                'threshold': threshold,
                'trend': trend
            },
            channels=self.notification_configs[NotificationType.PERFORMANCE_ALERT]['default_channels']
        )
        
        return self._queue_notification(notification)
    
    def _queue_notification(self, notification: Notification) -> Notification:
        """Adiciona notificação à fila"""
        
        self.notification_queue.append(notification)
        self._add_to_history(notification)
        
        # Processar notificação imediatamente se for urgente
        if notification.priority == 'urgent':
            self._process_notification(notification)
        
        return notification
    
    def _add_to_history(self, notification: Notification):
        """Adiciona notificação ao histórico"""
        
        self.notification_history.append(notification)
        
        # Manter tamanho do histórico
        if len(self.notification_history) > self.max_history_size:
            self.notification_history = self.notification_history[-self.max_history_size:]
    
    def _process_notification(self, notification: Notification):
        """Processa uma notificação enviando pelos canais configurados"""
        
        for channel in notification.channels:
            try:
                if channel == NotificationChannel.SLACK:
                    self._send_slack_notification(notification)
                elif channel == NotificationChannel.EMAIL:
                    self._send_email_notification(notification)
                elif channel == NotificationChannel.SMS:
                    self._send_sms_notification(notification)
                elif channel == NotificationChannel.WEBHOOK:
                    self._send_webhook_notification(notification)
                # Dashboard notifications são armazenadas na fila
                
            except Exception as e:
                print(f"Erro ao enviar notificação via {channel.value}: {str(e)}")
    
    def _send_slack_notification(self, notification: Notification):
        """Envia notificação para Slack"""
        
        # Aqui você integraria com a API do Slack
        # Por enquanto, apenas log
        slack_message = {
            "text": notification.title,
            "attachments": [
                {
                    "color": self._get_color_for_priority(notification.priority),
                    "fields": [
                        {
                            "title": "Mensagem",
                            "value": notification.message,
                            "short": False
                        },
                        {
                            "title": "Prioridade",
                            "value": notification.priority.upper(),
                            "short": True
                        },
                        {
                            "title": "Tipo",
                            "value": notification.type.value,
                            "short": True
                        }
                    ],
                    "ts": notification.created_at.timestamp()
                }
            ]
        }
        
        print(f"[SLACK] {json.dumps(slack_message, indent=2)}")
    
    def _send_email_notification(self, notification: Notification):
        """Envia notificação por email"""
        
        # Aqui você integraria com serviço de email
        email_data = {
            "to": self._get_notification_recipients('email'),
            "subject": notification.title,
            "body": f"""
{notification.message}

Detalhes:
- Tipo: {notification.type.value}
- Prioridade: {notification.priority}
- Data/Hora: {notification.created_at.strftime('%d/%m/%Y %H:%M:%S')}

{self._format_metadata_for_email(notification.metadata)}
            """.strip()
        }
        
        print(f"[EMAIL] {json.dumps(email_data, indent=2)}")
    
    def _send_sms_notification(self, notification: Notification):
        """Envia notificação por SMS"""
        
        # SMS deve ser conciso
        sms_message = f"{notification.title}\n{notification.message[:100]}..."
        
        sms_data = {
            "to": self._get_notification_recipients('sms'),
            "message": sms_message
        }
        
        print(f"[SMS] {json.dumps(sms_data, indent=2)}")
    
    def _send_webhook_notification(self, notification: Notification):
        """Envia notificação via webhook"""
        
        webhook_data = {
            "notification": asdict(notification),
            "timestamp": notification.created_at.isoformat()
        }
        
        print(f"[WEBHOOK] {json.dumps(webhook_data, indent=2)}")
    
    def _get_color_for_priority(self, priority: str) -> str:
        """Retorna cor para prioridade (Slack)"""
        colors = {
            'low': '#36a64f',      # Verde
            'medium': '#ff9500',   # Laranja
            'high': '#ff0000',     # Vermelho
            'urgent': '#8b0000'    # Vermelho escuro
        }
        return colors.get(priority, '#cccccc')
    
    def _get_notification_recipients(self, channel: str) -> List[str]:
        """Retorna lista de destinatários para o canal"""
        
        # Aqui você buscaria da configuração do sistema
        recipients = {
            'email': ['vendas@empresa.com', 'gerente@empresa.com'],
            'sms': ['+5511999999999']
        }
        
        return recipients.get(channel, [])
    
    def _format_metadata_for_email(self, metadata: Dict) -> str:
        """Formata metadados para email"""
        
        if not metadata:
            return ""
        
        formatted = "Informações adicionais:\n"
        for key, value in metadata.items():
            formatted += f"- {key.replace('_', ' ').title()}: {value}\n"
        
        return formatted
    
    def get_pending_notifications(self, limit: int = 50) -> List[Dict]:
        """Retorna notificações pendentes"""
        
        # Filtrar apenas notificações do dashboard
        dashboard_notifications = [
            n for n in self.notification_queue 
            if NotificationChannel.DASHBOARD in n.channels
        ]
        
        # Ordenar por prioridade e data
        priority_order = {'urgent': 4, 'high': 3, 'medium': 2, 'low': 1}
        dashboard_notifications.sort(
            key=lambda x: (priority_order.get(x.priority, 0), x.created_at),
            reverse=True
        )
        
        return [asdict(n) for n in dashboard_notifications[:limit]]
    
    def mark_notification_as_read(self, notification_id: str) -> bool:
        """Marca notificação como lida"""
        
        for i, notification in enumerate(self.notification_queue):
            if notification.id == notification_id:
                del self.notification_queue[i]
                return True
        
        return False
    
    def get_notification_stats(self) -> Dict:
        """Retorna estatísticas de notificações"""
        
        total_notifications = len(self.notification_history)
        pending_notifications = len(self.notification_queue)
        
        # Contar por tipo
        by_type = {}
        for notification in self.notification_history:
            type_name = notification.type.value
            by_type[type_name] = by_type.get(type_name, 0) + 1
        
        # Contar por prioridade
        by_priority = {}
        for notification in self.notification_history:
            priority = notification.priority
            by_priority[priority] = by_priority.get(priority, 0) + 1
        
        return {
            'total_notifications': total_notifications,
            'pending_notifications': pending_notifications,
            'by_type': by_type,
            'by_priority': by_priority
        }
    
    def process_pending_notifications(self):
        """Processa todas as notificações pendentes"""
        
        processed_count = 0
        
        for notification in self.notification_queue.copy():
            try:
                self._process_notification(notification)
                processed_count += 1
            except Exception as e:
                print(f"Erro ao processar notificação {notification.id}: {str(e)}")
        
        return processed_count


# Instância global do serviço
notification_service = NotificationService()


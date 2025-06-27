from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from src.models.user import db

class SystemConfig(db.Model):
    __tablename__ = 'system_config'
    
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=True)
    description = db.Column(db.Text, nullable=True)
    is_encrypted = db.Column(db.Boolean, default=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<SystemConfig {self.key}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'key': self.key,
            'value': self.value if not self.is_encrypted else '***',
            'description': self.description,
            'is_encrypted': self.is_encrypted,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class CRMIntegration(db.Model):
    __tablename__ = 'crm_integrations'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)  # pipedrive, hubspot, etc
    api_url = db.Column(db.String(255), nullable=False)
    api_key = db.Column(db.Text, nullable=True)  # criptografado
    api_token = db.Column(db.Text, nullable=True)  # criptografado
    
    # Configurações específicas
    webhook_url = db.Column(db.String(255), nullable=True)
    webhook_secret = db.Column(db.String(255), nullable=True)
    
    # Status
    is_active = db.Column(db.Boolean, default=True)
    last_sync = db.Column(db.DateTime, nullable=True)
    sync_status = db.Column(db.String(50), default='pending')  # pending, success, error
    error_message = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<CRMIntegration {self.name}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'api_url': self.api_url,
            'webhook_url': self.webhook_url,
            'is_active': self.is_active,
            'last_sync': self.last_sync.isoformat() if self.last_sync else None,
            'sync_status': self.sync_status,
            'error_message': self.error_message,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class MessageTemplate(db.Model):
    __tablename__ = 'message_templates'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False)  # welcome, followup, qualification, etc
    channel = db.Column(db.String(50), nullable=False)  # whatsapp, email, chat, phone
    
    # Conteúdo do template
    subject = db.Column(db.String(255), nullable=True)  # para emails
    content = db.Column(db.Text, nullable=False)
    variables = db.Column(db.JSON, nullable=True)  # variáveis disponíveis
    
    # Configurações
    is_active = db.Column(db.Boolean, default=True)
    trigger_conditions = db.Column(db.JSON, nullable=True)  # condições para disparo automático
    
    # Métricas
    usage_count = db.Column(db.Integer, default=0)
    success_rate = db.Column(db.Float, default=0.0)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<MessageTemplate {self.name} - {self.category}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'category': self.category,
            'channel': self.channel,
            'subject': self.subject,
            'content': self.content,
            'variables': self.variables,
            'is_active': self.is_active,
            'trigger_conditions': self.trigger_conditions,
            'usage_count': self.usage_count,
            'success_rate': self.success_rate,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class Analytics(db.Model):
    __tablename__ = 'analytics'
    
    id = db.Column(db.Integer, primary_key=True)
    metric_name = db.Column(db.String(100), nullable=False)
    metric_value = db.Column(db.Float, nullable=False)
    metric_type = db.Column(db.String(50), nullable=False)  # counter, gauge, histogram
    
    # Dimensões
    channel = db.Column(db.String(50), nullable=True)
    lead_category = db.Column(db.String(100), nullable=True)
    time_period = db.Column(db.String(20), nullable=True)  # hourly, daily, weekly, monthly
    
    # Metadados
    extra_data = db.Column(db.JSON, nullable=True)
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Analytics {self.metric_name}: {self.metric_value}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'metric_name': self.metric_name,
            'metric_value': self.metric_value,
            'metric_type': self.metric_type,
            'channel': self.channel,
            'lead_category': self.lead_category,
            'time_period': self.time_period,
            'extra_data': self.extra_data,
            'recorded_at': self.recorded_at.isoformat() if self.recorded_at else None
        }


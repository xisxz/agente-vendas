from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from src.models.user import db

class Lead(db.Model):
    __tablename__ = 'leads'
    
    id = db.Column(db.Integer, primary_key=True)
    pipedrive_id = db.Column(db.Integer, unique=True, nullable=True)  # ID no Pipedrive
    name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), nullable=True)
    phone = db.Column(db.String(50), nullable=True)
    company = db.Column(db.String(255), nullable=True)
    location = db.Column(db.String(255), nullable=True)
    
    # Status e qualificação
    status = db.Column(db.String(50), default='new')  # new, qualified, contacted, converted, lost
    qualification_score = db.Column(db.Float, default=0.0)
    category = db.Column(db.String(100), nullable=True)  # categoria do lead
    
    # Dados comportamentais
    last_interaction = db.Column(db.DateTime, default=datetime.utcnow)
    interaction_count = db.Column(db.Integer, default=0)
    sentiment_score = db.Column(db.Float, default=0.0)  # -1 a 1
    
    # Metadados
    source = db.Column(db.String(100), nullable=True)  # whatsapp, email, chat, phone
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relacionamentos
    conversations = db.relationship('Conversation', backref='lead', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Lead {self.name} - {self.status}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'pipedrive_id': self.pipedrive_id,
            'name': self.name,
            'email': self.email,
            'phone': self.phone,
            'company': self.company,
            'location': self.location,
            'status': self.status,
            'qualification_score': self.qualification_score,
            'category': self.category,
            'last_interaction': self.last_interaction.isoformat() if self.last_interaction else None,
            'interaction_count': self.interaction_count,
            'sentiment_score': self.sentiment_score,
            'source': self.source,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    def update_interaction(self):
        """Atualiza dados de interação"""
        self.last_interaction = datetime.utcnow()
        self.interaction_count += 1
        self.updated_at = datetime.utcnow()


class Conversation(db.Model):
    __tablename__ = 'conversations'
    
    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey('leads.id'), nullable=False)
    
    # Dados da mensagem
    channel = db.Column(db.String(50), nullable=False)  # whatsapp, email, chat, phone
    direction = db.Column(db.String(10), nullable=False)  # inbound, outbound
    message_content = db.Column(db.Text, nullable=False)
    
    # Análise de PLN
    intent = db.Column(db.String(100), nullable=True)
    entities = db.Column(db.JSON, nullable=True)  # entidades extraídas
    sentiment = db.Column(db.Float, nullable=True)  # sentimento da mensagem
    confidence = db.Column(db.Float, nullable=True)  # confiança da análise
    
    # Metadados
    is_escalated = db.Column(db.Boolean, default=False)
    escalation_reason = db.Column(db.String(255), nullable=True)
    human_agent_id = db.Column(db.String(100), nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Conversation {self.id} - {self.channel} - {self.direction}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'lead_id': self.lead_id,
            'channel': self.channel,
            'direction': self.direction,
            'message_content': self.message_content,
            'intent': self.intent,
            'entities': self.entities,
            'sentiment': self.sentiment,
            'confidence': self.confidence,
            'is_escalated': self.is_escalated,
            'escalation_reason': self.escalation_reason,
            'human_agent_id': self.human_agent_id,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class FollowUp(db.Model):
    __tablename__ = 'followups'
    
    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey('leads.id'), nullable=False)
    
    # Dados do follow-up
    scheduled_at = db.Column(db.DateTime, nullable=False)
    message_template = db.Column(db.Text, nullable=False)
    channel = db.Column(db.String(50), nullable=False)
    
    # Status
    status = db.Column(db.String(20), default='scheduled')  # scheduled, sent, failed, cancelled
    sent_at = db.Column(db.DateTime, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relacionamento
    lead = db.relationship('Lead', backref='followups')
    
    def __repr__(self):
        return f'<FollowUp {self.id} - {self.status}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'lead_id': self.lead_id,
            'scheduled_at': self.scheduled_at.isoformat() if self.scheduled_at else None,
            'message_template': self.message_template,
            'channel': self.channel,
            'status': self.status,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
            'error_message': self.error_message,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


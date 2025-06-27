from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from datetime import datetime
import re
import json

class ChannelAdapter(ABC):
    """Classe base para adaptadores de canal"""
    
    def __init__(self, channel_name: str):
        self.channel_name = channel_name
        self.max_message_length = 1000  # Padrão
        self.supports_rich_text = False
        self.supports_attachments = False
        self.supports_quick_replies = False
    
    @abstractmethod
    def format_outbound_message(self, message: str, lead_data: Dict = None, context: Dict = None) -> Dict:
        """Formata uma mensagem para envio no canal específico"""
        pass
    
    @abstractmethod
    def parse_inbound_message(self, raw_message: Dict) -> Dict:
        """Processa uma mensagem recebida do canal específico"""
        pass
    
    @abstractmethod
    def validate_message(self, message: str) -> Dict:
        """Valida se a mensagem está adequada para o canal"""
        pass
    
    def truncate_message(self, message: str) -> str:
        """Trunca mensagem se exceder o limite do canal"""
        if len(message) <= self.max_message_length:
            return message
        
        truncated = message[:self.max_message_length - 3] + "..."
        return truncated
    
    def extract_contact_info(self, message: str) -> Dict:
        """Extrai informações de contato da mensagem"""
        contact_info = {}
        
        # Email
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        emails = re.findall(email_pattern, message)
        if emails:
            contact_info['email'] = emails[0]
        
        # Telefone brasileiro
        phone_pattern = r'(?:\+55\s?)?(?:\(?[1-9]{2}\)?\s?)?(?:9\s?)?[0-9]{4}[-\s]?[0-9]{4}'
        phones = re.findall(phone_pattern, message)
        if phones:
            contact_info['phone'] = phones[0]
        
        return contact_info


class WhatsAppAdapter(ChannelAdapter):
    """Adaptador para WhatsApp Business API"""
    
    def __init__(self):
        super().__init__("whatsapp")
        self.max_message_length = 4096
        self.supports_rich_text = True
        self.supports_attachments = True
        self.supports_quick_replies = True
    
    def format_outbound_message(self, message: str, lead_data: Dict = None, context: Dict = None) -> Dict:
        """Formata mensagem para WhatsApp"""
        
        # Adicionar emojis apropriados
        formatted_message = self._add_emojis(message)
        
        # Truncar se necessário
        formatted_message = self.truncate_message(formatted_message)
        
        # Estrutura para WhatsApp Business API
        whatsapp_message = {
            "messaging_product": "whatsapp",
            "to": lead_data.get('phone') if lead_data else None,
            "type": "text",
            "text": {
                "body": formatted_message
            }
        }
        
        # Adicionar quick replies se apropriado
        if context and context.get('add_quick_replies'):
            whatsapp_message["type"] = "interactive"
            whatsapp_message["interactive"] = {
                "type": "button",
                "body": {"text": formatted_message},
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": "more_info", "title": "Mais informações"}},
                        {"type": "reply", "reply": {"id": "talk_human", "title": "Falar com humano"}},
                        {"type": "reply", "reply": {"id": "schedule_demo", "title": "Agendar demo"}}
                    ]
                }
            }
            del whatsapp_message["text"]
        
        return whatsapp_message
    
    def parse_inbound_message(self, raw_message: Dict) -> Dict:
        """Processa mensagem recebida do WhatsApp"""
        
        # Estrutura típica do webhook do WhatsApp
        message_data = {
            'channel': 'whatsapp',
            'direction': 'inbound',
            'timestamp': datetime.utcnow().isoformat(),
            'sender_info': {},
            'message_content': '',
            'message_type': 'text',
            'metadata': {}
        }
        
        try:
            # Extrair dados do remetente
            if 'contacts' in raw_message and raw_message['contacts']:
                contact = raw_message['contacts'][0]
                message_data['sender_info'] = {
                    'phone': contact.get('wa_id'),
                    'name': contact.get('profile', {}).get('name', 'Usuário WhatsApp')
                }
            
            # Extrair conteúdo da mensagem
            if 'messages' in raw_message and raw_message['messages']:
                msg = raw_message['messages'][0]
                message_data['message_type'] = msg.get('type', 'text')
                
                if msg['type'] == 'text':
                    message_data['message_content'] = msg['text']['body']
                elif msg['type'] == 'interactive':
                    # Resposta de botão
                    if 'button_reply' in msg['interactive']:
                        message_data['message_content'] = msg['interactive']['button_reply']['title']
                        message_data['metadata']['button_id'] = msg['interactive']['button_reply']['id']
                
                message_data['metadata']['message_id'] = msg.get('id')
                message_data['timestamp'] = msg.get('timestamp')
        
        except Exception as e:
            message_data['error'] = str(e)
        
        return message_data
    
    def validate_message(self, message: str) -> Dict:
        """Valida mensagem para WhatsApp"""
        issues = []
        
        if len(message) > self.max_message_length:
            issues.append(f"Mensagem muito longa ({len(message)} caracteres, máximo {self.max_message_length})")
        
        # Verificar caracteres não suportados
        if any(ord(char) > 65535 for char in message):
            issues.append("Contém caracteres não suportados pelo WhatsApp")
        
        return {
            'is_valid': len(issues) == 0,
            'issues': issues,
            'formatted_length': len(message)
        }
    
    def _add_emojis(self, message: str) -> str:
        """Adiciona emojis apropriados para WhatsApp"""
        
        # Mapeamento de contextos para emojis
        emoji_map = {
            'saudação': '👋',
            'produto': '🛍️',
            'preço': '💰',
            'demo': '🎯',
            'suporte': '🆘',
            'obrigado': '🙏',
            'parabéns': '🎉'
        }
        
        message_lower = message.lower()
        
        # Adicionar emoji no início se apropriado
        for context, emoji in emoji_map.items():
            if any(word in message_lower for word in self._get_context_words(context)):
                if not message.startswith(emoji):
                    message = f"{emoji} {message}"
                break
        
        return message
    
    def _get_context_words(self, context: str) -> List[str]:
        """Retorna palavras-chave para cada contexto"""
        context_words = {
            'saudação': ['olá', 'oi', 'bom dia', 'boa tarde', 'boa noite'],
            'produto': ['produto', 'serviço', 'solução'],
            'preço': ['preço', 'valor', 'custo', 'quanto'],
            'demo': ['demonstração', 'demo', 'apresentação'],
            'suporte': ['ajuda', 'suporte', 'problema'],
            'obrigado': ['obrigado', 'obrigada', 'valeu'],
            'parabéns': ['parabéns', 'excelente', 'ótimo']
        }
        return context_words.get(context, [])


class EmailAdapter(ChannelAdapter):
    """Adaptador para Email"""
    
    def __init__(self):
        super().__init__("email")
        self.max_message_length = 10000
        self.supports_rich_text = True
        self.supports_attachments = True
        self.supports_quick_replies = False
    
    def format_outbound_message(self, message: str, lead_data: Dict = None, context: Dict = None) -> Dict:
        """Formata mensagem para Email"""
        
        # Estrutura de email
        email_data = {
            'to': lead_data.get('email') if lead_data else None,
            'subject': self._generate_subject(message, context),
            'body_text': message,
            'body_html': self._convert_to_html(message),
            'from_name': context.get('sender_name', 'Equipe de Vendas'),
            'from_email': context.get('sender_email', 'vendas@empresa.com')
        }
        
        # Adicionar assinatura
        signature = self._get_email_signature(context)
        email_data['body_text'] += f"\n\n{signature}"
        email_data['body_html'] += f"<br><br>{self._convert_to_html(signature)}"
        
        return email_data
    
    def parse_inbound_message(self, raw_message: Dict) -> Dict:
        """Processa email recebido"""
        
        message_data = {
            'channel': 'email',
            'direction': 'inbound',
            'timestamp': datetime.utcnow().isoformat(),
            'sender_info': {},
            'message_content': '',
            'message_type': 'email',
            'metadata': {}
        }
        
        try:
            message_data['sender_info'] = {
                'email': raw_message.get('from_email'),
                'name': raw_message.get('from_name', 'Usuário Email')
            }
            
            message_data['message_content'] = raw_message.get('text_body', raw_message.get('html_body', ''))
            message_data['metadata'] = {
                'subject': raw_message.get('subject'),
                'message_id': raw_message.get('message_id'),
                'thread_id': raw_message.get('thread_id')
            }
        
        except Exception as e:
            message_data['error'] = str(e)
        
        return message_data
    
    def validate_message(self, message: str) -> Dict:
        """Valida mensagem para Email"""
        issues = []
        
        if len(message) > self.max_message_length:
            issues.append(f"Email muito longo ({len(message)} caracteres, máximo {self.max_message_length})")
        
        return {
            'is_valid': len(issues) == 0,
            'issues': issues,
            'formatted_length': len(message)
        }
    
    def _generate_subject(self, message: str, context: Dict = None) -> str:
        """Gera assunto do email baseado no conteúdo"""
        
        if context and context.get('subject'):
            return context['subject']
        
        # Gerar assunto baseado no conteúdo
        message_lower = message.lower()
        
        if 'demo' in message_lower or 'demonstração' in message_lower:
            return "Demonstração dos nossos produtos"
        elif 'preço' in message_lower or 'valor' in message_lower:
            return "Informações sobre preços e condições"
        elif 'produto' in message_lower or 'serviço' in message_lower:
            return "Informações sobre nossos produtos"
        elif 'suporte' in message_lower or 'ajuda' in message_lower:
            return "Suporte técnico"
        else:
            return "Resposta da nossa equipe"
    
    def _convert_to_html(self, text: str) -> str:
        """Converte texto simples para HTML"""
        html = text.replace('\n', '<br>')
        
        # Converter URLs em links
        url_pattern = r'(https?://[^\s]+)'
        html = re.sub(url_pattern, r'<a href="\1">\1</a>', html)
        
        return html
    
    def _get_email_signature(self, context: Dict = None) -> str:
        """Retorna assinatura do email"""
        return """
Atenciosamente,
Equipe de Vendas
📧 vendas@empresa.com
📱 (11) 99999-9999
🌐 www.empresa.com
        """.strip()


class ChatAdapter(ChannelAdapter):
    """Adaptador para Chat Web"""
    
    def __init__(self):
        super().__init__("chat")
        self.max_message_length = 2000
        self.supports_rich_text = True
        self.supports_attachments = False
        self.supports_quick_replies = True
    
    def format_outbound_message(self, message: str, lead_data: Dict = None, context: Dict = None) -> Dict:
        """Formata mensagem para Chat Web"""
        
        formatted_message = self.truncate_message(message)
        
        chat_message = {
            'type': 'text',
            'content': formatted_message,
            'timestamp': datetime.utcnow().isoformat(),
            'sender': 'bot',
            'metadata': {
                'channel': 'chat',
                'lead_id': lead_data.get('id') if lead_data else None
            }
        }
        
        # Adicionar quick replies se apropriado
        if context and context.get('add_quick_replies'):
            chat_message['quick_replies'] = [
                {'text': 'Mais informações', 'payload': 'more_info'},
                {'text': 'Falar com atendente', 'payload': 'talk_human'},
                {'text': 'Agendar demonstração', 'payload': 'schedule_demo'}
            ]
        
        return chat_message
    
    def parse_inbound_message(self, raw_message: Dict) -> Dict:
        """Processa mensagem recebida do Chat"""
        
        message_data = {
            'channel': 'chat',
            'direction': 'inbound',
            'timestamp': raw_message.get('timestamp', datetime.utcnow().isoformat()),
            'sender_info': {},
            'message_content': raw_message.get('content', ''),
            'message_type': raw_message.get('type', 'text'),
            'metadata': raw_message.get('metadata', {})
        }
        
        # Extrair informações do usuário se disponível
        if 'user' in raw_message:
            user = raw_message['user']
            message_data['sender_info'] = {
                'name': user.get('name', 'Usuário Chat'),
                'email': user.get('email'),
                'session_id': user.get('session_id')
            }
        
        return message_data
    
    def validate_message(self, message: str) -> Dict:
        """Valida mensagem para Chat"""
        issues = []
        
        if len(message) > self.max_message_length:
            issues.append(f"Mensagem muito longa para chat ({len(message)} caracteres, máximo {self.max_message_length})")
        
        return {
            'is_valid': len(issues) == 0,
            'issues': issues,
            'formatted_length': len(message)
        }


class PhoneAdapter(ChannelAdapter):
    """Adaptador para Telefone/Voz"""
    
    def __init__(self):
        super().__init__("phone")
        self.max_message_length = 500  # Mensagens de voz devem ser mais curtas
        self.supports_rich_text = False
        self.supports_attachments = False
        self.supports_quick_replies = False
    
    def format_outbound_message(self, message: str, lead_data: Dict = None, context: Dict = None) -> Dict:
        """Formata mensagem para síntese de voz"""
        
        # Adaptar para fala natural
        speech_message = self._adapt_for_speech(message)
        speech_message = self.truncate_message(speech_message)
        
        phone_message = {
            'type': 'speech',
            'content': speech_message,
            'voice_settings': {
                'language': 'pt-BR',
                'gender': 'female',
                'speed': 'normal'
            },
            'phone_number': lead_data.get('phone') if lead_data else None
        }
        
        return phone_message
    
    def parse_inbound_message(self, raw_message: Dict) -> Dict:
        """Processa chamada/áudio recebido"""
        
        message_data = {
            'channel': 'phone',
            'direction': 'inbound',
            'timestamp': raw_message.get('timestamp', datetime.utcnow().isoformat()),
            'sender_info': {},
            'message_content': raw_message.get('transcription', ''),
            'message_type': 'voice',
            'metadata': {
                'call_duration': raw_message.get('duration'),
                'audio_url': raw_message.get('audio_url'),
                'confidence': raw_message.get('transcription_confidence')
            }
        }
        
        if 'caller_id' in raw_message:
            message_data['sender_info'] = {
                'phone': raw_message['caller_id'],
                'name': 'Usuário Telefone'
            }
        
        return message_data
    
    def validate_message(self, message: str) -> Dict:
        """Valida mensagem para telefone"""
        issues = []
        
        if len(message) > self.max_message_length:
            issues.append(f"Mensagem muito longa para voz ({len(message)} caracteres, máximo {self.max_message_length})")
        
        # Verificar se contém apenas texto falável
        if re.search(r'[^\w\s\.,!?áéíóúâêîôûàèìòùãõç-]', message, re.IGNORECASE):
            issues.append("Contém caracteres não adequados para síntese de voz")
        
        return {
            'is_valid': len(issues) == 0,
            'issues': issues,
            'formatted_length': len(message)
        }
    
    def _adapt_for_speech(self, message: str) -> str:
        """Adapta texto para síntese de voz natural"""
        
        # Substituir abreviações
        replacements = {
            'R$': 'reais',
            '%': 'por cento',
            '&': 'e',
            '@': 'arroba',
            'www.': 'www ponto',
            '.com': 'ponto com'
        }
        
        adapted = message
        for old, new in replacements.items():
            adapted = adapted.replace(old, new)
        
        # Adicionar pausas naturais
        adapted = adapted.replace('.', '. ')
        adapted = adapted.replace(',', ', ')
        adapted = adapted.replace('!', '! ')
        adapted = adapted.replace('?', '? ')
        
        return adapted


class ChannelManager:
    """Gerenciador central dos adaptadores de canal"""
    
    def __init__(self):
        self.adapters = {
            'whatsapp': WhatsAppAdapter(),
            'email': EmailAdapter(),
            'chat': ChatAdapter(),
            'phone': PhoneAdapter()
        }
    
    def get_adapter(self, channel: str) -> ChannelAdapter:
        """Retorna o adaptador para o canal especificado"""
        return self.adapters.get(channel.lower())
    
    def format_message(self, channel: str, message: str, lead_data: Dict = None, context: Dict = None) -> Dict:
        """Formata mensagem para o canal específico"""
        adapter = self.get_adapter(channel)
        if not adapter:
            raise ValueError(f"Canal não suportado: {channel}")
        
        return adapter.format_outbound_message(message, lead_data, context)
    
    def parse_message(self, channel: str, raw_message: Dict) -> Dict:
        """Processa mensagem recebida do canal específico"""
        adapter = self.get_adapter(channel)
        if not adapter:
            raise ValueError(f"Canal não suportado: {channel}")
        
        return adapter.parse_inbound_message(raw_message)
    
    def validate_message(self, channel: str, message: str) -> Dict:
        """Valida mensagem para o canal específico"""
        adapter = self.get_adapter(channel)
        if not adapter:
            raise ValueError(f"Canal não suportado: {channel}")
        
        return adapter.validate_message(message)
    
    def get_supported_channels(self) -> List[str]:
        """Retorna lista de canais suportados"""
        return list(self.adapters.keys())
    
    def get_channel_capabilities(self, channel: str) -> Dict:
        """Retorna capacidades do canal"""
        adapter = self.get_adapter(channel)
        if not adapter:
            return {}
        
        return {
            'max_message_length': adapter.max_message_length,
            'supports_rich_text': adapter.supports_rich_text,
            'supports_attachments': adapter.supports_attachments,
            'supports_quick_replies': adapter.supports_quick_replies
        }


# Instância global do gerenciador
channel_manager = ChannelManager()


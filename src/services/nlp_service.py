import spacy
import re
from typing import Dict, List, Optional, Tuple
from textblob import TextBlob
from datetime import datetime
import json

class NLPService:
    """Serviço de Processamento de Linguagem Natural para o agente de vendas"""
    
    def __init__(self):
        # Carregar modelo do spaCy para português
        try:
            self.nlp = spacy.load("pt_core_news_sm")
        except OSError:
            print("Modelo pt_core_news_sm não encontrado. Usando modelo em branco.")
            self.nlp = spacy.blank("pt")
        
        # Definir intenções e suas palavras-chave
        self.intent_patterns = {
            'greeting': [
                'olá', 'oi', 'bom dia', 'boa tarde', 'boa noite', 'e aí', 'tudo bem',
                'como vai', 'prazer', 'hello', 'hi'
            ],
            'product_inquiry': [
                'produto', 'serviço', 'oferta', 'venda', 'comprar', 'preço', 'valor',
                'custo', 'quanto custa', 'informação', 'detalhes', 'especificação',
                'catálogo', 'disponível', 'estoque'
            ],
            'demo_request': [
                'demonstração', 'demo', 'teste', 'experimentar', 'ver funcionando',
                'apresentação', 'mostrar', 'exemplo', 'trial', 'versão de teste'
            ],
            'pricing_inquiry': [
                'preço', 'valor', 'custo', 'quanto', 'orçamento', 'cotação',
                'investimento', 'plano', 'pacote', 'tabela de preços'
            ],
            'support_request': [
                'ajuda', 'suporte', 'problema', 'dúvida', 'dificuldade', 'erro',
                'não funciona', 'bug', 'assistência', 'socorro'
            ],
            'complaint': [
                'reclamação', 'problema', 'insatisfeito', 'ruim', 'péssimo',
                'não gostei', 'decepcionado', 'cancelar', 'reembolso'
            ],
            'compliment': [
                'parabéns', 'excelente', 'ótimo', 'muito bom', 'perfeito',
                'adorei', 'gostei', 'satisfeito', 'recomendo'
            ],
            'goodbye': [
                'tchau', 'até logo', 'até mais', 'bye', 'adeus', 'falou',
                'até a próxima', 'obrigado', 'valeu'
            ],
            'contact_info': [
                'contato', 'telefone', 'email', 'endereço', 'localização',
                'onde fica', 'como falar', 'whatsapp'
            ],
            'availability': [
                'disponível', 'horário', 'quando', 'prazo', 'entrega',
                'funcionamento', 'aberto', 'fechado'
            ]
        }
        
        # Entidades importantes para vendas
        self.entity_patterns = {
            'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            'phone': r'(?:\+55\s?)?(?:\(?[1-9]{2}\)?\s?)?(?:9\s?)?[0-9]{4}[-\s]?[0-9]{4}',
            'money': r'R\$\s?[\d.,]+|[\d.,]+\s?reais?',
            'company': r'\b[A-Z][a-zA-Z\s]+(?:Ltda|S\.A\.|EIRELI|ME)\b',
            'name': r'\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)+\b'
        }
    
    def analyze_message(self, message: str) -> Dict:
        """Analisa uma mensagem e retorna intenção, entidades e sentimento"""
        
        # Limpar e normalizar texto
        cleaned_message = self._clean_text(message)
        
        # Processar com spaCy
        doc = self.nlp(cleaned_message)
        
        # Detectar intenção
        intent = self._detect_intent(cleaned_message)
        
        # Extrair entidades
        entities = self._extract_entities(message, doc)
        
        # Analisar sentimento
        sentiment = self._analyze_sentiment(cleaned_message)
        
        # Calcular confiança
        confidence = self._calculate_confidence(intent, entities, sentiment)
        
        return {
            'intent': intent,
            'entities': entities,
            'sentiment': sentiment,
            'confidence': confidence,
            'processed_text': cleaned_message,
            'tokens': [token.text for token in doc],
            'pos_tags': [(token.text, token.pos_) for token in doc]
        }
    
    def _clean_text(self, text: str) -> str:
        """Limpa e normaliza o texto"""
        # Converter para minúsculas
        text = text.lower()
        
        # Remover caracteres especiais excessivos
        text = re.sub(r'[!]{2,}', '!', text)
        text = re.sub(r'[?]{2,}', '?', text)
        text = re.sub(r'[.]{2,}', '...', text)
        
        # Remover espaços extras
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def _detect_intent(self, text: str) -> str:
        """Detecta a intenção da mensagem"""
        intent_scores = {}
        
        for intent, keywords in self.intent_patterns.items():
            score = 0
            for keyword in keywords:
                if keyword in text:
                    # Dar mais peso para palavras exatas
                    if f' {keyword} ' in f' {text} ':
                        score += 2
                    else:
                        score += 1
            
            if score > 0:
                intent_scores[intent] = score
        
        if intent_scores:
            # Retornar intenção com maior score
            return max(intent_scores, key=intent_scores.get)
        
        return 'general'
    
    def _extract_entities(self, text: str, doc) -> Dict:
        """Extrai entidades do texto"""
        entities = {}
        
        # Entidades do spaCy
        spacy_entities = {}
        for ent in doc.ents:
            if ent.label_ not in spacy_entities:
                spacy_entities[ent.label_] = []
            spacy_entities[ent.label_].append(ent.text)
        
        entities['spacy'] = spacy_entities
        
        # Entidades customizadas com regex
        custom_entities = {}
        for entity_type, pattern in self.entity_patterns.items():
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                custom_entities[entity_type] = matches
        
        entities['custom'] = custom_entities
        
        return entities
    
    def _analyze_sentiment(self, text: str) -> Dict:
        """Analisa o sentimento do texto"""
        try:
            # Usar TextBlob para análise de sentimento
            blob = TextBlob(text)
            polarity = blob.sentiment.polarity  # -1 a 1
            subjectivity = blob.sentiment.subjectivity  # 0 a 1
            
            # Classificar sentimento
            if polarity > 0.1:
                sentiment_label = 'positive'
            elif polarity < -0.1:
                sentiment_label = 'negative'
            else:
                sentiment_label = 'neutral'
            
            return {
                'polarity': polarity,
                'subjectivity': subjectivity,
                'label': sentiment_label
            }
        except Exception as e:
            return {
                'polarity': 0.0,
                'subjectivity': 0.0,
                'label': 'neutral',
                'error': str(e)
            }
    
    def _calculate_confidence(self, intent: str, entities: Dict, sentiment: Dict) -> float:
        """Calcula a confiança da análise"""
        confidence = 0.5  # Base
        
        # Aumentar confiança se intenção foi detectada
        if intent != 'general':
            confidence += 0.2
        
        # Aumentar confiança se entidades foram encontradas
        if entities.get('custom') or entities.get('spacy'):
            confidence += 0.2
        
        # Aumentar confiança se sentimento é claro
        if abs(sentiment.get('polarity', 0)) > 0.3:
            confidence += 0.1
        
        return min(confidence, 1.0)
    
    def generate_response(self, intent: str, entities: Dict, sentiment: Dict, 
                         lead_name: str = None, context: Dict = None) -> str:
        """Gera uma resposta humanizada baseada na análise"""
        
        # Templates de resposta por intenção
        response_templates = {
            'greeting': [
                f"Olá{f' {lead_name}' if lead_name else ''}! 😊 Como posso ajudá-lo hoje?",
                f"Oi{f' {lead_name}' if lead_name else ''}! Que bom falar com você! Em que posso ser útil?",
                f"Bom dia{f' {lead_name}' if lead_name else ''}! Estou aqui para ajudar. O que você gostaria de saber?"
            ],
            'product_inquiry': [
                "Fico feliz em saber do seu interesse! Temos soluções incríveis que podem atender suas necessidades. Que tipo de produto ou serviço você está procurando?",
                "Que ótimo! Adoraria apresentar nossos produtos para você. Pode me contar um pouco mais sobre o que você precisa?",
                "Perfeito! Temos várias opções que podem ser ideais para você. Qual é o seu principal objetivo ou necessidade?"
            ],
            'demo_request': [
                "Claro! Seria um prazer mostrar como nossa solução funciona. Quando seria um bom horário para você?",
                "Excelente ideia! Uma demonstração é a melhor forma de conhecer nosso produto. Você tem alguma preferência de horário?",
                "Perfeito! Vou agendar uma demo personalizada para você. Qual seria o melhor dia e horário?"
            ],
            'pricing_inquiry': [
                "Entendo sua curiosidade sobre os valores! Temos opções flexíveis que se adaptam a diferentes necessidades. Posso preparar uma proposta personalizada para você?",
                "Ótima pergunta! Nossos preços variam conforme o pacote e necessidades específicas. Que tal conversarmos sobre suas necessidades para eu apresentar a melhor opção?",
                "Com certeza! Para dar o melhor preço, preciso entender melhor suas necessidades. Pode me contar um pouco sobre seu projeto?"
            ],
            'support_request': [
                "Claro, estou aqui para ajudar! Pode me explicar qual dificuldade você está enfrentando?",
                "Sem problemas! Vamos resolver isso juntos. Me conta mais detalhes sobre o que está acontecendo?",
                "Entendo sua situação. Estou aqui para dar todo o suporte necessário. Qual é exatamente o problema?"
            ],
            'complaint': [
                "Lamento muito que você tenha tido essa experiência. Sua satisfação é muito importante para nós. Pode me contar o que aconteceu para eu poder ajudar?",
                "Peço desculpas pelo inconveniente. Vamos resolver isso da melhor forma possível. Me explica a situação para eu entender melhor?",
                "Sinto muito por isso. Sua opinião é muito valiosa e queremos melhorar. Pode me dar mais detalhes sobre o problema?"
            ],
            'compliment': [
                "Muito obrigado pelo feedback positivo! Fico muito feliz em saber que você está satisfeito. É isso que nos motiva a continuar melhorando!",
                "Que alegria receber esse retorno! Obrigado por compartilhar sua experiência positiva conosco!",
                "Fico emocionado com seu comentário! É muito gratificante saber que conseguimos atender suas expectativas!"
            ],
            'goodbye': [
                f"Foi um prazer conversar com você{f' {lead_name}' if lead_name else ''}! Qualquer coisa, estarei aqui. Tenha um ótimo dia! 😊",
                f"Obrigado pela conversa{f' {lead_name}' if lead_name else ''}! Até logo e conte comigo sempre que precisar!",
                f"Tchau{f' {lead_name}' if lead_name else ''}! Foi ótimo falar com você. Estarei sempre disponível para ajudar!"
            ],
            'contact_info': [
                "Claro! Você pode entrar em contato conosco pelo WhatsApp, email ou telefone. Qual forma de contato você prefere?",
                "Sem problemas! Temos vários canais de atendimento disponíveis. Como você gostaria de manter contato?",
                "Perfeito! Estamos sempre disponíveis para conversar. Qual é a melhor forma de contato para você?"
            ],
            'availability': [
                "Estamos disponíveis de segunda a sexta, das 8h às 18h. Mas pelo WhatsApp, sempre que possível, respondemos fora do horário também!",
                "Nosso atendimento funciona de segunda a sexta, das 8h às 18h. Posso ajudar você agora mesmo!",
                "Estamos aqui para você! Horário de atendimento: segunda a sexta, 8h às 18h. O que você precisa?"
            ],
            'general': [
                "Entendi! Como posso ajudar você da melhor forma?",
                "Interessante! Me conta mais sobre isso para eu poder ajudar melhor.",
                "Certo! Estou aqui para ajudar. O que você gostaria de saber?"
            ]
        }
        
        # Selecionar template baseado na intenção
        templates = response_templates.get(intent, response_templates['general'])
        
        # Escolher template baseado no sentimento
        if sentiment.get('label') == 'negative' and intent not in ['complaint', 'support_request']:
            # Para sentimentos negativos, ser mais empático
            empathetic_responses = [
                "Entendo sua preocupação. Estou aqui para ajudar da melhor forma possível.",
                "Percebo que você pode estar com alguma dúvida ou dificuldade. Vamos resolver isso juntos!",
                "Compreendo. Deixe-me ajudar você a esclarecer tudo."
            ]
            return empathetic_responses[0]
        
        # Retornar primeira opção do template (pode ser randomizado no futuro)
        return templates[0]
    
    def should_escalate(self, intent: str, sentiment: Dict, confidence: float, 
                       conversation_history: List = None) -> Dict:
        """Determina se a conversa deve ser escalonada para um humano"""
        
        escalation_reasons = []
        should_escalate = False
        
        # Escalar se confiança é muito baixa
        if confidence < 0.3:
            escalation_reasons.append("Baixa confiança na análise da mensagem")
            should_escalate = True
        
        # Escalar para reclamações sérias
        if intent == 'complaint' and sentiment.get('polarity', 0) < -0.5:
            escalation_reasons.append("Reclamação com sentimento muito negativo")
            should_escalate = True
        
        # Escalar para pedidos de suporte complexos
        if intent == 'support_request' and confidence < 0.5:
            escalation_reasons.append("Pedido de suporte complexo")
            should_escalate = True
        
        # Escalar se muitas mensagens sem resolução
        if conversation_history and len(conversation_history) > 5:
            recent_intents = [msg.get('intent') for msg in conversation_history[-5:]]
            if recent_intents.count('general') >= 3:
                escalation_reasons.append("Múltiplas mensagens sem intenção clara")
                should_escalate = True
        
        return {
            'should_escalate': should_escalate,
            'reasons': escalation_reasons,
            'priority': 'high' if sentiment.get('polarity', 0) < -0.5 else 'medium'
        }


# Instância global do serviço
nlp_service = NLPService()


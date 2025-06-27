import requests
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from src.models.lead import Lead, db
from src.models.config import CRMIntegration

class PipedriveService:
    """Serviço para integração com a API do Pipedrive"""
    
    def __init__(self, api_token: str, api_url: str = "https://api.pipedrive.com/v1"):
        self.api_token = api_token
        self.api_url = api_url.rstrip('/')
        self.session = requests.Session()
        self.session.params = {'api_token': api_token}
    
    def _make_request(self, method: str, endpoint: str, data: Dict = None) -> Dict:
        """Faz uma requisição para a API do Pipedrive"""
        url = f"{self.api_url}/{endpoint.lstrip('/')}"
        
        try:
            if method.upper() == 'GET':
                response = self.session.get(url, params=data)
            elif method.upper() == 'POST':
                response = self.session.post(url, json=data)
            elif method.upper() == 'PUT':
                response = self.session.put(url, json=data)
            elif method.upper() == 'DELETE':
                response = self.session.delete(url)
            else:
                raise ValueError(f"Método HTTP não suportado: {method}")
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"Erro na requisição para Pipedrive: {str(e)}")
    
    def create_person(self, lead_data: Dict) -> Dict:
        """Cria uma nova pessoa no Pipedrive"""
        person_data = {
            'name': lead_data.get('name'),
            'email': [lead_data.get('email')] if lead_data.get('email') else [],
            'phone': [lead_data.get('phone')] if lead_data.get('phone') else [],
            'org_name': lead_data.get('company'),
            'custom_fields': {
                'location': lead_data.get('location'),
                'source': lead_data.get('source'),
                'qualification_score': lead_data.get('qualification_score', 0)
            }
        }
        
        # Remove campos vazios
        person_data = {k: v for k, v in person_data.items() if v}
        
        result = self._make_request('POST', '/persons', person_data)
        return result.get('data', {})
    
    def update_person(self, person_id: int, lead_data: Dict) -> Dict:
        """Atualiza uma pessoa no Pipedrive"""
        person_data = {
            'name': lead_data.get('name'),
            'email': [lead_data.get('email')] if lead_data.get('email') else [],
            'phone': [lead_data.get('phone')] if lead_data.get('phone') else [],
            'org_name': lead_data.get('company'),
            'custom_fields': {
                'location': lead_data.get('location'),
                'source': lead_data.get('source'),
                'qualification_score': lead_data.get('qualification_score', 0)
            }
        }
        
        # Remove campos vazios
        person_data = {k: v for k, v in person_data.items() if v}
        
        result = self._make_request('PUT', f'/persons/{person_id}', person_data)
        return result.get('data', {})
    
    def get_person(self, person_id: int) -> Dict:
        """Busca uma pessoa no Pipedrive"""
        result = self._make_request('GET', f'/persons/{person_id}')
        return result.get('data', {})
    
    def search_person(self, term: str, fields: List[str] = None) -> List[Dict]:
        """Busca pessoas no Pipedrive por termo"""
        if fields is None:
            fields = ['name', 'email', 'phone']
        
        params = {
            'term': term,
            'fields': ','.join(fields),
            'exact_match': False
        }
        
        result = self._make_request('GET', '/persons/search', params)
        return result.get('data', {}).get('items', [])
    
    def create_deal(self, person_id: int, deal_data: Dict) -> Dict:
        """Cria um negócio no Pipedrive"""
        deal_payload = {
            'title': deal_data.get('title', f"Negócio - {deal_data.get('person_name', 'Lead')}"),
            'person_id': person_id,
            'value': deal_data.get('value'),
            'currency': deal_data.get('currency', 'BRL'),
            'stage_id': deal_data.get('stage_id'),
            'status': deal_data.get('status', 'open'),
            'expected_close_date': deal_data.get('expected_close_date'),
            'custom_fields': deal_data.get('custom_fields', {})
        }
        
        # Remove campos vazios
        deal_payload = {k: v for k, v in deal_payload.items() if v is not None}
        
        result = self._make_request('POST', '/deals', deal_payload)
        return result.get('data', {})
    
    def update_deal(self, deal_id: int, deal_data: Dict) -> Dict:
        """Atualiza um negócio no Pipedrive"""
        result = self._make_request('PUT', f'/deals/{deal_id}', deal_data)
        return result.get('data', {})
    
    def add_activity(self, person_id: int, activity_data: Dict) -> Dict:
        """Adiciona uma atividade no Pipedrive"""
        activity_payload = {
            'subject': activity_data.get('subject', 'Interação com Lead'),
            'type': activity_data.get('type', 'call'),  # call, meeting, task, deadline, email, lunch
            'person_id': person_id,
            'deal_id': activity_data.get('deal_id'),
            'due_date': activity_data.get('due_date'),
            'due_time': activity_data.get('due_time'),
            'duration': activity_data.get('duration'),
            'note': activity_data.get('note'),
            'done': activity_data.get('done', 0)
        }
        
        # Remove campos vazios
        activity_payload = {k: v for k, v in activity_payload.items() if v is not None}
        
        result = self._make_request('POST', '/activities', activity_payload)
        return result.get('data', {})
    
    def add_note(self, person_id: int, content: str, deal_id: int = None) -> Dict:
        """Adiciona uma nota no Pipedrive"""
        note_data = {
            'content': content,
            'person_id': person_id,
            'deal_id': deal_id
        }
        
        # Remove campos vazios
        note_data = {k: v for k, v in note_data.items() if v is not None}
        
        result = self._make_request('POST', '/notes', note_data)
        return result.get('data', {})
    
    def get_pipelines(self) -> List[Dict]:
        """Busca todos os pipelines disponíveis"""
        result = self._make_request('GET', '/pipelines')
        return result.get('data', [])
    
    def get_stages(self, pipeline_id: int = None) -> List[Dict]:
        """Busca os estágios de um pipeline"""
        endpoint = '/stages'
        params = {}
        if pipeline_id:
            params['pipeline_id'] = pipeline_id
            
        result = self._make_request('GET', endpoint, params)
        return result.get('data', [])
    
    def sync_lead_to_pipedrive(self, lead: Lead) -> Dict:
        """Sincroniza um lead local com o Pipedrive"""
        try:
            lead_data = {
                'name': lead.name,
                'email': lead.email,
                'phone': lead.phone,
                'company': lead.company,
                'location': lead.location,
                'source': lead.source,
                'qualification_score': lead.qualification_score
            }
            
            if lead.pipedrive_id:
                # Atualiza pessoa existente
                person_data = self.update_person(lead.pipedrive_id, lead_data)
            else:
                # Cria nova pessoa
                person_data = self.create_person(lead_data)
                lead.pipedrive_id = person_data.get('id')
                db.session.commit()
            
            return {
                'success': True,
                'pipedrive_id': person_data.get('id'),
                'data': person_data
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def sync_from_pipedrive(self, person_id: int) -> Dict:
        """Sincroniza dados do Pipedrive para o lead local"""
        try:
            person_data = self.get_person(person_id)
            
            # Busca lead local
            lead = Lead.query.filter_by(pipedrive_id=person_id).first()
            
            if not lead:
                # Cria novo lead
                lead = Lead(
                    pipedrive_id=person_id,
                    name=person_data.get('name', ''),
                    email=person_data.get('email', [{}])[0].get('value') if person_data.get('email') else None,
                    phone=person_data.get('phone', [{}])[0].get('value') if person_data.get('phone') else None,
                    company=person_data.get('org_name'),
                    source='pipedrive'
                )
                db.session.add(lead)
            else:
                # Atualiza lead existente
                lead.name = person_data.get('name', lead.name)
                if person_data.get('email'):
                    lead.email = person_data.get('email', [{}])[0].get('value')
                if person_data.get('phone'):
                    lead.phone = person_data.get('phone', [{}])[0].get('value')
                lead.company = person_data.get('org_name', lead.company)
                lead.updated_at = datetime.utcnow()
            
            db.session.commit()
            
            return {
                'success': True,
                'lead_id': lead.id,
                'data': lead.to_dict()
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }


def get_pipedrive_service() -> Optional[PipedriveService]:
    """Retorna uma instância do serviço Pipedrive configurado"""
    integration = CRMIntegration.query.filter_by(name='pipedrive', is_active=True).first()
    
    if not integration or not integration.api_token:
        return None
    
    return PipedriveService(
        api_token=integration.api_token,
        api_url=integration.api_url
    )


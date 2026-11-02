"""
Servicio de Autorización y Tenancy

Fuente canónica única para validación multi-tenant y prevención de IDOR.
Centraliza toda la lógica de pertenencia centro-recurso.

NO VALIDAR MANUALMENTE centro_id en routers o servicios.
USAR siempre este servicio para obtener entidades.
"""

from typing import TypeVar, Generic
from sqlmodel import Session, select
from fastapi import HTTPException
from domain.models.core import Paciente, Centro, Cita, Tratamiento
from domain.models.economico import Presupuesto

T = TypeVar('T')


class AuthorizationError(HTTPException):
    """Excepción estandarizada para errores de autorización/tenancy"""
    def __init__(self, detail: str = "Recurso no encontrado o no autorizado"):
        super().__init__(status_code=404, detail=detail)


class AuthorizationService:
    """
    Servicio centralizado de autorización multi-tenant.
    
    Garantiza que todas las entidades obtenidas pertenecen al centro activo.
    Previene IDOR y acceso cross-tenant.
    """
    
    def __init__(self, session: Session, centro_id: int, usuario_id: int | None = None):
        self.session = session
        self.centro_id = centro_id
        self.usuario_id = usuario_id

    def _validate_centro_membership(self, entity, entity_centro_id: int, entity_name: str = "Recurso"):
        """Validación interna de pertenencia al centro"""
        if entity_centro_id != self.centro_id:
            raise AuthorizationError(f"{entity_name} no pertenece al centro")
        return entity

    def get_paciente(self, paciente_id: int) -> Paciente:
        """
        Obtiene paciente validado que pertenece al centro.
        
        Args:
            paciente_id: ID del paciente
            
        Returns:
            Paciente validado
            
        Raises:
            AuthorizationError: Si paciente no existe o no pertenece al centro
        """
        paciente = self.session.get(Paciente, paciente_id)
        if not paciente:
            raise AuthorizationError("Paciente no encontrado")
        
        return self._validate_centro_membership(
            paciente, paciente.centro_id, "Paciente"
        )

    def get_paciente_by_historia(self, num_historia: str) -> Paciente:
        """
        Obtiene paciente por número de historia clínica validado.
        
        Args:
            num_historia: Número de historia clínica
            
        Returns:
            Paciente validado
            
        Raises:
            AuthorizationError: Si paciente no existe o no pertenece al centro
        """
        paciente = self.session.exec(
            select(Paciente).where(
                Paciente.num_historia == num_historia,
                Paciente.centro_id == self.centro_id
            )
        ).first()
        
        if not paciente:
            raise AuthorizationError("Paciente no encontrado")
        
        return paciente

    def get_presupuesto(self, presupuesto_id: int, paciente_id: int | None = None) -> Presupuesto:
        """
        Obtiene presupuesto validado que pertenece al centro.
        
        Args:
            presupuesto_id: ID del presupuesto
            paciente_id: ID del paciente (opcional, para validación adicional)
            
        Returns:
            Presupuesto validado
            
        Raises:
            AuthorizationError: Si presupuesto no existe o no pertenece al centro
        """
        presupuesto = self.session.get(Presupuesto, presupuesto_id)
        if not presupuesto:
            raise AuthorizationError("Presupuesto no encontrado")
        
        # Validar pertenencia al centro
        if presupuesto.centro_id != self.centro_id:
            raise AuthorizationError("Presupuesto no pertenece al centro")
        
        # Validar pertenencia al paciente si se especifica
        if paciente_id and presupuesto.paciente_id != paciente_id:
            raise AuthorizationError("Presupuesto no pertenece al paciente")
        
        return presupuesto

    def get_cita(self, cita_id: int, paciente_id: int | None = None) -> Cita:
        """
        Obtiene cita validada que pertenece al centro.
        
        Args:
            cita_id: ID de la cita
            paciente_id: ID del paciente (opcional, para validación adicional)
            
        Returns:
            Cita validada
            
        Raises:
            AuthorizationError: Si cita no existe o no pertenece al centro
        """
        cita = self.session.get(Cita, cita_id)
        if not cita:
            raise AuthorizationError("Cita no encontrada")
        
        # Validar pertenencia al centro
        if cita.centro_id != self.centro_id:
            raise AuthorizationError("Cita no pertenece al centro")
        
        # Validar pertenencia al paciente si se especifica
        if paciente_id and cita.paciente_id != paciente_id:
            raise AuthorizationError("Cita no pertenece al paciente")
        
        return cita

    def get_tratamiento(self, tratamiento_id: int, paciente_id: int | None = None) -> Tratamiento:
        """
        Obtiene tratamiento validado que pertenece al centro.
        
        Args:
            tratamiento_id: ID del tratamiento
            paciente_id: ID del paciente (opcional, para validación adicional)
            
        Returns:
            Tratamiento validado
            
        Raises:
            AuthorizationError: Si tratamiento no existe o no pertenece al centro
        """
        tratamiento = self.session.get(Tratamiento, tratamiento_id)
        if not tratamiento:
            raise AuthorizationError("Tratamiento no encontrado")
        
        # Validar pertenencia al centro
        if tratamiento.centro_id != self.centro_id:
            raise AuthorizationError("Tratamiento no pertenece al centro")
        
        # Validar pertenencia al paciente si se especifica
        if paciente_id and tratamiento.paciente_id != paciente_id:
            raise AuthorizationError("Tratamiento no pertenece al paciente")
        
        return tratamiento

    def assert_belongs_to_centro(self, entity, entity_centro_id: int, entity_name: str = "Recurso"):
        """
        Valida genéricamente que una entidad pertenece al centro.
        
        Args:
            entity: Entidad a validar
            entity_centro_id: ID del centro de la entidad
            entity_name: Nombre de la entidad para mensajes de error
            
        Raises:
            AuthorizationError: Si entidad no pertenece al centro
        """
        if not entity:
            raise AuthorizationError(f"{entity_name} no encontrado")
        
        if entity_centro_id != self.centro_id:
            raise AuthorizationError(f"{entity_name} no pertenece al centro")
        
        return entity

    def get_entity_validated(
        self, 
        model, 
        entity_id: int, 
        centro_id_field: str = "centro_id"
    ):
        """
        Obtiene entidad genérica con validación de pertenencia.
        
        Args:
            model: Modelo SQLModel
            entity_id: ID de la entidad
            centro_id_field: Nombre del campo centro_id en el modelo
            
        Returns:
            Entidad validada
            
        Raises:
            AuthorizationError: Si entidad no existe o no pertenece al centro
        """
        entity = self.session.get(model, entity_id)
        if not entity:
            raise AuthorizationError("Recurso no encontrado")
        
        entity_centro_id = getattr(entity, centro_id_field, None)
        if entity_centro_id is None:
            raise AuthorizationError("Entidad sin centro_id")
        
        return self._validate_centro_membership(
            entity, entity_centro_id, model.__name__
        )

    def get_current_centro_context(self) -> dict:
        """
        Retorna contexto actual de autorización.
        
        Returns:
            Dict con centro_id y usuario_id actuales
        """
        return {
            "centro_id": self.centro_id,
            "usuario_id": self.usuario_id,
            "service": "AuthorizationService"
        }

    def require_paciente_access(self, paciente_id: int) -> Paciente:
        """
        Método de conveniencia para obtener paciente con validación.
        Alias de get_paciente para claridad semántica.
        """
        return self.get_paciente(paciente_id)

    def require_presupuesto_access(
        self, 
        presupuesto_id: int, 
        paciente_id: int | None = None
    ) -> Presupuesto:
        """
        Método de conveniencia para obtener presupuesto con validación.
        Alias de get_presupuesto para claridad semántica.
        """
        return self.get_presupuesto(presupuesto_id, paciente_id)

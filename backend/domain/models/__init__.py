"""Registro de modelos de dominio para SQLModel.metadata.

MakingSmiles 2.0 — interconexión brutal: FKs totales hacia los 5 nodos-dios
(centro · paciente · colaborador · cita · tratamiento).
"""
from domain.models.core import (
    Centro, CentroBase,
    RazonSocial, RazonSocialBase,
    Paciente, PacienteBase, ConsentimientoPaciente,
    Colaborador, ColaboradorBase, ColaboradorCentro,
    Especialidad, ColaboradorEspecialidad,
    Cita, CitaBase,
    Tratamiento, TratamientoBase, CitaTratamiento,
    TratamientoFase, Poblacion, CodigoPostal, DispositivoPaciente,
)
from domain.models.clinico import (
    AlertaPaciente, Alergia, TipoAntecedente, SubtipoAntecedente,
    Diagnostico, Vademecum, MedicPreescrita,
    ImagenRx, HallazgoImagen, Cefalometria, AnotacionImagen, AnalisisCefalo, RomexisSync, RxExportada, Soap, PlanProximaCita,
)
from domain.models.economico import (
    Cliente, PacienteTarifa, EstadoPresupuesto, EstadoTratamiento,
    Tarifa, TarifaPrecio,
    Presupuesto, PresupuestoLinea, Pago, FormaPago,
    TratamientoRealizado, TratamientoRealizadoFase,
)
from domain.models.comunicacion import (
    Conversacion, Mensaje, Recall, MensajeInterno, EnvioEmail, EnvioEmailDestinatario,
    PlantillaMensaje, PollContexto, AccionBoton, EnvioAutomatico, LlamadaVoz,
    AgenteRevision,
)
from domain.models.identidad import (
    PlatformUser, Usuario, UsuarioPeriodo, Rol, Permiso, RolePermiso,
    UserCenterRole,
    Sistema, Area, RolArea, PasswordReset,
)
from domain.models.config import (
    Configuracion, ConfiguracionBase, ConfiguracionCreate, ConfiguracionRead, Integracion,
)
from domain.models.auditoria import Auditoria
from domain.models.ia import (
    BriefingAura, Transcripcion,
)
from domain.models.documentos import (
    Talonario, TalonarioReceta,
    Receta, RecetaLinea, Consentimiento, DocumentoGenerado,
    DocumentoAdmin, DocumentoPaciente, DocumentoFirmado, PlantillaDocumento,
)
from domain.models.agenda import (
    Agenda, TipoCita, EstadoCita, Gabinete,
    ColaboradorHorario, ColaboradorExcepcion, BloqueoAgenda,
)
from domain.models.dental import (
    OdontogramaEntrada, PeriodontogramaMedida,
)
from domain.models.gestoria import (
    Proveedor, Gasto, Liquidacion, LiquidacionLinea, Deuda, DeudaPago,
    MovimientoBancario, ModeloFiscal, GastoIncidencia,
)
from domain.models.protesis import (
    TrabajoProtesico, TrabajoProtesicoFase,
)
from domain.models.ortodoncia import (
    CasoOrtodoncia, IntervencionOrtodoncia, EstudioOrtodoncia, FotoOrtodoncia,
)
from domain.models.almacen import (
    Articulo, StockMovimiento,
)
from domain.models.agentes import (
    Agente, CapacidadCatalogo, AgenteCapacidad, AgenteCanalAjuste, AgentePermisoAdmin, AgentePersonalidad,
)

__all__ = [
    "Centro", "CentroBase", "RazonSocial", "RazonSocialBase",
    "Paciente", "PacienteBase", "ConsentimientoPaciente",
    "Colaborador", "ColaboradorBase",
    "ColaboradorCentro", "Especialidad", "ColaboradorEspecialidad",
    "Cita", "CitaBase", "Tratamiento",
    "TratamientoBase", "CitaTratamiento",
    "TratamientoFase", "Poblacion", "CodigoPostal", "DispositivoPaciente",
    "AlertaPaciente", "Alergia", "TipoAntecedente", "SubtipoAntecedente",
    "Diagnostico", "Vademecum", "MedicPreescrita",
    "ImagenRx", "HallazgoImagen", "Cefalometria", "AnotacionImagen", "AnalisisCefalo", "RomexisSync", "RxExportada", "Soap",
    "Cliente", "PacienteTarifa", "EstadoPresupuesto", "EstadoTratamiento", "Tarifa", "TarifaPrecio", "Presupuesto", "PresupuestoLinea", "Pago", "FormaPago",
    "TratamientoRealizado", "TratamientoRealizadoFase",
    "Agenda", "TipoCita", "EstadoCita",
    "PlatformUser", "Usuario", "UsuarioPeriodo", "Rol", "Permiso", "RolePermiso",
    "UserCenterRole",
    "Sistema", "Area", "RolArea", "PasswordReset",
    "Configuracion", "ConfiguracionBase", "ConfiguracionCreate", "ConfiguracionRead",
    "Integracion", "Auditoria",
    "Conversacion", "Mensaje", "Recall", "MensajeInterno", "EnvioEmail", "EnvioEmailDestinatario",
    "PlantillaMensaje", "PollContexto", "AccionBoton", "EnvioAutomatico", "LlamadaVoz",
    "AgenteRevision",
    "BriefingAura", "Transcripcion",
    "Talonario", "TalonarioReceta",
    "Receta", "RecetaLinea", "Consentimiento", "DocumentoGenerado",
    "DocumentoAdmin", "DocumentoPaciente", "DocumentoFirmado", "PlantillaDocumento",
    "Gabinete", "ColaboradorHorario", "ColaboradorExcepcion", "BloqueoAgenda",
    "OdontogramaEntrada", "PeriodontogramaMedida",
    "Proveedor", "Gasto", "Liquidacion", "LiquidacionLinea", "Deuda", "DeudaPago",
    "MovimientoBancario", "ModeloFiscal", "GastoIncidencia",
    "TrabajoProtesico", "TrabajoProtesicoFase",
    "CasoOrtodoncia", "IntervencionOrtodoncia", "EstudioOrtodoncia", "FotoOrtodoncia",
    "Articulo", "StockMovimiento",
    "Agente", "CapacidadCatalogo", "AgenteCapacidad", "AgenteCanalAjuste", "AgentePermisoAdmin", "AgentePersonalidad",
]

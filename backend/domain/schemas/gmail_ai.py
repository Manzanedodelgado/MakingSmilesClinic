"""
Esquema Pydantic estricto para la respuesta del Modelo IA Multimodal (Gestor IA).

Valida que la IA devuelva JSON completo, coherente y con razonamiento documentado.
"""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List, Literal, Annotated
from decimal import Decimal
import re


class IvaDesgloseLinea(BaseModel):
    """Una línea de desglose de IVA por tipo impositivo."""
    concepto: str = Field(..., description="Bienes o servicios a los que aplica este tipo de IVA")
    tipo_iva: float = Field(..., ge=0, le=21, description="Porcentaje aplicado (0, 4, 10, 21)")
    base: float = Field(..., description="Base imponible a este tipo")
    importe_iva: float = Field(..., description="Importe de IVA a este tipo (base * tipo_iva / 100)")

    @field_validator("importe_iva")
    @classmethod
    def validar_importe_iva(cls, v, info):
        """Verifica que importe_iva ≈ base * tipo_iva / 100 (tolerancia 0.02€ redondeo)."""
        if "base" in info.data and "tipo_iva" in info.data:
            base = info.data["base"]
            tipo = info.data["tipo_iva"]
            esperado = round(base * tipo / 100, 2)
            if abs(v - esperado) > 0.02:
                raise ValueError(f"importe_iva ({v}) no coincide con base*tipo/100 ({esperado})")
        return v


class GastoIAResponse(BaseModel):
    """
    Respuesta completa del modelo IA para un email procesado.
    
    Incluye clasificación, datos fiscales extraídos, y RAZONAMIENTO OBLIGATORIO
    documentando qué página/documento confirma cada dato.
    """
    
    # ═══════════════════════════════════════════════════════════════════════════
    # CLASIFICACIÓN
    # ═══════════════════════════════════════════════════════════════════════════
    accion: Literal["gasto", "incidencia", "descartado", "duplicado"] = Field(
        ..., description="Clasificación final del correo"
    )
    confianza: Literal["alta", "media", "baja"] = Field(
        ..., description="Nivel de confianza en la clasificación y extracción"
    )
    tipo_documento: Literal[
        "factura", "nomina", "impuesto", "abono_rectificativa", "recibo", "otro"
    ] = Field(..., description="Tipo exacto de documento contable")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # DATOS FISCALES (obligatorios si accion="gasto")
    # ═══════════════════════════════════════════════════════════════════════════
    proveedor_nombre: Optional[str] = Field(
        None, max_length=200, description="EMISOR REAL (nunca Tridental/Manzanedo)"
    )
    cif_emisor: Optional[str] = Field(
        None, max_length=20, description="CIF/NIF validado con dígito de control (ej: B12345674, X9461295S)"
    )
    numero_factura: Optional[str] = Field(
        None, max_length=60, description="Número exacto del documento/factura"
    )
    fecha_emision: Optional[str] = Field(
        None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="Fecha en formato YYYY-MM-DD"
    )
    base_imponible: Optional[float] = Field(
        None, description="Base imponible total (suma de bases en desglose)"
    )
    iva_pct: float = Field(
        default=0, ge=0, le=21, description="IVA principal (0 si exento/mixto, usar iva_desglose)"
    )
    iva_desglose: List[IvaDesgloseLinea] = Field(
        default_factory=list, description="Una línea por cada tipo de IVA distinto"
    )
    irpf_importe: float = Field(
        default=0, description="Retención IRPF en euros (solo autónomos/nóminas/alquiler)"
    )
    suplido: float = Field(
        default=0, description="Gasto exento adelantado por proveedor (ej. Consenur)"
    )
    seguridad_social_importe: float = Field(
        default=0, description="Solo nóminas: cuota empresa SS"
    )
    total: Optional[float] = Field(
        None, description="Importe total final (puede ser negativo en abonos)"
    )
    divisa: str = Field(default="EUR", max_length=3, description="EUR/USD...")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # METADATOS Y CONTEXTO
    # ═══════════════════════════════════════════════════════════════════════════
    concepto: Optional[str] = Field(None, max_length=300, description="Resumen breve bienes/servicios")
    categoria_contable: Optional[str] = Field(
        None, description="Categoría según tabla oficial clínica"
    )
    direccion_proveedor: Optional[str] = Field(None, max_length=300)
    telefono_proveedor: Optional[str] = Field(None, max_length=40)
    email_proveedor: Optional[str] = Field(None, max_length=255)
    destinatario: Optional[str] = Field(
        None, description="Debe ser Tridental/Rubio García Dental/Manzanedo"
    )
    origen_dato: Literal[
        "adjunto_pdf", "adjunto_imagen", "cuerpo_email", "enlace", "portal"
    ] = Field(..., description="Dónde se encontró el gasto")
    enlace: Optional[str] = Field(None, max_length=500, description="URL si portal/enlace directo")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # RAZONAMIENTO OBLIGATORIO (campo crítico para auditoría)
    # ═══════════════════════════════════════════════════════════════════════════
    notas: str = Field(
        ..., min_length=10,
        description="RAZONAMIENTO DETALLADO: qué página confirma qué, aritmética, discrepancias, dudas. "
                    "Ej: 'Pág 3 PDF 00220 confirma CIF X9461295S. Base 780 - IRPF 117 (15%) = 663 ✓. "
                    "Fila 189 Hoja 1 coincide. Fila 402/403 duplicadas.'"
    )
    motivo_descarte: Optional[str] = Field(
        None, description="Obligatorio si accion!=gasto: razón detallada"
    )
    instrucciones_aplicadas: List[str] = Field(
        default_factory=list, description="Pasos/reglas aplicadas: ['PASO 3 CIF validado', 'PASO 4 Base-IRPF=Total', ...]"
    )
    
    # ═══════════════════════════════════════════════════════════════════════════
    # VALIDACIONES CRUZADAS (calculadas por la IA, verificadas por nosotros)
    # ═══════════════════════════════════════════════════════════════════════════
    aritmetica_verificada: bool = Field(
        default=False, description="True si la IA verificó que total = base + IVA - IRPF + suplido + SS"
    )
    cif_validado: bool = Field(
        default=False, description="True si la IA validó dígito de control del CIF"
    )
    duplicado_detectado: bool = Field(
        default=False, description="True si la IA detectó posible duplicado en BD"
    )
    
    # ═══════════════════════════════════════════════════════════════════════════
    # VALIDADORES DE MODELO
    # ═══════════════════════════════════════════════════════════════════════════
    
    @field_validator("cif_emisor")
    @classmethod
    def validar_formato_cif(cls, v):
        """Valida formato básico CIF/NIF/NIE español (9 chars alfanuméricos)."""
        if v is None:
            return v
        v = v.upper().strip()
        # Patrón: letra + 7 dígitos + control (CIF) | 8 dígitos + letra (NIF) | XYZ + 7 dígitos + letra (NIE)
        if not re.match(r'^([A-HJ-NP-SUVW]\d{7}[\dA-J]|\d{8}[A-HJ-NP-TV-Z]|[XYZ]\d{7}[A-HJ-NP-TV-Z])$', v):
            raise ValueError(f"CIF/NIF '{v}' no tiene formato válido español (9 chars)")
        return v
    
    @field_validator("fecha_emision")
    @classmethod
    def validar_rango_fecha(cls, v):
        """Fecha razonable: 2018-2027."""
        if v is None:
            return v
        try:
            year = int(v[:4])
            if year < 2018 or year > 2027:
                raise ValueError(f"Año {year} fuera de rango razonable (2018-2027)")
        except (ValueError, IndexError):
            raise ValueError(f"Fecha '{v}' inválida, debe ser YYYY-MM-DD")
        return v
    
    @model_validator(mode="after")
    def validar_coherencia_gasto(self):
        """Validaciones cruzadas solo si accion='gasto'."""
        if self.accion != "gasto":
            return self
        
        # Campos obligatorios para gasto
        obligatorios = [
            ("proveedor_nombre", self.proveedor_nombre),
            ("cif_emisor", self.cif_emisor),
            ("numero_factura", self.numero_factura),
            ("fecha_emision", self.fecha_emision),
            ("base_imponible", self.base_imponible),
            ("total", self.total),
            ("destinatario", self.destinatario),
            ("categoria_contable", self.categoria_contable),
        ]
        for nombre, valor in obligatorios:
            if valor is None or (isinstance(valor, str) and not valor.strip()):
                raise ValueError(f"Campo obligatorio para 'gasto': {nombre}")
        
        # Validar destinatario es clínica
        dest = (self.destinatario or "").upper()
        if not any(x in dest for x in ["TRIDENTAL", "RUBIO GARCIA", "MANZANEDO"]):
            raise ValueError(f"Destinatario '{self.destinatario}' no es Tridental/Rubio García/Manzanedo")
        
        # Validar proveedor NO es clínica
        prov = (self.proveedor_nombre or "").upper()
        if any(x in prov for x in ["TRIDENTAL", "RUBIO GARCIA", "MANZANEDO"]):
            raise ValueError(f"Proveedor '{self.proveedor_nombre}' es la clínica (prohibido)")
        
        # Validar aritmética si la IA dice que la verificó
        if self.aritmetica_verificada and self.base_imponible is not None and self.total is not None:
            iva_total = sum(l.importe_iva for l in self.iva_desglose) if self.iva_desglose else 0
            calculado = round(
                (self.base_imponible or 0) + iva_total - (self.irpf_importe or 0) 
                + (self.suplido or 0) + (self.seguridad_social_importe or 0), 2
            )
            if abs(calculado - self.total) > 0.02:
                raise ValueError(
                    f"Aritmética no cuadra: calculado={calculado} vs total={self.total} "
                    f"(base={self.base_imponible}, IVA={iva_total}, IRPF={self.irpf_importe}, "
                    f"suplido={self.suplido}, SS={self.seguridad_social_importe})"
                )
        
        # Validar coherencia iva_desglose vs iva_pct
        if self.iva_desglose:
            iva_sum = sum(l.importe_iva for l in self.iva_desglose)
            base_sum = sum(l.base for l in self.iva_desglose)
            if self.base_imponible is not None and abs(base_sum - self.base_imponible) > 0.02:
                raise ValueError(f"Suma bases desglose ({base_sum}) ≠ base_imponible ({self.base_imponible})")
            # Si hay desglose, iva_pct debe ser 0 (mixto) o coincidir con el único tipo
            tipos = set(l.tipo_iva for l in self.iva_desglose)
            if len(tipos) == 1 and self.iva_pct not in (0, list(tipos)[0]):
                raise ValueError(f"iva_pct ({self.iva_pct}) no coincide con tipo único en desglose ({list(tipos)[0]})")
        
        # Validar notas mínimas
        if len(self.notas.strip()) < 20:
            raise ValueError("Campo 'notas' debe contener razonamiento detallado (mín 20 chars)")
        
        return self
    
    @model_validator(mode="after")
    def validar_motivo_descarte(self):
        """motivo_descarte obligatorio si no es gasto."""
        if self.accion != "gasto" and (not self.motivo_descarte or not self.motivo_descarte.strip()):
            raise ValueError(f"motivo_descarte obligatorio cuando accion='{self.accion}'")
        return self


# ═══════════════════════════════════════════════════════════════════════════════
# ESQUEMA PARA GEMINI (response_schema nativo)
# ════════════════════════════════════════════════════════════════════════════════

GEMINI_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "accion": {"type": "STRING", "enum": ["gasto", "incidencia", "descartado", "duplicado"]},
        "confianza": {"type": "STRING", "enum": ["alta", "media", "baja"]},
        "tipo_documento": {"type": "STRING", "enum": ["factura", "nomina", "impuesto", "abono_rectificativa", "recibo", "otro"]},
        "proveedor_nombre": {"type": "STRING", "nullable": True},
        "cif_emisor": {"type": "STRING", "nullable": True},
        "numero_factura": {"type": "STRING", "nullable": True},
        "fecha_emision": {"type": "STRING", "nullable": True},
        "base_imponible": {"type": "NUMBER", "nullable": True},
        "iva_pct": {"type": "NUMBER", "nullable": True},
        "iva_desglose": {
            "type": "ARRAY", "nullable": True,
            "items": {
                "type": "OBJECT",
                "properties": {
                    "concepto": {"type": "STRING"},
                    "tipo_iva": {"type": "NUMBER"},
                    "base": {"type": "NUMBER"},
                    "importe_iva": {"type": "NUMBER"}
                },
                "required": ["concepto", "tipo_iva", "base", "importe_iva"]
            }
        },
        "irpf_importe": {"type": "NUMBER", "nullable": True},
        "suplido": {"type": "NUMBER", "nullable": True},
        "seguridad_social_importe": {"type": "NUMBER", "nullable": True},
        "total": {"type": "NUMBER", "nullable": True},
        "divisa": {"type": "STRING", "nullable": True},
        "concepto": {"type": "STRING", "nullable": True},
        "categoria_contable": {"type": "STRING", "nullable": True},
        "direccion_proveedor": {"type": "STRING", "nullable": True},
        "telefono_proveedor": {"type": "STRING", "nullable": True},
        "email_proveedor": {"type": "STRING", "nullable": True},
        "destinatario": {"type": "STRING", "nullable": True},
        "origen_dato": {"type": "STRING", "enum": ["adjunto_pdf", "adjunto_imagen", "cuerpo_email", "enlace", "portal"]},
        "enlace": {"type": "STRING", "nullable": True},
        "notas": {"type": "STRING"},
        "motivo_descarte": {"type": "STRING", "nullable": True},
        "instrucciones_aplicadas": {"type": "ARRAY", "items": {"type": "STRING"}},
        "aritmetica_verificada": {"type": "BOOLEAN"},
        "cif_validado": {"type": "BOOLEAN"},
        "duplicado_detectado": {"type": "BOOLEAN"}
    },
    "required": [
        "accion", "confianza", "tipo_documento", "proveedor_nombre", "cif_emisor",
        "numero_factura", "fecha_emision", "base_imponible", "iva_pct", "iva_desglose",
        "irpf_importe", "suplido", "seguridad_social_importe", "total", "divisa",
        "concepto", "categoria_contable", "direccion_proveedor", "telefono_proveedor",
        "email_proveedor", "destinatario", "origen_dato", "enlace", "notas",
        "motivo_descarte", "instrucciones_aplicadas", "aritmetica_verificada",
        "cif_validado", "duplicado_detectado"
    ]
}


# ════════════════════════════════════════════════════════════════════════════════
# ESQUEMA PARA OPENAI/GROQ/CEREBRAS (json_schema)
# ════════════════════════════════════════════════════════════════════════════════

def to_openai_schema() -> dict:
    """Convierte el schema Pydantic a formato OpenAI json_schema (tipos minúsculas, sin nullable)."""
    schema = GastoIAResponse.model_json_schema()
    
    def convert(node):
        if isinstance(node, dict):
            new = {}
            for k, v in node.items():
                if k == "nullable":
                    continue
                new[k] = convert(v)
            if "type" in new and isinstance(new["type"], str):
                new["type"] = new["type"].lower()
            return new
        if isinstance(node, list):
            return [convert(x) for x in node]
        return node
    
    return convert(schema)


__all__ = [
    "IvaDesgloseLinea",
    "GastoIAResponse", 
    "GEMINI_RESPONSE_SCHEMA",
    "to_openai_schema"
]
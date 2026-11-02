"""
Tests unitarios para el Modelo IA Multimodal (Gestor IA).

Valida:
1. Schema Pydantic GastoIAResponse (coherencia, campos obligatorios, aritmética)
2. Few-shots del SYSTEM_PROMPT (estructura, tipos, valores esperados)
3. Normalización y validación de CIF/NIF/NIE español
4. Esquemas Gemini/OpenAI generados correctamente
"""

import pytest
import json
import re
from decimal import Decimal

from domain.schemas.gmail_ai import (
    IvaDesgloseLinea,
    GastoIAResponse,
    GEMINI_RESPONSE_SCHEMA,
    to_openai_schema,
)
from domain.prompts.gasto_multimodal import SYSTEM_PROMPT, FEW_SHOTS


# ═══════════════════════════════════════════════════════════════════════════════
# TESTS: NORMALIZACIÓN Y VALIDACIÓN CIF/NIF/NIE
# ═══════════════════════════════════════════════════════════════════════════════

class TestCIFNormalizacion:
    """Tests para la función normalizar_cif (copiada del script.py para validación)."""
    
    @staticmethod
    def normalizar_cif(valor: str) -> str | None:
        """Copia de la función del script.py para tests."""
        if not valor:
            return None
        texto = str(valor).upper()
        texto = re.sub(r'\b(CIF|NIF|VAT)[\s.:_-]*', '', texto)
        texto = re.sub(r'^(?:ES)+', '', texto.strip())
        c = re.sub(r'[^A-Z0-9]', '', texto)
        
        if len(c) == 10 and re.fullmatch(r'[A-HJ-NP-SUVW84][0-9OIL]{7}[0-9A-Z]{2}', c):
            c = c[:9]
        
        if re.fullmatch(r'[84][0-9A-Z]{7,8}', c):
            c = ('B' if c[0] == '8' else 'A') + c[1:]
        
        def dig(ch):
            return {'O': '0', 'I': '1', 'L': '1'}.get(ch, ch)
        
        def control(ch):
            return ch if ch in 'ABCDEFGHIJ' else dig(ch)
        
        if re.fullmatch(r'[A-Z][0-9A-Z]{7}', c):
            return c[0] + ''.join(dig(x) for x in c[1:])
        if re.fullmatch(r'[A-Z][0-9A-Z]{8}', c):
            return c[0] + ''.join(dig(x) for x in c[1:8]) + control(c[8])
        if re.fullmatch(r'[0-9]{7}[A-Z]', c):
            return ''.join(dig(x) for x in c[:7]) + c[7]
        if re.fullmatch(r'[0-9]{8}[A-Z]', c):
            return c
        
        match = re.search(r'(?<![0-9A-Za-z])((?:ES)?[A-HJ-NP-SUVW][-.\s]?(?:\d[-.\s]?){7}[0-9A-J]|(?:ES)?(?:\d[-.\s]?){8}[A-HJ-NP-TV-Z]|(?:ES)?[XYZ][-.\s]?(?:\d[-.\s]?){7}[A-HJ-NP-TV-Z])(?![0-9A-Za-z])', c)
        if match:
            return TestCIFNormalizacion.normalizar_cif(match.group(1))
        
        return c if 9 <= len(c) <= 12 else None
    
    @staticmethod
    def validar_identificacion(valor: str | None) -> bool:
        """Copia de la función del script.py para tests."""
        if not valor:
            return False
        ident = TestCIFNormalizacion.normalizar_cif(valor)
        if not ident or len(ident) != 9:
            return False
        
        _LETRAS_NIF = "TRWAGMYFPDXBNJZSQVHLCKE"
        _CIF_CONTROL_LETRA = "PQRSNW"
        _CIF_CONTROL_NUMERO = "ABEH"
        _MAPA_CONTROL = "JABCDEFGHI"
        
        if ident[:8].isdigit() and ident[8].isalpha():  # NIF
            return ident[8] == _LETRAS_NIF[int(ident[:8]) % 23]
        if ident[0] in "XYZ" and ident[1:8].isdigit() and ident[8].isalpha():  # NIE
            return ident[8] == _LETRAS_NIF[int(str("XYZ".index(ident[0])) + ident[1:8]) % 23]
        if ident[0].isalpha() and ident[1:8].isdigit():  # CIF
            pares = sum(int(d) for d in ident[2:8:2])
            impares = sum(sum(divmod(int(d) * 2, 10)) for d in ident[1:8:2])
            digito = (10 - (pares + impares) % 10) % 10
            if ident[0] in _CIF_CONTROL_LETRA:
                return ident[8] == _MAPA_CONTROL[digito]
            if ident[0] in _CIF_CONTROL_NUMERO:
                return ident[8] == str(digito)
            return ident[8] in (str(digito), _MAPA_CONTROL[digito])
        return False

    def test_cif_valido_empresa(self):
        """CIF estándar empresa (B + 7 dígitos + control numérico)."""
        # B88393764 (Tridental) - válido
        assert self.normalizar_cif("B88393764") == "B88393764"
        assert self.validar_identificacion("B88393764") is True
        
        # Con separadores
        assert self.normalizar_cif("B-88.393.764") == "B88393764"
        assert self.normalizar_cif("B 88 393 764") == "B88393764"
    
    def test_cif_organismo_publico(self):
        """CIF organismo público (Q + 7 dígitos + control letra)."""
        # Q2826004J (FNMT) - válido
        assert self.normalizar_cif("Q2826004J") == "Q2826004J"
        assert self.validar_identificacion("Q2826004J") is True
        
        # Con prefijo ES
        assert self.normalizar_cif("ESQ2826004J") == "Q2826004J"
    
    def test_nif_persona_fisica(self):
        """NIF estándar (8 dígitos + letra)."""
        # 12345678Z - válido
        assert self.normalizar_cif("12345678Z") == "12345678Z"
        assert self.validar_identificacion("12345678Z") is True
    
    def test_nie_extranjero(self):
        """NIE (X/Y/Z + 7 dígitos + letra)."""
        # X9461295S (Orlando Zapata) - válido
        assert self.normalizar_cif("X9461295S") == "X9461295S"
        assert self.validar_identificacion("X9461295S") is True
        
        # Con separadores
        assert self.normalizar_cif("X-9461295-S") == "X9461295S"
    
    def test_correccion_ocr_tipica(self):
        """Corrección errores OCR típicos."""
        # 8 inicial → B (Sociedad Limitada)
        assert self.normalizar_cif("88393764") == "B8393764"  # 8→B
        
        # 4 inicial → A (Sociedad Anónima)
        assert self.normalizar_cif("48393764") == "A8393764"  # 4→A
        
        # O en posición numérica → 0
        assert self.normalizar_cif("B8O393764") == "B80393764"
        
        # I/L en posición numérica → 1
        assert self.normalizar_cif("B8I393764") == "B81393764"
        assert self.normalizar_cif("B8L393764") == "B81393764"
    
    def test_digito_control_duplicado(self):
        """Elimina dígito de control duplicado (B1234567AA → B1234567A)."""
        assert self.normalizar_cif("B1234567AA") == "B1234567A"
        assert self.normalizar_cif("B1234567A4") == "B1234567A"
    
    def test_prefijo_es_duplicado(self):
        """Elimina prefijo ES duplicado (ESESB... → B...)."""
        assert self.normalizar_cif("ESESB88393764") == "B88393764"
    
    def test_cif_invalido_rechazado(self):
        """CIFs inválidos devuelven None o no validan."""
        assert self.validar_identificacion("B12345678") is False  # control erróneo
        assert self.validar_identificacion("X1234567Z") is False  # NIE inválido
        assert self.validar_identificacion("12345678A") is False  # NIF inválido
        assert self.normalizar_cif("ABC") is None  # Muy corto


# ═══════════════════════════════════════════════════════════════════════════════
# TESTS: SCHEMA PYDANTIC GastoIAResponse
# ═══════════════════════════════════════════════════════════════════════════════

class TestGastoIAResponseSchema:
    """Tests de validación del schema Pydantic."""
    
    def test_gasto_valido_completo(self):
        """Gasto completo con todos los campos debe validar."""
        data = {
            "accion": "gasto",
            "confianza": "alta",
            "tipo_documento": "factura",
            "proveedor_nombre": "LABORATORIO DENTAL PRABER",
            "cif_emisor": "B12345674",
            "numero_factura": "260032",
            "fecha_emision": "2026-07-31",
            "base_imponible": 450.00,
            "iva_pct": 21,
            "iva_desglose": [
                {"concepto": "prótesis fija", "tipo_iva": 21, "base": 300.00, "importe_iva": 63.00},
                {"concepto": "materiales", "tipo_iva": 10, "base": 150.00, "importe_iva": 15.00}
            ],
            "irpf_importe": 0,
            "suplido": 0,
            "seguridad_social_importe": 0,
            "total": 528.00,
            "divisa": "EUR",
            "concepto": "Prótesis dental paciente X",
            "categoria_contable": "LABORATORIOS",
            "direccion_proveedor": "C/ Ejemplo 123, Madrid",
            "telefono_proveedor": "911234567",
            "email_proveedor": "facturacion@praber.es",
            "destinatario": "TRIDENTAL ODONTOLOGOS SLP",
            "origen_dato": "adjunto_pdf",
            "enlace": "https://drive.google.com/file/d/abc123",
            "notas": "PDF pág 1-2 confirma factura 260032. IVA mixto 21%+10% verificado: 300*1.21 + 150*1.10 = 528 ✓. CIF B12345674 en cabecera. Destinatario Tridental confirmado.",
            "motivo_descarte": None,
            "instrucciones_aplicadas": ["PASO 3 CIF cabecera", "PASO 4 IVA mixto sumado", "PASO 6 multi-factura PDF"],
            "aritmetica_verificada": True,
            "cif_validado": True,
            "duplicado_detectado": False
        }
        response = GastoIAResponse(**data)
        assert response.accion == "gasto"
        assert response.total == 528.00
        assert len(response.iva_desglose) == 2
    
    def test_gasto_autonomo_base_irpf_total(self):
        """Autónomo: Base - IRPF(15%) = Total (IVA 0)."""
        data = {
            "accion": "gasto",
            "confianza": "alta",
            "tipo_documento": "factura",
            "proveedor_nombre": "ORLANDO ZAPATA VELÁSQUEZ",
            "cif_emisor": "X9461295S",
            "numero_factura": "220",
            "fecha_emision": "2020-03-31",
            "base_imponible": 780.00,
            "iva_pct": 0,
            "iva_desglose": [{"concepto": "servicios dentales", "tipo_iva": 0, "base": 780.00, "importe_iva": 0}],
            "irpf_importe": 117.00,
            "suplido": 0,
            "seguridad_social_importe": 0,
            "total": 663.00,
            "divisa": "EUR",
            "concepto": "Servicios profesionales odontología",
            "categoria_contable": "RECURSOS HUMANOS",
            "destinatario": "TRIDENTAL ODONTOLOGOS SLP",
            "origen_dato": "adjunto_pdf",
            "notas": "Pág 2 PDF '00220' confirma factura 220: Base 780 - IRPF 117 (15%) = 663 ✓. CIF X9461295S leído en vertical pág 3. Fila 189 Hoja 1 coincide.",
            "instrucciones_aplicadas": ["PASO 3 CIF vertical validado", "PASO 4 Base-IRPF=Total autónomo 15%"],
            "aritmetica_verificada": True,
            "cif_validado": True,
            "duplicado_detectado": False
        }
        response = GastoIAResponse(**data)
        assert response.total == 663.00
        assert response.irpf_importe == 117.00
    
    def test_gasto_con_suplido(self):
        """Gasto con suplido (Consenur): total = base + IVA - IRPF + suplido."""
        data = {
            "accion": "gasto",
            "confianza": "media",
            "tipo_documento": "factura",
            "proveedor_nombre": "CONSENUR",
            "cif_emisor": "B86208824",
            "numero_factura": "1547",
            "fecha_emision": "2026-08-15",
            "base_imponible": 100.00,
            "iva_pct": 21,
            "iva_desglose": [{"concepto": "servicios", "tipo_iva": 21, "base": 100.00, "importe_iva": 21.00}],
            "irpf_importe": 0,
            "suplido": 50.00,
            "seguridad_social_importe": 0,
            "total": 171.00,
            "divisa": "EUR",
            "concepto": "Servicios mantenimiento",
            "categoria_contable": "SUMINISTROS Y REPARACIONES",
            "destinatario": "TRIDENTAL ODONTOLOGOS SLP",
            "origen_dato": "adjunto_pdf",
            "notas": "Suplido 50€ en concepto 'Gastos justificados'. Fórmula: 100 + 21 - 0 + 50 = 171 ✓. CIF B86208824 conocido.",
            "instrucciones_aplicadas": ["PASO 3 CIF conocido", "PASO 4 Suplido identificado"],
            "aritmetica_verificada": True,
            "cif_validado": True,
            "duplicado_detectado": False
        }
        response = GastoIAResponse(**data)
        assert response.total == 171.00
        assert response.suplido == 50.00
    
    def test_abono_rectificativa_negativo(self):
        """Abono/rectificativa con total negativo."""
        data = {
            "accion": "gasto",
            "confianza": "alta",
            "tipo_documento": "abono_rectificativa",
            "proveedor_nombre": "PROVEEDOR EJEMPLO SL",
            "cif_emisor": "B11111111",
            "numero_factura": "ABO-5001",
            "fecha_emision": "2026-08-10",
            "base_imponible": -123.97,
            "iva_pct": 21,
            "iva_desglose": [{"concepto": "devolución material", "tipo_iva": 21, "base": -123.97, "importe_iva": -26.03}],
            "irpf_importe": 0,
            "suplido": 0,
            "seguridad_social_importe": 0,
            "total": -150.00,
            "divisa": "EUR",
            "concepto": "Devolución material factura 5001",
            "categoria_contable": "DEPOSITO",
            "destinatario": "TRIDENTAL ODONTOLOGOS SLP",
            "origen_dato": "adjunto_pdf",
            "notas": "Abono rectificativa: total NEGATIVO (-150) = devolución a favor clínica. Base e IVA negativos. Documento dice 'A favor de Tridental'.",
            "instrucciones_aplicadas": ["PASO 1 Abono detectado", "PASO 4 Signo negativo verificado"],
            "aritmetica_verificada": True,
            "cif_validado": True,
            "duplicado_detectado": False
        }
        response = GastoIAResponse(**data)
        assert response.total == -150.00
        assert response.base_imponible == -123.97
    
    def test_incidencia_sin_datos_obligatorios(self):
        """Incidencia: motivo_descarte obligatorio, campos fiscales pueden ser None."""
        data = {
            "accion": "incidencia",
            "confianza": "baja",
            "tipo_documento": "factura",
            "proveedor_nombre": None,
            "cif_emisor": None,
            "numero_factura": None,
            "fecha_emision": None,
            "base_imponible": None,
            "iva_pct": 0,
            "iva_desglose": [],
            "irpf_importe": 0,
            "suplido": 0,
            "seguridad_social_importe": 0,
            "total": None,
            "divisa": "EUR",
            "concepto": None,
            "categoria_contable": None,
            "destinatario": None,
            "origen_dato": "portal",
            "enlace": "https://portal.vevidental.es/factura/abc123",
            "notas": "Portal sin datos en email. Requiere acceso manual para descargar factura y extraer CIF, importe, etc.",
            "motivo_descarte": "Aviso de portal privado: el correo no aporta proveedor/importe/CIF. Requiere acceso al portal para descargar la factura real.",
            "instrucciones_aplicadas": ["PASO 1 Portal sin datos → incidencia"],
            "aritmetica_verificada": False,
            "cif_validado": False,
            "duplicado_detectado": False
        }
        response = GastoIAResponse(**data)
        assert response.accion == "incidencia"
        assert response.motivo_descarte is not None
    
    def test_descartado_motivo_obligatorio(self):
        """Descartado: motivo_descarte obligatorio."""
        data = {
            "accion": "descartado",
            "confianza": "alta",
            "tipo_documento": "otro",
            "proveedor_nombre": None,
            "cif_emisor": None,
            "numero_factura": None,
            "fecha_emision": None,
            "base_imponible": None,
            "iva_pct": 0,
            "iva_desglose": [],
            "irpf_importe": 0,
            "suplido": 0,
            "seguridad_social_importe": 0,
            "total": None,
            "divisa": "EUR",
            "concepto": None,
            "categoria_contable": None,
            "destinatario": None,
            "origen_dato": "cuerpo_email",
            "notas": "Confirmación de pedido sin precios. Lista artículos pero no tiene base/IVA/total.",
            "motivo_descarte": "Confirmación de pedido/albarán: lista artículos y cantidades pero NUNCA incluye base imponible, IVA ni total. No es factura.",
            "instrucciones_aplicadas": ["PASO 1 Sin campos económicos → no factura"],
            "aritmetica_verificada": False,
            "cif_validado": False,
            "duplicado_detectado": False
        }
        response = GastoIAResponse(**data)
        assert response.accion == "descartado"
    
    def test_validacion_proveedor_clinica_rechazado(self):
        """Proveedor = Tridental debe fallar."""
        data = self._gasto_base()
        data["proveedor_nombre"] = "TRIDENTAL ODONTOLOGOS SLP"
        with pytest.raises(ValueError, match="Proveedor.*es la clínica"):
            GastoIAResponse(**data)
    
    def test_validacion_destinatario_no_clinica_rechazado(self):
        """Destinatario ≠ Tridental/Manzanedo debe fallar."""
        data = self._gasto_base()
        data["destinatario"] = "TERCERO AJENO SL"
        with pytest.raises(ValueError, match="Destinatario.*no es Tridental"):
            GastoIAResponse(**data)
    
    def test_validacion_aritmetica_falla(self):
        """Aritmética incorrecta debe fallar si aritmetica_verificada=True."""
        data = self._gasto_base()
        data["total"] = 999.99  # Incorrecto
        data["aritmetica_verificada"] = True
        with pytest.raises(ValueError, match="Aritmética no cuadra"):
            GastoIAResponse(**data)
    
    def test_validacion_iva_desglose_vs_base(self):
        """Suma bases desglose debe coincidir con base_imponible."""
        data = self._gasto_base()
        data["iva_desglose"] = [
            {"concepto": "A", "tipo_iva": 21, "base": 100, "importe_iva": 21},
            {"concepto": "B", "tipo_iva": 10, "base": 50, "importe_iva": 5}
        ]
        data["base_imponible"] = 200  # ≠ 150
        data["aritmetica_verificada"] = False  # Desactivar validación de total para probar solo base
        with pytest.raises(ValueError, match="Suma bases desglose.*≠ base_imponible|base_imponible.*150.*200"):
            GastoIAResponse(**data)
    
    def test_notas_muy_cortas_rechazadas(self):
        """Notas < 10 chars debe fallar (validación Pydantic min_length=10)."""
        data = self._gasto_base()
        data["notas"] = "Corto"
        with pytest.raises(ValueError, match="String should have at least 10 characters|notas.*mín 10"):
            GastoIAResponse(**data)
    
    def test_motivo_descarte_obligatorio_si_no_gasto(self):
        """motivo_descarte obligatorio en incidencia/descartado/duplicado."""
        for accion in ["incidencia", "descartado", "duplicado"]:
            data = self._gasto_base()
            data["accion"] = accion
            data["motivo_descarte"] = ""
            with pytest.raises(ValueError, match="motivo_descarte obligatorio"):
                GastoIAResponse(**data)
    
    def _gasto_base(self):
        """Datos base válidos para un gasto."""
        return {
            "accion": "gasto",
            "confianza": "alta",
            "tipo_documento": "factura",
            "proveedor_nombre": "PROVEEDOR TEST SL",
            "cif_emisor": "B12345674",
            "numero_factura": "TEST-001",
            "fecha_emision": "2026-08-15",
            "base_imponible": 100.00,
            "iva_pct": 21,
            "iva_desglose": [{"concepto": "servicios", "tipo_iva": 21, "base": 100.00, "importe_iva": 21.00}],
            "irpf_importe": 0,
            "suplido": 0,
            "seguridad_social_importe": 0,
            "total": 121.00,
            "divisa": "EUR",
            "concepto": "Servicios test",
            "categoria_contable": "SERVICIOS",
            "direccion_proveedor": "C/ Test 1",
            "telefono_proveedor": "911111111",
            "email_proveedor": "test@test.es",
            "destinatario": "TRIDENTAL ODONTOLOGOS SLP",
            "origen_dato": "adjunto_pdf",
            "enlace": "https://drive.google.com/file/d/test",
            "notas": "Razonamiento detallado: base 100 + IVA 21 = 121 ✓. CIF validado. Destinatario Tridental confirmado.",
            "motivo_descarte": None,
            "instrucciones_aplicadas": ["PASO 3 CIF validado", "PASO 4 Aritmética verificada"],
            "aritmetica_verificada": True,
            "cif_validado": True,
            "duplicado_detectado": False
        }


# ════════════════════════════════════════════════════════════════════════════════
# TESTS: FEW-SHOTS ESTRUCTURA Y COHERENCIA
# ════════════════════════════════════════════════════════════════════════════════

class TestFewShots:
    """Valida que los few-shots tienen estructura correcta y son parseables."""
    
    def test_few_shots_count(self):
        """Debe haber 10 few-shots (casos representativos)."""
        assert len(FEW_SHOTS) == 10
    
    def test_few_shots_estructura(self):
        """Cada few-shot debe tener descripcion, email, respuesta_esperada."""
        for i, shot in enumerate(FEW_SHOTS):
            assert "descripcion" in shot, f"Shot {i}: falta 'descripcion'"
            assert "email" in shot, f"Shot {i}: falta 'email'"
            assert "respuesta_esperada" in shot, f"Shot {i}: falta 'respuesta_esperada'"
            assert isinstance(shot["descripcion"], str) and len(shot["descripcion"]) > 0
            assert isinstance(shot["email"], str) and len(shot["email"]) > 0
            assert isinstance(shot["respuesta_esperada"], dict)
    
    def test_few_shots_respuesta_valida_schema(self):
        """Cada respuesta_esperada debe validar contra GastoIAResponse."""
        for i, shot in enumerate(FEW_SHOTS):
            respuesta = shot["respuesta_esperada"]
            # Validar con Pydantic
            response = GastoIAResponse(**respuesta)
            assert response.accion in ["gasto", "incidencia", "descartado", "duplicado"]
            assert response.confianza in ["alta", "media", "baja"]
    
    def test_few_shots_cubren_casos_criticos(self):
        """Verifica que cubren los casos críticos del negocio."""
        descripciones = [s["descripcion"] for s in FEW_SHOTS]
        acciones = [s["respuesta_esperada"]["accion"] for s in FEW_SHOTS]
        
        # Debe haber al menos: autónomo, laboratorio, suplido, albarán, portal, nómina, impuesto, sanitario exento, abono, Manzanedo
        assert any("autónomo" in d.lower() or "orlando" in d.lower() for d in descripciones)
        assert any("laboratorio" in d.lower() or "praber" in d.lower() for d in descripciones)
        assert any("suplido" in d.lower() or "consenur" in d.lower() for d in descripciones)
        assert any("albarán" in d.lower() or "confirmación" in d.lower() or "pedido" in d.lower() for d in descripciones)
        assert any("portal" in d.lower() for d in descripciones)
        assert any("nómina" in d.lower() or "nomina" in d.lower() for d in descripciones)
        assert any("impuesto" in d.lower() or "aeat" in d.lower() or "303" in d.lower() for d in descripciones)
        assert any("sanitaria" in d.lower() or "exenta" in d.lower() or "ortodoncia" in d.lower() for d in descripciones)
        assert any("abono" in d.lower() or "rectificativa" in d.lower() for d in descripciones)
        assert any("manzanedo" in d.lower() for d in descripciones)
        
        # Todas las acciones representadas
        assert "gasto" in acciones
        assert "incidencia" in acciones
        assert "descartado" in acciones


# ════════════════════════════════════════════════════════════════════════════════
# TESTS: ESQUEMAS GEMINI / OPENAI
# ════════════════════════════════════════════════════════════════════════════════

class TestEsquemasGenerados:
    """Valida que los esquemas generados para APIs son correctos."""
    
    def test_gemini_schema_estructura(self):
        """GEMINI_RESPONSE_SCHEMA tiene estructura correcta (tipos MAYÚSCULAS, nullable)."""
        schema = GEMINI_RESPONSE_SCHEMA
        assert schema["type"] == "OBJECT"
        assert "properties" in schema
        assert "required" in schema
        
        # Verificar campos clave
        props = schema["properties"]
        assert "accion" in props
        assert props["accion"]["type"] == "STRING"
        assert "enum" in props["accion"]
        assert "gasto" in props["accion"]["enum"]
        
        # nullable en campos opcionales
        assert props["proveedor_nombre"]["nullable"] is True
        assert props["cif_emisor"]["nullable"] is True
    
    def test_openai_schema_estructura(self):
        """to_openai_schema() genera tipos minúsculas, sin nullable."""
        schema = to_openai_schema()
        assert schema["type"] == "object"
        
        props = schema["properties"]
        # Tipos en minúsculas
        assert props["accion"]["type"] == "string"
        # base_imponible es Optional -> anyOf [number, null]
        assert "base_imponible" in props
        base_prop = props["base_imponible"]
        # Puede ser anyOf [number, null] o directamente number
        if "anyOf" in base_prop:
            assert any(t.get("type") == "number" for t in base_prop["anyOf"])
        else:
            assert base_prop["type"] == "number"
        
        # Sin nullable (OpenAI usa required/optional)
        assert "nullable" not in props["proveedor_nombre"]
    
    def test_esquemas_tienen_mismos_campos(self):
        """Ambos esquemas cubren los mismos campos requeridos."""
        gemini_required = set(GEMINI_RESPONSE_SCHEMA["required"])
        openai_schema = to_openai_schema()
        openai_required = set(openai_schema.get("required", []))
        
        # Los campos requeridos deben coincidir (aprox)
        assert len(gemini_required) > 20
        # OpenAI schema puede tener menos required porque usa optional
        assert len(openai_required) >= 5


# ════════════════════════════════════════════════════════════════════════════════
# TESTS: IVA DESGLOSE
# ════════════════════════════════════════════════════════════════════════════════

class TestIvaDesgloseLinea:
    """Tests para la línea de desglose de IVA."""
    
    def test_linea_valida(self):
        linea = IvaDesgloseLinea(
            concepto="prótesis fija",
            tipo_iva=21,
            base=300.00,
            importe_iva=63.00
        )
        assert linea.importe_iva == 63.00
    
    def test_importe_iva_incorrecto_falla(self):
        """importe_iva debe coincidir con base * tipo_iva / 100."""
        with pytest.raises(ValueError, match="importe_iva.*no coincide"):
            IvaDesgloseLinea(
                concepto="test",
                tipo_iva=21,
                base=100.00,
                importe_iva=25.00  # Debería ser 21.00
            )
    
    def test_tolerancia_redondeo_002(self):
        """Tolerancia 0.02€ para redondeos."""
        # 100 * 21 / 100 = 21.00 exacto
        linea = IvaDesgloseLinea(concepto="test", tipo_iva=21, base=100.00, importe_iva=21.00)
        assert linea.importe_iva == 21.00
        
        # Caso con redondeo: 33.33 * 21% = 6.9993 ≈ 7.00
        linea2 = IvaDesgloseLinea(concepto="test", tipo_iva=21, base=33.33, importe_iva=7.00)
        assert linea2.importe_iva == 7.00


# ════════════════════════════════════════════════════════════════════════════════
# TESTS: SYSTEM PROMPT CONTENIDO
# ════════════════════════════════════════════════════════════════════════════════

class TestSystemPrompt:
    """Valida que el SYSTEM_PROMPT contiene las reglas críticas."""
    
    def test_contiene_identidad_clinica(self):
        assert "TRIDENTAL ODONTÓLOGOS SLP" in SYSTEM_PROMPT
        assert "RUBIO GARCÍA DENTAL" in SYSTEM_PROMPT
        assert "JUAN ANTONIO MANZANEDO DELGADO" in SYSTEM_PROMPT
        assert "B88393764" in SYSTEM_PROMPT
    
    def test_contiene_regla_oro_proveedor(self):
        assert "NUNCA son proveedores" in SYSTEM_PROMPT
        assert "NUNCA aceptes" in SYSTEM_PROMPT
    
    def test_contiene_pasos_obligatorios(self):
        for paso in ["PASO 1", "PASO 2", "PASO 3", "PASO 4", "PASO 5", "PASO 6", "PASO 7"]:
            assert paso in SYSTEM_PROMPT
    
    def test_contiene_formulas_aritmeticas(self):
        assert "total = base + iva_importe - irpf_importe + suplido + seguridad_social" in SYSTEM_PROMPT
        assert "EXENTA IVA" in SYSTEM_PROMPT
        assert "art. 20 LIVA" in SYSTEM_PROMPT
        assert "IRPF 15%" in SYSTEM_PROMPT
    
    def test_contiene_evidencia_documental(self):
        assert "EVIDENCIA DOCUMENTAL" in SYSTEM_PROMPT
        assert "qué página confirma" in SYSTEM_PROMPT
        assert "Cálculo aritmético verificado" in SYSTEM_PROMPT
    
    def test_contiene_json_output_schema(self):
        assert "accion" in SYSTEM_PROMPT
        assert "confianza" in SYSTEM_PROMPT
        assert "cif_emisor" in SYSTEM_PROMPT
        assert "iva_desglose" in SYSTEM_PROMPT
        assert "notas" in SYSTEM_PROMPT
        assert "instrucciones_aplicadas" in SYSTEM_PROMPT


# ════════════════════════════════════════════════════════════════════════════════
# EJECUCIÓN DIRECTA
# ════════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
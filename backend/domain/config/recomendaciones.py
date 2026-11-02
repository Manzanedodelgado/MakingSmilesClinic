"""Catálogo de recomendaciones al paciente (seleccionables al final de la consulta).

Fuente de la verdad en runtime = CONFIG (clave `clinica.recomendaciones`, por centro).
Esta constante es SOLO el valor por defecto con el que se siembra esa clave; una vez
en CONFIG, el centro puede editarlo sin tocar código.
"""

RECOMENDACIONES_CATALOGO: dict = {
    "secciones": [
        {
            "clave": "higiene",
            "titulo": "Higiene Bucal",
            "icono": "Toothbrush",
            "color": "#1500A0",
            "items": [
                "Cepilla tus dientes 2-3 veces al día",
                "Usa hilo dental diariamente",
                "Enjuague bucal después de las comidas",
                "Cambia tu cepillo cada 3 meses",
                "Cepilla suavemente, sin presionar",
            ],
        },
        {
            "clave": "dieta",
            "titulo": "Dieta y Hábitos",
            "icono": "Apple",
            "color": "#1ca0d1",
            "items": [
                "Evita alimentos y bebidas azucaradas",
                "Reduce el consumo de ácidos (cítricos, refrescos)",
                "Limita alimentos muy duros o pegajosos",
                "Aumenta consumo de calcio y fibra",
                "Evita tabaco y alcohol",
            ],
        },
        {
            "clave": "medicacion",
            "titulo": "Medicación Post-Tratamiento",
            "icono": "Pill",
            "color": "#2DD9C3",
            "items": [
                "Toma los antibióticos prescritos completos",
                "Toma analgésicos según se indica",
                "Sigue el tratamiento antiinflamatorio prescrito",
                "No suspendas la medicación sin consultar",
            ],
        },
        {
            "clave": "reposo",
            "titulo": "Actividad y Reposo",
            "icono": "Bed",
            "color": "#FF6B6B",
            "items": [
                "Evita esfuerzo físico intenso 24-48 horas",
                "No hagas enjuagues bucales durante 24 horas",
                "Duerme con la cabeza elevada los primeros días",
                "Evita fumar y alcohol 48-72 horas",
                "Limita la masticación en el lado tratado",
            ],
        },
        {
            "clave": "seguimiento",
            "titulo": "Seguimiento",
            "icono": "Calendar",
            "color": "#FFA500",
            "items": [
                "Mantén tu próxima cita programada",
                "Contacta si tienes dolor persistente",
                "Avisa si notas sangrado o inflamación",
                "Consulta si hay cambios en la zona tratada",
                "Realiza revisión de control en el plazo indicado",
            ],
        },
    ]
}

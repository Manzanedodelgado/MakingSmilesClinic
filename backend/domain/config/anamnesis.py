"""Catálogo de anamnesis (cuestionario de salud del paciente).

Fuente de la verdad en runtime = CONFIG (clave `clinica.anamnesis`, por centro).
Esta constante es SOLO el valor por defecto con el que se siembra esa clave; una vez
en CONFIG, el centro puede editarlo sin tocar código. 6 secciones · 96 ítems.
`criticos` = ítems que deben resaltarse como alerta clínica al marcarse.
"""

ANAMNESIS_CATALOGO: dict = {
    "secciones": [
        {
            "clave": "sistemicos", "titulo": "Antecedentes Sistémicos",
            "icono": "Stethoscope", "color": "#1500A0",
            "items": [
                "Diabetes Mellitus (Tipo I)", "Diabetes Mellitus (Tipo II)", "Hepatitis A",
                "Hepatitis B", "Hepatitis C", "VIH / SIDA", "Tuberculosis",
                "Epilepsia / Convulsiones", "Asma", "EPOC", "Apnea del Sueño",
                "Problemas Tiroides (Hipo)", "Problemas Tiroides (Hiper)", "Anemia",
                "Problemas de Coagulación", "Cáncer (en tratamiento)", "Cáncer (en remisión)",
                "Úlcera Gástrica / Reflujo", "Insuficiencia Renal", "Insuficiencia Hepática",
                "Enfermedades Autoinmunes", "Artritis Reumatoide", "Lupus", "Fibromialgia",
                "Enfermedad de Crohn", "Colitis Ulcerosa",
            ],
        },
        {
            "clave": "cardiovascular", "titulo": "Perfil Cardiovascular",
            "icono": "Heart", "color": "#1500A0",
            "items": [
                "Hipertensión Arterial", "Hipotensión", "Infarto de Miocardio",
                "Angina de Pecho", "Soplo Cardíaco", "Valvulopatías", "Marcapasos",
                "Arritmias", "Insuficiencia Cardíaca", "Trombosis Venosa", "Varices",
                "Endocarditis previa", "Prótesis Valvular",
            ],
        },
        {
            "clave": "alergias", "titulo": "Alergias",
            "icono": "AlertTriangle", "color": "#1500A0",
            "items": [
                "Alergia a Penicilina / Amoxicilina", "Alergia a Anestesia Local",
                "Alergia a Aspirina / AINES", "Alergia a Codeína", "Alergia al Látex",
                "Alergia a Metales (Níquel)", "Alergia a Yodo", "Alergia a Sulfamidas",
            ],
        },
        {
            "clave": "medicacion", "titulo": "Medicación Actual",
            "icono": "Pill", "color": "#1ca0d1",
            "items": [
                "Anticoagulantes (Sintrom/Warfarina)", "Antiagregantes (Adiro/Aspirina)",
                "Bifosfonatos (Alendronato/Zometa)", "Corticoides", "Inmunosupresores",
                "Quimioterapia", "Radioterapia (cabeza/cuello)", "Antidepresivos",
                "Ansiolíticos / Benzodiacepinas", "Antihipertensivos", "Insulina",
                "Antidiabéticos orales", "Antiepilépticos", "Hormona tiroidea",
                "Anticonceptivos orales",
            ],
        },
        {
            "clave": "bucodental", "titulo": "Salud Bucodental",
            "icono": "Smile", "color": "#3388FF",
            "items": [
                "Sangrado de Encías", "Sensibilidad al Frío", "Sensibilidad al Calor",
                "Movilidad Dental", "Dolor en ATM (Articulación)", "Chasquidos al abrir/cerrar",
                "Limitación apertura bucal", "Bruxismo (Aprieta)", "Bruxismo (Rechina)",
                "Sequedad de Boca (Xerostomía)", "Halitosis", "Llagas / Aftas recurrentes",
                "Ortodoncia previa", "Implantes previos", "Prótesis removible", "Cirugía oral previa",
            ],
        },
        {
            "clave": "habitos", "titulo": "Hábitos y Estilo de Vida",
            "icono": "Activity", "color": "#1500A0",
            "items": [
                "Fumador actual", "Exfumador", "Vapea", "Consumo habitual de alcohol",
                "Drogas recreativas", "Embarazada", "Lactancia", "Dieta alta en azúcares",
                "Cepillado < 2 veces/día", "No usa hilo dental", "No usa enjuague",
                "Onicofagia (se muerde las uñas)", "Muerde objetos (bolígrafos, etc.)",
            ],
        },
    ],
    "criticos": [
        "Alergia a Penicilina / Amoxicilina", "Alergia a Anestesia Local",
        "Alergia a Aspirina / AINES", "Alergia al Látex", "Infarto de Miocardio",
        "Marcapasos", "Prótesis Valvular", "Endocarditis previa",
        "Anticoagulantes (Sintrom/Warfarina)", "Bifosfonatos (Alendronato/Zometa)",
        "VIH / SIDA", "Hepatitis B", "Hepatitis C", "Quimioterapia",
        "Radioterapia (cabeza/cuello)", "Embarazada",
    ],
}


def anamnesis_items() -> set[str]:
    """Conjunto plano de todos los ítems válidos (para validar respuestas)."""
    return {item for sec in ANAMNESIS_CATALOGO["secciones"] for item in sec["items"]}

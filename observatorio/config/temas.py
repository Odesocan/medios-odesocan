"""
Temáticas y diccionarios de palabras clave.

El clasificador (`observatorio/clasificacion/`) puntúa cada noticia contra
estas listas. `peso_titulo` es cuánto suma una coincidencia en el titular: con
peso 4 una sola palabra clave ya supera el umbral de 2,6, lo que prioriza no
perder cobertura frente a algún falso positivo.
"""
# ── Temáticas y diccionarios de palabras clave ────────────────────────────────
# Cada tema tiene palabras clave (título + cuerpo) que activan la clasificación.
# Orden importa: la primera coincidencia con mayor score gana.

TEMAS = {
    "migracion": {
        "label":  "Migración",
        "color":  "#1565c0",
        "keywords": [
            # --- términos nucleares ---
            "migrante", "migrantes", "migración", "migratorio", "migratorios",
            "inmigrante", "inmigrantes", "inmigración",
            "patera", "pateras", "cayuco", "cayucos",
            # --- menores y acogida migratoria ---
            "mena", "menas", "menor extranjero", "menores no acompañados",
            "acogida de migrantes", "acogida humanitaria", "centro de internamiento",
            # --- rutas y travesías ---
            "ruta canaria", "ruta atlántica", "travesía migratoria", "naufragio",
            "lancha neumática", "embarcación migrantes",
            # --- política migratoria ---
            "frontex", "repatriación", "regularización", "solicitante de asilo",
            "refugiado", "refugiados", "cupo migratorio", "reparto migrantes",
            "crisis migratoria", "flujo migratorio", "llegada de migrantes",
            "rescate marítimo", "salvamento marítimo",
        ],
        "peso_titulo": 3,
    },
    "economia": {
        "label":  "Economía",
        "color":  "#2e7d32",
        "keywords": [
            # --- indicadores macro ---
            "pib", "producto interior bruto", "inflación", "ipc",
            "recesión", "crecimiento económico", "actividad económica",
            # --- empleo y mercado laboral ---
            "tasa de paro", "tasa de desempleo", "tasa de empleo",
            "desempleo", "empleo", "epa", "afiliación seguridad social",
            "convenio colectivo", "negociación colectiva", "sindicato",
            "salario mínimo", "subida salarial", "reforma laboral",
            # --- comercio y tejido empresarial ---
            "exportación canaria", "importación canaria", "balanza comercial",
            "zona especial canaria", "zec", "zona franca",
            "rie", "régimen económico fiscal", "ref",
            "autónomo", "autónomos", "pyme", "cierre de empresa",
            "concurso de acreedores", "ere", "erte",
        ],
        "peso_titulo": 3,
    },
    "presupuestos": {
        "label":  "Presupuestos",
        "color":  "#e65100",
        "keywords": [
            # --- presupuestos públicos ---
            "presupuesto", "presupuestos", "presupuestos generales",
            "ley de presupuestos", "pge", "presupuesto autonómico",
            "partida presupuestaria", "crédito extraordinario",
            # --- gasto e inversión pública ---
            "gasto público", "inversión pública", "inversión estatal",
            "dotación presupuestaria", "ejecución presupuestaria",
            # --- fiscalidad ---
            "hacienda canaria", "agencia tributaria", "recaudación fiscal",
            "impuesto canario", "igic", "tributo", "aiem",
            "deuda pública", "déficit público", "superávit",
            # --- financiación territorial ---
            "financiación autonómica", "convenio de carreteras",
            "subvención pública", "fondos europeos", "fondos next generation",
            "transferencia estatal", "enmienda presupuestaria",
        ],
        "peso_titulo": 3,
    },
    "violencia_genero": {
        "label":  "Violencia de género",
        "color":  "#880e4f",
        "keywords": [
            # --- términos nucleares ---
            "violencia de género", "violencia machista", "violencia contra la mujer",
            "feminicidio", "femicidio", "mujer asesinada",
            # --- formas de violencia ---
            "maltrato machista", "maltratador", "agresor machista",
            "agresión sexual", "violación", "violador",
            "acoso sexual", "sumisión química",
            # --- protección y respuesta institucional ---
            "orden de alejamiento", "orden de protección",
            "punto violeta", "pacto de estado violencia",
            "casa de acogida víctimas", "víctima de género",
            "denuncia por maltrato", "denuncia por violencia de género",
            # --- conceptos asociados ---
            "misoginia", "machismo", "control coercitivo",
        ],
        "peso_titulo": 4,
    },
    "politica": {
        "label":  "Política",
        "color":  "#4a148c",
        "keywords": [
            # --- instituciones canarias ---
            "parlamento canario", "gobierno de canarias", "gobierno canario",
            "cabildo insular", "cabildo de tenerife", "cabildo de gran canaria",
            "consejería", "diputado del común",
            # --- partidos y actores ---
            "coalición canaria", "nueva canarias", "psoe canarias",
            "pp canarias", "podemos canarias", "drago", "asamblea socialista",
            # --- actividad parlamentaria ---
            "pleno parlamentario", "pleno del cabildo", "pleno municipal",
            "moción de censura", "proposición de ley", "decreto ley",
            "elecciones canarias", "elecciones municipales", "votación parlamentaria",
            "pacto de gobierno", "investidura", "oposición parlamentaria",
            # --- competencias y estatuto ---
            "estatuto de autonomía", "transferencia competencial",
            "régimen especial canario",
        ],
        "peso_titulo": 2,
    },
    "medio_ambiente": {
        "label":  "Medio ambiente",
        "color":  "#1b5e20",
        "keywords": [
            # --- cambio climático y emisiones ---
            "cambio climático", "calentamiento global", "emisiones co2",
            "huella de carbono", "descarbonización", "gases de efecto invernadero",
            # --- contaminación y residuos ---
            "contaminación ambiental", "vertido ilegal", "vertido al mar",
            "residuos urbanos", "reciclaje", "planta de residuos",
            "contaminación atmosférica", "microplástico",
            # --- energía ---
            "energía renovable", "energía fotovoltaica", "energía eólica",
            "parque eólico", "planta solar", "transición energética",
            # --- biodiversidad y espacios naturales ---
            "biodiversidad", "especie protegida", "especie invasora",
            "parque natural", "parque nacional", "reserva de la biosfera",
            "red natura 2000", "posidonia",
            # --- emergencias ambientales ---
            "incendio forestal", "sequía", "desertificación",
        ],
        "peso_titulo": 2,
    },
    "vivienda": {
        "label":  "Vivienda",
        "color":  "#f57f17",
        "keywords": [
            # --- acceso a vivienda ---
            "precio de la vivienda", "acceso a la vivienda", "burbuja inmobiliaria",
            "vivienda asequible", "primera vivienda", "compraventa de vivienda",
            # --- alquiler ---
            "alquiler", "precio del alquiler", "subida del alquiler",
            "arrendamiento", "inquilino", "bono alquiler joven",
            "alquiler vacacional", "vivienda vacacional",
            # --- vivienda pública y social ---
            "vivienda social", "vivienda pública", "vivienda protegida",
            "parque de vivienda", "promoción de vivienda",
            "ley de vivienda", "plan de vivienda",
            # --- problemas habitacionales ---
            "desahucio", "lanzamiento judicial", "okupación",
            "sinhogarismo", "emergencia habitacional",
            # --- urbanismo vinculado ---
            "suelo urbanizable", "plan general de ordenación",
            "hipoteca", "mercado inmobiliario",
        ],
        "peso_titulo": 3,
    },
    "sanidad": {
        "label":  "Sanidad",
        "color":  "#008591",
        "keywords": [
            # --- sistema sanitario canario ---
            "servicio canario de salud", "scs", "sanidad canaria",
            "hospital", "hospital universitario", "centro de salud",
            "atención primaria", "urgencias hospitalarias",
            # --- personal sanitario ---
            "personal sanitario", "médico de familia", "enfermería",
            "huelga médicos", "huelga sanitaria", "plaza mir",
            "médico especialista", "déficit de médicos",
            # --- listas de espera y gestión ---
            "lista de espera", "lista de espera quirúrgica",
            "saturación de urgencias", "cama hospitalaria",
            "ambulancia", "ambulatorio",
            # --- salud pública ---
            "vacunación", "campaña de vacunación", "epidemia", "brote",
            "alerta sanitaria", "oncología", "quirófano",
        ],
        "peso_titulo": 3,
    },
    "salud_mental": {
        "label":  "Salud mental",
        "color":  "#d28aff",
        "keywords": [
            # --- términos nucleares ---
            "salud mental", "trastorno mental", "enfermedad mental",
            "crisis de salud mental",
            # --- trastornos específicos ---
            "depresión", "ansiedad", "trastorno bipolar",
            "trastorno alimentario", "anorexia", "bulimia",
            "trastorno obsesivo", "esquizofrenia",
            # --- suicidio ---
            "suicidio", "conducta suicida", "prevención del suicidio",
            "ideación suicida", "teléfono de la esperanza",
            # --- atención y profesionales ---
            "psiquiatría", "psicólogo", "psicología clínica",
            "unidad de salud mental", "atención psicológica",
            # --- adicciones ---
            "drogodependencia", "ludopatía", "adicción al juego",
            "centro de adicciones",
            # --- estrés y bienestar ---
            "burnout", "estrés postraumático",
        ],
        "peso_titulo": 4,
    },
    "turismo": {
        "label":  "Turismo",
        "color":  "#0277bd",
        "keywords": [
            # --- términos nucleares ---
            "turismo", "turistas", "turista", "turístico", "turística",
            "sector turístico", "industria turística",
            # --- alojamiento ---
            "hotel", "hotelero", "ocupación hotelera", "pernoctación",
            "planta alojativa", "resort", "apartamento turístico",
            # --- volumen y datos ---
            "llegada de turistas", "visitantes", "cruceristas",
            "gasto turístico", "estancia media",
            # --- modelo turístico ---
            "masificación turística", "turismo de masas", "turismofobia",
            "moratoria turística", "ecotasa", "tasa turística",
            "turismo sostenible", "turismo rural",
            # --- instituciones y promoción ---
            "promotur", "patronato de turismo", "turespaña",
            "tour operador", "destino turístico",
        ],
        "peso_titulo": 3,
    },
    "dependencia_discapacidad": {
        "label":  "Dependencia y Discapacidad",
        "color":  "#0ea5e9",
        "keywords": [
            # --- dependencia ---
            "ley de dependencia", "grado de dependencia",
            "persona dependiente", "persona mayor dependiente",
            "reconocimiento de dependencia", "prestación por dependencia",
            "saad", "sistema de dependencia",
            # --- discapacidad ---
            "discapacidad", "persona con discapacidad",
            "diversidad funcional", "certificado de discapacidad",
            "grado de discapacidad", "discapacidad intelectual",
            # --- cuidados ---
            "cuidador familiar", "cuidadora", "ayuda a domicilio",
            "asistencia personal", "teleasistencia",
            # --- centros y recursos ---
            "residencia de mayores", "centro de día",
            "centro ocupacional", "imserso",
            # --- accesibilidad ---
            "accesibilidad", "barrera arquitectónica",
            "silla de ruedas", "lengua de signos",
        ],
        "peso_titulo": 3,
    },
    "justicia": {
        "label":  "Justicia",
        "color":  "#37474f",
        "keywords": [
            # --- sistema judicial ---
            "tribunal superior de justicia", "tsjc", "audiencia provincial",
            "juzgado", "juez", "jueza", "magistrado", "magistrada",
            "fiscalía", "fiscal", "ministerio fiscal",
            # --- proceso judicial ---
            "sentencia", "sentencia firme", "juicio oral", "vista oral",
            "instrucción judicial", "auto judicial", "recurso de apelación",
            "recurso de casación", "causa penal", "procedimiento judicial",
            # --- delitos y condenas ---
            "condena", "absolución", "imputado", "investigado",
            "acusado", "pena de prisión", "delito", "estafa",
            "corrupción judicial", "prevaricación", "blanqueo de capitales",
            "trama corrupta", "caso judicial",
            # --- justicia y acceso ---
            "asistencia jurídica gratuita", "turno de oficio",
            "colapso judicial", "atasco judicial",
            "justicia restaurativa", "mediación judicial",
        ],
        "peso_titulo": 3,
    },
    "diversidad": {
        "label":  "Diversidad",
        "color":  "#7b1fa2",
        "keywords": [
            # --- diversidad sexual y de género ---
            "lgtbi", "lgtbiq", "lgbtq", "orgullo lgtbi",
            "homosexual", "homosexualidad", "lesbiana", "bisexual",
            "transexual", "transgénero", "persona trans",
            "identidad de género", "orientación sexual",
            "matrimonio igualitario", "ley trans",
            "homofobia", "transfobia", "lgtbifobia", "delito de odio",
            # --- diversidad étnica y cultural ---
            "diversidad cultural", "multiculturalidad", "interculturalidad",
            "racismo", "xenofobia", "discriminación racial",
            "pueblo gitano", "comunidad gitana", "etnia",
            "antirracismo", "discurso de odio",
            # --- inclusión ---
            "inclusión social", "inclusión educativa",
            "no discriminación", "ley de igualdad de trato",
        ],
        "peso_titulo": 3,
    },
    "cuidados": {
        "label":  "Cuidados",
        "color":  "#ef6c00",
        "keywords": [
            # --- crianza y conciliación ---
            "crianza", "maternidad", "paternidad",
            "permiso de maternidad", "permiso de paternidad",
            "permiso parental", "baja maternal", "baja paternal",
            "conciliación laboral", "conciliación familiar",
            "corresponsabilidad", "corresponsabilidad familiar",
            # --- cuidados de larga duración ---
            "cuidados de larga duración", "cuidado de mayores",
            "cuidado de dependientes", "cuidador no profesional",
            "cuidadora informal", "sobrecarga del cuidador",
            "respiro familiar", "servicio de respiro",
            # --- infancia ---
            "escuela infantil", "guardería", "educación infantil",
            "plaza de guardería", "cheque guardería",
            # --- economía de los cuidados ---
            "economía de los cuidados", "trabajo no remunerado",
            "trabajo doméstico", "empleada de hogar",
            "sistema de cuidados", "derecho al cuidado",
            "crisis de los cuidados", "profesionalización de los cuidados",
        ],
        "peso_titulo": 3,
    },
    "igualdad": {
        "label":  "Igualdad",
        "color":  "#ad1457",
        "keywords": [
            # --- igualdad de género ---
            "igualdad de género", "igualdad entre hombres y mujeres",
            "brecha de género", "brecha salarial", "techo de cristal",
            "paridad", "cuota de género", "plan de igualdad",
            "perspectiva de género", "transversalidad de género",
            "feminismo", "empoderamiento femenino",
            "instituto de la mujer", "instituto canario de igualdad",
            "ley de igualdad", "ley orgánica de igualdad",
            # --- igualdad material y social ---
            "desigualdad social", "desigualdad económica",
            "pobreza", "tasa de pobreza", "exclusión social",
            "riesgo de pobreza", "pobreza infantil", "pobreza energética",
            "renta mínima", "ingreso mínimo vital", "prestación canaria de inserción",
            "índice de gini", "redistribución",
            # --- derechos e instituciones ---
            "derechos sociales", "justicia social",
            "servicios sociales", "política social",
        ],
        "peso_titulo": 3,
    },
}

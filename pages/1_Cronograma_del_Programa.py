import streamlit as st
from datetime import datetime, timedelta, date
import uuid
import urllib.parse

st.set_page_config(
    page_title="Cronograma del Programa - 90 Dias",
    page_icon="📅",
    layout="wide",
)

# ============================================================
# CONFIGURACION DEL PROGRAMA - EDITA ESTA SECCION
# ============================================================
# Personaliza las tareas de tu programa de 90 dias.
#
# Cada tarea tiene:
#   - dia: numero de dia desde el inicio (1 = primer dia)
#   - titulo: nombre de la tarea que aparecera en el calendario
#   - descripcion: instrucciones para el cliente
#   - link: URL al recurso (video, documento, plataforma, etc.)
#   - duracion_minutos: duracion estimada (aparece en el evento)
#
# Agrega, elimina o modifica tareas segun tu programa.
# ============================================================

NOMBRE_PROGRAMA = "Programa de 90 Dias"

PROGRAMA_TAREAS = [
    # === SEMANA 1: FUNDAMENTOS ===
    {
        "dia": 1,
        "titulo": "Dia 1 - Bienvenida y Configuracion Inicial",
        "descripcion": "Mira el video de bienvenida, configura tu cuenta y familiarizate con la plataforma.",
        "link": "https://tu-plataforma.com/modulo-1/bienvenida",
        "duracion_minutos": 60,
    },
    {
        "dia": 3,
        "titulo": "Dia 3 - Define tus Objetivos",
        "descripcion": "Completa la hoja de trabajo para definir tus objetivos principales del programa.",
        "link": "https://tu-plataforma.com/modulo-1/objetivos",
        "duracion_minutos": 45,
    },
    {
        "dia": 5,
        "titulo": "Dia 5 - Evaluacion Inicial",
        "descripcion": "Realiza la evaluacion inicial para medir tu punto de partida.",
        "link": "https://tu-plataforma.com/modulo-1/evaluacion",
        "duracion_minutos": 30,
    },
    # === SEMANA 2: MODULO 2 ===
    {
        "dia": 8,
        "titulo": "Dia 8 - Modulo 2: Fundamentos Clave",
        "descripcion": "Mira las lecciones del Modulo 2 y toma notas de los conceptos principales.",
        "link": "https://tu-plataforma.com/modulo-2",
        "duracion_minutos": 90,
    },
    {
        "dia": 11,
        "titulo": "Dia 11 - Tarea del Modulo 2",
        "descripcion": "Completa los ejercicios practicos del Modulo 2.",
        "link": "https://tu-plataforma.com/modulo-2/tarea",
        "duracion_minutos": 60,
    },
    # === SEMANA 3-4: MODULO 3 ===
    {
        "dia": 15,
        "titulo": "Dia 15 - Modulo 3: Estrategia",
        "descripcion": "Aprende las estrategias clave del Modulo 3. Mira todos los videos.",
        "link": "https://tu-plataforma.com/modulo-3",
        "duracion_minutos": 90,
    },
    {
        "dia": 19,
        "titulo": "Dia 19 - Tarea del Modulo 3",
        "descripcion": "Aplica las estrategias aprendidas con los ejercicios del Modulo 3.",
        "link": "https://tu-plataforma.com/modulo-3/tarea",
        "duracion_minutos": 60,
    },
    {
        "dia": 22,
        "titulo": "Dia 22 - Revision de Progreso (Mes 1)",
        "descripcion": "Revisa tu avance del primer mes. Completa el formulario de seguimiento.",
        "link": "https://tu-plataforma.com/revision-mes-1",
        "duracion_minutos": 30,
    },
    # === SEMANA 5-6: MODULO 4 ===
    {
        "dia": 29,
        "titulo": "Dia 29 - Modulo 4: Implementacion",
        "descripcion": "Comienza la fase de implementacion con el Modulo 4.",
        "link": "https://tu-plataforma.com/modulo-4",
        "duracion_minutos": 90,
    },
    {
        "dia": 33,
        "titulo": "Dia 33 - Tarea del Modulo 4",
        "descripcion": "Entrega los ejercicios de implementacion del Modulo 4.",
        "link": "https://tu-plataforma.com/modulo-4/tarea",
        "duracion_minutos": 60,
    },
    # === SEMANA 7-8: MODULO 5 ===
    {
        "dia": 43,
        "titulo": "Dia 43 - Modulo 5: Optimizacion",
        "descripcion": "Aprende tecnicas avanzadas de optimizacion en el Modulo 5.",
        "link": "https://tu-plataforma.com/modulo-5",
        "duracion_minutos": 90,
    },
    {
        "dia": 47,
        "titulo": "Dia 47 - Tarea del Modulo 5",
        "descripcion": "Completa los ejercicios avanzados del Modulo 5.",
        "link": "https://tu-plataforma.com/modulo-5/tarea",
        "duracion_minutos": 60,
    },
    {
        "dia": 50,
        "titulo": "Dia 50 - Revision de Progreso (Mitad del Programa)",
        "descripcion": "Evaluacion de mitad de programa. Revisa tus logros y ajusta tu plan.",
        "link": "https://tu-plataforma.com/revision-mitad",
        "duracion_minutos": 30,
    },
    # === SEMANA 9-10: MODULO 6 ===
    {
        "dia": 57,
        "titulo": "Dia 57 - Modulo 6: Escalamiento",
        "descripcion": "Aprende a escalar los resultados obtenidos con el Modulo 6.",
        "link": "https://tu-plataforma.com/modulo-6",
        "duracion_minutos": 90,
    },
    {
        "dia": 61,
        "titulo": "Dia 61 - Tarea del Modulo 6",
        "descripcion": "Implementa las estrategias de escalamiento del Modulo 6.",
        "link": "https://tu-plataforma.com/modulo-6/tarea",
        "duracion_minutos": 60,
    },
    # === SEMANA 11-12: MODULO 7 ===
    {
        "dia": 71,
        "titulo": "Dia 71 - Modulo 7: Consolidacion",
        "descripcion": "Consolida todo lo aprendido con el Modulo 7.",
        "link": "https://tu-plataforma.com/modulo-7",
        "duracion_minutos": 90,
    },
    {
        "dia": 75,
        "titulo": "Dia 75 - Tarea del Modulo 7",
        "descripcion": "Entrega el proyecto final del Modulo 7.",
        "link": "https://tu-plataforma.com/modulo-7/tarea",
        "duracion_minutos": 60,
    },
    # === SEMANA 13: CIERRE ===
    {
        "dia": 82,
        "titulo": "Dia 82 - Preparacion para el Cierre",
        "descripcion": "Prepara tu presentacion final y revisa todos los modulos completados.",
        "link": "https://tu-plataforma.com/cierre/preparacion",
        "duracion_minutos": 60,
    },
    {
        "dia": 87,
        "titulo": "Dia 87 - Evaluacion Final",
        "descripcion": "Completa la evaluacion final del programa para medir tu progreso.",
        "link": "https://tu-plataforma.com/cierre/evaluacion-final",
        "duracion_minutos": 45,
    },
    {
        "dia": 90,
        "titulo": "Dia 90 - Graduacion y Proximos Pasos",
        "descripcion": "Celebra tu graduacion! Revisa los proximos pasos y recursos adicionales.",
        "link": "https://tu-plataforma.com/cierre/graduacion",
        "duracion_minutos": 30,
    },
]

# ============================================================
# FIN DE CONFIGURACION - No necesitas editar debajo de aqui
# ============================================================


def _escapar_ics(texto: str) -> str:
    """Escapa caracteres especiales para el formato iCalendar (RFC 5545)."""
    texto = texto.replace("\\", "\\\\")
    texto = texto.replace(";", "\\;")
    texto = texto.replace(",", "\\,")
    texto = texto.replace("\n", "\\n")
    return texto


def generar_ics(fecha_inicio: date, tareas: list[dict]) -> str:
    """Genera el contenido de un archivo .ics con todas las tareas del programa.

    El archivo resultante es compatible con Google Calendar, Outlook,
    Apple Calendar y cualquier app que soporte el estandar iCalendar.
    """
    lineas = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:-//{NOMBRE_PROGRAMA}//ES",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escapar_ics(NOMBRE_PROGRAMA)}",
    ]

    for tarea in tareas:
        fecha = fecha_inicio + timedelta(days=tarea["dia"] - 1)
        hora_inicio = datetime.combine(fecha, datetime.min.time()).replace(hour=9)
        hora_fin = hora_inicio + timedelta(minutes=tarea["duracion_minutos"])

        descripcion = tarea["descripcion"]
        if tarea.get("link"):
            descripcion += f"\\n\\nRecurso: {tarea['link']}"

        uid = str(uuid.uuid4())

        lineas.extend([
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}",
            f"DTSTART:{hora_inicio.strftime('%Y%m%dT%H%M%S')}",
            f"DTEND:{hora_fin.strftime('%Y%m%dT%H%M%S')}",
            f"SUMMARY:{_escapar_ics(tarea['titulo'])}",
            f"DESCRIPTION:{_escapar_ics(descripcion)}",
        ])

        if tarea.get("link"):
            lineas.append(f"URL:{tarea['link']}")

        # Recordatorio 30 minutos antes
        lineas.extend([
            "BEGIN:VALARM",
            "TRIGGER:-PT30M",
            "ACTION:DISPLAY",
            f"DESCRIPTION:Recordatorio: {_escapar_ics(tarea['titulo'])}",
            "END:VALARM",
            "END:VEVENT",
        ])

    lineas.append("END:VCALENDAR")
    return "\r\n".join(lineas)


def generar_google_calendar_url(
    fecha: date, titulo: str, descripcion: str, link: str, duracion_minutos: int
) -> str:
    """Genera un URL para agregar un evento individual a Google Calendar."""
    hora_inicio = datetime.combine(fecha, datetime.min.time()).replace(hour=9)
    hora_fin = hora_inicio + timedelta(minutes=duracion_minutos)

    desc = descripcion
    if link:
        desc += f"\n\nRecurso: {link}"

    params = {
        "action": "TEMPLATE",
        "text": titulo,
        "dates": (
            f"{hora_inicio.strftime('%Y%m%dT%H%M%S')}"
            f"/{hora_fin.strftime('%Y%m%dT%H%M%S')}"
        ),
        "details": desc,
    }

    return "https://www.google.com/calendar/render?" + urllib.parse.urlencode(params)


def agrupar_por_fase(tareas: list[dict]) -> list[tuple[str, list[dict]]]:
    """Agrupa las tareas por fase del programa basado en el dia."""
    fases = [
        ("Semana 1-2: Fundamentos", 1, 14),
        ("Semana 3-4: Estrategia", 15, 28),
        ("Semana 5-6: Implementacion", 29, 42),
        ("Semana 7-8: Optimizacion", 43, 56),
        ("Semana 9-10: Escalamiento", 57, 70),
        ("Semana 11-12: Consolidacion", 71, 84),
        ("Semana 13: Cierre", 85, 90),
    ]

    resultado = []
    for nombre_fase, dia_inicio, dia_fin in fases:
        tareas_fase = [t for t in tareas if dia_inicio <= t["dia"] <= dia_fin]
        if tareas_fase:
            resultado.append((nombre_fase, tareas_fase))

    return resultado


def main():
    st.title("Cronograma del Programa")
    st.markdown(
        f"Organiza tus proximos **90 dias** del **{NOMBRE_PROGRAMA}** de forma automatica. "
        "Selecciona tu fecha de inicio y agrega todas las tareas a tu calendario con un solo clic."
    )

    st.divider()

    # --- Panel de configuracion ---
    col_config, col_preview = st.columns([1, 2])

    with col_config:
        st.subheader("Tu fecha de inicio")

        fecha_inicio = st.date_input(
            "Selecciona cuando empiezas",
            value=date.today(),
            min_value=date.today() - timedelta(days=30),
            help="Elige la fecha en que quieres comenzar el programa",
        )

        fecha_fin = fecha_inicio + timedelta(days=89)

        st.info(
            f"**Inicio:** {fecha_inicio.strftime('%d/%m/%Y')}\n\n"
            f"**Fin:** {fecha_fin.strftime('%d/%m/%Y')}\n\n"
            f"**Total de tareas:** {len(PROGRAMA_TAREAS)}"
        )

        st.divider()

        # Generar ICS
        ics_content = generar_ics(fecha_inicio, PROGRAMA_TAREAS)

        st.subheader("Agregar a tu calendario")

        st.download_button(
            label="Descargar cronograma (.ics)",
            data=ics_content,
            file_name="cronograma_programa.ics",
            mime="text/calendar",
            type="primary",
            use_container_width=True,
        )

        st.caption(
            "Compatible con **Google Calendar**, **Outlook**, "
            "**Apple Calendar** y cualquier app de calendario."
        )

        with st.expander("Como importar en Google Calendar"):
            st.markdown(
                "1. Descarga el archivo **.ics** con el boton de arriba\n"
                "2. Abre [Google Calendar](https://calendar.google.com) en tu computadora\n"
                "3. En la barra lateral izquierda, busca **Otros calendarios** y haz clic en **+**\n"
                "4. Selecciona **Importar**\n"
                "5. Elige el archivo .ics que descargaste\n"
                "6. Selecciona el calendario donde quieres agregar las tareas\n"
                "7. Haz clic en **Importar**\n\n"
                "Todas las tareas apareceran automaticamente en tu calendario "
                "con recordatorios 30 minutos antes."
            )

        with st.expander("Como importar en Outlook"):
            st.markdown(
                "1. Descarga el archivo **.ics**\n"
                "2. Abre Outlook y ve a la seccion de **Calendario**\n"
                "3. Haz clic en **Agregar calendario** > **Desde archivo**\n"
                "4. Selecciona el archivo .ics\n"
                "5. Confirma la importacion"
            )

        with st.expander("Como importar en Apple Calendar"):
            st.markdown(
                "1. Descarga el archivo **.ics**\n"
                "2. Haz doble clic en el archivo descargado\n"
                "3. Apple Calendar se abrira automaticamente\n"
                "4. Confirma que deseas agregar los eventos"
            )

    # --- Vista previa del cronograma ---
    with col_preview:
        st.subheader("Vista previa de tu cronograma")

        fases = agrupar_por_fase(PROGRAMA_TAREAS)

        for nombre_fase, tareas_fase in fases:
            st.markdown(f"#### {nombre_fase}")

            for tarea in tareas_fase:
                fecha = fecha_inicio + timedelta(days=tarea["dia"] - 1)
                duracion = tarea["duracion_minutos"]

                with st.container(border=True):
                    c_fecha, c_info, c_accion = st.columns([1, 3, 1])

                    with c_fecha:
                        st.markdown(f"**{fecha.strftime('%d %b')}**")
                        st.caption(f"Dia {tarea['dia']}")

                    with c_info:
                        st.markdown(f"**{tarea['titulo']}**")
                        st.caption(f"{tarea['descripcion']}")
                        if duracion:
                            horas = duracion // 60
                            minutos = duracion % 60
                            if horas and minutos:
                                st.caption(f"Duracion: {horas}h {minutos}min")
                            elif horas:
                                st.caption(f"Duracion: {horas}h")
                            else:
                                st.caption(f"Duracion: {minutos}min")

                    with c_accion:
                        if tarea.get("link"):
                            gcal_url = generar_google_calendar_url(
                                fecha,
                                tarea["titulo"],
                                tarea["descripcion"],
                                tarea["link"],
                                tarea["duracion_minutos"],
                            )
                            st.link_button(
                                "+ Google Cal",
                                gcal_url,
                                use_container_width=True,
                            )

            st.markdown("")  # Espaciado entre fases


if __name__ == "__main__":
    main()

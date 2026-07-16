import streamlit as st
import subprocess
import tempfile
import os
import base64
import shutil
import time
import re
from pathlib import Path

import gdown
from PIL import Image
from io import BytesIO
from openai import OpenAI
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="Transcripcion y Descripcion de Video",
    page_icon="🎬",
    layout="wide",
)


# --- Verificar dependencias del sistema ---
def verificar_dependencias():
    faltantes = []
    if not shutil.which("ffmpeg"):
        faltantes.append("ffmpeg")
    if not shutil.which("yt-dlp"):
        faltantes.append("yt-dlp")
    if faltantes:
        st.error(
            f"Faltan dependencias del sistema: **{', '.join(faltantes)}**. "
            f"Instalalas con: `pip install yt-dlp` y `apt install ffmpeg` (o `brew install ffmpeg`)."
        )
        st.stop()


# --- Funciones principales ---


def extraer_id_google_drive(url: str) -> str | None:
    """Extrae el file ID de un link de Google Drive."""
    patterns = [
        r'/file/d/([a-zA-Z0-9_-]+)',       # /file/d/ID/view
        r'id=([a-zA-Z0-9_-]+)',             # ?id=ID
        r'/open\?id=([a-zA-Z0-9_-]+)',      # /open?id=ID
        r'drive\.google\.com/uc\?.*id=([a-zA-Z0-9_-]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def descargar_google_drive(url: str, output_dir: str) -> str:
    """Descarga un archivo desde Google Drive."""
    file_id = extraer_id_google_drive(url)
    if not file_id:
        st.error("No se pudo extraer el ID del archivo de Google Drive. Verifica el link.")
        st.stop()

    output_path = os.path.join(output_dir, "drive_file")
    try:
        download_url = f"https://drive.google.com/uc?id={file_id}"
        result = gdown.download(download_url, output_path, quiet=False)
        if result is None:
            st.error(
                "No se pudo descargar el archivo. Verifica que:\n"
                "1. El link sea correcto\n"
                "2. El archivo tenga permisos de **'Cualquier persona con el link'**\n"
                "3. No sea un archivo demasiado grande para descarga directa"
            )
            st.stop()
        # gdown puede cambiar el nombre del archivo
        if result != output_path and os.path.exists(result):
            return result
        return output_path
    except Exception as e:
        st.error(f"Error al descargar desde Google Drive: {e}")
        st.stop()


def descargar_video(url: str, output_dir: str) -> str:
    """Descarga un video usando yt-dlp."""
    output_template = os.path.join(output_dir, "video.%(ext)s")
    cmd = [
        "yt-dlp",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", output_template,
        url,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300)
    except subprocess.CalledProcessError as e:
        stderr = e.stderr or ""
        # Detectar errores comunes de autenticacion
        auth_keywords = [
            "registered users", "cookies", "login required", "private",
            "sign in", "authentication", "not authorized", "login-required",
        ]
        es_error_auth = any(kw.lower() in stderr.lower() for kw in auth_keywords)

        if es_error_auth:
            plataforma = "esta plataforma"
            if "facebook" in url.lower() or "fb.com" in url.lower():
                plataforma = "Facebook"
            elif "instagram" in url.lower():
                plataforma = "Instagram"
            elif "linkedin" in url.lower():
                plataforma = "LinkedIn"

            st.error(
                f"**{plataforma} requiere autenticacion** para descargar este video.\n\n"
                "**Soluciones alternativas:**\n\n"
                "1. **Descarga el video manualmente** (con una extension del navegador como "
                "'Video Downloader Plus' o similar) y subelo desde la tab **'Subir archivo'**.\n\n"
                "2. **Sube el video a Google Drive** (con permisos de 'Cualquier persona con el link') "
                "y pega el link en la tab **'Google Drive'** - mucho mas rapido que subirlo desde tu PC.\n\n"
                "3. Si el video es publico, verifica que la URL sea la version publica del video."
            )
        else:
            st.error(f"Error al descargar el video:\n```\n{stderr}\n```")
        st.stop()
    except subprocess.TimeoutExpired:
        st.error("La descarga tardo demasiado (>5 min). Intenta con un video mas corto.")
        st.stop()

    # Buscar el archivo descargado
    for f in Path(output_dir).iterdir():
        if f.name.startswith("video") and f.suffix in (".mp4", ".mkv", ".webm"):
            return str(f)

    st.error("No se encontro el archivo de video descargado.")
    st.stop()


def guardar_archivo_subido(archivo, output_dir: str) -> str:
    """Guarda un archivo subido a disco en chunks para evitar problemas de memoria."""
    ext = Path(archivo.name).suffix.lower()
    archivo_path = os.path.join(output_dir, f"uploaded{ext}")
    with open(archivo_path, "wb") as f:
        # Escribir en chunks de 1MB para archivos grandes
        data = archivo.getbuffer()
        f.write(data)
    return archivo_path


def es_archivo_audio(path: str) -> bool:
    """Determina si un archivo es solo audio (sin video)."""
    ext = Path(path).suffix.lower()
    if ext in (".mp3", ".wav", ".m4a", ".ogg", ".flac"):
        return True
    # Para MP4 y otros, verificar si tienen stream de video
    if ext in (".mp4", ".mkv", ".webm", ".mov", ".avi"):
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v",
             "-show_entries", "stream=codec_type", "-of", "csv=p=0", path],
            capture_output=True, text=True,
        )
        return result.stdout.strip() == ""
    return False


def extraer_audio(video_path: str, output_dir: str) -> str:
    """Extrae el audio del video en formato mp3."""
    audio_path = os.path.join(output_dir, "audio.mp3")
    cmd = [
        "ffmpeg", "-i", video_path,
        "-vn", "-ar", "16000", "-ac", "1", "-b:a", "64k",
        audio_path, "-y",
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=180)
    except subprocess.CalledProcessError as e:
        st.error(f"Error al extraer audio:\n```\n{e.stderr}\n```")
        st.stop()
    return audio_path


def dividir_audio(audio_path: str, output_dir: str, max_size_mb: int = 24) -> list[str]:
    """Si el audio supera el limite de Whisper (25MB), lo divide en segmentos."""
    size_mb = os.path.getsize(audio_path) / (1024 * 1024)
    if size_mb <= max_size_mb:
        return [audio_path]

    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", audio_path],
        capture_output=True, text=True,
    )
    duration = float(result.stdout.strip())

    num_segments = int(size_mb / max_size_mb) + 1
    segment_duration = duration / num_segments

    segments = []
    for i in range(num_segments):
        start = i * segment_duration
        seg_path = os.path.join(output_dir, f"audio_seg_{i}.mp3")
        cmd = [
            "ffmpeg", "-i", audio_path,
            "-ss", str(start), "-t", str(segment_duration),
            "-ar", "16000", "-ac", "1", "-b:a", "64k",
            seg_path, "-y",
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        segments.append(seg_path)

    return segments


def transcribir_audio(audio_path: str, output_dir: str) -> str:
    """Transcribe el audio usando OpenAI Whisper API."""
    client = OpenAI()

    segments = dividir_audio(audio_path, output_dir)
    transcripciones = []

    for i, seg_path in enumerate(segments):
        if len(segments) > 1:
            st.text(f"Transcribiendo segmento {i + 1}/{len(segments)}...")
        with open(seg_path, "rb") as audio_file:
            try:
                response = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                )
                transcripciones.append(response.text)
            except Exception as e:
                st.error(f"Error en la transcripcion: {e}")
                st.stop()
        if len(segments) > 1 and i < len(segments) - 1:
            time.sleep(0.5)

    return " ".join(transcripciones)


def obtener_duracion_video(video_path: str) -> float:
    """Obtiene la duracion del video en segundos."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video_path],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def extraer_fotogramas(video_path: str, output_dir: str, num_frames: int = 5) -> list[str]:
    """Extrae fotogramas distribuidos uniformemente a lo largo del video."""
    duration = obtener_duracion_video(video_path)
    if duration <= 0:
        return []
    timestamps = [duration * i / (num_frames + 1) for i in range(1, num_frames + 1)]

    frame_paths = []
    for i, t in enumerate(timestamps):
        frame_path = os.path.join(output_dir, f"frame_{i:03d}.jpg")
        cmd = [
            "ffmpeg", "-ss", str(t), "-i", video_path,
            "-frames:v", "1", "-q:v", "2",
            frame_path, "-y",
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        frame_paths.append(frame_path)

    return frame_paths


def preparar_imagen_para_api(image_path: str, max_size: int = 1568, quality: int = 80) -> str:
    """Redimensiona y comprime una imagen para reducir su tamano antes de enviarla a la API."""
    img = Image.open(image_path)
    if img.mode != "RGB":
        img = img.convert("RGB")

    # Redimensionar si es muy grande (mantiene aspect ratio)
    if max(img.size) > max_size:
        img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

    # Comprimir a JPEG en memoria
    buffer = BytesIO()
    img.save(buffer, format="JPEG", quality=quality, optimize=True)
    buffer.seek(0)
    return base64.standard_b64encode(buffer.read()).decode("utf-8")


def describir_fotograma(client: Anthropic, image_path: str, frame_num: int, total: int, max_retries: int = 3) -> str:
    """Describe un fotograma usando Claude Vision con reintentos automaticos."""
    image_b64 = preparar_imagen_para_api(image_path)

    ultimo_error = None
    for intento in range(max_retries):
        try:
            response = client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=500,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": image_b64,
                                },
                            },
                            {
                                "type": "text",
                                "text": (
                                    f"Este es el fotograma {frame_num} de {total} de un video. "
                                    "Haz dos cosas:\n\n"
                                    "1. **TEXTO EN PANTALLA**: Lee y transcribe TODO el texto visible en la imagen: "
                                    "titulos, subtitulos, text overlays, captions, watermarks, logos con texto, "
                                    "textos animados, hashtags, nombres de usuario, cualquier texto superpuesto. "
                                    "Transcribelo exactamente como aparece.\n\n"
                                    "2. **DESCRIPCION VISUAL**: Describe detalladamente la escena: "
                                    "personas, objetos, colores, ambiente, acciones y composicion.\n\n"
                                    "Responde en espanol."
                                ),
                            },
                        ],
                    }
                ],
            )
            return response.content[0].text
        except Exception as e:
            ultimo_error = e
            if intento < max_retries - 1:
                # Backoff exponencial: 2s, 4s, 8s
                time.sleep(2 ** (intento + 1))

    return f"Error al describir fotograma tras {max_retries} intentos: {ultimo_error}"


def describir_todos_fotogramas(frame_paths: list[str]) -> list[dict]:
    """Describe todos los fotogramas extraidos."""
    # Cliente con timeout mas largo (60s) para evitar connection errors
    client = Anthropic(timeout=60.0, max_retries=2)
    resultados = []
    progress = st.progress(0)
    total = len(frame_paths)

    for i, path in enumerate(frame_paths):
        descripcion = describir_fotograma(client, path, i + 1, total)
        resultados.append({"path": path, "description": descripcion})
        progress.progress((i + 1) / total)
        # Pequena pausa entre llamadas para evitar rate limits
        if i < total - 1:
            time.sleep(0.3)

    progress.empty()
    return resultados


def analizar_contexto(transcripcion: str, descripciones: list[dict] | None = None, max_retries: int = 3) -> str:
    """Usa Claude para analizar el contexto completo del video/audio con reintentos."""
    client = Anthropic(timeout=60.0, max_retries=2)

    contenido = f"## Transcripcion del audio:\n{transcripcion}\n\n"
    if descripciones:
        contenido += "## Descripcion visual de los fotogramas:\n"
        for i, d in enumerate(descripciones):
            contenido += f"\n### Fotograma {i+1}:\n{d['description']}\n"

    ultimo_error = None
    for intento in range(max_retries):
        try:
            response = client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=1500,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "Analiza el siguiente contenido de un video/audio y proporciona un analisis completo.\n\n"
                            f"{contenido}\n\n"
                            "Responde con las siguientes secciones:\n\n"
                            "1. **RESUMEN**: Un resumen conciso de que trata el video/audio (2-3 oraciones).\n\n"
                            "2. **CONTEXTO**: Que tipo de contenido es (anuncio publicitario, tutorial, podcast, "
                            "entrevista, presentacion, contenido educativo, entretenimiento, etc.) y para que audiencia.\n\n"
                            "3. **MENSAJE CLAVE**: Cual es el mensaje principal o proposito del contenido. "
                            "Si es un anuncio, que producto/servicio promueve y que estrategia usa.\n\n"
                            "4. **TONO Y ESTILO**: Describe el tono (formal, casual, emocional, humoristico, urgente, etc.) "
                            "y el estilo de comunicacion.\n\n"
                            "5. **PUNTOS IMPORTANTES**: Lista los puntos mas relevantes mencionados.\n\n"
                            "Responde en espanol."
                        ),
                    }
                ],
            )
            return response.content[0].text
        except Exception as e:
            ultimo_error = e
            if intento < max_retries - 1:
                time.sleep(2 ** (intento + 1))

    return f"Error al analizar contexto tras {max_retries} intentos: {ultimo_error}"


# --- Interfaz principal ---


def mostrar_resultados_previos():
    """Muestra resultados guardados de la sesion anterior."""
    if not any(k in st.session_state for k in ["transcripcion", "descripciones", "contexto"]):
        return

    st.info("Resultados de la ultima sesion:")

    if "contexto" in st.session_state:
        st.subheader("Analisis de Contexto")
        st.markdown(st.session_state["contexto"])
        st.divider()

    col1, col2 = st.columns(2)
    with col1:
        if "transcripcion" in st.session_state:
            st.subheader("Transcripcion")
            st.text_area("Texto transcrito", st.session_state["transcripcion"], height=400)
            st.download_button(
                "Descargar transcripcion",
                st.session_state["transcripcion"],
                file_name="transcripcion.txt",
                mime="text/plain",
            )

    with col2:
        if "descripciones" in st.session_state:
            st.subheader("Descripcion Visual")
            for i, desc in enumerate(st.session_state["descripciones"]):
                st.markdown(f"**Fotograma {i+1}:**")
                st.markdown(desc["description"])
                st.divider()


def procesar_contenido(video_path: str, tmpdir: str, solo_audio: bool, solo_transcripcion: bool, saltar_contexto: bool, num_frames: int):
    """Procesa el video/audio: transcribe, describe fotogramas, y analiza contexto."""
    transcripcion = None
    descripciones = None

    # Siempre transcribir
    st.subheader("Transcripcion")
    with st.spinner("Extrayendo audio..."):
        audio_path = extraer_audio(video_path, tmpdir)
    with st.spinner("Transcribiendo con Whisper..."):
        transcripcion = transcribir_audio(audio_path, tmpdir)

    st.session_state["transcripcion"] = transcripcion
    st.text_area("Texto transcrito", transcripcion, height=300)
    st.download_button(
        "Descargar transcripcion",
        transcripcion,
        file_name="transcripcion.txt",
        mime="text/plain",
    )

    # Describir fotogramas si aplica
    if not solo_audio and not solo_transcripcion:
        st.divider()
        st.subheader("Descripcion Visual")
        with st.spinner("Extrayendo fotogramas..."):
            frames = extraer_fotogramas(video_path, tmpdir, num_frames)
        if frames:
            with st.spinner("Analizando fotogramas con Claude..."):
                descripciones_raw = describir_todos_fotogramas(frames)

            descripciones = [{"description": d["description"]} for d in descripciones_raw]
            st.session_state["descripciones"] = descripciones

            for desc in descripciones_raw:
                st.image(desc["path"], width=350)
                st.markdown(desc["description"])
                st.divider()

            texto_desc = "\n\n---\n\n".join(
                [f"Fotograma {i+1}:\n{d['description']}" for i, d in enumerate(descripciones_raw)]
            )
            st.download_button(
                "Descargar descripciones",
                texto_desc,
                file_name="descripciones.txt",
                mime="text/plain",
            )

    # Analisis de contexto con IA (opcional)
    if not saltar_contexto:
        st.divider()
        st.subheader("Analisis de Contexto")
        with st.spinner("Analizando contexto del contenido con IA..."):
            contexto = analizar_contexto(transcripcion, descripciones)

        st.session_state["contexto"] = contexto
        st.markdown(contexto)
        st.download_button(
            "Descargar analisis",
            contexto,
            file_name="analisis_contexto.txt",
            mime="text/plain",
        )


def procesar_multiples_audios(archivos, solo_transcripcion: bool, saltar_contexto: bool, num_frames: int):
    """Transcribe multiples archivos de audio/video de una sola vez."""
    resultados = []

    st.subheader(f"Procesando {len(archivos)} archivos...")
    progress = st.progress(0)

    for idx, archivo in enumerate(archivos):
        st.markdown(f"### Archivo {idx + 1}: `{archivo.name}`")

        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                with st.spinner(f"Guardando {archivo.name}..."):
                    file_path = guardar_archivo_subido(archivo, tmpdir)
                    solo_audio = es_archivo_audio(file_path)

                with st.spinner(f"Extrayendo audio de {archivo.name}..."):
                    audio_path = extraer_audio(file_path, tmpdir)

                with st.spinner(f"Transcribiendo {archivo.name}..."):
                    client = OpenAI()
                    segments = dividir_audio(audio_path, tmpdir)
                    partes = []
                    for seg_path in segments:
                        with open(seg_path, "rb") as audio_file:
                            response = client.audio.transcriptions.create(
                                model="whisper-1",
                                file=audio_file,
                            )
                            partes.append(response.text)
                    transcripcion = " ".join(partes)

                resultados.append({
                    "archivo": archivo.name,
                    "transcripcion": transcripcion,
                })

                st.text_area(
                    f"Transcripcion de {archivo.name}",
                    transcripcion,
                    height=200,
                    key=f"trans_{idx}",
                )
                st.download_button(
                    f"Descargar transcripcion de {archivo.name}",
                    transcripcion,
                    file_name=f"{Path(archivo.name).stem}_transcripcion.txt",
                    mime="text/plain",
                    key=f"dl_{idx}",
                )
                st.divider()
            except Exception as e:
                st.error(f"Error procesando {archivo.name}: {e}")
                resultados.append({
                    "archivo": archivo.name,
                    "transcripcion": f"ERROR: {e}",
                })

        progress.progress((idx + 1) / len(archivos))

    progress.empty()

    # Descargar todas las transcripciones juntas
    if resultados:
        st.success(f"Completados {len(resultados)} archivos")
        todas = "\n\n" + ("=" * 60) + "\n\n"
        todas = todas.join([
            f"ARCHIVO: {r['archivo']}\n\n{r['transcripcion']}" for r in resultados
        ])
        st.download_button(
            "Descargar TODAS las transcripciones",
            todas,
            file_name="transcripciones_completas.txt",
            mime="text/plain",
            type="primary",
        )

        st.session_state["transcripciones_multiples"] = resultados


def main():
    verificar_dependencias()

    st.title("Transcripcion y Descripcion de Video")
    st.markdown("Ingresa la URL de un video o sube un archivo para obtener su transcripcion, descripcion visual y analisis de contexto.")

    # Sidebar para configuracion
    with st.sidebar:
        st.header("Configuracion")

        openai_key = os.getenv("OPENAI_API_KEY", "") or st.session_state.get("openai_key", "")
        anthropic_key = os.getenv("ANTHROPIC_API_KEY", "") or st.session_state.get("anthropic_key", "")

        if openai_key and anthropic_key:
            st.success("API keys configuradas")
        else:
            st.warning("Ingresa tus API keys para continuar")

        new_openai = st.text_input(
            "OpenAI API Key",
            type="password",
            value=openai_key,
            help="Necesaria para la transcripcion con Whisper",
        )
        new_anthropic = st.text_input(
            "Anthropic API Key",
            type="password",
            value=anthropic_key,
            help="Necesaria para la descripcion visual con Claude",
        )

        if new_openai:
            st.session_state["openai_key"] = new_openai
            os.environ["OPENAI_API_KEY"] = new_openai
        if new_anthropic:
            st.session_state["anthropic_key"] = new_anthropic
            os.environ["ANTHROPIC_API_KEY"] = new_anthropic

        st.divider()
        st.header("Opciones")
        solo_transcripcion = st.checkbox(
            "Saltar analisis visual",
            help="No analizar fotogramas del video (mas rapido y barato)",
        )
        saltar_contexto = st.checkbox(
            "Saltar analisis de contexto",
            help="No generar el analisis de contexto con IA (solo transcribir)",
        )
        num_frames = st.slider("Numero de fotogramas a analizar", 1, 10, 5,
                                disabled=solo_transcripcion)

        st.divider()
        st.markdown(
            "**Powered by:**\n"
            "- OpenAI Whisper (transcripcion)\n"
            "- Claude Sonnet (descripcion visual + contexto)\n"
            "- yt-dlp (descarga)\n"
            "- FFmpeg (procesamiento)"
        )

    # Input principal - Tabs
    tab_url, tab_drive, tab_archivo, tab_multiple = st.tabs([
        "Desde URL",
        "Google Drive",
        "Subir archivo",
        "Multiples audios",
    ])

    with tab_url:
        url = st.text_input("URL del video (YouTube, Vimeo, Twitter, TikTok, etc.)")
        st.caption(
            "Nota: **Facebook, Instagram y LinkedIn** requieren autenticacion. "
            "Para esos, descarga el video y usa las tabs de **Google Drive** o **Subir archivo**."
        )
        procesar_url = st.button("Procesar URL", type="primary", use_container_width=True)

    with tab_drive:
        drive_url = st.text_input(
            "Link de Google Drive",
            placeholder="https://drive.google.com/file/d/.../view",
        )
        st.caption("El archivo debe tener permisos de **'Cualquier persona con el link'**")
        procesar_drive = st.button("Descargar y procesar", type="primary", use_container_width=True)

    with tab_archivo:
        archivo = st.file_uploader(
            "Sube un archivo de video o audio",
            type=["mp4", "mkv", "webm", "mov", "avi", "mp3", "wav", "m4a", "ogg", "flac"],
            help="Formatos soportados: MP4, MKV, WebM, MOV, AVI, MP3, WAV, M4A, OGG, FLAC",
        )
        procesar_archivo = st.button("Procesar archivo", type="primary", use_container_width=True)

    with tab_multiple:
        st.markdown("**Transcribe varios archivos de una sola vez** (ideal para audios de clientes)")
        archivos_multiples = st.file_uploader(
            "Sube multiples archivos de audio o video",
            type=["mp3", "wav", "m4a", "ogg", "flac", "mp4", "mkv", "webm", "mov", "avi"],
            accept_multiple_files=True,
            help="Puedes seleccionar varios archivos a la vez. Solo se transcribira el audio.",
        )
        procesar_multiples = st.button(
            "Transcribir todos", type="primary", use_container_width=True
        )

    # Determinar si hay algo que procesar
    debe_procesar = False
    fuente = None

    if procesar_url and url:
        debe_procesar = True
        fuente = "url"
    elif procesar_url and not url:
        st.warning("Por favor ingresa una URL.")
    elif procesar_drive and drive_url:
        debe_procesar = True
        fuente = "drive"
    elif procesar_drive and not drive_url:
        st.warning("Por favor pega un link de Google Drive.")
    elif procesar_archivo and archivo:
        debe_procesar = True
        fuente = "archivo"
    elif procesar_archivo and not archivo:
        st.warning("Por favor sube un archivo.")
    elif procesar_multiples and archivos_multiples:
        debe_procesar = True
        fuente = "multiples"
    elif procesar_multiples and not archivos_multiples:
        st.warning("Por favor sube al menos un archivo.")

    if debe_procesar:
        if not os.getenv("OPENAI_API_KEY"):
            st.error("Por favor configura tu OpenAI API key en la barra lateral.")
            return
        # Anthropic solo se necesita si NO es modo multiples y no se saltan contexto+visual
        necesita_anthropic = fuente != "multiples" and (not solo_transcripcion or not saltar_contexto)
        if necesita_anthropic and not os.getenv("ANTHROPIC_API_KEY"):
            st.error("Por favor configura tu Anthropic API key en la barra lateral.")
            return

        if fuente == "multiples":
            procesar_multiples_audios(archivos_multiples, solo_transcripcion, saltar_contexto, num_frames)
            return

        with tempfile.TemporaryDirectory() as tmpdir:
            solo_audio = False

            if fuente == "url":
                with st.status("Descargando video...", expanded=True) as status:
                    video_path = descargar_video(url, tmpdir)
                    duracion = obtener_duracion_video(video_path)
                    status.update(
                        label=f"Video descargado ({duracion:.0f} segundos)",
                        state="complete",
                    )
            elif fuente == "drive":
                with st.status("Descargando desde Google Drive...", expanded=True) as status:
                    video_path = descargar_google_drive(drive_url, tmpdir)
                    solo_audio = es_archivo_audio(video_path)
                    duracion = obtener_duracion_video(video_path)
                    tipo = "Audio" if solo_audio else "Video"
                    status.update(
                        label=f"{tipo} descargado desde Drive ({duracion:.0f} segundos)",
                        state="complete",
                    )
            else:
                with st.spinner("Guardando archivo..."):
                    video_path = guardar_archivo_subido(archivo, tmpdir)
                    solo_audio = es_archivo_audio(video_path)
                    duracion = obtener_duracion_video(video_path)
                    tipo = "Audio" if solo_audio else "Video"
                    st.success(f"{tipo} cargado ({duracion:.0f} segundos)")

            procesar_contenido(video_path, tmpdir, solo_audio, solo_transcripcion, saltar_contexto, num_frames)

    else:
        mostrar_resultados_previos()


if __name__ == "__main__":
    main()

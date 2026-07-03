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
        result = gdown.download(download_url, output_path, quiet=False, fuzzy=True)
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


def normalizar_url_wistia(url: str) -> str:
    """Detecta media_ids o embeds de Wistia y los convierte a URL de iframe."""
    url = url.strip()
    if re.fullmatch(r'[a-zA-Z0-9]{10}', url):
        return f"https://fast.wistia.net/embed/iframe/{url}"
    m = re.search(r'wistia_async_([a-zA-Z0-9]{10})', url)
    if m:
        return f"https://fast.wistia.net/embed/iframe/{m.group(1)}"
    if re.search(r'wistia\.(?:net|com)/embed/iframe/', url):
        return url
    m = re.search(r'wistia\.(?:net|com)/embed/medias/([a-zA-Z0-9]{10})', url)
    if m:
        return f"https://fast.wistia.net/embed/iframe/{m.group(1)}"
    return url


def es_url_youtube(url: str) -> bool:
    return bool(re.search(r'(?:youtube\.com|youtu\.be)', url))


def extraer_youtube_id(url: str) -> str | None:
    """Extrae el video ID de una URL de YouTube."""
    patterns = [
        r'(?:v=)([a-zA-Z0-9_-]{11})',
        r'(?:youtu\.be/)([a-zA-Z0-9_-]{11})',
        r'(?:embed/)([a-zA-Z0-9_-]{11})',
        r'(?:shorts/)([a-zA-Z0-9_-]{11})',
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def obtener_transcripcion_youtube(video_id: str) -> str | None:
    """Obtiene subtitulos directamente de YouTube sin descargar el video."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return None

    ytt = YouTubeTranscriptApi()
    for langs in [['es', 'es-419', 'es-ES'], ['en', 'en-US', 'en-GB'], None]:
        try:
            if langs:
                transcript = ytt.fetch(video_id, languages=langs)
            else:
                transcript = ytt.fetch(video_id)
            return ' '.join([entry.text for entry in transcript])
        except Exception:
            continue
    return None


def descargar_video(
    url: str,
    output_dir: str,
    cookies_file: str | None = None,
    referer: str | None = None,
    video_password: str | None = None,
) -> str:
    """Descarga un video usando yt-dlp."""
    output_template = os.path.join(output_dir, "video.%(ext)s")
    cmd = [
        "yt-dlp",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", output_template,
    ]
    if cookies_file:
        cmd += ["--cookies", cookies_file]
    if referer:
        cmd += ["--referer", referer]
    if video_password:
        cmd += ["--video-password", video_password]
    cmd.append(url)
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)
    except subprocess.CalledProcessError as e:
        stderr = e.stderr or ""
        if "Sign in to confirm" in stderr or "HTTP Error 429" in stderr:
            st.error(
                "YouTube bloqueo la descarga desde este servidor.\n\n"
                "**Opciones:**\n"
                "1. Activa **'Solo transcripcion'** en la barra lateral para obtener "
                "subtitulos directamente de YouTube (sin descargar el video)\n"
                "2. Sube tus **cookies de YouTube** en 'Opciones avanzadas'\n"
                "3. Descarga el video en tu PC con `yt-dlp` y subelo en 'Subir archivo'"
            )
        else:
            st.error(f"Error al descargar el video:\n```\n{stderr}\n```")
        return None
    except subprocess.TimeoutExpired:
        st.error("La descarga tardo demasiado (>10 min). Intenta con un video mas corto.")
        return None

    for f in Path(output_dir).iterdir():
        if f.name.startswith("video") and f.suffix in (".mp4", ".mkv", ".webm"):
            return str(f)

    st.error("No se encontro el archivo de video descargado.")
    return None


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


def describir_fotograma(client: Anthropic, image_path: str, frame_num: int, total: int) -> str:
    """Describe un fotograma usando Claude Vision."""
    with open(image_path, "rb") as f:
        image_b64 = base64.standard_b64encode(f.read()).decode("utf-8")

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
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
        return f"Error al describir fotograma: {e}"


def describir_todos_fotogramas(frame_paths: list[str]) -> list[dict]:
    """Describe todos los fotogramas extraidos."""
    client = Anthropic()
    resultados = []
    progress = st.progress(0)
    total = len(frame_paths)

    for i, path in enumerate(frame_paths):
        descripcion = describir_fotograma(client, path, i + 1, total)
        resultados.append({"path": path, "description": descripcion})
        progress.progress((i + 1) / total)

    progress.empty()
    return resultados


def analizar_contexto(transcripcion: str, descripciones: list[dict] | None = None) -> str:
    """Usa Claude para analizar el contexto completo del video/audio."""
    client = Anthropic()

    contenido = f"## Transcripcion del audio:\n{transcripcion}\n\n"
    if descripciones:
        contenido += "## Descripcion visual de los fotogramas:\n"
        for i, d in enumerate(descripciones):
            contenido += f"\n### Fotograma {i+1}:\n{d['description']}\n"

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
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
        return f"Error al analizar contexto: {e}"


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


def procesar_contenido(
    video_path: str | None,
    tmpdir: str,
    solo_audio: bool,
    solo_transcripcion: bool,
    num_frames: int,
    transcripcion_previa: str | None = None,
):
    """Procesa el video/audio: transcribe, describe fotogramas, y analiza contexto."""
    transcripcion = transcripcion_previa
    descripciones = None

    st.subheader("Transcripcion")
    if transcripcion is None:
        with st.spinner("Extrayendo audio..."):
            audio_path = extraer_audio(video_path, tmpdir)
        with st.spinner("Transcribiendo con Whisper..."):
            transcripcion = transcribir_audio(audio_path, tmpdir)
    else:
        st.info("Transcripcion obtenida directamente de YouTube")

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

    # Analisis de contexto con IA
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
            "Solo transcripcion",
            help="Solo transcribir el audio, sin analizar fotogramas (mas rapido y barato)",
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

    # Input principal - Tabs para URL, Google Drive, o archivo local
    tab_url, tab_drive, tab_archivo = st.tabs(["Desde URL", "Google Drive", "Subir archivo"])

    with tab_url:
        url = st.text_input(
            "URL del video (YouTube, Vimeo, Twitter, TikTok, Wistia, etc.)",
            help="Tambien acepta el media_id de Wistia (10 caracteres alfanumericos).",
        )
        with st.expander("Opciones avanzadas (sitios con login, Wistia protegido, etc.)"):
            cookies_upload = st.file_uploader(
                "Cookies (archivo cookies.txt formato Netscape)",
                type=["txt"],
                help=(
                    "Para descargar videos detras de login (Kajabi, Teachable, Thinkific, "
                    "Hotmart, etc.) exporta tus cookies desde el navegador con la extension "
                    "'Get cookies.txt LOCALLY' (Chrome/Firefox) y subelas aqui."
                ),
                key="cookies_url",
            )
            referer_url = st.text_input(
                "Referer URL",
                placeholder="https://www.tucurso.com/clases/leccion-1",
                help=(
                    "URL de la pagina donde esta embebido el video. Necesario para Wistia "
                    "con restriccion de dominio."
                ),
                key="referer_url_input",
            )
            video_password = st.text_input(
                "Password del video",
                type="password",
                help=(
                    "Contrasena del video (no del sitio). Solo si Wistia/Vimeo le pone "
                    "password al video especifico."
                ),
                key="vpass_url",
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

    if debe_procesar:
        if not os.getenv("OPENAI_API_KEY") or not os.getenv("ANTHROPIC_API_KEY"):
            st.error("Por favor configura ambas API keys en la barra lateral.")
            return

        with tempfile.TemporaryDirectory() as tmpdir:
            solo_audio = False

            if fuente == "url":
                cookies_path = None
                if cookies_upload is not None:
                    cookies_path = os.path.join(tmpdir, "cookies.txt")
                    with open(cookies_path, "wb") as f:
                        f.write(cookies_upload.getbuffer())

                url_normalizada = normalizar_url_wistia(url)
                if url_normalizada != url:
                    st.info(f"URL de Wistia detectada, usando: `{url_normalizada}`")

                # YouTube: intentar obtener subtitulos directamente
                yt_id = extraer_youtube_id(url)
                yt_transcript = None
                if yt_id:
                    with st.spinner("Buscando subtitulos en YouTube..."):
                        yt_transcript = obtener_transcripcion_youtube(yt_id)

                if yt_id and yt_transcript and solo_transcripcion:
                    st.success("Subtitulos obtenidos directamente de YouTube")
                    procesar_contenido(
                        None, tmpdir, False, True, num_frames,
                        transcripcion_previa=yt_transcript,
                    )
                    return
                else:
                    with st.status("Descargando video...", expanded=True) as status:
                        video_path = descargar_video(
                            url_normalizada,
                            tmpdir,
                            cookies_file=cookies_path,
                            referer=referer_url or None,
                            video_password=video_password or None,
                        )
                    if video_path is None:
                        if yt_transcript:
                            st.warning(
                                "No se pudo descargar el video de YouTube, "
                                "pero se obtuvieron los subtitulos."
                            )
                            procesar_contenido(
                                None, tmpdir, False, True, num_frames,
                                transcripcion_previa=yt_transcript,
                            )
                            return
                        else:
                            st.stop()
                    else:
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

            procesar_contenido(video_path, tmpdir, solo_audio, solo_transcripcion, num_frames)

    else:
        mostrar_resultados_previos()


if __name__ == "__main__":
    main()

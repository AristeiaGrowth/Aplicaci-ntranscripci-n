import streamlit as st
import subprocess
import tempfile
import os
import base64
import shutil
import time
from pathlib import Path

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
        st.error(f"Error al descargar el video:\n```\n{e.stderr}\n```")
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


def extraer_audio(video_path: str, output_dir: str) -> str:
    """Extrae el audio del video en formato mp3 (para respetar el limite de 25MB de Whisper)."""
    audio_path = os.path.join(output_dir, "audio.mp3")
    cmd = [
        "ffmpeg", "-i", video_path,
        "-vn", "-ar", "16000", "-ac", "1", "-b:a", "64k",
        audio_path, "-y",
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)
    except subprocess.CalledProcessError as e:
        st.error(f"Error al extraer audio:\n```\n{e.stderr}\n```")
        st.stop()
    return audio_path


def dividir_audio(audio_path: str, output_dir: str, max_size_mb: int = 24) -> list[str]:
    """Si el audio supera el limite de Whisper (25MB), lo divide en segmentos."""
    size_mb = os.path.getsize(audio_path) / (1024 * 1024)
    if size_mb <= max_size_mb:
        return [audio_path]

    # Obtener duracion
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", audio_path],
        capture_output=True, text=True,
    )
    duration = float(result.stdout.strip())

    # Calcular cuantos segmentos necesitamos
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
    return float(result.stdout.strip())


def extraer_fotogramas(video_path: str, output_dir: str, num_frames: int = 5) -> list[str]:
    """Extrae fotogramas distribuidos uniformemente a lo largo del video."""
    duration = obtener_duracion_video(video_path)
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


# --- Interfaz principal ---


def main():
    verificar_dependencias()

    st.title("Transcripcion y Descripcion de Video")
    st.markdown("Ingresa la URL de un video para obtener su transcripcion y una descripcion visual basada en sus fotogramas.")

    # Sidebar para configuracion
    with st.sidebar:
        st.header("Configuracion")

        # API keys: primero revisar env vars, luego session state, luego pedir
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

        # Guardar en session state y env
        if new_openai:
            st.session_state["openai_key"] = new_openai
            os.environ["OPENAI_API_KEY"] = new_openai
        if new_anthropic:
            st.session_state["anthropic_key"] = new_anthropic
            os.environ["ANTHROPIC_API_KEY"] = new_anthropic

        num_frames = st.slider("Numero de fotogramas a analizar", 1, 10, 5)

        st.divider()
        st.markdown(
            "**Powered by:**\n"
            "- OpenAI Whisper (transcripcion)\n"
            "- Claude Sonnet (descripcion visual)\n"
            "- yt-dlp (descarga)\n"
            "- FFmpeg (procesamiento)"
        )

    # Input principal - Tabs para URL o archivo local
    tab_url, tab_archivo = st.tabs(["Desde URL", "Subir archivo"])

    with tab_url:
        url = st.text_input("URL del video (YouTube, Vimeo, Twitter, TikTok, etc.)")
        procesar_url = st.button("Procesar URL", type="primary", use_container_width=True)

    with tab_archivo:
        archivo = st.file_uploader(
            "Sube un archivo de video o audio",
            type=["mp4", "mkv", "webm", "mov", "avi", "mp3", "wav", "m4a", "ogg", "flac"],
            help="Formatos soportados: MP4, MKV, WebM, MOV, AVI, MP3, WAV, M4A, OGG, FLAC",
        )
        procesar_archivo = st.button("Procesar archivo", type="primary", use_container_width=True)

    # Determinar si hay algo que procesar
    debe_procesar = False
    fuente = None  # "url" o "archivo"

    if procesar_url and url:
        debe_procesar = True
        fuente = "url"
    elif procesar_url and not url:
        st.warning("Por favor ingresa una URL.")
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
            es_solo_audio = False

            if fuente == "url":
                # Descargar video desde URL
                with st.status("Descargando video...", expanded=True) as status:
                    video_path = descargar_video(url, tmpdir)
                    duracion = obtener_duracion_video(video_path)
                    status.update(
                        label=f"Video descargado ({duracion:.0f} segundos)",
                        state="complete",
                    )
            else:
                # Guardar archivo subido a disco
                ext = Path(archivo.name).suffix.lower()
                archivo_path = os.path.join(tmpdir, f"uploaded{ext}")
                with open(archivo_path, "wb") as f:
                    f.write(archivo.getbuffer())

                es_solo_audio = ext in (".mp3", ".wav", ".m4a", ".ogg", ".flac")
                video_path = archivo_path

                duracion = obtener_duracion_video(archivo_path)
                tipo = "Audio" if es_solo_audio else "Video"
                st.success(f"{tipo} cargado ({duracion:.0f} segundos)")

            # Procesar
            if es_solo_audio:
                # Solo transcribir, no hay fotogramas
                st.subheader("Transcripcion")
                with st.spinner("Preparando audio..."):
                    audio_path = extraer_audio(video_path, tmpdir)
                with st.spinner("Transcribiendo con Whisper..."):
                    transcripcion = transcribir_audio(audio_path, tmpdir)

                st.session_state["transcripcion"] = transcripcion
                st.text_area("Texto transcrito", transcripcion, height=400)
                st.download_button(
                    "Descargar transcripcion",
                    transcripcion,
                    file_name="transcripcion.txt",
                    mime="text/plain",
                )
            else:
                # Video: transcribir + describir fotogramas
                col1, col2 = st.columns(2)

                with col1:
                    st.subheader("Transcripcion")
                    with st.spinner("Extrayendo audio..."):
                        audio_path = extraer_audio(video_path, tmpdir)
                    with st.spinner("Transcribiendo con Whisper..."):
                        transcripcion = transcribir_audio(audio_path, tmpdir)

                    st.session_state["transcripcion"] = transcripcion
                    st.text_area("Texto transcrito", transcripcion, height=400)
                    st.download_button(
                        "Descargar transcripcion",
                        transcripcion,
                        file_name="transcripcion.txt",
                        mime="text/plain",
                    )

                with col2:
                    st.subheader("Descripcion Visual")
                    with st.spinner("Extrayendo fotogramas..."):
                        frames = extraer_fotogramas(video_path, tmpdir, num_frames)
                    with st.spinner("Analizando fotogramas con Claude..."):
                        descripciones = describir_todos_fotogramas(frames)

                    descripciones_texto = [
                        {"description": d["description"]} for d in descripciones
                    ]
                    st.session_state["descripciones"] = descripciones_texto

                    for desc in descripciones:
                        st.image(desc["path"], width=350)
                        st.markdown(desc["description"])
                        st.divider()

                    texto_desc = "\n\n---\n\n".join(
                        [f"Fotograma {i+1}:\n{d['description']}" for i, d in enumerate(descripciones)]
                    )
                    st.download_button(
                        "Descargar descripciones",
                        texto_desc,
                        file_name="descripciones.txt",
                        mime="text/plain",
                    )

    # Mostrar resultados previos si existen (al recargar la pagina)
    elif "transcripcion" in st.session_state or "descripciones" in st.session_state:
        st.info("Resultados de la ultima sesion:")
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

                texto_desc = "\n\n---\n\n".join(
                    [f"Fotograma {i+1}:\n{d['description']}" for i, d in enumerate(st.session_state["descripciones"])]
                )
                st.download_button(
                    "Descargar descripciones",
                    texto_desc,
                    file_name="descripciones.txt",
                    mime="text/plain",
                )


if __name__ == "__main__":
    main()

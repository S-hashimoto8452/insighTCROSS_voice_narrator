import asyncio
import datetime as dt
from pathlib import Path

import streamlit as st
from gtts import gTTS
import edge_tts

# gTTSの速度近似用（ffmpegがない環境では失敗する場合あり）
from pydub import AudioSegment
from pydub.effects import speedup

st.set_page_config(page_title="TCROSS Data Science Unit (EN/JA)", page_icon="🗣️")

# --- 設定 ---
VOICES = {
    ("en", "Female"): "en-US-JennyNeural",
    ("en", "Male"): "en-US-GuyNeural",
    ("ja", "Female"): "ja-JP-NanamiNeural",
    ("ja", "Male"): "ja-JP-KeitaNeural",
}

DEFAULT_TEXT = {
    "en": "The development of a new drug takes immense time and substantial financial investment.",
    "ja": "新薬の開発には多大な時間と大きな投資が必要です。"
}

SPEED_OPTIONS = [0.5, 0.75, 1.0, 1.25, 1.5]  # 表示順

# Edge-TTS の rate 文字列に変換
def speed_to_edge_rate(x: float) -> str:
    # 1.0→+0%, 1.25→+25%, 0.75→-25%, 0.5→-50%, 1.5→+50%
    pct = int(round((x - 1.0) * 100))
    if pct > 0:
        return f"+{pct}%"
    elif pct < 0:
        return f"{pct}%"
    else:
        return "+0%"   # 0は "+0%" に固定（"0%" はNG）

OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# --- 合成関数 ---
async def synthesize_edge_tts(text: str, lang: str, gender: str, speed: float, out_path: Path) -> Path:
    voice = VOICES.get((lang, gender), VOICES[("en", "Female")])
    rate_str = speed_to_edge_rate(speed)      # ← 文字列に変換
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate_str)
    with open(out_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
    return out_path

def synthesize_gtts(text: str, lang: str, speed: float, out_path: Path) -> Path:
    # まず通常速度で生成
    tmp_path = out_path.with_suffix(".tmp.mp3")
    gTTS(text=text, lang=lang).save(str(tmp_path))

    # 速度が1.0ならそのまま
    if abs(speed - 1.0) < 1e-6:
        Path(tmp_path).rename(out_path)
        return out_path

    # pydub で速度近似（ffmpeg 必須）
    try:
        seg = AudioSegment.from_file(tmp_path)
        # pydub.effects.speedup はピッチをできるだけ維持したままテンポ変更（近似）
        adjusted = speedup(seg, playback_speed=speed)
        adjusted.export(out_path, format="mp3")
        Path(tmp_path).unlink(missing_ok=True)
        return out_path
    except Exception as e:
        # 失敗したら元の速度で出す
        Path(tmp_path).rename(out_path)
        raise RuntimeError(
            f"gTTSの速度変更に失敗しました（ffmpeg未導入の可能性）。通常速度の音声を出力しました。詳細: {e}"
        )

# --- UI ---
st.title("🗣️ InsighTCROSS® Digital Narrator(Eng / JPN)")

with st.sidebar:
    st.header("Settings")

    lang_label = st.radio("Narration Language / ナレーション言語", ["English", "日本語"], index=0)
    lang = "en" if lang_label == "English" else "ja"

    gender = st.radio("Voice Gender / 話者の性別", ["Female", "Male"], index=0)

    engine = st.radio(
        "Engine",
        ["Edge-TTS (recommended)", "gTTS (fallback)"],
        index=0,
        help="Edge-TTS: 高品質・男女/速度切替可 / gTTS: 速度は近似（ffmpeg必要）",
    )

    speed = st.radio("Speech speed / 読み上げ速度", SPEED_OPTIONS, index=2, format_func=lambda x: f"{x}×")

text = st.text_area(
    "Input text / 入力テキスト",
    value=DEFAULT_TEXT["en" if "English" in lang_label else "ja"],
    height=150,
)

col1, col2 = st.columns([1, 3])
with col1:
    generate = st.button("Generate / 生成")
with col2:
    st.caption("*生成した音声はこの下に表示・ダウンロードできます。*")

if generate:
    if not text.strip():
        st.warning("Please enter some text. / テキストを入力してください。")
        st.stop()

    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"tekross_voice_{lang}_{gender.lower()}_{str(speed).replace('.', '_')}x_{timestamp}.mp3"
    out_path = OUTPUT_DIR / filename

    try:
        if engine.startswith("Edge-TTS"):
            try:
                asyncio.run(synthesize_edge_tts(text, lang, gender, speed, out_path))
            except RuntimeError:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(synthesize_edge_tts(text, lang, gender, speed, out_path))
                loop.close()
        else:
            synthesize_gtts(text, lang, speed, out_path)

        st.success("Done! / 生成しました。")
        audio_bytes = out_path.read_bytes()
        st.audio(audio_bytes, format="audio/mp3")
        st.download_button(
            label="Download MP3 / MP3をダウンロード",
            data=audio_bytes,
            file_name=filename,
            mime="audio/mpeg",
        )
        st.info(f"Saved to: {out_path}")

    except Exception as e:
        st.error(f"Error: {e}")
        # 失敗しても一応ファイルができていれば再生・DLを出す
        if out_path.exists():
            audio_bytes = out_path.read_bytes()
            st.audio(audio_bytes, format="audio/mp3")
            st.download_button("Download MP3 / MP3をダウンロード", audio_bytes, file_name=filename, mime="audio/mpeg")

"""文字转语音模块 —— 含语速调节 + 预合成"""
import os
from core.config import AUDIO_DIR, PRESSURE_TTS_SPEED


class TTSHandler:
    """文字转语音处理器。
    MVP阶段返回文本由前端TTS播放，预留真实TTS接口。
    """

    def __init__(self):
        os.makedirs(AUDIO_DIR, exist_ok=True)

    def synthesize(self, text: str, speed: float = 1.0,
                   session_id: str = "", label: str = "") -> dict:
        """
        文字转语音。
        返回 {"success": bool, "audio_path": str, "text": str, "error": str}
        """
        if not text:
            return {"success": False, "audio_path": "", "text": "", "error": "文本为空"}

        # TODO: 接入真实TTS API
        # 调用 TaoToken TTS 或 阿里云 TTS
        # response = requests.post(tts_api_url, json={"text": text, "speed": speed})
        # audio_data = response.content
        # filepath = save_audio(audio_data, session_id, label)

        # MVP 阶段：返回文本让前端用浏览器 Web Speech API 播放
        # 标记 speed 信息供前端使用
        return {
            "success": True,
            "audio_path": "",  # MVP阶段无真实音频文件
            "text": text,
            "speed": speed,
            "error": ""
        }

    def get_speed(self, pressure: bool = False) -> float:
        """获取当前TTS语速"""
        return PRESSURE_TTS_SPEED if pressure else 1.0


tts_handler = TTSHandler()

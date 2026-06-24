"""语音转文字模块 —— 含边缘情况处理"""
import os
from core.config import AUDIO_DIR


class STTHandler:
    """语音转文字处理器。
    MVP阶段使用文本输入模拟，预留真实STT接口。
    """

    def __init__(self):
        os.makedirs(AUDIO_DIR, exist_ok=True)

    def transcribe(self, audio_file_path: str) -> dict:
        """
        语音文件转文字。
        返回 {"success": bool, "text": str, "error": str}
        """
        # MVP: 检查文件是否存在
        if not audio_file_path or not os.path.exists(audio_file_path):
            return {"success": False, "text": "", "error": "音频文件不存在"}

        # 检查文件大小（小于100字节视为空音频）
        file_size = os.path.getsize(audio_file_path)
        if file_size < 100:
            return {"success": False, "text": "", "error": "音频文件为空或过短"}

        # TODO: 接入真实STT API
        # 调用 TaoToken 语音API 或 讯飞语音
        # import requests
        # response = requests.post(stt_api_url, files={"audio": open(audio_file_path, "rb")})
        # return {"success": True, "text": response.json()["text"], "error": ""}

        # MVP 阶段返回占位
        return {"success": False, "text": "", "error": "STT服务未接入，请使用文字输入模式"}

    def is_noise(self, text: str) -> bool:
        """判断转录结果是否为噪音（全是无意义字符）"""
        if not text or not text.strip():
            return True
        # 去除标点后字数不足2个
        import re
        chars = re.sub(r'[^\w\u4e00-\u9fff]', '', text)
        return len(chars) < 2

    def save_audio(self, audio_data: bytes, session_id: str, question_index: int) -> str:
        """保存原始音频文件"""
        filename = f"{session_id}_q{question_index}.wav"
        filepath = os.path.join(AUDIO_DIR, filename)
        with open(filepath, "wb") as f:
            f.write(audio_data)
        return filepath


stt_handler = STTHandler()
